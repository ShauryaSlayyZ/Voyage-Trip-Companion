# backend/tests/test_cpsat_model_builder.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from datetime import datetime, timedelta
from ortools.sat.python import cp_model

from core.models import Task, Itinerary, StateSnapshot
from core.enums import TaskStatus, DisruptionType, TaskType
from core.events import DisruptionEvent
from agents.optimizers.preprocessor import DisruptionPreprocessor
from agents.optimizers.cpsat_model_builder import CPSATModelBuilder


NOW = datetime(2026, 5, 20, 9, 0)


def make_task(tid, start_h, duration_h, travel=0, task_type=TaskType.REST):
    start = NOW + timedelta(hours=start_h)
    end   = start + timedelta(hours=duration_h)
    return Task(
        id=tid, title=tid, location="L",
        start_time=start, end_time=end,
        travel_time_to_next=travel,
        task_type=task_type,
    )


def build(future_tasks, locked_tasks=None, disruption=None,
          lock_ordering=True, lock_to_same_day=True):
    locked_tasks = locked_tasks or []
    snap = StateSnapshot(current_time=NOW, itinerary=Itinerary(tasks=[]))

    d = disruption or DisruptionEvent(
        type=DisruptionType.DELAY, task_id=None,
        detected_at=NOW, delay_minutes=0,
    )

    pre = DisruptionPreprocessor().run(
        StateSnapshot(current_time=NOW, itinerary=Itinerary(tasks=future_tasks)),
        d,
    )

    return CPSATModelBuilder().build_cpsat_model(
        snapshot=snap,
        future_tasks=future_tasks,
        locked_tasks=locked_tasks,
        disruption=d,
        preprocessor_output=pre,
        transition_matrix={},
        lock_ordering=lock_ordering,
        lock_to_same_day=lock_to_same_day,
    )


def solve(artifacts, extra_constraints=None):
    model = artifacts["model"]
    if extra_constraints:
        extra_constraints(model, artifacts)
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return solver, status


class TestVariableStructure:

    def test_all_vars_created(self):
        tasks = [make_task("t1", 1, 1), make_task("t2", 3, 1)]
        art = build(tasks)
        for tid in ["t1", "t2"]:
            assert tid in art["start_vars"]
            assert tid in art["end_vars"]
            assert tid in art["scheduled_vars"]
            assert tid in art["shift_vars"]
            assert tid in art["cross_day_vars"]

    def test_dropped_task_vars_are_zero(self):
        tasks = [make_task("t1", 1, 1)]
        art = build(tasks)

        def force_drop(model, a):
            model.Add(a["scheduled_vars"]["t1"] == 0)

        solver, status = solve(art, force_drop)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        assert solver.Value(art["start_vars"]["t1"]) == 0
        assert solver.Value(art["end_vars"]["t1"]) == 0
        assert solver.Value(art["shift_vars"]["t1"]) == 0
        assert solver.Value(art["cross_day_vars"]["t1"]) == 0

    def test_scheduled_task_end_equals_start_plus_duration(self):
        t1 = make_task("t1", 1, 2)  # 2h duration = 120min
        art = build([t1])

        def force_schedule(model, a):
            model.Add(a["scheduled_vars"]["t1"] == 1)

        solver, status = solve(art, force_schedule)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        s = solver.Value(art["start_vars"]["t1"])
        e = solver.Value(art["end_vars"]["t1"])
        assert e == s + 120


class TestHardConstraints:

    def test_no_overlap_two_tasks(self):
        t1 = make_task("t1", 1, 1)
        t2 = make_task("t2", 1, 1)  # same slot — must not overlap
        art = build([t1, t2])

        def force_both(model, a):
            model.Add(a["scheduled_vars"]["t1"] == 1)
            model.Add(a["scheduled_vars"]["t2"] == 1)

        solver, status = solve(art, force_both)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        e1 = solver.Value(art["end_vars"]["t1"])
        s2 = solver.Value(art["start_vars"]["t2"])
        e2 = solver.Value(art["end_vars"]["t2"])
        s1 = solver.Value(art["start_vars"]["t1"])
        # One must finish before the other starts
        assert e1 <= s2 or e2 <= s1

    def test_travel_time_enforced(self):
        t1 = make_task("t1", 1, 1, travel=30)
        t2 = make_task("t2", 3, 1)
        art = build([t1, t2], lock_ordering=True)

        def force_both(model, a):
            model.Add(a["scheduled_vars"]["t1"] == 1)
            model.Add(a["scheduled_vars"]["t2"] == 1)

        solver, status = solve(art, force_both)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        e1 = solver.Value(art["end_vars"]["t1"])
        s2 = solver.Value(art["start_vars"]["t2"])
        assert s2 >= e1 + 30

    def test_closed_task_forced_drop(self):
        t1 = make_task("t1", 1, 1)
        d = DisruptionEvent(
            type=DisruptionType.CLOSED, task_id="t1",
            detected_at=NOW,
        )
        art = build([t1], disruption=d)
        solver, status = solve(art)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        assert solver.Value(art["scheduled_vars"]["t1"]) == 0

    def test_trivially_infeasible_task_dropped(self):
        t1 = make_task("t1", 1, 1)
        # Force trivial infeasibility via closed disruption
        d = DisruptionEvent(
            type=DisruptionType.CLOSED, task_id="t1",
            detected_at=NOW,
        )
        art = build([t1], disruption=d)
        solver, status = solve(art)
        assert solver.Value(art["scheduled_vars"]["t1"]) == 0

    def test_forward_only_shift(self):
        t1 = make_task("t1", 2, 1)  # original start = +2h = 120min
        art = build([t1])

        def force_schedule(model, a):
            model.Add(a["scheduled_vars"]["t1"] == 1)

        solver, status = solve(art, force_schedule)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        s = solver.Value(art["start_vars"]["t1"])
        assert s >= 120  # cannot start before original time

    def test_same_day_lock_prevents_midnight_spill(self):
        t1 = make_task("t1", 1, 1)
        art = build([t1], lock_to_same_day=True)

        def force_schedule(model, a):
            model.Add(a["scheduled_vars"]["t1"] == 1)

        solver, status = solve(art, force_schedule)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        s = solver.Value(art["start_vars"]["t1"])
        assert s < 1440  # must be same day

    def test_ordering_locked_phase1(self):
        t1 = make_task("t1", 1, 1)
        t2 = make_task("t2", 3, 1)
        art = build([t1, t2], lock_ordering=True)

        def force_both(model, a):
            model.Add(a["scheduled_vars"]["t1"] == 1)
            model.Add(a["scheduled_vars"]["t2"] == 1)
            # Try to force t2 before t1 — should be infeasible given ordering
            # Actually ordering here means t2 >= end(t1) + travel
            # Just verify t2 starts after t1 ends
            pass

        solver, status = solve(art, force_both)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        e1 = solver.Value(art["end_vars"]["t1"])
        s2 = solver.Value(art["start_vars"]["t2"])
        assert s2 >= e1


class TestModelOutput:

    def test_original_start_rels_present(self):
        tasks = [make_task("t1", 1, 1), make_task("t2", 3, 1)]
        art = build(tasks)
        assert "original_start_rels" in art
        assert "t1" in art["original_start_rels"]
        assert "t2" in art["original_start_rels"]

    def test_original_start_rel_correct(self):
        t1 = make_task("t1", 2, 1)  # 2h after NOW = 120 min
        art = build([t1])
        assert art["original_start_rels"]["t1"] == 120
