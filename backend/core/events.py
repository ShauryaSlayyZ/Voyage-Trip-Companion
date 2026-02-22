from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.enums import DisruptionType, DisruptionSeverity, ReoptScope
from core.models import Task

@dataclass
class DisruptionEvent:
    type: DisruptionType
    task_id: Optional[str]
    detected_at: datetime
    severity: DisruptionSeverity = DisruptionSeverity.MEDIUM  # ← new
    delay_minutes: Optional[int] = None                        # ← new (was in metadata)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReoptOption:
    id: str
    scope: ReoptScope                           # ← new
    new_start_times: Dict[str, datetime]        # ← new: task_id → new start
    dropped_task_ids: List[str]                 # ← new
    total_shift_minutes: int                    # ← new
    objective_value: float                      # ← new
    explanation: str                            # ← new
    new_future_tasks: List[Task] = field(default_factory=list)  # kept for compat


@dataclass
class ReoptimizationProposal:
    disruption: DisruptionEvent
    options: List[ReoptOption]
    needs_confirmation: bool
    infeasible: bool = False                    # ← new
    infeasibility_reason: Optional[str] = None  # ← new