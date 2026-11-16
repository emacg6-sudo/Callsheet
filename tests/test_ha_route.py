"""Fork: route notifications through one configured Home Assistant service (app options)."""
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "callsheet" / "app"))
import ha  # noqa: E402

BASE = "http://supervisor/core/api"


class RouteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"CALLSHEET_DATA": self.tmp.name})
        self.env.start()
        os.environ.pop("CALLSHEET_HA_API_BASE", None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def opts(self, **o):
        (pathlib.Path(self.tmp.name) / "options.json").write_text(json.dumps(o))

    def test_no_options_is_upstream(self):
        self.assertIsNone(ha.route())
        ha.check_allowed("POST", BASE + "/services/notify/mobile_app_example_phone")

    def test_routed(self):
        self.opts(notify_service="router.send", notify_service_data_key="extra_data",
                  notify_service_extra='{"class": "status", "topic": "callsheet"}')
        ha.check_allowed("POST", BASE + "/services/router/send")
        ha.check_allowed("GET", BASE + "/services")
        for bad in ("/services/notify/mobile_app_example_phone", "/services/script/other", "/services/router/send2"):
            with self.assertRaises(ha.NotAllowed):
                ha.check_allowed("POST", BASE + bad)
        with mock.patch.object(ha, "request") as req:
            ha.notify("mobile_app_example_phone", {"title": "T", "message": "M", "data": {"tag": "x"}})
        method, url, body = req.call_args[0]
        self.assertEqual((method, url), ("POST", BASE + "/services/router/send"))
        self.assertEqual(body, {"class": "status", "topic": "callsheet", "message": "M", "title": "T",
                                "targets": ["notify.mobile_app_example_phone"], "extra_data": {"tag": "x"}})

    def test_bad_options_ignored(self):
        for svc in ("notify.mobile_app_example", "nodot", "a.b/c", "../x.y"):
            self.opts(notify_service=svc)
            self.assertIsNone(ha.route(), svc)
        self.opts(notify_service="a.b", notify_service_extra="not json", notify_service_data_key="bad key")
        self.assertEqual(ha.route(), ("a", "b", "data", {}))


if __name__ == "__main__":
    unittest.main()
