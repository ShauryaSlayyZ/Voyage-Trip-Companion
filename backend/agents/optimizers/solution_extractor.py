# backend/agents/optimizers/solution_extractor.py

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from ortools.sat.python import cp_model

from core.models import Task, StateSnapshot
from core.events import DisruptionEvent, ReoptOption, ReoptimizationProposal
from core.enums import ReoptScope


class SolutionExtractor:
    """
    Reads solver output and converts it into a ReoptimizationProposal.

    Responsibilities:
    - Extract start times, dropped tasks, shift amounts
    - Convert relative minutes back to absolute datetime
    - Generate human-readable explanation
    - Rank multiple options by objective value
    - Handle infeasible case cleanly
    """

    def extract(
        self,
        solver: cp_model.CpSolver,
        status: int,
        model_artifacts: Dict[str, Any],
        future_tasks: List[Task],
        snapshot: StateSnapshot,
        disruption: DisruptionEvent,
        scope: ReoptScope,
        option_id: str,
        objective_meta: Dict[str, Any],
    ) -> Optional[ReoptOption]:
        """
        Extract a single ReoptOption from solver result.
        Returns None if no feasible solution found.
        """

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        scheduled_vars  = model_artifacts["scheduled_vars"]
        start_vars      = model_artifacts["start_vars"]
        end_vars        = model_artifacts["end_vars"]
        shift_vars      = model_artifacts["shift_vars"]

        current_time    = snapshot.current_time
        task_map        = {t.id: t for t in future_tasks}

        new_start_times: Dict[str, datetime] = {}
        dropped_task_ids: List[str] = []
        total_shift_minutes: int = 0
        shift_details: List[Dict] = []
        drop_details: List[Dict] = []

        for task in future_tasks:
            tid = task.id

            is_scheduled = bool(solver.Value(scheduled_vars[tid]))

            if is_scheduled:
                # Convert relative minutes back to absolute datetime
                start_rel = solver.Value(start_vars[tid])
                new_start = current_time + timedelta(minutes=start_rel)
                new_start_times[tid] = new_start

                # Shift amount
                shift_min = solver.Value(shift_vars[tid])
                total_shift_minutes += shift_min

                if shift_min > 0:
                    shift_details.append({
                        "task_id": tid,
                        "title": task.title,
                        "shift_minutes": shift_min,
                        "original_start": task.start_time,
                        "new_start": new_start,
                    })
            else:
                dropped_task_ids.append(tid)
                drop_details.append({
                    "task_id": tid,
                    "title": task.title,
                    "priority": task.priority,
                })

        objective_value = solver.ObjectiveValue()

        explanation = self._generate_explanation(
            scope=scope,
            shift_details=shift_details,
            drop_details=drop_details,
            total_shift_minutes=total_shift_minutes,
            disruption=disruption,
            objective_value=objective_value,
        )

        # Rebuild new_future_tasks list for compat with existing system
        new_future_tasks = self._rebuild_tasks(
            future_tasks=future_tasks,
            new_start_times=new_start_times,
            dropped_task_ids=dropped_task_ids,
        )

        return ReoptOption(
            id=option_id,
            scope=scope,
            new_start_times=new_start_times,
            dropped_task_ids=dropped_task_ids,
            total_shift_minutes=total_shift_minutes,
            objective_value=objective_value,
            explanation=explanation,
            new_future_tasks=new_future_tasks,
        )

    def build_infeasible_proposal(
        self,
        disruption: DisruptionEvent,
        future_tasks: List[Task],
    ) -> ReoptimizationProposal:
        """
        Called when all phases fail to find a feasible solution.
        Returns a structured infeasible proposal with reason.
        """
        reason = self._diagnose_infeasibility(future_tasks, disruption)

        return ReoptimizationProposal(
            disruption=disruption,
            options=[],
            needs_confirmation=False,
            infeasible=True,
            infeasibility_reason=reason,
        )

    def build_proposal(
        self,
        options: List[ReoptOption],
        disruption: DisruptionEvent,
        severity_threshold: int = 2,
    ) -> ReoptimizationProposal:
        """
        Assembles final proposal from ranked options.
        Sets needs_confirmation based on number of options
        and disruption severity.
        """
        # Sort by objective value — lower is better
        ranked = sorted(options, key=lambda o: o.objective_value)

        # Confirm if multiple options exist or scope expanded beyond same-slot
        needs_confirmation = (
            len(ranked) > 1
            or any(o.scope != ReoptScope.SAME_SLOT for o in ranked)
        )

        return ReoptimizationProposal(
            disruption=disruption,
            options=ranked,
            needs_confirmation=needs_confirmation,
            infeasible=False,
        )

    # -----------------------------------------------------------------------
    # Explanation Generator
    # -----------------------------------------------------------------------

    def _generate_explanation(
        self,
        scope: ReoptScope,
        shift_details: List[Dict],
        drop_details: List[Dict],
        total_shift_minutes: int,
        disruption: DisruptionEvent,
        objective_value: float,
    ) -> str:

        parts = []

        # Scope label
        scope_label = {
            ReoptScope.SAME_SLOT: "Minor adjustment within original time slots",
            ReoptScope.SAME_DAY:  "Rescheduled within the same day",
            ReoptScope.CROSS_DAY: "Some tasks moved to the next day",
        }.get(scope, "Rescheduled")

        parts.append(scope_label + ".")

        # Shift summary
        if shift_details:
            if total_shift_minutes < 60:
                parts.append(
                    f"{len(shift_details)} task(s) shifted by "
                    f"{total_shift_minutes} min total."
                )
            else:
                hours = total_shift_minutes // 60
                mins = total_shift_minutes % 60
                parts.append(
                    f"{len(shift_details)} task(s) shifted by "
                    f"{hours}h {mins}m total."
                )

        # Drop summary
        if drop_details:
            dropped_titles = [d["title"] for d in drop_details]
            parts.append(
                f"Dropped: {', '.join(dropped_titles)}."
            )
        else:
            parts.append("No tasks dropped.")

        # Score note
        parts.append(f"Disruption score: {int(objective_value)}.")

        return " ".join(parts)

    # -----------------------------------------------------------------------
    # Task Rebuilder
    # -----------------------------------------------------------------------

    def _rebuild_tasks(
        self,
        future_tasks: List[Task],
        new_start_times: Dict[str, datetime],
        dropped_task_ids: List[str],
    ) -> List[Task]:
        """
        Returns updated Task copies with new start/end times.
        Dropped tasks are excluded.
        """
        import copy
        rebuilt = []

        for task in future_tasks:
            if task.id in dropped_task_ids:
                continue

            new_task = copy.copy(task)
            new_start = new_start_times[task.id]
            duration = task.end_time - task.start_time

            new_task.start_time = new_start
            new_task.end_time = new_start + duration

            rebuilt.append(new_task)

        return rebuilt

    # -----------------------------------------------------------------------
    # Infeasibility Diagnosis
    # -----------------------------------------------------------------------

    def _diagnose_infeasibility(
        self,
        future_tasks: List[Task],
        disruption: DisruptionEvent,
    ) -> str:
        """
        Best-effort human-readable explanation of why no solution exists.
        """
        reasons = []

        if not future_tasks:
            return "No future tasks to schedule."

        # Check for tasks with zero-width windows
        tight_tasks = [
            t for t in future_tasks
            if t.duration_minutes >= int(
                (t.time_window_end - t.time_window_start).total_seconds() / 60
            )
        ]
        if tight_tasks:
            titles = [t.title for t in tight_tasks]
            reasons.append(
                f"Tasks with no scheduling flexibility: {', '.join(titles)}."
            )

        # Check disruption type
        from core.enums import DisruptionType
        if disruption.type == DisruptionType.CLOSED and disruption.task_id:
            reasons.append(
                f"Venue closed for task {disruption.task_id}."
            )

        delay = disruption.delay_minutes or 0
        if delay > 0:
            reasons.append(
                f"Delay of {delay} minutes cannot be absorbed "
                f"within remaining time windows."
            )

        if not reasons:
            reasons.append(
                "No feasible schedule exists given current constraints."
            )

        return " ".join(reasons)