# backend/tests/test_objective.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from datetime import datetime, timedelta
from ortools.sat.python import cp_model

from core.models import Task, Itinerary, StateSnapshot
from core.enums import DisruptionType, TaskType
from core.events import DisruptionEvent
from agents.optimizers.preprocessor import DisruptionPreprocessor
from agents.optimizers.cpsat_model_builder import CPSATModelBuilder
from agents.optimizers.objective import (
    ObjectiveBuilder, ObjectiveWeights,
    DEFAULT_WEIGHTS, validate_hierarchy,
)


NOW = datetime(2026, 5, 20, 9, 0)


def make_task(tid, start_h, duration_h, priority=3,
              task_type=TaskType.REST, is_fixed=False):
    start = NOW + timedelta(hours=start_h)
    end   = start + timedelta(hours=duration_h)
    t = Task(
        id=tid, title=tid, location="L",
        start_time=start, end_time=end,
        priority=priority,
        task_type=TaskType.FIXED if is_fixed else task_type,
    )
    return t


def build_and_solve(tasks, disruption=None, weights=None):
    weights = weights or DEFAULT_WEIGHTS
    d = disruption or DisruptionEvent(
        type=DisruptionType.DELAY, task_id=None,
        detected_at=NOW, delay_minutes=0,
    )
    snap = StateSnapshot(
        current_time=NOW,
        itinerary=Itinerary(tasks=tasks),
    )
    pre = DisruptionPreprocessor().run(snap, d)
    artifacts = CPSATModelBuilder().build_cpsat_model(
        snapshot=snap,
        future_tasks=tasks,
        locked_tasks=[],
        disruption=d,
        preprocessor_output=pre,
        transition_matrix={},
    )
    obj_meta = ObjectiveBuilder().build_objective(
        model=artifacts["model"],
        model_artifacts=artifacts,
        future_tasks=tasks,
        disruption=d,
        weights=weights,
    )
    solver = cp_model.CpSolver()
    status = solver.Solve(artifacts["model"])
    return solver, status, artifacts, obj_meta


class TestHierarchyValidator(unittest.TestCase):

    def test_default_weights_valid(self):
        self.assertTrue(validate_hierarchy(DEFAULT_WEIGHTS))

    def test_broken_drop_shift_hierarchy(self):
        # Max shift = (1 + 0.5*5) * 480 = 1680
        # drop_base = 1000 < 1680 → hierarchy broken
        broken = ObjectiveWeights(drop_base=1000)
        with self.assertRaises(AssertionError):
            validate_hierarchy(broken)

    def test_broken_cross_day_fatigue_hierarchy(self):
        broken = ObjectiveWeights(cross_day=100, fatigue=200)
        with self.assertRaises(AssertionError):
            validate_hierarchy(broken)

    def test_broken_fatigue_late_hierarchy(self):
        # worst_late = 5 * 120 = 600
        # fatigue = 100 < 600 → broken
        broken = ObjectiveWeights(fatigue=100)
        with self.assertRaises(AssertionError):
            validate_hierarchy(broken)


class TestObjectiveBehavior(unittest.TestCase):

    def test_solver_finds_optimal(self):
        tasks = [make_task("t1", 1, 1), make_task("t2", 3, 1)]
        solver, status, _, _ = build_and_solve(tasks)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))

    def test_drop_costs_more_than_shift(self):
        # Single task: solver should prefer scheduling (shift) over dropping
        tasks = [make_task("t1", 1, 1, priority=3)]
        solver, status, art, _ = build_and_solve(tasks)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))
        # With no disruption, task should be scheduled not dropped
        self.assertEqual(solver.Value(art["scheduled_vars"]["t1"]), 1)

    def test_fixed_task_never_dropped(self):
        # Fixed task has enormous drop penalty — solver should always schedule it
        tasks = [make_task("t1", 1, 1, priority=5, is_fixed=True)]
        solver, status, art, _ = build_and_solve(tasks)
        self.assertIn(status, (cp_model.OPTIMAL, cp_model.FEASIBLE))
        self.assertEqual(solver.Value(art["scheduled_vars"]["t1"]), 1)

    def test_weather_penalty_only_on_walking_tasks(self):
        tasks = [
            make_task("t1", 1, 1, task_type=TaskType.WALKING),
            make_task("t2", 3, 1, task_type=TaskType.REST),
        ]
        d = DisruptionEvent(
            type=DisruptionType.WEATHER, task_id=None,
            detected_at=NOW,
        )
        _, _, _, meta = build_and_solve(tasks, disruption=d)
        weather_ids = [e["task_id"] for e in meta["penalty_meta"]["weather"]]
        self.assertIn("t1", weather_ids)
        self.assertNotIn("t2", weather_ids)

    def test_high_priority_shift_costs_more(self):
        # Priority 5 task shift weight = 1 + 0.5*5 = 3 (int) = 3
        # Priority 1 task shift weight = 1 + 0.5*1 = 1 (int) = 1
        meta_high = None
        meta_low  = None

        for p, store in [(5, "high"), (1, "low")]:
            tasks = [make_task("t1", 1, 1, priority=p)]
            _, _, _, meta = build_and_solve(tasks)
            if store == "high":
                meta_high = meta
            else:
                meta_low = meta

        w_high = meta_high["penalty_meta"]["shift"][0]["weight_per_minute"]
        w_low  = meta_low["penalty_meta"]["shift"][0]["weight_per_minute"]
        self.assertGreater(w_high, w_low)

    def test_penalty_meta_structure(self):
        tasks = [make_task("t1", 1, 1)]
        _, _, _, meta = build_and_solve(tasks)
        self.assertIn("drop",      meta["penalty_meta"])
        self.assertIn("shift",     meta["penalty_meta"])
        self.assertIn("late",      meta["penalty_meta"])
        self.assertIn("cross_day", meta["penalty_meta"])
        self.assertIn("fatigue",   meta["penalty_meta"])
        self.assertIn("weather",   meta["penalty_meta"])


if __name__ == "__main__":
    unittest.main()