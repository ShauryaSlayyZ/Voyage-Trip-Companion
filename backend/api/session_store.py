# backend/api/session_store.py
"""
In-memory store for ReoptimizationProposal sessions.

Sessions expire after SESSION_TTL_SECONDS to avoid unbounded growth.
In production, swap this for Redis if you need multi-process support.
"""
import time
import uuid
from typing import Dict, Optional, Tuple
from core.events import ReoptimizationProposal

SESSION_TTL_SECONDS = 300  # 5 minutes

# {session_id: (proposal, created_at)}
_store: Dict[str, Tuple[ReoptimizationProposal, float]] = {}


def create_session(proposal: ReoptimizationProposal) -> str:
    """Store a proposal and return a unique session_id."""
    session_id = str(uuid.uuid4())
    _store[session_id] = (proposal, time.time())
    _evict_expired()
    return session_id


def get_session(session_id: str) -> Optional[ReoptimizationProposal]:
    """Retrieve a proposal by session_id. Returns None if missing or expired."""
    entry = _store.get(session_id)
    if entry is None:
        return None
    proposal, created_at = entry
    if time.time() - created_at > SESSION_TTL_SECONDS:
        del _store[session_id]
        return None
    return proposal


def delete_session(session_id: str) -> None:
    """Remove a session after it has been applied."""
    _store.pop(session_id, None)


def _evict_expired() -> None:
    """Remove all expired sessions."""
    now = time.time()
    expired = [sid for sid, (_, ts) in _store.items() if now - ts > SESSION_TTL_SECONDS]
    for sid in expired:
        del _store[sid]
