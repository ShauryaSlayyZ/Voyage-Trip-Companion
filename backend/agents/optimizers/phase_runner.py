# backend/agents/optimizers/phase_runner.py

import copy
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from core.models import Task, StateSnapshot
from core.events import DisruptionEvent, ReoptOption, ReoptimizationProposal
from core.enums import ReoptScope

from agents.optimizers.preprocessor import (
    DisruptionPreprocessor, PreprocessorOutput, VariableBounds
)
from agents.optimizers.cpsat_model_builder import CPSATModelBuilder
from agents.optimizers.objective import (
    ObjectiveBuilder, ObjectiveWeights, DEFAULT_WEIGHTS, validate_hierarchy
)
from agents.optimizers.solution_extractor import SolutionExtractor


# ---------------------------------------------------------------------------
# Phase Configuration
# ---------------------------------------------------------------------------

@dataclass
class PhaseConfig:
    name: str
    scope: ReoptScope
    lock_ordering: bool
    lock_to_same_day: bool
    time_limit_seconds: float
    drop_low_priority: bool


PHASE_CONFIGS = [
    PhaseConfig(
        name="Phase1_SameSlot",
        scope=ReoptScope.SAME_SLOT,
        lock_ordering=True,
        lock_to_same_day=True,
        time_limit_seconds=2.0,
        drop_low_priority=False,
    ),
    PhaseConfig(
        name="Phase2_SameDay",
        scope=ReoptScope.SAME_DAY,
        lock_ordering=False,
        lock_to_same_day=True,
        time_limit_seconds=5.0,
        drop_low_priority=False,
    ),
    PhaseConfig(
        name="Phase3_CrossDay",
        scope=ReoptScope.CROSS_DAY,
        lock_ordering=False,
        lock_to_same_day=False,
        time_limit_seconds=10.0,
        drop_low_priority=True,
    ),
]

# Priority thresholds
MUST_PRESERVE = 4   # priority >= 4 → never drop
ATTEMPT_SAVE  = 3   # priority == 3 → try to save, drop if needed
DROPPABLE     = 2   # priority <= 2 → free to drop in Phase 3


# ---------------------------------------------------------------------------
# Phase Runner
# ---------------------------------------------------------------------------

