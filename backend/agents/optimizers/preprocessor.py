# backend/agents/optimizers/preprocessor.py

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from core.models import Task, StateSnapshot
from core.events import DisruptionEvent
from core.enums import TaskStatus, CompletionType, DisruptionType


# ---------------------------------------------------------------------------
# Output Data Structures
# ---------------------------------------------------------------------------

@dataclass
class TaskClassification:
    fixed_tasks: List[Task] = field(default_factory=list)   # COMPLETED + EXPLICIT → immutable
    past_tasks: List[Task] = field(default_factory=list)    # COMPLETED + IMPLICIT → rollback-eligible
    active_task: Optional[Task] = None                      # currently executing
    future_tasks: List[Task] = field(default_factory=list)  # PLANNED → adjustable
    
    @staticmethod
    def _to_rel_minutes_static(dt: datetime, reference: datetime) -> int:
        return int((dt - reference).total_seconds() / 60)


@dataclass
class CascadeResult:
    """
    Output of forward disruption propagation.
    delay_map: task_id → propagated delay in minutes
    affected_ids: ordered list of affected task ids
    cascade_boundary_id: first task NOT affected (absorbed the delay)
    """
    delay_map: Dict[str, int] = field(default_factory=dict)
    affected_ids: List[str] = field(default_factory=list)
    cascade_boundary_id: Optional[str] = None
    total_propagated_delay: int = 0


@dataclass
class VariableBounds:
    """
    Tightened CP-SAT variable bounds per task (relative minutes from current_time).
    lb: earliest possible start
    ub: latest possible start (must finish within time window)
    """
    lb: int   # lower bound on start_var
    ub: int   # upper bound on start_var


@dataclass
class PreprocessorOutput:
    classification: TaskClassification
    cascade: CascadeResult
    bounds: Dict[str, VariableBounds]       # task_id → bounds
    trivially_infeasible: List[str]         # task_ids that cannot be scheduled
    planning_horizon_minutes: int           # H for CP-SAT model


# ---------------------------------------------------------------------------
# Preprocessor
# ---------------------------------------------------------------------------

