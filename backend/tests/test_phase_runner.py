# backend/tests/test_phase_runner.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from datetime import datetime, timedelta

from core.models import Task, Itinerary, StateSnapshot
from core.enums import TaskStatus, DisruptionType, ReoptScope, TaskType
from core.events import DisruptionEvent
from agents.optimizers.preprocessor import DisruptionPreprocessor
from agents.optimizers.phase_runner import PhaseRunner

NOW = datetime(2026, 5, 20, 9, 0)

def make_task(tid, start_h, duration_h, priority=3):
    start = NOW + timedelta(hours=start_h)
    end   = start + timedelta(hours=duration_h)
    return Task(
        id=tid, title=tid, location="L",
        start_time=start, end_time=end,
        priority=priority,
        task_type=TaskType.REST,  # Default
    )

class TestPhaseRunnerIntegration(unittest.TestCase):
    def setUp(self):
        self.runner = PhaseRunner()
        self.preprocessor = DisruptionPreprocessor()

    def _run(self, tasks, disruption):
        snap = StateSnapshot(
            current_time=NOW,
            itinerary=Itinerary(tasks=tasks)
        )
        pre_out = self.preprocessor.run(
            snapshot=snap,
            disruption=disruption,
            planning_horizon_minutes=2880,
        )
        
        return self.runner.run(
            snapshot=snap,
            disruption=disruption,
            preprocessor_output=pre_out,
            transition_matrix={},
        )

    def test_phase1_solves_simple_shift(self):
        # Disruption: 30 min delay
        # Task starts at 10:00 (NOW+1h). Delay pushes to 10:30.
        # Phase 1 allows +60 min shift. Should succeed.
        t1 = make_task("t1", 1, 1)
        d = DisruptionEvent(
            type=DisruptionType.DELAY,
            task_id=None,
            detected_at=NOW,
            delay_minutes=30
        )
        proposal = self._run([t1], d)
        
        self.assertFalse(proposal.infeasible)
        self.assertTrue(len(proposal.options) >= 1)
        # Option 1 should be SAME_SLOT
        self.assertEqual(proposal.options[0].scope, ReoptScope.SAME_SLOT)

    def test_phase2_needed_for_large_shift(self):
        # Disruption: 90 min delay
        # Task starts at 10:00. Pushes to 11:30.
        # Phase 1 limit is +60 min (start <= 11:00). So Phase 1 should fail.
        # Phase 2 (Same Day) has no tight shift limit. Should succeed.
        t1 = make_task("t1", 1, 1)
        d = DisruptionEvent(
            type=DisruptionType.DELAY,
            task_id=None,
            detected_at=NOW,
            delay_minutes=90
        )
        proposal = self._run([t1], d)
        
        self.assertFalse(proposal.infeasible)
        # Should have at least one option
        self.assertTrue(len(proposal.options) >= 1)
        
        # Best option should be SAME_DAY (or SAME_SLOT if my math on bounds is loose, 
        # but 90 > 60, so SAME_SLOT should be invalid/empty if logic holds)
        # Actually PhaseRunner returns ALL found options from successful phases.
        # If Phase 1 fails, it won't be in options.
        
        scopes = [o.scope for o in proposal.options]
        self.assertNotIn(ReoptScope.SAME_SLOT, scopes)
        self.assertIn(ReoptScope.SAME_DAY, scopes)

    def test_phase3_cross_day_needed(self):
        # Task takes 14 hours, starts at 10:00 AM (NOW+1). Ends 24:00 (Midnight).
        # Disruption: 2 hour delay.
        # New Start: 12:00. New End: 02:00 (Next Day).
        # Phase 2 (Same Day) cap is 23:00 (11 PM). So Phase 2 should fail.
        # Phase 3 (Cross Day) should succeed.
        
        # Duration: 14 hours = 840 mins
        t1 = make_task("t1", 1, 14) 
        d = DisruptionEvent(
            type=DisruptionType.DELAY,
            task_id=None,
            detected_at=NOW,
            delay_minutes=120 # +2 hours
        )
        proposal = self._run([t1], d)
        
        self.assertFalse(proposal.infeasible)
        scopes = [o.scope for o in proposal.options]
        
        self.assertNotIn(ReoptScope.SAME_SLOT, scopes)
        self.assertNotIn(ReoptScope.SAME_DAY, scopes)
        self.assertIn(ReoptScope.CROSS_DAY, scopes)

    def test_no_future_tasks_returns_infeasible(self):
        # If no future tasks, PhaseRunner returns infeasible mechanism (or empty proposal?)
        # Logic says: "No future tasks to schedule" -> Infeasible Proposal
        d = DisruptionEvent(
            type=DisruptionType.DELAY, task_id=None,
            detected_at=NOW, delay_minutes=30
        )
        proposal = self._run([], d)
        self.assertTrue(proposal.infeasible)

if __name__ == "__main__":
    unittest.main()
