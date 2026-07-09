import json
import unittest

from adsp_desktop_app import WatcherApi


class DesktopAppEventTest(unittest.TestCase):
    def test_build_command_enables_gui_events(self):
        api = WatcherApi()
        command = api._build_command(api._coerce_config({}))
        self.assertIn("--gui-events", command)

    def test_json_result_event_populates_results(self):
        api = WatcherApi()
        payload = {
            "type": "seat_hits",
            "time": "2026-07-10 00:30:00",
            "count": 1,
            "hits": [
                {
                    "no": 30,
                    "region": "서울특별시",
                    "seats": 12,
                    "site": "ADsP (서울) 용강중학교",
                    "address": "서울 용산구 이촌로65가길 91 용강중학교",
                    "line": "No.30 - 서울특별시 - ADsP (서울) 용강중학교 - 서울 용산구 이촌로65가길 91 용강중학교 - 클립보드 12석",
                    "source": "clipboard",
                }
            ],
        }
        api._classify_line("ADSP_WATCHER_RESULT_JSON " + json.dumps(payload, ensure_ascii=True))

        results = api.poll()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["no"], "30")
        self.assertEqual(results[0]["region"], "서울특별시")
        self.assertEqual(results[0]["seats"], "12")
        self.assertEqual(results[0]["site"], "ADsP (서울) 용강중학교")
        self.assertEqual(results[0]["address"], "서울 용산구 이촌로65가길 91 용강중학교")


if __name__ == "__main__":
    unittest.main()
