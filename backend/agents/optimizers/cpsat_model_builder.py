# backend/agents/optimizers/cpsat_model_builder.py

from typing import List, Dict, Tuple, Optional, Any
from datetime import datetime
from ortools.sat.python import cp_model

from core.models import Task, StateSnapshot
from core.events import DisruptionEvent
from core.enums import DisruptionType
from agents.optimizers.preprocessor import PreprocessorOutput


class CPSATModelBuilder:
    """
    Builds the CP-SAT constraint model for itinerary re-optimization.

    - Order-preserving (Phase 1 default)
    - Optional interval pattern for droppable tasks
    - Tightened bounds from PreprocessorOutput
    - O(N) constraints via chain ordering + AddNoOverlap
    """

    def build_cpsat_model(
        self,
        snapshot: StateSnapshot,
        future_tasks: List[Task],
        locked_tasks: List[Task],
        disruption: Optional[DisruptionEvent],
        preprocessor_output: PreprocessorOutput,
        transition_matrix: Dict[Tuple[str, str], int],
        lock_ordering: bool = True,        # Phase 1: True, Phase 2: False
        lock_to_same_day: bool = True,     # Phase 1&2: True, Phase 3: False
        planning_horizon_minutes: int = 1440,
    ) -> Dict[str, Any]:

        model = cp_model.CpModel()
        H = planning_horizon_minutes
        DAY_BOUNDARY = 1440  # minutes in a day

        start_vars = {}
        end_vars = {}
        interval_vars = {}
        scheduled_vars = {}
        shift_vars = {}
        cross_day_vars = {}

        # -----------------------------------------------------------------------
        # Locked task boundary (from explicitly completed / fixed tasks)
        # -----------------------------------------------------------------------
        last_locked_end_rel = 0
        locked_to_first_travel = 0

        if locked_tasks:
            last_locked = max(locked_tasks, key=lambda t: t.end_time)
            last_locked_end_rel = int(
                (last_locked.end_time - snapshot.current_time).total_seconds() / 60
            )

            if future_tasks:
                locked_to_first_travel = transition_matrix.get(
                    (last_locked.id, future_tasks[0].id), 0
                )

        # -----------------------------------------------------------------------
        # Build variables per future task
        # -----------------------------------------------------------------------
        trivially_infeasible = set(preprocessor_output.trivially_infeasible)

        for task in future_tasks:
            tid = task.id
            duration = task.duration_minutes

            # Tightened bounds from preprocessor
            b = preprocessor_output.bounds[tid]
            lb = b.lb
            ub = b.ub



            # --- Core decision variables ---
            start = model.NewIntVar(lb, H, f"start_{tid}")
            end = model.NewIntVar(lb, H, f"end_{tid}")
            scheduled = model.NewBoolVar(f"scheduled_{tid}")

            # --- Shift variable (forward-only deviation from original start) ---
            # shift = start - original_start (always >= 0 since start >= original_start)
            original_start_rel = lb - preprocessor_output.cascade.delay_map.get(tid, 0)
            original_start_rel = max(0, original_start_rel)
            shift = model.NewIntVar(0, H, f"shift_{tid}")

            # --- Optional interval (native CP-SAT pattern) ---
            interval = model.NewOptionalIntervalVar(
                start, duration, end, scheduled, f"interval_{tid}"
            )

            # --- Cross-day indicator ---
            cross_day = model.NewBoolVar(f"cross_day_{tid}")

            # -----------------------------------------------------------------------
            # Constraints
            # -----------------------------------------------------------------------

            # 1. Force drop if trivially infeasible
            if tid in trivially_infeasible:
                model.Add(scheduled == 0)

            # 2. Duration: enforced by OptionalIntervalVar natively
            #    end = start + duration when scheduled
            #    But we also set unscheduled state explicitly:
            model.Add(start == 0).OnlyEnforceIf(scheduled.Not())
            model.Add(end == 0).OnlyEnforceIf(scheduled.Not())

            # 3. Forward-only: start >= original_start_rel when scheduled
            model.Add(start >= original_start_rel).OnlyEnforceIf(scheduled)

            # 4. Time window: must start within window
            model.Add(start >= lb).OnlyEnforceIf(scheduled)
            model.Add(end <= b.ub + duration).OnlyEnforceIf(scheduled)

            # 5. Shift = start - original_start (simplified, forward-only)
            model.Add(shift == start - original_start_rel).OnlyEnforceIf(scheduled)
            model.Add(shift == 0).OnlyEnforceIf(scheduled.Not())

            # 6. Cross-day: correctly reified in both directions
            #    cross_day=1 ↔ start >= DAY_BOUNDARY (when scheduled)
            model.Add(start >= DAY_BOUNDARY).OnlyEnforceIf([cross_day, scheduled])
            model.Add(start < DAY_BOUNDARY).OnlyEnforceIf([cross_day.Not(), scheduled])
            model.Add(cross_day == 0).OnlyEnforceIf(scheduled.Not())

            # 7. Same-day lock (Phase 1 & 2)
            if lock_to_same_day:
                model.Add(end <= DAY_BOUNDARY).OnlyEnforceIf(scheduled)

            # Store
            start_vars[tid] = start
            end_vars[tid] = end
            interval_vars[tid] = interval
            scheduled_vars[tid] = scheduled
            shift_vars[tid] = shift
            cross_day_vars[tid] = cross_day

        # -----------------------------------------------------------------------
        # Global No-Overlap (handles all optional intervals correctly)
        # -----------------------------------------------------------------------
        model.AddNoOverlap(list(interval_vars.values()))

        # -----------------------------------------------------------------------
        # Chain Order + Travel Constraints
        # Only enforce between adjacent pairs in original order
        # -----------------------------------------------------------------------
        if lock_ordering:
            for i in range(len(future_tasks) - 1):
                t_i = future_tasks[i]
                t_j = future_tasks[i + 1]
                travel = transition_matrix.get((t_i.id, t_j.id), 0)

                # If both scheduled: j must start after i ends + travel
                model.Add(
                    start_vars[t_j.id] >= end_vars[t_i.id] + travel
                ).OnlyEnforceIf([
                    scheduled_vars[t_i.id],
                    scheduled_vars[t_j.id],
                ])

        # -----------------------------------------------------------------------
        # Locked Boundary Constraint
        # First future task must start after last locked task ends + travel
        # -----------------------------------------------------------------------
        if future_tasks and locked_tasks:
            first_id = future_tasks[0].id
            model.Add(
                start_vars[first_id] >= last_locked_end_rel + locked_to_first_travel
            ).OnlyEnforceIf(scheduled_vars[first_id])

        # -----------------------------------------------------------------------
        # Disruption-Specific Hard Constraints
        # -----------------------------------------------------------------------
        if disruption:
            if disruption.type == DisruptionType.CLOSED:
                affected = disruption.task_id
                if affected and affected in scheduled_vars:
                    model.Add(scheduled_vars[affected] == 0)

        return {
            "model": model,
            "start_vars": start_vars,
            "end_vars": end_vars,
            "interval_vars": interval_vars,
            "scheduled_vars": scheduled_vars,
            "shift_vars": shift_vars,
            "cross_day_vars": cross_day_vars,
            "original_start_rels": {
                tid: max(0, preprocessor_output.bounds[tid].lb -
                         preprocessor_output.cascade.delay_map.get(tid, 0))
                for tid in start_vars
            },
        }
