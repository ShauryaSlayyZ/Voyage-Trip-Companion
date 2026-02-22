from datetime import datetime
from typing import List, Optional

from core.models import StateSnapshot
from core.enums import DisruptionType, DisruptionSeverity
from core.events import DisruptionEvent

class MonitoringAgent:
    """
    Pure signal adapter.
    Translates external signals into DisruptionEvents.
    No internal state. No internal detection of missed tasks.
    Time must be provided explicitly for determinism.
    """

    def detect(self, snapshot: StateSnapshot) -> List[DisruptionEvent]:
        """
        No-op by default as requested.
        Internal state (MISSED, LATE_ARRIVAL) is handled by StateAgent history.
        Future extensions can add logic here if needed.
        """
        return []

    def detect_external_closure(self, task_id: Optional[str], detected_at: datetime) -> DisruptionEvent:
        return DisruptionEvent(
            type=DisruptionType.CLOSED,
            task_id=task_id,
            detected_at=detected_at,
            severity=DisruptionSeverity.HIGH,
            metadata={"closure_time": detected_at}
        )

    def detect_external_delay(self, task_id: Optional[str], minutes: int, detected_at: datetime) -> DisruptionEvent:
        severity = DisruptionSeverity.LOW
        if minutes > 30:
            severity = DisruptionSeverity.MEDIUM
        if minutes > 120:
            severity = DisruptionSeverity.HIGH

        return DisruptionEvent(
            type=DisruptionType.DELAY,
            task_id=task_id,
            detected_at=detected_at,
            severity=severity,
            delay_minutes=minutes,
            metadata={"delay_minutes": minutes}
        )

    def detect_external_weather(self, task_id: Optional[str], severity: str, detected_at: datetime) -> DisruptionEvent:
        # Map string severity to enum if possible, else default
        enum_severity = DisruptionSeverity.MEDIUM
        try:
             enum_severity = DisruptionSeverity(severity.upper())
        except:
             pass

        return DisruptionEvent(
            type=DisruptionType.WEATHER,
            task_id=task_id,
            detected_at=detected_at,
            severity=enum_severity,
            metadata={"severity": severity}
        )
