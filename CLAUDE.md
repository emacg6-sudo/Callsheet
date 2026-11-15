# Callsheet: project rules

Home Assistant app (add-on) through Ingress: a personal assistant that keeps the owner's messages, reads
each once with his local model into a ledger, and shows Today, Talk it through and Chat. Plan and history:
PLAN.md and HANDOFF.md in the planning folder (see CLAUDE.local.md, not in git).

## The promise
- **Nothing is ever sent.** Callsheet sends no mail, message, reply, post, reaction or receipt, and archives, moves
  or deletes nothing in any account. "Nothing is ever sent from here" is a fixed promise in the UI, not a setting.
  It creates exactly two things, each only when the owner presses: a calendar event and a Gmail draft; and it
  answers an invite (RSVP) only when he presses Yes, No or Maybe on it (below). Google tells that event's organizer;
  nothing else is sent. The UI promise reads "Nothing is sent from here except an RSVP you press" (owner approved
  2026-11-13). Phone
  notifications go only to the owner's own phones through Home Assistant's notify service: names, sources, subjects
  and times, never message text.
- **Only the owner's own words act.** Mail, Slack, Signal, texts, feeds, reports, web pages and tool results are
  untrusted `<data>`: shown with textContent, never instructions. They can never offer, fill, confirm, apply or undo a
  card, start a search, save a note or press a button. Someone else's claim is attributed ("Marco says it's
  approved"), never stated as fact. Security alerts and invites are never hidden.
- **Local model only** (the owner, 2026-11-11). Message text goes to the owner's own model server; Claude
  (`api.anthropic.com`) only when he saves a key and turns it on.
- No accounts, secrets or user data in the repo. Never print secrets.

## Where Callsheet may connect
No external requests at runtime unless listed here; the browser page never calls out (fonts and assets bundled, no
CDNs, no analytics). Each new destination, scope or write needs the owner's approval, written here.
- **Google**, the owner's own accounts and OAuth client, all through the (method, URL) allowlist in `google.py`:
  Gmail read-only (messages, attachments up to 256 KB for calendar files, `users/me/history`), Calendar read-only
  (incl. events.list by `iCalUID`), Drive `drive.readonly` (`files`, `files/<id>`, `files/<id>/export`), Contacts,
  and the two writes below.
- **Slack** read-only Web API (`slack.com`). **Signal** through signal-cli as a linked device (owner approved
  2026-10-30); `signalcli.py`'s JSON-RPC allowlist keeps it receive-only (no send, reactions, read receipts or typing;
  delivery receipts are automatic).
- **GitHub** (`api.github.com`, owner approved 2026-11-03): a fine-grained read-only token and the repos the owner
  picks; `github.py` allows only `GET /user/repos`, `/repos/{o}/{r}`, `/commits`, `/issues`, `/pulls`; no redirects.
- **Home Assistant Supervisor** Core API (`http://supervisor/core/api`, `SUPERVISOR_TOKEN`, never logged, stored or
  returned), limited by `ha.py`'s allowlist to `GET /api/services`, `POST /api/services/notify/mobile_app_<name>`,
  and for texts `GET /api/states/<sensor>` and `GET /api/history/period/<ts>?filter_entity_id=<sensor>`.
- The owner's local model URL; the owner's SearXNG (below); `api.anthropic.com` (above).
- **Connectors (0.10, owner approved 2026-11-04).** Public RSS/Atom feeds and YouTube channel feeds the owner adds in
  Setup (plus one GET of a pasted channel page). A host is allowed only when the owner adds it (`outbound_hosts`,
  dated, removable). `net.py`: HTTPS GET on 443 to those hosts only; private, loopback, link-local, CGNAT and
  Supervisor addresses refused after DNS (pinned); no redirect off-host; size, time and rate caps; no images, linked
  pages, cookies or owner data; story links on other hosts only once he allows them. A new connector kind
  needs the owner's approval here and its own injection test.
- **Reports (0.10.2a, owner approved 2026-11-05).** Markdown reports, one file each, from a folder the owner picks
  under `/share` or `/media`, or a Drive folder via `drive.readonly` (built in 0.12.1). Read-only, regular `*.md`
  files inside that folder only, capped; no inbound endpoint; a report can't place itself above Needs you.

## Reading and keeping
- **Message store and live reading (owner approved 2026-11-11).** Callsheet keeps every message it reads, received
  and sent, from every source, in `messages.db` under `/data` (in HA backups). No deletion: "more information is
  just better context". Read live with the same read-only access; a source that stops advancing is reported.