class PhaseRunner:
    """
    Executes multi-phase CP-SAT solving strategy.

    Phase 1: Same-slot repair   — tight bounds, locked order, 2s
    Phase 2: Same-day relaxed   — free order, same day, 5s
    Phase 3: Cross-day          — priority-driven drops, venue hours, 10s

    Returns up to 2 candidate options ranked by objective value.
    Never mutates state.
    """

    END_OF_DAY_MINUTES  = 23 * 60           # 11 PM relative to day start
    NEXT_DAY_START      = 24 * 60 + 7 * 60  # next day 7 AM in relative minutes
    NEXT_DAY_END        = 24 * 60 + 22 * 60 # next day 10 PM in relative minutes

    def __init__(self):
        self.builder   = CPSATModelBuilder()
        self.objective = ObjectiveBuilder()
        self.extractor = SolutionExtractor()

    def run(
        self,
        snapshot: StateSnapshot,
        disruption: DisruptionEvent,
        preprocessor_output: PreprocessorOutput,
        transition_matrix: Dict[Tuple[str, str], int],
        weights: ObjectiveWeights = DEFAULT_WEIGHTS,
    ) -> ReoptimizationProposal:

        validate_hierarchy(weights)

        future_tasks = preprocessor_output.classification.future_tasks
        locked_tasks = preprocessor_output.classification.fixed_tasks

        if not future_tasks:
            print("[PhaseRunner] ⚠️ No future tasks to schedule.")
            return self.extractor.build_infeasible_proposal(
                disruption=disruption,
                future_tasks=[],
            )

        candidates: List[ReoptOption] = []
        last_solution: Optional[ReoptOption] = None

        for phase in PHASE_CONFIGS:
            print(f"[PhaseRunner] 🔄 Running {phase.name}...")

            # Compute phase-specific bounds
            phase_bounds = self._compute_phase_bounds(
                preprocessor_output=preprocessor_output,
                future_tasks=future_tasks,
                phase=phase,
                snapshot=snapshot,
            )

            # Compute phase-specific weights
            phase_weights = self._compute_phase_weights(
                base_weights=weights,
                phase=phase,
            )

            # Build model with phase bounds
            artifacts = self.builder.build_cpsat_model(
                snapshot=snapshot,
                future_tasks=future_tasks,
                locked_tasks=locked_tasks,
                disruption=disruption,
                preprocessor_output=self._with_bounds(
                    preprocessor_output, phase_bounds
                ),
                transition_matrix=transition_matrix,
                lock_ordering=phase.lock_ordering,
                lock_to_same_day=phase.lock_to_same_day,
                planning_horizon_minutes=preprocessor_output.planning_horizon_minutes,
            )

            model = artifacts["model"]

            # Build objective
            obj_meta = self.objective.build_objective(
                model=model,
                model_artifacts=artifacts,
                future_tasks=future_tasks,
                disruption=disruption,
                weights=phase_weights,
            )

            # Warm start from previous phase if available
            if last_solution:
                self._inject_hints(
                    model=model,
                    artifacts=artifacts,
                    previous=last_solution,
                    future_tasks=future_tasks,
                    snapshot=snapshot,
                )

            # Configure and run solver
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds   = phase.time_limit_seconds
            solver.parameters.num_search_workers    = 4
            solver.parameters.log_search_progress   = False
            solver.parameters.cp_model_presolve     = True

            status = solver.Solve(model)

            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                print(
                    f"[PhaseRunner] ✅ {phase.name}: {solver.StatusName(status)} "
                    f"score={int(solver.ObjectiveValue())}"
                )

                option = self.extractor.extract(
                    solver=solver,
                    status=status,
                    model_artifacts=artifacts,
                    future_tasks=future_tasks,
                    snapshot=snapshot,
                    disruption=disruption,
                    scope=phase.scope,
                    option_id=f"opt_{phase.scope.value.lower()}",
                    objective_meta=obj_meta,
                )

                if option:
                    candidates.append(option)
                    last_solution = option

                    # Phase 1 success → still run Phase 2 for alternative option
                    # Phase 2 success → stop here, no need for cross-day
                    if phase.scope == ReoptScope.SAME_DAY:
                        print("[PhaseRunner] ✅ Same-day solution found. Stopping.")
                        break

            else:
                print(
                    f"[PhaseRunner] ⚠️ {phase.name}: No solution "
                    f"({solver.StatusName(status)})"
                )

        if not candidates:
            print("[PhaseRunner] ❌ All phases exhausted. No feasible solution.")
            return self.extractor.build_infeasible_proposal(
                disruption=disruption,
                future_tasks=future_tasks,
            )

        return self.extractor.build_proposal(
            options=candidates,
            disruption=disruption,
        )

    # -----------------------------------------------------------------------
    # Phase-Specific Bound Computation
    # -----------------------------------------------------------------------

    def _compute_phase_bounds(
        self,
        preprocessor_output: PreprocessorOutput,
        future_tasks: List[Task],
        phase: PhaseConfig,
        snapshot: StateSnapshot,
    ) -> Dict[str, VariableBounds]:

        bounds = dict(preprocessor_output.bounds)
        current_time = snapshot.current_time
        current_minutes = current_time.hour * 60 + current_time.minute

        for task in future_tasks:
            tid = task.id
            b   = bounds[tid]

            if phase.scope == ReoptScope.SAME_SLOT:
                # Limit shift to +60 min from ORIGINAL start (before disruption)
                # This ensures large delays force a transition to Phase 2 (Same Day)
                delay = preprocessor_output.cascade.delay_map.get(tid, 0)
                original_start_rel = max(0, b.lb - delay)
                
                new_ub = min(original_start_rel + 60, b.ub)
                bounds[tid] = VariableBounds(lb=b.lb, ub=new_ub)

            elif phase.scope == ReoptScope.SAME_DAY:
                # Cap at end-of-day so tasks don't spill past 11 PM
                minutes_until_eod = self.END_OF_DAY_MINUTES - current_minutes
                eod_ub = max(0, minutes_until_eod - task.duration_minutes)
                new_ub = min(b.ub, eod_ub)
                bounds[tid] = VariableBounds(lb=b.lb, ub=new_ub)

            elif phase.scope == ReoptScope.CROSS_DAY:
                minutes_until_eod = self.END_OF_DAY_MINUTES - current_minutes
                eod_ub = max(0, minutes_until_eod - task.duration_minutes)

                if b.lb > eod_ub:
                    # Task cannot fit today → open next-day window
                    next_lb = self.NEXT_DAY_START
                    next_ub = self.NEXT_DAY_END - task.duration_minutes

                    # Intersect with venue hours if present
                    if task.venue_open and task.venue_close:
                        venue_open_rel = int(
                            (task.venue_open - current_time).total_seconds() / 60
                        ) + 1440  # offset to next day
                        venue_close_rel = int(
                            (task.venue_close - current_time).total_seconds() / 60
                        ) + 1440

                        next_lb = max(next_lb, venue_open_rel)
                        next_ub = min(next_ub, venue_close_rel - task.duration_minutes)

                    next_ub = max(next_ub, next_lb)
                    bounds[tid] = VariableBounds(lb=next_lb, ub=next_ub)

                # else: task can still fit today, keep existing bounds

        return bounds

    # -----------------------------------------------------------------------
    # Phase-Specific Weight Adjustment
    # -----------------------------------------------------------------------

    def _compute_phase_weights(
        self,
        base_weights: ObjectiveWeights,
        phase: PhaseConfig,
    ) -> ObjectiveWeights:

        w = copy.copy(base_weights)

        if phase.scope == ReoptScope.CROSS_DAY and phase.drop_low_priority:
            # Low-priority tasks become free to drop
            # High-priority tasks still protected by drop_priority_mul × priority
            w.drop_base  = 500
            w.cross_day  = 800

        return w

    # -----------------------------------------------------------------------
    # Warm Start Hint Injection
    # -----------------------------------------------------------------------

    def _inject_hints(
        self,
        model: cp_model.CpModel,
        artifacts: Dict,
        previous: ReoptOption,
        future_tasks: List[Task],
        snapshot: StateSnapshot,
    ) -> None:

        current_time = snapshot.current_time

        for task in future_tasks:
            tid = task.id

            if tid not in artifacts["start_vars"]:
                continue

            if tid in previous.new_start_times:
                hint_dt  = previous.new_start_times[tid]
                hint_rel = int((hint_dt - current_time).total_seconds() / 60)
                hint_rel = max(0, hint_rel)
                model.AddHint(artifacts["start_vars"][tid], hint_rel)
                model.AddHint(artifacts["scheduled_vars"][tid], 1)
            else:
                # Was dropped in previous phase
                model.AddHint(artifacts["scheduled_vars"][tid], 0)

    # -----------------------------------------------------------------------
    # Utility: Swap Bounds in PreprocessorOutput
    # -----------------------------------------------------------------------

    @staticmethod
    def _with_bounds(
        original: PreprocessorOutput,
        new_bounds: Dict[str, VariableBounds],
    ) -> PreprocessorOutput:

        return PreprocessorOutput(
            classification=original.classification,
            cascade=original.cascade,
            bounds=new_bounds,
            trivially_infeasible=original.trivially_infeasible,
            planning_horizon_minutes=original.planning_horizon_minutes,
        )