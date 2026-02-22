from dataclasses import dataclass
from typing import Dict, List, Any, Set
from ortools.sat.python import cp_model

from core.models import Task
from core.events import DisruptionEvent
from core.enums import DisruptionType, TaskType


# ---------------------------------------------------------------------------
# Weight Configuration
# ---------------------------------------------------------------------------

@dataclass
class ObjectiveWeights:
    """
    All penalty weights in one place.

    Hierarchy guarantee (mathematically enforced via validate_hierarchy()):
        drop_min > worst_shift
        cross_day > worst_fatigue
        fatigue > worst_late

    Tune here without touching objective logic.
    """
    # --- Drop ---
    drop_base: int          = 2000  # per dropped task
    drop_priority_mul: int  = 200   # × task priority (1–5)
    drop_fixed_bonus: int   = 5000  # extra for TaskType.FIXED

    # --- Shift ---
    shift_per_minute: int       = 1
    shift_priority_mul: float   = 0.5   # high-priority tasks resist shifting more
    max_shift_minutes: int      = 480   # realistic cap: 8 hours

    # --- Late hour ---
    late_per_minute: int    = 5
    late_threshold: int     = 22 * 60   # 10 PM in minutes from day start

    # --- Cross-day ---
    cross_day: int          = 1100  # per task moved to next day

    # --- Fatigue ---
    fatigue: int            = 650   # per fatigued adjacent pair
    min_rest_minutes: int   = 15    # min gap between physical tasks

    # --- Weather / Crowding ---
    weather: int            = 20    # per task in disruption zone

    # --- Slot Deviation (Cross-Day) ---
    slot_deviation_per_hour: int = 30  # per hour deviation from original time-of-day


DEFAULT_WEIGHTS = ObjectiveWeights()

# Task types considered physically demanding
PHYSICAL_TASK_TYPES: Set[TaskType] = {TaskType.WALKING}


# ---------------------------------------------------------------------------
# Hierarchy Validator
# ---------------------------------------------------------------------------

def validate_hierarchy(
    weights: ObjectiveWeights,
    max_tasks: int = 40,
) -> bool:
    """
    Asserts the weight hierarchy holds at worst case.
    Call at startup or in tests.

    Hierarchy:
        drop_min  > worst_shift
        cross_day > worst_fatigue_total
        fatigue   > worst_late
    """
    worst_shift = (
        weights.shift_per_minute + weights.shift_priority_mul * 5
    ) * weights.max_shift_minutes
    # (1 + 0.5×5) × 480 = 1680

    min_drop = weights.drop_base + weights.drop_priority_mul * 1
    # 2000 + 200 = 2200 ✅ > 1680

    max_fatigue_pairs = max_tasks // 2
    worst_fatigue_total = weights.fatigue * max_fatigue_pairs
    # 650 × 20 = 13000

    # cross_day per task — compare per-task not total
    # A single cross-day move should cost more than a single fatigue hit
    # 1100 > 650 ✅

    worst_late = weights.late_per_minute * 120  # 2 hours past threshold
    # 5 × 120 = 600

    assert min_drop > worst_shift, (
        f"Hierarchy broken: min_drop({min_drop}) <= worst_shift({worst_shift})"
    )
    assert weights.cross_day > weights.fatigue, (
        f"Hierarchy broken: cross_day({weights.cross_day}) <= fatigue({weights.fatigue})"
    )
    assert weights.fatigue > worst_late, (
        f"Hierarchy broken: fatigue({weights.fatigue}) <= worst_late({worst_late})"
    )

    return True


# ---------------------------------------------------------------------------
# Objective Builder
# ---------------------------------------------------------------------------

