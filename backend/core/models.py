from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from core.enums import TaskStatus, CompletionType, TaskType

@dataclass
class Task:
    id: str
    title: str                          # maps from "description" in JSON
    location: str
    start_time: datetime
    end_time: datetime
    task_type: TaskType = TaskType.REST  # maps from "type" in JSON

    # Scheduling fields
    status: TaskStatus = TaskStatus.PLANNED
    completion: CompletionType = CompletionType.NONE

    # Optimization fields
    priority: int = 3                   # 1 (lowest) to 5 (highest)
    travel_time_to_next: int = 0        # minutes to next task's location

    # Time windows — defaults to start/end times (tight window)
    # Can be loosened to allow flexibility
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    
    # Venue constraints (hard bounds)
    venue_open: Optional[datetime] = None
    venue_close: Optional[datetime] = None

    def __post_init__(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")

        # Default time windows to task times if not provided
        if self.time_window_start is None:
            self.time_window_start = self.start_time
        if self.time_window_end is None:
            self.time_window_end = self.end_time

        # Normalize PENDING → PLANNED for JSON compat
        if self.status == TaskStatus.PENDING:
            self.status = TaskStatus.PLANNED

    @property
    def duration_minutes(self) -> int:
        """Derived duration — single source of truth."""
        return int((self.end_time - self.start_time).total_seconds() / 60)

    @property
    def is_fixed(self) -> bool:
        """Fixed tasks have highest drop penalty."""
        return self.task_type == TaskType.FIXED

    @property
    def is_immutable(self) -> bool:
        """Explicitly completed tasks cannot be touched."""
        return (
            self.status == TaskStatus.COMPLETED
            and self.completion == CompletionType.EXPLICIT
        )


@dataclass
class Itinerary:
    tasks: List[Task] = field(default_factory=list)

    def __post_init__(self):
        self.tasks = list(self.tasks)
        self.tasks.sort(key=lambda x: x.start_time)

    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        return next((t for t in self.tasks if t.id == task_id), None)


@dataclass(frozen=True)
class StateSnapshot:
    current_time: datetime
    itinerary: Itinerary