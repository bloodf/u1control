"""The Dashboard's layouts: kept in the plugin's settings (not the page's storage), checked before they are stored."""

import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests"), os.path.join(ROOT, "scripts")]

import settings  # noqa: E402
from test_automagic import PluginBase  # noqa: E402

LAYOUT = {"v": 1, "active": 1, "layouts": [
    {"name": "Default", "items": [{"id": "job", "x": 0, "y": 0, "w": 12, "h": 3}, {"id": "console", "x": 0, "y": 3, "w": 12, "h": 7, "cfg": {"lines": 100}}]},
    {"name": "Night", "items": [{"id": "camera", "x": 0, "y": 0, "w": 6, "h": 8, "cfg": {"aspect": "4/3"}}]}]}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "settings.json")
        self.store = settings.Store(self.path)

    def test_kept_and_read_back_after_a_restart(self):
        self.assertEqual(self.store.effective()["dashboard"], {})   # the page's default layout
        self.assertEqual(self.store.update({"dashboard": LAYOUT})["dashboard"], LAYOUT)
        self.assertEqual(settings.Store(self.path).effective()["dashboard"], LAYOUT)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["dashboard"], LAYOUT)

    def test_anything_else_keeps_what_is_stored(self):
        self.store.update({"dashboard": LAYOUT})
        item = LAYOUT["layouts"][0]["items"][0]
        bad = [None, "x", [], {}, {"v": 2, "layouts": LAYOUT["layouts"]}, {"v": 1, "layouts": []},
               {"v": 1, "layouts": [{"name": "A"}]}, {"v": 1, "layouts": [{"name": 3, "items": []}]},
               {"v": 1, "layouts": [{"name": "A", "items": [dict(item, x=-1)]}]},
               {"v": 1, "layouts": [{"name": "A", "items": [dict(item, w=True)]}]},
               {"v": 1, "layouts": [{"name": "A", "items": [dict(item, id="")]}]},
               {"v": 1, "layouts": [{"name": "A", "items": [dict(item, cfg={"k": [1]})]}]},
               {"v": 1, "layouts": [{"name": "A", "items": []}] * 13},
               {"v": 1, "layouts": [{"name": "A", "items": [dict(item, id="w%d" % i) for i in range(41)]}]},
               {"v": 1, "layouts": [{"name": "A", "items": [dict(item, cfg={"k" * 40: "v" * 900})] * 40}] * 12}]
        for value in bad:
            self.assertEqual(self.store.update({"dashboard": value})["dashboard"], LAYOUT, repr(value)[:80])

    def test_cleaned_on_the_way_in(self):
        value = {"v": 1, "active": 9, "extra": 1, "layouts": [{"name": "N" * 60, "junk": 1, "items": [{"id": "job", "x": 0, "y": 0, "w": 4, "h": 3, "more": 1}]}]}
        self.assertEqual(self.store.update({"dashboard": value})["dashboard"],
                         {"v": 1, "active": 0, "layouts": [{"name": "N" * 40, "items": [{"id": "job", "x": 0, "y": 0, "w": 4, "h": 3}]}]})

    def test_hand_edited_file_is_handed_to_the_page_as_is(self):
        """A stored value that is a dict but not a dashboard reaches the page, which shows its default instead."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"dashboard": {"broken": True}}, f)
        self.assertEqual(settings.Store(self.path).effective()["dashboard"], {"broken": True})
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"dashboard": "broken"}, f)
        self.assertEqual(settings.Store(self.path).effective()["dashboard"], {})


class PageMessageTests(PluginBase):
    def test_page_saves_its_layouts_and_gets_them_back_in_the_config(self):
        _, ns = self.load(preset={"name": "Snapmaker U1 (0.4 nozzle)", "printer_model": "Snapmaker U1", "slicing_pipeline_plugin": ""})
        page = ns["U1ControlPage"]()
        self.addCleanup(lambda: ns["service"]().close())
        page.on_message({"type": "dashboard", "value": LAYOUT})
        self.assertEqual(page._config_message()["settings"]["dashboard"], LAYOUT)
        page.on_message({"type": "dashboard", "value": {"v": 1, "layouts": "no"}})   # refused: the stored one stays
        self.assertEqual(page._config_message()["settings"]["dashboard"], LAYOUT)
        page.on_message({"type": "save_settings", "settings": {"host": "127.0.0.1:1"}})   # Settings' Save leaves it alone
        self.assertEqual(page._config_message()["settings"]["dashboard"], LAYOUT)


if __name__ == "__main__":
    unittest.main()