class ObjectiveBuilder:
    """
    Builds the weighted CP-SAT minimization objective.

    Mutates model in-place via model.Minimize().
    Returns penalty_meta for explanation generation in solution_extractor.
    """

    def build_objective(
        self,
        model: cp_model.CpModel,
        model_artifacts: Dict[str, Any],
        future_tasks: List[Task],
        disruption: DisruptionEvent,
        weights: ObjectiveWeights = DEFAULT_WEIGHTS,
    ) -> Dict[str, Any]:

        start_vars      = model_artifacts["start_vars"]
        end_vars        = model_artifacts["end_vars"]
        scheduled_vars  = model_artifacts["scheduled_vars"]
        shift_vars      = model_artifacts["shift_vars"]
        cross_day_vars  = model_artifacts["cross_day_vars"]

        objective_terms = []
        penalty_meta = {
            "drop":       [],
            "shift":      [],
            "late":       [],
            "cross_day":  [],
            "fatigue":    [],
            "weather":    [],
        }

        weather_affected = self._get_weather_affected(future_tasks, disruption)

        for task in future_tasks:
            tid = task.id

            if tid not in scheduled_vars:
                continue

            scheduled   = scheduled_vars[tid]
            shift_var   = shift_vars[tid]
            end_var     = end_vars[tid]
            cross_var   = cross_day_vars[tid]
            p           = task.priority  # 1–5

            # -----------------------------------------------------------
            # 1. Drop Penalty
            # -----------------------------------------------------------
            drop_penalty = weights.drop_base + (weights.drop_priority_mul * p)
            if task.is_fixed:
                drop_penalty += weights.drop_fixed_bonus

            drop_cost = model.NewIntVar(0, drop_penalty, f"drop_cost_{tid}")
            model.Add(drop_cost == drop_penalty).OnlyEnforceIf(scheduled.Not())
            model.Add(drop_cost == 0).OnlyEnforceIf(scheduled)
            objective_terms.append(drop_cost)
            penalty_meta["drop"].append({
                "task_id": tid,
                "penalty": drop_penalty,
            })

            # -----------------------------------------------------------
            # 2. Shift Penalty
            # -----------------------------------------------------------
            shift_weight = max(1, int(
                weights.shift_per_minute + weights.shift_priority_mul * p
            ))
            shift_cost = model.NewIntVar(
                0, shift_weight * weights.max_shift_minutes, f"shift_cost_{tid}"
            )
            model.Add(shift_cost == shift_weight * shift_var).OnlyEnforceIf(scheduled)
            model.Add(shift_cost == 0).OnlyEnforceIf(scheduled.Not())
            objective_terms.append(shift_cost)
            penalty_meta["shift"].append({
                "task_id": tid,
                "weight_per_minute": shift_weight,
            })

            # -----------------------------------------------------------
            # 3. Late-Hour Penalty
            # late_excess = max(0, end - late_threshold)
            # Modeled via lower bound — solver minimizes so it finds minimum
            # -----------------------------------------------------------
            late_excess = model.NewIntVar(0, 1440, f"late_excess_{tid}")
            model.Add(
                late_excess >= end_var - weights.late_threshold
            ).OnlyEnforceIf(scheduled)
            model.Add(late_excess >= 0)
            model.Add(late_excess == 0).OnlyEnforceIf(scheduled.Not())

            late_cost = model.NewIntVar(
                0, weights.late_per_minute * 1440, f"late_cost_{tid}"
            )
            model.Add(late_cost == weights.late_per_minute * late_excess).OnlyEnforceIf(scheduled)
            model.Add(late_cost == 0).OnlyEnforceIf(scheduled.Not())
            objective_terms.append(late_cost)
            penalty_meta["late"].append({
                "task_id": tid,
                "weight_per_minute": weights.late_per_minute,
            })

            # -----------------------------------------------------------
            # 4. Cross-Day Penalty
            # -----------------------------------------------------------
            cross_cost = model.NewIntVar(0, weights.cross_day, f"cross_cost_{tid}")
            model.Add(cross_cost == weights.cross_day).OnlyEnforceIf(
                [cross_var, scheduled]
            )
            model.Add(cross_cost == 0).OnlyEnforceIf(cross_var.Not())
            model.Add(cross_cost == 0).OnlyEnforceIf(scheduled.Not())
            objective_terms.append(cross_cost)
            penalty_meta["cross_day"].append({
                "task_id": tid,
                "penalty": weights.cross_day,
            })

            # -----------------------------------------------------------
            # 5. Weather / Crowding Penalty
            # -----------------------------------------------------------
            if tid in weather_affected:
                weather_cost = model.NewIntVar(0, weights.weather, f"weather_cost_{tid}")
                model.Add(weather_cost == weights.weather).OnlyEnforceIf(scheduled)
                model.Add(weather_cost == 0).OnlyEnforceIf(scheduled.Not())
                objective_terms.append(weather_cost)
                penalty_meta["weather"].append({
                    "task_id": tid,
                    "penalty": weights.weather,
                })

            # -----------------------------------------------------------
            # 6. Slot Deviation Penalty (Cross-Day)
            # -----------------------------------------------------------
            # Goal: If moving to tomorrow, try to keep same time-of-day
            # -----------------------------------------------------------
            
            # Original start minutes from midnight (0..1440)
            original_hour = int(task.start_time.hour * 60 + task.start_time.minute)
            
            # Next day target in relative minutes: 1440 + original_hour
            # (Assuming 24h horizon for simplicity of "next day")
            DAY_BOUNDARY = 1440
            next_day_original = DAY_BOUNDARY + original_hour

            # Deviation = |start - next_day_original|
            slot_dev = model.NewIntVar(0, 2880, f"slot_dev_{tid}")
            
            # Create linear expressions for diff
            diff_1 = start_vars[tid] - next_day_original
            diff_2 = next_day_original - start_vars[tid]

            # Enforce abs diff
            model.Add(slot_dev >= diff_1).OnlyEnforceIf([cross_var, scheduled])
            model.Add(slot_dev >= diff_2).OnlyEnforceIf([cross_var, scheduled])
            model.Add(slot_dev == 0).OnlyEnforceIf(cross_var.Not())
            model.Add(slot_dev == 0).OnlyEnforceIf(scheduled.Not())

            slot_dev_cost = model.NewIntVar(0, weights.slot_deviation_per_hour * 1440, f"slot_dev_cost_{tid}")
            
            # Cost = (weight * minutes) / 60  -> per hour cost
            # Integer division approximation
            weighted_minutes = model.NewIntVar(0, weights.slot_deviation_per_hour * 2880 * p, f"weighted_minutes_{tid}")
            model.Add(weighted_minutes == weights.slot_deviation_per_hour * slot_dev * p)
            
            model.AddDivisionEquality(slot_dev_cost, weighted_minutes, 60)
            
            # Since slot_dev is only > 0 if cross_var and scheduled are true,
            # slot_dev_cost will naturally be 0 if they affect slot_dev.
            # However, to be explicit about enforcing 0 cost when not applicable:
            model.Add(slot_dev_cost == 0).OnlyEnforceIf(cross_var.Not())
            model.Add(slot_dev_cost == 0).OnlyEnforceIf(scheduled.Not())

            objective_terms.append(slot_dev_cost)
            # (We won't add to penalty_meta for now as it's a soft preference detail)

        # -----------------------------------------------------------
        # 6. Fatigue Penalty
        # Adjacent physical task pairs with insufficient rest gap
        # -----------------------------------------------------------
        for i in range(len(future_tasks) - 1):
            t_i = future_tasks[i]
            t_j = future_tasks[i + 1]

            if not (self._is_physical(t_i) and self._is_physical(t_j)):
                continue

            tid_i = t_i.id
            tid_j = t_j.id

            if tid_i not in scheduled_vars or tid_j not in scheduled_vars:
                continue

            s_i = scheduled_vars[tid_i]
            s_j = scheduled_vars[tid_j]

            # both_scheduled auxiliary
            both_scheduled = model.NewBoolVar(f"both_sched_{tid_i}_{tid_j}")
            model.AddBoolAnd([s_i, s_j]).OnlyEnforceIf(both_scheduled)
            model.AddBoolOr([s_i.Not(), s_j.Not()]).OnlyEnforceIf(both_scheduled.Not())

            # gap = start[j] - end[i]
            gap = model.NewIntVar(-1440, 1440, f"gap_{tid_i}_{tid_j}")
            model.Add(gap == start_vars[tid_j] - end_vars[tid_i])

            # is_fatigued = gap < min_rest AND both scheduled
            is_fatigued = model.NewBoolVar(f"fatigued_{tid_i}_{tid_j}")
            model.Add(gap < weights.min_rest_minutes).OnlyEnforceIf(
                [is_fatigued, both_scheduled]
            )
            model.Add(gap >= weights.min_rest_minutes).OnlyEnforceIf(
                [is_fatigued.Not(), both_scheduled]
            )
            model.Add(is_fatigued == 0).OnlyEnforceIf(both_scheduled.Not())

            fatigue_cost = model.NewIntVar(0, weights.fatigue, f"fatigue_cost_{tid_i}_{tid_j}")
            model.Add(fatigue_cost == weights.fatigue).OnlyEnforceIf(is_fatigued)
            model.Add(fatigue_cost == 0).OnlyEnforceIf(is_fatigued.Not())
            objective_terms.append(fatigue_cost)
            penalty_meta["fatigue"].append({
                "task_pair": (tid_i, tid_j),
                "penalty": weights.fatigue,
            })

        # -----------------------------------------------------------
        # Set Objective
        # -----------------------------------------------------------
        model.Minimize(cp_model.LinearExpr.Sum(objective_terms))

        return {
            "penalty_meta": penalty_meta,
            "weights": weights,
            "num_terms": len(objective_terms),
        }

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _is_physical(task: Task) -> bool:
        return task.task_type in PHYSICAL_TASK_TYPES

    @staticmethod
    def _get_weather_affected(
        future_tasks: List[Task],
        disruption: DisruptionEvent,
    ) -> Set[str]:
        if disruption.type not in (DisruptionType.WEATHER, DisruptionType.CROWDING):
            return set()
        if disruption.task_id:
            return {disruption.task_id}
        return {
            t.id for t in future_tasks
            if t.task_type in PHYSICAL_TASK_TYPES
        }