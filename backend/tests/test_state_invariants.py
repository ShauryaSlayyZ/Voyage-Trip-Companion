# backend/tests/test_state_invariants.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from datetime import datetime, timedelta

from core.models import Task, Itinerary, StateSnapshot
from core.enums import TaskStatus, CompletionType, ReoptScope
from core.events import ReoptOption, DisruptionEvent, DisruptionType
from agents.state_agent import StateAgent


BASE = datetime(2026, 5, 20, 10, 0)


def make_task(tid, start_h, end_h):
    return Task(
        id=tid, title=tid, location="L",
        start_time=BASE + timedelta(hours=start_h),
        end_time=BASE + timedelta(hours=end_h),
    )


def make_option(tasks):
    """Build a minimal valid ReoptOption from a list of tasks."""
    return ReoptOption(
        id="opt_test",
        scope=ReoptScope.SAME_DAY,
        explanation="Test option",
        new_future_tasks=tasks,
        new_start_times={t.id: t.start_time for t in tasks},
        dropped_task_ids=[],
        total_shift_minutes=0,
        objective_value=0.0,
    )


def make_agent(tasks, current_offset_h=0):
    snap = StateSnapshot(
        current_time=BASE + timedelta(hours=current_offset_h),
        itinerary=Itinerary(tasks=tasks),
    )
    return StateAgent(snap)


class TestExplicitImmutability:

    def test_explicit_completed_preserved_after_proposal(self):
        t1 = make_task("t1", 0, 1)
        t2 = make_task("t2", 2, 3)
        agent = make_agent([t1, t2])

        agent.advance_time(30)   # 10:30
        agent.confirm_task("t1")
        agent.advance_time(60)   # 11:30

        t3 = make_task("t3", 2, 3)
        agent.apply_proposal(make_option([t3]))

        final = agent.get_state_snapshot()
        ids = [t.id for t in final.itinerary.tasks]
        assert "t1" in ids
        assert "t3" in ids
        assert "t2" not in ids

        t1_final = next(t for t in final.itinerary.tasks if t.id == "t1")
        assert t1_final.status == TaskStatus.COMPLETED
        assert t1_final.completion == CompletionType.EXPLICIT

    def test_explicit_start_time_unchanged(self):
        t1 = make_task("t1", 0, 1)
        agent = make_agent([t1])
        agent.advance_time(30)
        agent.confirm_task("t1")

        original_start = t1.start_time
        t2 = make_task("t2", 2, 3)
        agent.apply_proposal(make_option([t2]))

        final = agent.get_state_snapshot()
        t1_final = next(t for t in final.itinerary.tasks if t.id == "t1")
        assert t1_final.start_time == original_start


class TestImplicitRollback:

    def test_missed_task_rolls_back_to_planned(self):
        t1 = make_task("t1", 0, 1)
        agent = make_agent([t1])
        agent.advance_time(120)  # past end

        s = agent.get_state_snapshot()
        assert s.itinerary.tasks[0].status == TaskStatus.MISSED

        agent.rollback_implicit("t1")

        s2 = agent.get_state_snapshot()
        assert s2.itinerary.tasks[0].status == TaskStatus.PLANNED
        assert s2.itinerary.tasks[0].completion == CompletionType.NONE

    def test_explicit_task_cannot_be_rolled_back(self):
        t1 = make_task("t1", 0, 1)
        agent = make_agent([t1])
        agent.advance_time(30)
        agent.confirm_task("t1")

        with pytest.raises(Exception):
            agent.rollback_implicit("t1")


class TestTimeProgression:

    def test_current_time_advances(self):
        agent = make_agent([])
        before = agent.get_state_snapshot().current_time
        agent.advance_time(60)
        after = agent.get_state_snapshot().current_time
        assert after == before + timedelta(minutes=60)

    def test_task_becomes_missed_after_end_time(self):
        t1 = make_task("t1", 0, 1)  # ends at 11:00
        agent = make_agent([t1])
        agent.advance_time(90)  # 11:30 — past end

        s = agent.get_state_snapshot()
        assert s.itinerary.tasks[0].status in (
            TaskStatus.MISSED, TaskStatus.COMPLETED
        )

    def test_no_time_rewind(self):
        agent = make_agent([])
        agent.advance_time(60)
        t = agent.get_state_snapshot().current_time

        # Advancing by 0 should not go backward
        agent.advance_time(0)
        assert agent.get_state_snapshot().current_time >= t


class TestProposalApplication:

    def test_future_tasks_replaced(self):
        t1 = make_task("t1", 0, 1)
        t2 = make_task("t2", 2, 3)
        agent = make_agent([t1, t2])

        t3 = make_task("t3", 2, 3)
        agent.apply_proposal(make_option([t3]))

        final = agent.get_state_snapshot()
        ids = [t.id for t in final.itinerary.tasks]
        assert "t3" in ids

    def test_empty_proposal_clears_future(self):
        t1 = make_task("t1", 1, 2)
        agent = make_agent([t1])
        agent.apply_proposal(make_option([]))

        final = agent.get_state_snapshot()
        planned = [t for t in final.itinerary.tasks
                   if t.status == TaskStatus.PLANNED]
        assert len(planned) == 0