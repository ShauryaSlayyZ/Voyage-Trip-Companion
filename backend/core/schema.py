from __future__ import annotations
from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    IN_PROGRESS = "IN_PROGRESS" # Legacy, mapping to ACTIVE if needed or keep for nuance? Let's use ACTIVE.
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"

class CompletionType(str, Enum):
    NONE = "NONE"
    IMPLICIT = "IMPLICIT"  # Assumed by time passing
    EXPLICIT = "EXPLICIT"  # Confirmed by user

class Task(BaseModel):
    id: str
    description: str
    start_time: datetime
    end_time: datetime
    location: str
    status: TaskStatus = TaskStatus.PENDING
    completion_type: CompletionType = CompletionType.NONE
    is_flexible: bool = True
    priority: int = 1

    @field_validator("end_time")
    def end_time_must_be_after_start(cls, v, info):
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("end_time must be after start_time")
        return v

class Itinerary(BaseModel):
    tasks: List[Task] = []

    def get_task(self, task_id: str) -> Optional[Task]:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

class UserLocation(BaseModel):
    lat: float
    lon: float
    timestamp: datetime
    semantic_location: Optional[str] = None

class SystemState(BaseModel):
    current_time: datetime
    user_location: Optional[UserLocation] = None
    itinerary: Itinerary

    @property
    def completed_tasks(self) -> List[Task]:
        return [t for t in self.itinerary.tasks if t.status == TaskStatus.COMPLETED]
    
    @property
    def explicit_completed_tasks(self) -> List[Task]:
        return [t for t in self.company.tasks if t.status == TaskStatus.COMPLETED and t.completion_type == CompletionType.EXPLICIT]

    @property
    def pending_tasks(self) -> List[Task]:
        # Includes PENDING and ACTIVE?
        return [t for t in self.itinerary.tasks if t.status in (TaskStatus.PENDING, TaskStatus.ACTIVE)]

class ProposalOption(BaseModel):
    id: str
    description: str  # e.g., "Shift whole itinerary by 30 mins"
    affected_tasks: List[Task] # The NEW versions of the tasks
    score: float
    reason: str

class ReoptimizationProposal(BaseModel):
    options: List[ProposalOption]
    needs_confirmation: bool
