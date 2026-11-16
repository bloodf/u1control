"""Time-lapses (0.11.0): the `timelapse` root, one entry per video with its pictures, covers for the page, and a
delete that takes the video and its pictures. The fake U1 has the roots of a real one: `camera` is read only."""

import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import fakes  # noqa: E402
import files  # noqa: E402
from files import timelapse_videos  # noqa: E402
from test_review_fixes import call, make_service  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"cover" * 10
PRINT = "orcatest_u1_20261116130921"


def entry(path, size=1, modified=0):
    return {"path": path, "size": size, "modified": modified, "permissions": "rw"}


class PairingTests(unittest.TestCase):
    def test_one_entry_per_video_with_its_cover_and_last_frame(self):
        videos = timelapse_videos([entry(PRINT + ".jpg", 9000, 12), entry(PRINT + ".mp4", 375588, 10),
                                   entry(PRINT + "_cover.jpg", 40000, 11), entry("monitor.jpg", 5, 99)])
        self.assertEqual(videos, [{"path": "timelapse/" + PRINT + ".mp4", "file": PRINT + ".mp4", "name": "orcatest_u1",
                                   "size": 375588, "modified": 10, "cover": "timelapse/" + PRINT + "_cover.jpg",
                                   "pictures": ["timelapse/" + PRINT + "_cover.jpg", "timelapse/" + PRINT + ".jpg"]}])

    def test_newest_first(self):
        videos = timelapse_videos([entry("a_20260101000000.mp4", modified=5), entry("b_20260102000000.mp4", modified=9),
                                   entry("c.mp4", modified=None)])
        self.assertEqual([v["file"] for v in videos], ["b_20260102000000.mp4", "a_20260101000000.mp4", "c.mp4"])

    def test_missing_cover_falls_back_to_the_last_frame_then_to_none(self):
        videos = {v["file"]: v for v in timelapse_videos([entry("a.mp4"), entry("a.jpg"), entry("b.mp4")])}
        self.assertEqual((videos["a.mp4"]["cover"], videos["a.mp4"]["pictures"]), ("timelapse/a.jpg", ["timelapse/a.jpg"]))
        self.assertEqual((videos["b.mp4"]["cover"], videos["b.mp4"]["pictures"]), (None, []))

    def test_odd_names(self):
        names = ["Benchy (1) final_20261116130921", "café à la crème_20261116130922", "no stamp", "x_2026",
                 "_20261116130923", "a.b.c_20261116130924", "UPPER_20261116130925"]
        listing = [entry(n + ext) for n in names for ext in (".mp4", "_cover.jpg")]
        listing += [entry("UPPER_20261116130925.JPG"), entry("shout.MP4"), entry("shout_cover.JPEG")]
        videos = {v["file"]: v for v in timelapse_videos(listing)}
        self.assertEqual({f: v["name"] for f, v in videos.items()},
                         {"Benchy (1) final_20261116130921.mp4": "Benchy (1) final", "café à la crème_20261116130922.mp4": "café à la crème",
                          "no stamp.mp4": "no stamp", "x_2026.mp4": "x_2026", "_20261116130923.mp4": "_20261116130923",
                          "a.b.c_20261116130924.mp4": "a.b.c", "UPPER_20261116130925.mp4": "UPPER", "shout.MP4": "shout"})
        for name in names:
            self.assertEqual(videos[name + ".mp4"]["cover"], "timelapse/" + name + "_cover.jpg", name)
        self.assertEqual(videos["UPPER_20261116130925.mp4"]["pictures"],
                         ["timelapse/UPPER_20261116130925_cover.jpg", "timelapse/UPPER_20261116130925.JPG"])
        self.assertEqual(videos["shout.MP4"]["pictures"], ["timelapse/shout_cover.JPEG"])

    def test_a_picture_belongs_to_one_video_only(self):
        """'a_cover.jpg' is the last frame of a_cover.mp4, not the cover of a.mp4: deleting a.mp4 must leave it."""
        videos = {v["file"]: v for v in timelapse_videos([entry("a.mp4"), entry("a_cover.mp4"), entry("a_cover.jpg"),
                                                          entry("a_cover_cover.jpg")])}
        self.assertEqual(videos["a.mp4"]["pictures"], [])
        self.assertEqual(videos["a_cover.mp4"]["pictures"], ["timelapse/a_cover_cover.jpg", "timelapse/a_cover.jpg"])

    def test_videos_sharing_a_name_get_no_pictures(self):
        """a.mp4 and a.MP4: nothing says whose a.jpg is, so deleting either video leaves the pictures."""
        videos = timelapse_videos([entry("a.MP4"), entry("a.mp4"), entry("a.jpg"), entry("a_cover.jpg"), entry("b.mp4"), entry("b.jpg")])
        self.assertEqual({v["file"]: v["pictures"] for v in videos}, {"a.MP4": [], "a.mp4": [], "b.mp4": ["timelapse/b.jpg"]})

    def test_unpaired_pictures_and_other_files_are_no_videos(self):
        self.assertEqual(timelapse_videos([entry("monitor.jpg"), entry("gone_cover.jpg"), entry("notes.txt"), entry("a.mp4.part")]), [])

    def test_subfolders_pair_inside_their_folder(self):
        videos = {v["path"]: v for v in timelapse_videos([entry("old/a.mp4"), entry("old/a_cover.jpg"), entry("a.mp4"), entry("a.jpg")])}
        self.assertEqual(videos["timelapse/old/a.mp4"]["pictures"], ["timelapse/old/a_cover.jpg"])
        self.assertEqual(videos["timelapse/a.mp4"]["pictures"], ["timelapse/a.jpg"])
        self.assertEqual(videos["timelapse/old/a.mp4"]["name"], "a")

    def test_malformed_and_unsafe_entries_are_skipped(self):
        bad = [None, "a.mp4", {"size": 1}, {"path": 7}, entry("../gcodes/a.mp4"), entry("x/../a.mp4"), entry("/abs.mp4"),
               entry(".hidden.mp4"), entry("x//a.mp4"), entry("./a.mp4"), entry("")]
        self.assertEqual(timelapse_videos(bad), [])
        for listing in (None, {}, "x", 5):
            self.assertEqual(timelapse_videos(listing), [])
        self.assertEqual(timelapse_videos([entry("a.mp4", "big", True)])[0]["size"], None)   # not numbers: left out


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.fake.files.update({"timelapse/" + PRINT + ".mp4": b"v" * 5000, "timelapse/" + PRINT + "_cover.jpg": JPEG,
                                "timelapse/" + PRINT + ".jpg": JPEG, "timelapse/other_20261115080000.mp4": b"v",
                                "timelapse/other_20261115080000_cover.jpg": JPEG, "timelapse/monitor.jpg": JPEG})
        self.svc, self.pub = make_service(self, self.fake)

    def run_cmd(self, cmd, **args):
        return call(self, self.svc, self.pub, cmd, **args)

    def test_lists_the_videos_of_the_timelapse_root(self):
        got = self.run_cmd("timelapses")["result"]
        self.assertIs(got["supported"], True)
        self.assertEqual([(v["path"], v["name"], v["size"], v["cover"]) for v in got["videos"]],
                         [("timelapse/other_20261115080000.mp4", "other", 1, "timelapse/other_20261115080000_cover.jpg"),
                          ("timelapse/" + PRINT + ".mp4", "orcatest_u1", 5000, "timelapse/" + PRINT + "_cover.jpg")])

    def test_a_firmware_without_the_root_says_so_and_lists_nothing(self):
        self.fake.roots = [r for r in self.fake.roots if r["name"] != "timelapse"]
        self.assertEqual(self.run_cmd("timelapses")["result"], {"supported": False, "videos": []})
        self.fake.roots = "broken"
        self.assertEqual(self.run_cmd("timelapses")["result"], {"supported": False, "videos": []})

    def test_delete_removes_the_video_and_its_pictures_through_the_writable_root(self):
        path = "timelapse/" + PRINT + ".mp4"
        self.assertEqual(self.run_cmd("timelapse_delete", path=path)["result"],
                         {"deleted": ["timelapse/" + PRINT + "_cover.jpg", "timelapse/" + PRINT + ".jpg", path]})
        self.assertEqual(self.fake.deleted, ["/server/files/timelapse/" + PRINT + "_cover.jpg",
                                             "/server/files/timelapse/" + PRINT + ".jpg", "/server/files/" + path])
        self.assertEqual(sorted(self.fake.files), ["timelapse/monitor.jpg", "timelapse/other_20261115080000.mp4",
                                                   "timelapse/other_20261115080000_cover.jpg"])   # nothing else went
        self.assertIn("not a time-lapse on the printer", self.run_cmd("timelapse_delete", path=path)["error"])   # gone now

    def test_delete_refuses_everything_but_a_listed_video(self):
        for bad in ("camera/" + PRINT + ".mp4", "gcodes/a.gcode", "timelapse", "timelapse/../gcodes/a.gcode",
                    "timelapse/" + PRINT + "_cover.jpg", "timelapse/monitor.jpg", "timelapse/missing.mp4", "", None,
                    "config/printer.cfg", "/etc/passwd", "timelapse/..", "timelapse/./../x.mp4"):
            with self.subTest(path=bad):
                self.assertIn("error", self.run_cmd("timelapse_delete", path=bad))
        self.assertEqual(self.fake.deleted, [])

    def test_a_failed_picture_delete_keeps_the_video(self):
        self.fake.undeletable.add("timelapse/" + PRINT + ".jpg")
        self.assertIn("delete failed", self.run_cmd("timelapse_delete", path="timelapse/" + PRINT + ".mp4")["error"])
        self.assertIn("timelapse/" + PRINT + ".mp4", self.fake.files)   # still listed, so it can be tried again
        self.fake.undeletable.clear()
        self.assertIn("result", self.run_cmd("timelapse_delete", path="timelapse/" + PRINT + ".mp4"))
        self.assertNotIn("timelapse/" + PRINT + ".mp4", self.fake.files)

    def test_the_camera_root_stays_read_only_and_the_file_manager_keeps_its_roots(self):
        """What the U1 does (405 under `camera`), and why the generic commands don't learn the new root."""
        self.fake.files["camera/t.mp4"] = b"v"
        self.assertIn("Path not available for DELETE", self.run_cmd("delete", path="camera/t.mp4")["error"])
        for cmd, args in (("delete", {"path": "timelapse/" + PRINT + ".mp4"}), ("files", {"path": "timelapse"}),
                          ("rename", {"path": "timelapse/" + PRINT + ".mp4", "name": "x.mp4"}), ("mkdir", {"path": "timelapse/new"}),
                          ("move", {"path": "timelapse/" + PRINT + ".mp4", "folder": "timelapse"}), ("folders", {"root": "timelapse"}),
                          ("thumbnail", {"path": "timelapse/" + PRINT + "_cover.jpg"})):
            with self.subTest(cmd=cmd):
                self.assertIn("bad path", self.run_cmd(cmd, **args)["error"])
        self.assertEqual((self.fake.deleted, self.fake.moved, self.fake.made), ([], [], []))
        self.assertEqual(files.FILE_ROOTS, ("gcodes", "camera"))

    def test_cover_is_a_jpeg_data_url_from_the_timelapse_root_only(self):
        url = self.run_cmd("timelapse_cover", path="timelapse/" + PRINT + "_cover.jpg")["result"]
        self.assertTrue(url.startswith("data:image/jpeg;base64,/9j/"), url[:40])
        self.fake.files.update({"gcodes/x.jpg": JPEG, "camera/x.jpg": JPEG, "timelapse/fake.jpg": b"<svg onload=alert(1)>"})
        for bad in ("timelapse/" + PRINT + ".mp4", "gcodes/x.jpg", "camera/x.jpg", "timelapse/../gcodes/x.jpg", "timelapse",
                    "timelapse/fake.jpg", "timelapse/missing.jpg", "timelapse/x.png", ""):
            with self.subTest(path=bad):
                self.assertIn("error", self.run_cmd("timelapse_cover", path=bad))

    def test_cover_size_cap(self):
        self.fake.files["timelapse/edge.jpg"] = JPEG + b"x" * (files.COVER_MAX - len(JPEG))
        self.fake.files["timelapse/huge.jpg"] = JPEG + b"x" * (files.COVER_MAX - len(JPEG) + 1)
        self.assertIn("result", self.run_cmd("timelapse_cover", path="timelapse/edge.jpg"))
        self.assertIn("too large", self.run_cmd("timelapse_cover", path="timelapse/huge.jpg")["error"])
        with mock.patch.object(files, "COVER_MAX", 16):
            self.assertIn("too large", self.run_cmd("timelapse_cover", path="timelapse/" + PRINT + "_cover.jpg")["error"])

    def test_covers_use_the_thumbnail_queue_not_the_command_worker(self):
        with mock.patch.object(self.svc, "thumbs") as thumbs:
            self.svc.submit(1, "timelapse_cover", {"path": "timelapse/a.jpg"})
        self.assertEqual(thumbs.put_nowait.call_args[0][0][:3], (1, "timelapse_cover", {"path": "timelapse/a.jpg"}))

    def test_download_saves_a_timelapse_and_still_refuses_other_roots(self):
        home = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home}):
            saved = self.run_cmd("download", path="timelapse/" + PRINT + ".mp4")["result"]
            for bad in ("config/printer.cfg", "timelapse/../config/printer.cfg", "logs/klippy.log"):
                self.assertIn("bad path", self.run_cmd("download", path=bad)["error"])
        self.assertEqual((os.path.dirname(saved), os.path.basename(saved)), (os.path.join(home, "Downloads", "u1control"), PRINT + ".mp4"))
        self.assertEqual(os.path.getsize(saved), 5000)
        self.assertEqual(os.listdir(os.path.dirname(saved)), [PRINT + ".mp4"])

    def test_delete_works_while_printing(self):
        self.fake.state = "printing"
        self.assertIn("result", self.run_cmd("timelapse_delete", path="timelapse/other_20261115080000.mp4"))


if __name__ == "__main__":
    unittest.main()
