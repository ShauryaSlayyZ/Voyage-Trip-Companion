# backend/tests/test_preprocessor.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from datetime import datetime, timedelta

from core.models import Task, Itinerary, StateSnapshot
from core.enums import TaskStatus, CompletionType, DisruptionType, TaskType
from core.events import DisruptionEvent
from agents.optimizers.preprocessor import DisruptionPreprocessor


def make_task(tid, start_offset_h, duration_h, base,
              status=TaskStatus.PLANNED,
              completion=CompletionType.NONE,
              task_type=TaskType.REST,
              travel_to_next=0):
    start = base + timedelta(hours=start_offset_h)
    end   = start + timedelta(hours=duration_h)
    return Task(
        id=tid, title=tid, location="X",
        start_time=start, end_time=end,
        status=status, completion=completion,
        task_type=task_type,
        travel_time_to_next=travel_to_next,
    )


class TestClassification(unittest.TestCase):
    def setUp(self):
        self.base = datetime(2026, 5, 20, 8, 0)
        self.processor = DisruptionPreprocessor()

    def _run(self, tasks, current_offset_h=1.5, delay=30, task_id=None):
        snap = StateSnapshot(
            current_time=self.base + timedelta(hours=current_offset_h),
            itinerary=Itinerary(tasks=tasks),
        )
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id=task_id,
            detected_at=snap.current_time, delay_minutes=delay,
        )
        return self.processor.run(snap, d)

    def test_explicit_completed_goes_to_fixed(self):
        t1 = make_task("t1", 0, 1, self.base,
                       status=TaskStatus.COMPLETED,
                       completion=CompletionType.EXPLICIT,
                       task_type=TaskType.FIXED)
        t2 = make_task("t2", 2, 1, self.base)
        out = self._run([t1, t2])
        self.assertEqual(len(out.classification.fixed_tasks), 1)
        self.assertEqual(out.classification.fixed_tasks[0].id, "t1")
        self.assertEqual(len(out.classification.future_tasks), 1)

    def test_implicit_completed_goes_to_past(self):
        t1 = make_task("t1", 0, 1, self.base,
                       status=TaskStatus.COMPLETED,
                       completion=CompletionType.IMPLICIT)
        out = self._run([t1])
        self.assertEqual(len(out.classification.past_tasks), 1)
        self.assertEqual(len(out.classification.fixed_tasks), 0)

    def test_missed_task_goes_to_fixed(self):
        t1 = make_task("t1", 0, 1, self.base, status=TaskStatus.MISSED)
        out = self._run([t1])
        self.assertIn("t1", [t.id for t in out.classification.fixed_tasks])

    def test_active_task_classified(self):
        t1 = make_task("t1", 0, 2, self.base, status=TaskStatus.ACTIVE)
        t2 = make_task("t2", 3, 1, self.base)
        out = self._run([t1, t2])
        self.assertIsNotNone(out.classification.active_task)
        self.assertEqual(out.classification.active_task.id, "t1")

    def test_planned_in_past_goes_to_fixed(self):
        # Task ends before current_time — should be treated as fixed
        t1 = make_task("t1", 0, 1, self.base)  # ends at 9:00
        # current_time = 9:30 (1.5h offset), t1 ends at 9:00
        out = self._run([t1])
        self.assertIn("t1", [t.id for t in out.classification.fixed_tasks])


