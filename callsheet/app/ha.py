"""The only code in Callsheet that talks to Home Assistant (0.5.1: phone notifications).

By construction: every request goes through `request()`, which checks it against an explicit allowlist of exactly
four (method, URL) forms on the Supervisor's Core API proxy:
  GET  <core>/services                        (to list the notify.mobile_app_* targets)
  POST <core>/services/notify/mobile_app_<x>  (to send one notification to one phone)
  GET  <core>/states/sensor.<x>_last_notification
                                              (0.16.1 texts: one phone's "Last notification" sensor, owner approved
                                               2026-11-11)
  GET  <core>/history/period/<UTC time>?filter_entity_id=sensor.<x>_last_notification
                                              (0.16.1 texts: that sensor's changes since a time)
Anything else (other services, other states or entities, events, templates, other query strings, other hosts) raises
NotAllowed before any network I/O. Redirects are not followed.

The Supervisor gives the app SUPERVISOR_TOKEN when config.yaml has `homeassistant_api: true`. The token is read
from the environment per request and only ever put in the Authorization header: it is never logged, stored,
returned or put in an error message.

Optional (fork): the app options `notify_service`, `notify_service_data_key` and `notify_service_extra` send every
notification to one Home Assistant service (e.g. a house's own notification router) instead of notify.mobile_app_<x>.
The chosen phone goes in as `targets: ["notify.mobile_app_<x>"]`; the allowlist then also admits exactly
POST <core>/services/<domain>/<service> for that one configured service, and no longer admits notify.mobile_app_<x>.

CALLSHEET_HA_API_BASE (tests only) points the client at a fake Core API.
"""
import datetime as dt
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

CORE_API = "http://supervisor/core/api"
TIMEOUT = 10
SERVICE = re.compile(r"mobile_app_[a-z0-9_]{1,64}")
NOTIFY_SENSOR = re.compile(r"sensor\.[a-z0-9_]{1,64}_last_notification")   # 0.16.1: the Companion app's sensor
HISTORY_START = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00")      # a UTC time, seconds
ROUTE_SERVICE = re.compile(r"[a-z0-9_]{1,64}\.[a-z0-9_]{1,64}")
DATA_KEY = re.compile(r"[a-z0-9_]{1,64}")
NOT_IN_HA = "Phone notifications work when Callsheet runs as a Home Assistant app."


def api_base():
    return os.environ.get("CALLSHEET_HA_API_BASE", CORE_API).rstrip("/")


def _options():
    try:
        o = json.loads((pathlib.Path(os.environ.get("CALLSHEET_DATA", "/data")) / "options.json").read_text())
    except (OSError, ValueError):
        return {}
    return o if isinstance(o, dict) else {}


def route():
    """(domain, service, data_key, extra) when the app options route notifications through one HA service, else None.
    A malformed option is ignored (notifications then go to the phone as usual)."""
    o = _options()
    svc = str(o.get("notify_service") or "").strip()
    if not ROUTE_SERVICE.fullmatch(svc) or svc.startswith("notify."):
        return None
    key = str(o.get("notify_service_data_key") or "data").strip()
    if not DATA_KEY.fullmatch(key):
        key = "data"
    try:
        extra = json.loads(o.get("notify_service_extra") or "{}")
    except (TypeError, ValueError):
        extra = {}
    domain, name = svc.split(".", 1)
    return domain, name, key, extra if isinstance(extra, dict) else {}


def _token():
    return os.environ.get("SUPERVISOR_TOKEN", "").strip()


def available():
    """True when the Supervisor gave Callsheet its Core API token."""
    return bool(_token())


class NotAllowed(Exception):
    """A request outside the allowlist. A programming error, never a user error."""


class HAError(Exception):
    """Home Assistant said no or couldn't be reached. .status: HTTP status (0 for network errors);
    .code: "gone" (the phone's notify service isn't there), "auth", "unreachable", "server", "unavailable"."""

    def __init__(self, message, status=0, code=""):
        super().__init__(message)
        self.status = status
        self.code = code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a 3xx becomes an HTTPError; never follow to another URL


_opener = urllib.request.build_opener(_NoRedirect)


def check_allowed(method, url):
    method = method.upper()
    parts = urllib.parse.urlsplit(url)
    base = urllib.parse.urlsplit(api_base())
    if (parts.scheme, parts.netloc) != (base.scheme, base.netloc) or parts.fragment or "#" in url \
            or "%" in parts.path or ".." in parts.path or parts.username or parts.password:
        raise NotAllowed(f"{method} to this URL is not allowed")
    path, root = parts.path, base.path.rstrip("/")
    hist = root + "/history/period/"
    if parts.query or "?" in url:   # 0.16.1: only the history read has a query, and only this one
        q = parts.query
        if method == "GET" and path.startswith(hist) and HISTORY_START.fullmatch(path[len(hist):]) \
                and q.startswith("filter_entity_id=") and NOTIFY_SENSOR.fullmatch(q[len("filter_entity_id="):]):
            return
        raise NotAllowed(f"{method} to this URL is not allowed")
    if method == "GET" and path == root + "/services":
        return
    if method == "GET" and path.startswith(root + "/states/") \
            and NOTIFY_SENSOR.fullmatch(path[len(root + "/states/"):]):
        return
    r = route()
    if r:
        if method == "POST" and path == f"{root}/services/{r[0]}/{r[1]}":
            return
        raise NotAllowed(f"{method} {path} is not allowed")
    prefix = root + "/services/notify/"
    if method == "POST" and path.startswith(prefix) and SERVICE.fullmatch(path[len(prefix):]):
        return
    raise NotAllowed(f"{method} {path} is not allowed")