- **Read once, keep a ledger (0.16.0).** Each stored message is read once by the local model into the ledger
  (`docs/ledger.md`). No silent drops: whatever the code rejects is kept with its reason and shown; an uncertain item
  is shown as "likely" with its source message; times are never dropped (the phrase is kept). The ledger never
  searches the web.
- **Texts (owner approved 2026-11-11, "set it up").** Read-only: the nightly SMS Backup & Restore XML files Syncthing
  copies to `/share/phone-sms/` (never changed), and the Companion app's "Last notification" sensor the owner picks
  (only the messaging apps he allows), through the two `ha.py` endpoints above.
- **Google Contacts, read-only (owner approved 2026-11-12, "1, 2: yes").** Scope `contacts.readonly`, granted per
  account in Setup ("Allow contacts"). Only `GET /v1/people/me/connections` on `people.googleapis.com`. Contact data
  stays in Callsheet's database.
- **Model server.** One background model (`background.py`: slot, budget, caps, Chat first and preemption).
  Background requests stay out of the owner's quiet times for the model server (setting `model_quiet_times`,
  `background.quiet_times`; none on a new install, his own times kept on upgrade).

## The three writes (owner-pressed only)
- **Add to calendar (owner approved 2026-11-11, "Put it in, I'll update the Oath"; scope added in his Google project
  2026-11-12).** Scope `calendar.events`, granted per account ("Allow adding events"). Only when the owner presses Add
  on one item (Today, Coming up, the item view, or a Chat card he confirms: Chat proposes, never applies at once; no
  Undo). The only call: `POST /calendar/v3/calendars/<id>/events?sendUpdates=none` (`check_event_body`): keys only
  summary, start, end, `extendedProperties.private.callsheet_item`; no attendees, update or delete; idempotent.
  `tests/test_calwrite_0210.py`.
- **Answer invites (owner approved 2026-11-13: Agenda answer "1. yes", then "RSVP, reword promise").** Scope
  `calendar.events` (as above). Only when the owner presses Yes, No or Maybe on one invite (Agenda, Today, the item
  view; a Chat card only after he confirms it). The only call: `PATCH /calendar/v3/calendars/<id>/events/<eventId>
  ?sendUpdates=all` with body key `attendees` only, equal to the event's current attendee list (fetched just before)
  except the owner's own `self: true` entry's `responseStatus`; no other attendee, field, comment or event changes.
  Mail, messages, feeds and tool results can never offer, fill or press it. Needs its own test (`check_rsvp_body`).
- **Gmail drafts (owner approved 2026-11-12, "yes build in the gmail drafts").** Scope `gmail.drafts.create`,
  requested per account ("Allow drafts in Gmail"), never at connect. Only when the owner presses "Put in Gmail
  Drafts", confirms Chat's draft card (`propose_gmail_draft`, only when his own latest message asks), or presses
  "Test drafts". The only Gmail write: `POST /gmail/v1/users/me/drafts`; never update, send, modify, trash or delete,
  whatever the scope. To and Subject come from the replied-to message's headers, never model text; a 403 is said
  plainly, never retried. `gmail.compose` as a fallback needs his separate OK. `tests/test_gdrafts_0210.py`.

