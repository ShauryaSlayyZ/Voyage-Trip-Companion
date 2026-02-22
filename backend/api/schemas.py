# backend/api/schemas.py
"""
Pydantic request/response schemas for the FastAPI layer.
These are the contracts the frontend relies on - never break them without versioning.
"""
from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

class TaskOut(BaseModel):
    """Single task as returned by the API."""
    id: str
    title: str
    location: str
    start_time: datetime
    end_time: datetime
    priority: int
    status: str
    task_type: str
    venue_open: Optional[datetime] = None
    venue_close: Optional[datetime] = None
    travel_time_to_next: int = 0
    duration_minutes: int


# ---------------------------------------------------------------------------
# Itinerary
# ---------------------------------------------------------------------------

class ItineraryOut(BaseModel):
    """Full itinerary returned to the frontend."""
    tasks: List[TaskOut]
    as_of: datetime = Field(default_factory=datetime.utcnow)


class ItineraryIn(BaseModel):
    """Payload to upload/replace the itinerary (from travel agent side)."""
    tasks: List[Dict[str, Any]]   # raw dicts, validated by loader internally


# ---------------------------------------------------------------------------
# Disruption → Reoptimize
# ---------------------------------------------------------------------------

class DisruptionRequest(BaseModel):
    """
    Frontend sends this when a disruption is detected or injected.
    All fields except `type` are optional.
    """
    type: str = Field(..., examples=["DELAY", "CLOSED", "WEATHER"])
    task_id: Optional[str] = None          # which task is affected (None = global)
    delay_minutes: Optional[int] = None    # only for DELAY type
    severity: str = "MEDIUM"              # LOW | MEDIUM | HIGH | CRITICAL


class OptionOut(BaseModel):
    """One re-optimization option returned to the user for review."""
    id: str
    scope: str                             # SAME_SLOT | SAME_DAY | CROSS_DAY
    explanation: str
    total_shift_minutes: int
    dropped_task_ids: List[str]
    new_start_times: Dict[str, str]        # task_id → ISO datetime string
    objective_value: float


class ReoptimizeResponse(BaseModel):
    """
    Response from POST /reoptimize.
    Contains a session_id so the frontend can later call /preview or /apply.
    """
    session_id: str
    options: List[OptionOut]
    needs_confirmation: bool
    infeasible: bool = False
    infeasibility_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Preview / Apply
# ---------------------------------------------------------------------------

class PreviewRequest(BaseModel):
    """
    Frontend sends this after user selects an option.
    Returns new schedule WITHOUT committing.
    """
    session_id: str
    chosen_option_id: str


class PreviewResponse(BaseModel):
    """
    Shows what the itinerary will look like if this option is applied.
    User then presses 'Apply' to commit.
    """
    chosen_option_id: str
    preview_itinerary: List[TaskOut]
    dropped_tasks: List[str]
    explanation: str


class ApplyRequest(BaseModel):
    """
    Frontend sends this when user confirms 'Apply'.
    Commits the chosen option to the active itinerary.
    """
    session_id: str
    chosen_option_id: str


class ApplyResponse(BaseModel):
    """Confirms the option was applied and returns the updated itinerary."""
    applied_option_id: str
    updated_itinerary: ItineraryOut
    message: str


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    env: str
    version: str = "0.1.0"