class TestCascadePropagation(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 20, 10, 0)
        self.processor = DisruptionPreprocessor()

    def _snap(self, tasks):
        return StateSnapshot(
            current_time=self.now,
            itinerary=Itinerary(tasks=tasks),
        )

    def test_simple_cascade(self):
        tasks = [
            make_task("t1", 1, 1, self.now, travel_to_next=10),
            make_task("t2", 2.5, 1, self.now),
        ]
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id="t1",
            detected_at=self.now, delay_minutes=45,
        )
        out = self.processor.run(self._snap(tasks), d)
        self.assertEqual(out.cascade.delay_map["t1"], 45)
        # t1 ends at 12:00 + 45 = 12:45, travel 10 → arrive 12:55
        # t2 starts at 12:30 → push = 25
        self.assertEqual(out.cascade.delay_map["t2"], 25)

    def test_cascade_absorbed_by_slack(self):
        tasks = [
            make_task("t1", 1, 1, self.now, travel_to_next=0),
            make_task("t2", 5, 1, self.now),   # large gap
        ]
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id="t1",
            detected_at=self.now, delay_minutes=30,
        )
        out = self.processor.run(self._snap(tasks), d)
        self.assertIn("t1", out.cascade.delay_map)
        self.assertNotIn("t2", out.cascade.delay_map)
        self.assertEqual(out.cascade.cascade_boundary_id, "t2")

    def test_no_cascade_on_closed_disruption(self):
        tasks = [make_task("t1", 1, 1, self.now)]
        d = DisruptionEvent(
            type=DisruptionType.CLOSED, task_id="t1",
            detected_at=self.now,
        )
        out = self.processor.run(self._snap(tasks), d)
        self.assertEqual(out.cascade.total_propagated_delay, 0)
        self.assertEqual(len(out.cascade.delay_map), 0)

    def test_no_future_tasks(self):
        snap = StateSnapshot(
            current_time=self.now,
            itinerary=Itinerary(tasks=[]),
        )
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id=None,
            detected_at=self.now, delay_minutes=30,
        )
        out = self.processor.run(snap, d)
        self.assertEqual(len(out.classification.future_tasks), 0)
        self.assertEqual(out.cascade.total_propagated_delay, 30)

    def test_complex_cascade_with_absorption(self):
        # From original test — preserve exactly
        now = datetime(2026, 5, 20, 10, 0)
        tasks = [
            Task(id="t1", title="Meeting", location="Office",
                 start_time=now + timedelta(hours=1),
                 end_time=now + timedelta(hours=2),
                 travel_time_to_next=10),
            Task(id="t2", title="Lunch", location="Bistro",
                 start_time=now + timedelta(hours=2, minutes=30),
                 end_time=now + timedelta(hours=3, minutes=30),
                 travel_time_to_next=15),
            Task(id="t3", title="Museum", location="Museum",
                 start_time=now + timedelta(hours=5),
                 end_time=now + timedelta(hours=7)),
        ]
        snap = StateSnapshot(current_time=now, itinerary=Itinerary(tasks=tasks))
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id="t1",
            detected_at=now, delay_minutes=45,
        )
        result = self.processor.run(snap, d)
        self.assertEqual(result.cascade.delay_map["t1"], 45)
        self.assertEqual(result.cascade.delay_map["t2"], 25)
        self.assertNotIn("t3", result.cascade.delay_map)
        self.assertEqual(result.cascade.cascade_boundary_id, "t3")


class TestBoundsAndInfeasibility(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 5, 20, 10, 0)
        self.processor = DisruptionPreprocessor()

    def _snap(self, tasks):
        return StateSnapshot(
            current_time=self.now,
            itinerary=Itinerary(tasks=tasks),
        )

    def test_lb_reflects_cascade(self):
        tasks = [make_task("t1", 1, 1, self.now)]
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id="t1",
            detected_at=self.now, delay_minutes=60,
        )
        out = self.processor.run(self._snap(tasks), d)
        # t1 original start: now+1h = rel 60min
        # delay: 60 → cascaded start = 120min from now
        self.assertGreaterEqual(out.bounds["t1"].lb, 120)

    def test_closed_task_infeasible(self):
        tasks = [make_task("t1", 1, 1, self.now)]
        d = DisruptionEvent(
            type=DisruptionType.CLOSED, task_id="t1",
            detected_at=self.now,
        )
        out = self.processor.run(self._snap(tasks), d)
        self.assertIn("t1", out.trivially_infeasible)

    def test_tight_window_infeasible(self):
        # Task duration 2h but window only 1h
        t1 = make_task("t1", 1, 2, self.now)
        # Override time window to be tight
        t1.time_window_start = self.now + timedelta(hours=1)
        t1.time_window_end   = self.now + timedelta(hours=2)  # only 1h window
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id=None,
            detected_at=self.now, delay_minutes=0,
        )
        out = self.processor.run(self._snap([t1]), d)
        self.assertIn("t1", out.trivially_infeasible)

    def test_ub_capped_at_horizon(self):
        tasks = [make_task("t1", 1, 1, self.now)]
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id=None,
            detected_at=self.now, delay_minutes=0,
        )
        out = self.processor.run(self._snap(tasks), d,)
        self.assertLessEqual(out.bounds["t1"].ub, 1440)

    def _snap(self, tasks):
        return StateSnapshot(
            current_time=self.now,
            itinerary=Itinerary(tasks=tasks),
        )


if __name__ == "__main__":
    unittest.main()