def request(method, url, body=None):
    """Make one allowlisted request; returns parsed JSON (or None for an empty body)."""
    check_allowed(method, url)
    token = _token()
    if not token:
        raise HAError(NOT_IN_HA, 0, "unavailable")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper())
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    try:
        with _opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise HAError(_plain(e.code, url), e.code, _code(e.code, url)) from None
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            raise HAError("Home Assistant didn't answer in time.", 0, "unreachable") from None
        raise HAError("Couldn't reach Home Assistant.", 0, "unreachable") from None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        raise HAError("Home Assistant sent an answer Callsheet can't read.", 200, "server") from None


def _is_notify(url):
    return "/services/notify/" in urllib.parse.urlsplit(url).path


def _is_state(url):
    return "/states/" in urllib.parse.urlsplit(url).path


def _code(status, url):
    if status in (400, 404) and _is_notify(url):
        return "gone"
    if status == 404 and _is_state(url):
        return "missing"
    if status in (401, 403):
        return "auth"
    return "server"


def _plain(status, url):
    if status in (400, 404) and _is_notify(url):
        name = urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1]
        return (f"Home Assistant doesn't know {friendly(name)} (notify.{name}) any more. Open the Home Assistant app "
                "on that phone, or pick another phone.")
    if status == 404 and _is_state(url):
        return "Home Assistant doesn't have that sensor (it may be turned off in the Companion app)."
    if status in (401, 403):
        return ("Home Assistant didn't let Callsheet in. Restart the Callsheet app in Home Assistant; if that doesn't "
                "help, reinstall this version (it needs Home Assistant API access).")
    if 300 <= status < 400:
        return "Home Assistant sent an unexpected redirect."
    if status >= 500:
        return "Home Assistant had a problem. Try again in a minute."
    return f"Home Assistant said no (HTTP {status})."


# --- the two calls ----------------------------------------------------------------
def notify_targets():
    """The notify.mobile_app_* services Home Assistant lists: [{id, name}] sorted by name."""
    res = request("GET", api_base() + "/services")
    ids = set()
    for d in res if isinstance(res, list) else []:
        if isinstance(d, dict) and d.get("domain") == "notify" and isinstance(d.get("services"), dict):
            ids.update(s for s in d["services"] if isinstance(s, str) and SERVICE.fullmatch(s))
    return sorted(({"id": s, "name": friendly(s)} for s in ids), key=lambda t: (t["name"].lower(), t["id"]))


def notify(service, payload):
    """POST one notification ({message, title, data}) to notify.<service>."""
    if not isinstance(service, str) or not SERVICE.fullmatch(service):
        raise NotAllowed("not a mobile_app notify service")
    r = route()
    if r:
        domain, name, key, extra = r
        body = dict(extra)
        body.update({"message": payload.get("message", ""), "targets": ["notify." + service]})
        if payload.get("title"):
            body["title"] = payload["title"]
        data = payload.get("data") or {}
        if data:
            body[key] = data
        request("POST", f"{api_base()}/services/{domain}/{name}", body)
        return
    request("POST", api_base() + "/services/notify/" + service, payload)


# --- 0.16.1 texts: the phone's "Last notification" sensor (texts.py) ------------------------------------------------
def notification_state(entity_id):
    """The sensor's current state object ({entity_id, state, attributes, last_changed, last_updated})."""
    if not isinstance(entity_id, str) or not NOTIFY_SENSOR.fullmatch(entity_id):
        raise NotAllowed("not a last_notification sensor")
    return request("GET", api_base() + "/states/" + entity_id)


def notification_history(entity_id, since):
    """The sensor's states since `since` (a Unix time), oldest first: [state objects]."""
    if not isinstance(entity_id, str) or not NOTIFY_SENSOR.fullmatch(entity_id):
        raise NotAllowed("not a last_notification sensor")
    start = dt.datetime.fromtimestamp(int(since), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    res = request("GET", api_base() + "/history/period/" + start + "?filter_entity_id=" + entity_id)
    out = []
    for lst in res if isinstance(res, list) else []:
        out += [s for s in lst if isinstance(s, dict)] if isinstance(lst, list) else []
    return out


_WORDS = {"iphone": "iPhone", "ipad": "iPad", "ipod": "iPod", "imac": "iMac", "macbook": "MacBook",
          "watch": "Watch", "pixel": "Pixel", "galaxy": "Galaxy", "oneplus": "OnePlus"}


def friendly(service):
    """A name for a phone from its service id: mobile_app_kitchen_ipad -> "Kitchen iPad", mobile_app_pixel_8 ->
    "Pixel 8"."""
    core = str(service or "")
    core = core[len("mobile_app_"):] if core.startswith("mobile_app_") else core
    words = []
    for w in (x for x in core.split("_") if x):
        if w in _WORDS:
            words.append(_WORDS[w])
        elif any(ch.isdigit() for ch in w):
            words.append(w)
        else:
            words.append(w[:1].upper() + w[1:])
    return " ".join(words) or "Phone"
