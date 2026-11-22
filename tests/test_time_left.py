"""Time left of a print (the slicer's estimate first) and a monitor that keeps going after any failure."""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src", "u1control"), os.path.join(ROOT, "tests")]

import agent  # noqa: E402
import fakes  # noqa: E402
import service as service_mod  # noqa: E402
import u1  # noqa: E402
from moonraker import PrinterError  # noqa: E402
from service import Service, Target  # noqa: E402
from test_u1control import wait_for  # noqa: E402


class TimeLeftTests(unittest.TestCase):
    def test_slicer_estimate_wins_over_extrapolation(self):
        # 10 % in after 1.5 h (start sequence included): extrapolating says 13.5 h, the slicer's 10 h file 9 h
        view = {"progress": 0.1, "print_duration": 5400, "estimated_time": 36000}
        self.assertAlmostEqual(u1.time_left(view), 32400)
        self.assertEqual(agent.push_status({**view, "state": "printing"})["print"]["mc_remaining_time"], 540)

    def test_without_an_estimate_time_spent_is_extrapolated(self):
        self.assertAlmostEqual(u1.time_left({"progress": 0.25, "print_duration": 600}), 1800)
        self.assertAlmostEqual(u1.time_left({"progress": 0.25, "print_duration": 600, "estimated_time": 0}), 1800)

    def test_unknown(self):
        for view in ({}, {"progress": 1.0, "estimated_time": 100}, {"progress": 0.005, "print_duration": 10},
                     {"progress": True, "estimated_time": 100}, {"progress": None, "estimated_time": 100}):
            self.assertIsNone(u1.time_left(view), view)
        self.assertEqual(agent.push_status({"state": "printing"})["print"]["mc_remaining_time"], 0)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.fake = fakes.FakePrinter()
        self.addCleanup(self.fake.close)
        self.pub, self.logs = [], []
        self.svc = Service(self.pub.append, log=self.logs.append)
        self.addCleanup(self.svc.close)
        self.svc.set_target(Target(self.fake.host))

    def statuses(self):
        return [m["data"] for m in self.pub if m.get("type") == "status"]

    def test_status_carries_the_slicer_estimate_and_time_left(self):
        self.fake.estimated_time = 36000
        self.svc._push_status()
        view = self.statuses()[-1]
        self.assertEqual(view["estimated_time"], 36000)
        self.assertAlmostEqual(view["left"], 36000 * (1 - view["progress"]))

    def test_monitor_survives_a_failing_round_and_logs_the_outage_once(self):
        real = self.svc._push_status
        failures = [PrinterError("can't reach the U1 (timed out)")] * 2
        boom = [RuntimeError("boom")]

        def push():
            if failures:
                raise failures.pop()
            return real()

        def failed(gen):
            if boom:
                raise boom.pop()

        with mock.patch.object(service_mod, "STATUS_RETRY", 0.05), mock.patch.object(service_mod, "STATUS_EVERY", 0.05), \
                mock.patch.object(self.svc, "_push_status", push), mock.patch.object(self.svc, "_status_failed", failed):
            self.assertTrue(wait_for(lambda: (self.svc.touch() or True) and self.statuses(), timeout=10))
        text = "\n".join(self.logs)
        self.assertEqual(text.count("status read failed"), 1)
        self.assertIn("monitor round failed: boom", text)
        self.assertIn("the U1 answers again", text)


if __name__ == "__main__":
    unittest.main()