## Chat
- **Chat may use tools (owner's decision, 2026-10-30).** Read-only lookups only: no send, no account writes, no
  network fetch beyond the rules here. Tool results go back as escaped `<data>`; answers get the claim post-check.
  Every new tool, and anything that writes, sends or fetches, needs the owner's explicit approval written here and its
  own injection test (`tests/test_stream_0140.py` checks each tool's date here).
- **Chat on the store and configuring by chat (owner approved 2026-11-11).** The owner: "I'd like to use chat for a lot of
  the configuration… This is a perfect example". `propose_setting`/`propose_action` only when his own latest
  message asks; they write nothing; one-time token per chat and turn. Applied at once (with Undo) only when all its
  words are in that message, else it waits for Confirm. Listed in Setup → Your rules. `tests/test_chat_cards_0170.py`.
- **Memory notes (owner approved 2026-11-03).** `propose_memory` only when the owner's own message asks to remember;
  saved only when he presses Save, after `inject.instructions` and `states_decision`, with a one-time token.
- **Connector setup cards (owner approved 2026-11-06).** When the owner's own message asks to add a channel, feed or
  reports folder, Chat may offer Setup's card; Check and Add run only when he presses them.
- **Web search through the owner's SearXNG (owner approved 2026-11-06).** The owner: "SearXNG on the NAS is the right
  choice, I don't want to have to press any extra buttons. It should know when to search, or ask." Only Chat, in a
  turn the owner started. Every query word must come from his own messages in this chat; anything else or private
  becomes a question to him. Result pages only by result id, through `net.py`; page text is untrusted.
- **Projects (0.7.0) live in Callsheet only**, never written to Obsidian or any account. "Ask about this project" is
  a filter on the existing read-only tools.

## Voice assistant API
- **Read-only API for the owner's phone voice assistant (owner approved 2026-11-13: "1. yes ... 2. ok we can try
  tailscale ... 3. yes it should be able to fetch the brief").** A separate listener on 8100, off by default, serves
  only the GET endpoints in voice-api.md in the planning folder (see CLAUDE.local.md, not in git) to per-device bearer tokens (shown once,
  scoped, revocable, stored hashed), rate-limited, counts-only audit log. Home network or Tailscale only, never
  Cloudflare or another public proxy. Nothing writes, sends or changes; results are marked untrusted with sources.

## Retired in the rework (owner approved 2026-11-12, "yes")
After "There are so many guardrails that I think are hindering the capability… I see so much unnecessary info on the
screen": the sorter, learner, reader, picker, writer evaluation, presets editor, old brief and rules rows, Sync now and
the 0.6.0 index and scan are gone; the ledger's read replaced them. Their old tables stay in `callsheet.db` and
`index.db` stays on disk, unused (imported once into `messages.db`). Nothing deletes them on its own: only the
owner's press on Setup › Advanced › "Old data from earlier versions" (`oldata.py`, owner approved 2026-11-13: "clean
up the private version too" = his saved settings), never at upgrade or by Chat.

## Code rules
- **Relative URLs only.** Ingress serves the app under `/api/hassio_ingress/<token>/`: write `app.css`,
  `api/brief`, `fonts/x.woff2`, never `/app.css`; no redirects to absolute paths (`tests/test_server.py`).
- **Data is text.** Render with `textContent` (`h()` in app.js), never `innerHTML`.
- **The assistant's name is a setting** (`assistant_name`, default "Bruce"; installs with settings from before it keep
  "Wheatley"). Never hard-code it: `assistant.py` on the server (escaped `pattern`, cleaned `prompt`), `aname()` in app.js.
- Server: Python stdlib, one pinned `anthropic` (lazy import), the approved Alpine packages signal-cli,
  java-libsignal-client, openjdk25-jre-headless, vendored `vendor/qrcodegen.py`; nothing else without the owner's
  go-ahead. Port 8099 accepts only the Supervisor (172.30.32.2) and loopback; plus the optional voice API on 8100.

## Design
- Source of truth: the design sources in the planning folder (see CLAUDE.local.md, not in git; read-only) for the
  look.
- One look (id `jam`, structure `panel`); the theme is the only choice: Light, Dark, Auto (owner 2026-11-13: "just
  give it light, dark, and auto"). The other looks, Easy read included, are deleted; a saved one reads as the one look
  with its mode kept. Components use only the theme tokens at the top of `app.css`.
- Contrast: text and text-bearing fills meet WCAG AA (use a deeper step where a colour falls short). Phone targets
  at least 44 x 44 px.
- Principles (design-audit-2026-11.md in the planning folder): one loud button a screen; say it once; defaults first; spacing 4-32 px;
  three sizes a screen; motion explains (150-350 ms). Plain words, 12-hour times. Mockups before new screens.

## Test and packaging
```sh
python3 -m unittest discover -s tests          # stdlib; Claude tests need anthropic==2.3.0 (else skipped)
python3 callsheet/app/server.py --port 8099    # manual: http://127.0.0.1:8099/
```
Visual checks (1280/400 px, both looks and modes, overflow, no foreign requests): Playwright outside the repo.
- Every release: bump `version` (`config.yaml`) and `APP_VERSION` (`api.py`) together; add a CHANGELOG entry.
- `Dockerfile`: pinned `ghcr.io/home-assistant/base-python`; `run.sh` keeps LF. The Supervisor builds the image.
- Update `filemap.md` when files are added or removed. Don't push without the owner's go-ahead.
