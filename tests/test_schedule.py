import unittest
from datetime import time

from wecom_rusher.schedule import PollSchedule


class PollScheduleTests(unittest.TestCase):
    def test_rush_interval_applies_inside_window(self):
        schedule = PollSchedule(5.0, 0.5, time(11, 0), time(12, 0))
        self.assertEqual(schedule.interval_at(time(11, 30)), 0.5)

    def test_start_is_inclusive_and_end_is_exclusive(self):
        schedule = PollSchedule(5.0, 0.5, time(11, 0), time(12, 0))
        self.assertEqual(schedule.interval_at(time(11, 0)), 0.5)
        self.assertEqual(schedule.interval_at(time(12, 0)), 5.0)

    def test_normal_interval_applies_outside_window(self):
        schedule = PollSchedule(5.0, 0.5, time(11, 0), time(12, 0))
        self.assertEqual(schedule.interval_at(time(10, 59)), 5.0)
        self.assertEqual(schedule.interval_at(time(12, 1)), 5.0)