class DisruptionPreprocessor:
    """
    Phase 0 of the re-optimization engine.

    Responsibilities:
    1. Classify tasks into FIXED / PAST / ACTIVE / FUTURE
    2. Propagate disruption delay forward through task chain
    3. Tighten CP-SAT variable bounds
    4. Identify trivially infeasible tasks (closed, outside window)

    Pure Python. No OR-Tools dependency.
    """

    DEFAULT_HORIZON_MINUTES = 1440  # 24 hours

    def run(
        self,
        snapshot: StateSnapshot,
        disruption: DisruptionEvent,
        planning_horizon_minutes: int = DEFAULT_HORIZON_MINUTES,
    ) -> PreprocessorOutput:

        current_time = snapshot.current_time

        # Step 1: Classify
        classification = self._classify_tasks(snapshot, current_time)

        # Step 2: Cascade propagation
        cascade = self._propagate_cascade(
            classification.future_tasks,
            classification.active_task,
            disruption,
            current_time,
        )

        # Step 3: Tighten bounds
        bounds = self._compute_bounds(
            classification.future_tasks,
            cascade,
            current_time,
            planning_horizon_minutes,
        )

        # Step 4: Identify trivially infeasible
        trivially_infeasible = self._find_infeasible(
            classification.future_tasks,
            bounds,
            disruption,
        )

        return PreprocessorOutput(
            classification=classification,
            cascade=cascade,
            bounds=bounds,
            trivially_infeasible=trivially_infeasible,
            planning_horizon_minutes=planning_horizon_minutes,
        )

    # -----------------------------------------------------------------------
    # Step 1: Task Classification
    # -----------------------------------------------------------------------

    def _classify_tasks(
        self,
        snapshot: StateSnapshot,
        current_time: datetime,
    ) -> TaskClassification:

        fixed, past, future = [], [], []
        active = None

        for task in snapshot.itinerary.tasks:

            # Immutable: explicitly completed
            if (
                task.status == TaskStatus.COMPLETED
                and task.completion == CompletionType.EXPLICIT
            ):
                fixed.append(task)

            # Rollback-eligible: implicitly completed
            elif (
                task.status == TaskStatus.COMPLETED
                and task.completion == CompletionType.IMPLICIT
            ):
                past.append(task)

            # Currently active
            elif task.status == TaskStatus.ACTIVE:
                active = task

            # Missed tasks before current_time → treat as fixed (cannot rewind)
            elif task.status == TaskStatus.MISSED:
                fixed.append(task)

            # Future: planned tasks
            elif task.status == TaskStatus.PLANNED:
                # Guard: if somehow a planned task is in the past, treat as missed
                if task.end_time <= current_time:
                    fixed.append(task)
                else:
                    future.append(task)

        # Ensure sorted by start_time
        future.sort(key=lambda t: t.start_time)

        return TaskClassification(
            fixed_tasks=fixed,
            past_tasks=past,
            active_task=active,
            future_tasks=future,
        )

    # -----------------------------------------------------------------------
    # Step 2: Cascade Propagation
    # -----------------------------------------------------------------------

    def _propagate_cascade(
        self,
        future_tasks: List[Task],
        active_task: Optional[Task],
        disruption: DisruptionEvent,
        current_time: datetime,
    ) -> CascadeResult:

        result = CascadeResult()

        # Determine initial delay
        initial_delay = self._extract_initial_delay(disruption, active_task, current_time)
        result.total_propagated_delay = initial_delay

        if not future_tasks:
            return result

        if initial_delay <= 0:
            return result

        # Find the starting point of cascade
        # If disruption targets a specific task, start from there
        # Otherwise start from the first future task
        start_idx = 0
        if disruption.task_id:
            for idx, task in enumerate(future_tasks):
                if task.id == disruption.task_id:
                    start_idx = idx
                    break

        accumulated_delay = initial_delay

        for i in range(start_idx, len(future_tasks)):
            task = future_tasks[i]

            if accumulated_delay <= 0:
                result.cascade_boundary_id = task.id
                break

            result.delay_map[task.id] = accumulated_delay
            result.affected_ids.append(task.id)

            # Check how much slack exists between this task and the next
            if i + 1 < len(future_tasks):
                next_task = future_tasks[i + 1]
                gap_minutes = int(
                    (next_task.start_time - task.end_time).total_seconds() / 60
                )
                travel = task.travel_time_to_next

                # Slack = gap between tasks minus required travel time
                slack = max(0, gap_minutes - travel)

                # Delay absorbed by slack
                accumulated_delay = max(0, accumulated_delay - slack)
            else:
                # Last task — delay remains but has nowhere to cascade
                accumulated_delay = 0

        return result

    def _extract_initial_delay(
        self,
        disruption: DisruptionEvent,
        active_task: Optional[Task],
        current_time: datetime,
    ) -> int:
        """Determine the initial delay in minutes from the disruption event."""

        if disruption.type == DisruptionType.CLOSED:
            # Closed venue: task will be dropped, no time delay propagated
            return 0

        if disruption.delay_minutes is not None:
            return disruption.delay_minutes

        # Infer delay from active task overrun
        if active_task and disruption.type == DisruptionType.DELAY:
            expected_end = active_task.end_time
            overrun = int((current_time - expected_end).total_seconds() / 60)
            return max(0, overrun)

        # Fallback from metadata
        return int(disruption.metadata.get("delay_minutes", 0))

    # -----------------------------------------------------------------------
    # Step 3: Bound Tightening
    # -----------------------------------------------------------------------

    def _compute_bounds(
        self,
        future_tasks: List[Task],
        cascade: CascadeResult,
        current_time: datetime,
        horizon: int,
    ) -> Dict[str, VariableBounds]:

        bounds = {}

        for task in future_tasks:
            task_id = task.id

            # Convert datetime to relative minutes from current_time
            original_start_rel = self._to_rel_minutes(task.start_time, current_time)
            window_start_rel = self._to_rel_minutes(task.time_window_start, current_time)
            window_end_rel = self._to_rel_minutes(task.time_window_end, current_time)

            # Intersect time window with venue hours if provided
            if task.venue_open and task.venue_close:
                venue_open_rel = self._to_rel_minutes(task.venue_open, current_time)
                venue_close_rel = self._to_rel_minutes(task.venue_close, current_time)
                
                # Effective window = intersection
                window_start_rel = max(window_start_rel, venue_open_rel)
                window_end_rel = min(window_end_rel, venue_close_rel)
                
                # If intersection is empty → trivially infeasible
                if window_start_rel >= window_end_rel:
                    # Will be caught in _find_infeasible()
                    pass

            # Lower bound: max of (current_time=0, window_start, cascaded_delay)
            propagated_delay = cascade.delay_map.get(task_id, 0)
            cascaded_start = original_start_rel + propagated_delay

            lb = max(0, window_start_rel, cascaded_start)

            # Upper bound: task must START early enough to finish within window
            ub = window_end_rel - task.duration_minutes

            # Safety: ub must be >= lb (if not, task is infeasible — caught in step 4)
            ub = max(ub, lb)

            # Cap at horizon
            ub = min(ub, horizon)

            bounds[task_id] = VariableBounds(lb=lb, ub=ub)

        return bounds

    # -----------------------------------------------------------------------
    # Step 4: Trivially Infeasible Detection
    # -----------------------------------------------------------------------

    def _find_infeasible(
        self,
        future_tasks: List[Task],
        bounds: Dict[str, VariableBounds],
        disruption: DisruptionEvent,
    ) -> List[str]:

        infeasible = []

        for task in future_tasks:
            task_id = task.id

            # Closed venue disruption targeting this task
            if (
                disruption.type == DisruptionType.CLOSED
                and disruption.task_id == task_id
            ):
                infeasible.append(task_id)
                continue

            # Window too tight: task cannot fit within its time window
            b = bounds.get(task_id)
            if b and b.lb > b.ub:
                infeasible.append(task_id)
                continue

            # Duration exceeds remaining window
            window_duration = int(
                (task.time_window_end - task.time_window_start).total_seconds() / 60
            )
            if task.duration_minutes > window_duration:
                infeasible.append(task_id)

        return infeasible

    # -----------------------------------------------------------------------
    # Utility
    # -----------------------------------------------------------------------

    @staticmethod
    def _to_rel_minutes(dt: datetime, reference: datetime) -> int:
        return int((dt - reference).total_seconds() / 60)
