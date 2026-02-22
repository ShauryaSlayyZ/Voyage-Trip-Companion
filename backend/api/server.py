# backend/api/server.py
"""
FastAPI application — Voyage Trip Companion API.

Endpoints
---------
GET  /health           — liveness check (no auth)
GET  /itinerary        — current itinerary
POST /itinerary        — upload / replace itinerary
POST /reoptimize       — inject disruption → returns options
POST /preview          — preview a chosen option (no commit)
POST /apply            — commit a chosen option to the itinerary
"""
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import get_settings
from core.enums import DisruptionType, DisruptionSeverity, TaskStatus
from core.events import DisruptionEvent, ReoptOption
from core.loader import load_itinerary_from_json
from core.models import Itinerary, StateSnapshot, Task

from agents.state_agent import StateAgent
from agents.reoptimization_agent import ReoptimizationAgent

from api.schemas import (
    ApplyRequest, ApplyResponse,
    DisruptionRequest,
    HealthResponse,
    ItineraryIn, ItineraryOut,
    OptionOut,
    PreviewRequest, PreviewResponse,
    ReoptimizeResponse,
    TaskOut,
)
from api import session_store

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
settings = get_settings()
logging.basicConfig(
    level=logging.getLevelName(settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voyage.api")

# ---------------------------------------------------------------------------
# App-level singletons (initialised in lifespan)
# ---------------------------------------------------------------------------
_state_agent: StateAgent = None
_reopt_agent: ReoptimizationAgent = None
_itinerary_file: str = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstrap agents on startup; clean up on shutdown."""
    global _state_agent, _reopt_agent, _itinerary_file

    _itinerary_file = os.path.join(
        os.path.dirname(__file__), "..", "..", settings.ITINERARY_FILE
    )
    _itinerary_file = os.path.normpath(_itinerary_file)

    logger.info("Loading itinerary from %s", _itinerary_file)
    try:
        itinerary = load_itinerary_from_json(_itinerary_file)
    except FileNotFoundError:
        logger.warning("itinerary.json not found — starting with empty itinerary")
        itinerary = Itinerary(tasks=[])

    _state_agent = StateAgent(itinerary=itinerary)
    _reopt_agent = ReoptimizationAgent()

    logger.info("Voyage API ready — %d tasks loaded", len(itinerary.tasks))
    yield
    logger.info("Voyage API shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Voyage Trip Companion API",
    version="0.1.0",
    description="Real-time itinerary re-optimisation for travel agents and travellers.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _task_to_out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        location=task.location,
        start_time=task.start_time,
        end_time=task.end_time,
        priority=task.priority,
        status=task.status.value,
        task_type=task.task_type.value,
        venue_open=task.venue_open,
        venue_close=task.venue_close,
        travel_time_to_next=task.travel_time_to_next,
        duration_minutes=task.duration_minutes,
    )


def _option_to_out(option: ReoptOption) -> OptionOut:
    return OptionOut(
        id=option.id,
        scope=option.scope.value,
        explanation=option.explanation,
        total_shift_minutes=option.total_shift_minutes,
        dropped_task_ids=option.dropped_task_ids,
        new_start_times={k: v.isoformat() for k, v in option.new_start_times.items()},
        objective_value=option.objective_value,
    )


def _get_state() -> StateSnapshot:
    """Get the current state snapshot — raises 503 if agents not ready."""
    if _state_agent is None:
        raise HTTPException(503, "Agents not initialised")
    return _state_agent.get_state_snapshot()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Liveness check — no auth needed."""
    return HealthResponse(env=settings.ENV)


@app.get("/itinerary", response_model=ItineraryOut, tags=["Itinerary"])
async def get_itinerary():
    """Return the current itinerary."""
    state = _get_state()
    tasks_out = [_task_to_out(t) for t in state.itinerary.tasks]
    logger.info("GET /itinerary → %d tasks", len(tasks_out))
    return ItineraryOut(tasks=tasks_out, as_of=state.current_time)


@app.post("/itinerary", response_model=ItineraryOut, tags=["Itinerary"])
async def upload_itinerary(payload: ItineraryIn):
    """
    Upload or replace the active itinerary.
    Accepts raw task dicts — validates through internal loader logic.
    """
    global _state_agent

    # Write to temp file then load through the existing loader
    tmp_path = _itinerary_file
    with open(tmp_path, "w") as f:
        json.dump(payload.tasks, f, default=str)

    try:
        itinerary = load_itinerary_from_json(tmp_path)
    except Exception as e:
        raise HTTPException(422, f"Invalid itinerary data: {e}")

    _state_agent = StateAgent(itinerary=itinerary)
    logger.info("Itinerary replaced — %d tasks", len(itinerary.tasks))
    return ItineraryOut(tasks=[_task_to_out(t) for t in itinerary.tasks])


@app.post("/reoptimize", response_model=ReoptimizeResponse, tags=["Disruption"])
async def reoptimize(request: DisruptionRequest):
    """
    Inject a disruption and run the re-optimisation pipeline.
    Returns a list of candidate options and a session_id.
    The user reviews options, then calls POST /preview and POST /apply.
    """
    state = _get_state()

    # Map string type to enum (with validation)
    try:
        disruption_type = DisruptionType(request.type.upper())
    except ValueError:
        raise HTTPException(422, f"Unknown disruption type: {request.type}. "
                            f"Valid values: {[e.value for e in DisruptionType]}")

    try:
        severity = DisruptionSeverity(request.severity.upper())
    except ValueError:
        severity = DisruptionSeverity.MEDIUM

    disruption = DisruptionEvent(
        type=disruption_type,
        task_id=request.task_id,
        detected_at=state.current_time,
        severity=severity,
        delay_minutes=request.delay_minutes,
    )

    logger.info("POST /reoptimize — type=%s task_id=%s delay=%s",
                disruption_type.value, request.task_id, request.delay_minutes)

    proposal = _reopt_agent.reoptimize(state, disruption)

    session_id = session_store.create_session(proposal)

    options_out = [_option_to_out(o) for o in proposal.options]
    logger.info("Reoptimiz → session=%s options=%d infeasible=%s",
                session_id, len(options_out), proposal.infeasible)

    return ReoptimizeResponse(
        session_id=session_id,
        options=options_out,
        needs_confirmation=proposal.needs_confirmation,
        infeasible=proposal.infeasible,
        infeasibility_reason=proposal.infeasibility_reason,
    )


@app.post("/preview", response_model=PreviewResponse, tags=["Disruption"])
async def preview(request: PreviewRequest):
    """
    Preview what the itinerary will look like if the chosen option is applied.
    Does NOT commit anything — this is a safe read-only preview.
    """
    proposal = session_store.get_session(request.session_id)
    if proposal is None:
        raise HTTPException(404, "Session not found or expired. Call /reoptimize again.")

    # Find the chosen option
    option = next((o for o in proposal.options if o.id == request.chosen_option_id), None)
    if option is None:
        raise HTTPException(404, f"Option '{request.chosen_option_id}' not found. "
                            f"Available: {[o.id for o in proposal.options]}")

    state = _get_state()
    preview_tasks: List[TaskOut] = []

    for task in state.itinerary.tasks:
        if task.id in option.dropped_task_ids:
            continue  # dropped — skip in preview
        out = _task_to_out(task)
        if task.id in option.new_start_times:
            # Apply new start time for preview
            new_start = option.new_start_times[task.id]
            duration = task.duration_minutes
            new_end = new_start.replace(
                hour=new_start.hour,
                minute=new_start.minute
            )
            from datetime import timedelta
            new_end = new_start + timedelta(minutes=duration)
            out = out.model_copy(update={
                "start_time": new_start,
                "end_time": new_end,
            })
        preview_tasks.append(out)

    preview_tasks.sort(key=lambda t: t.start_time)

    logger.info("POST /preview — session=%s option=%s", request.session_id, request.chosen_option_id)

    return PreviewResponse(
        chosen_option_id=option.id,
        preview_itinerary=preview_tasks,
        dropped_tasks=option.dropped_task_ids,
        explanation=option.explanation,
    )


@app.post("/apply", response_model=ApplyResponse, tags=["Disruption"])
async def apply(request: ApplyRequest):
    """
    Commit the chosen option to the active itinerary.
    Call this only after the user has reviewed the preview and pressed 'Apply'.
    """
    proposal = session_store.get_session(request.session_id)
    if proposal is None:
        raise HTTPException(404, "Session not found or expired. Call /reoptimize again.")

    option = next((o for o in proposal.options if o.id == request.chosen_option_id), None)
    if option is None:
        raise HTTPException(404, f"Option '{request.chosen_option_id}' not found.")

    # Apply the option via StateAgent
    try:
        _state_agent.apply_proposal(option)
    except Exception as e:
        logger.exception("Failed to apply option %s", request.chosen_option_id)
        raise HTTPException(500, f"Failed to apply option: {e}")

    # Remove session after successful apply
    session_store.delete_session(request.session_id)

    state = _get_state()
    updated_tasks = [_task_to_out(t) for t in state.itinerary.tasks]

    logger.info("POST /apply — session=%s option=%s applied", request.session_id, request.chosen_option_id)

    return ApplyResponse(
        applied_option_id=option.id,
        updated_itinerary=ItineraryOut(tasks=updated_tasks),
        message=f"Option '{option.id}' applied. "
                f"{len(option.dropped_task_ids)} task(s) dropped, "
                f"{len(option.new_start_times)} task(s) rescheduled.",
    )
