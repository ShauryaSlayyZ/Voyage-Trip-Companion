from enum import Enum, auto

class TaskStatus(str, Enum):
    PLANNED = "PLANNED"
    PENDING = "PENDING"    # alias for JSON compat — maps to PLANNED on load
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"

class CompletionType(str, Enum):
    NONE = "NONE"
    IMPLICIT = "IMPLICIT"
    EXPLICIT = "EXPLICIT"

class DisruptionType(str, Enum):
    DELAY = "DELAY"
    WEATHER = "WEATHER"
    CLOSED = "CLOSED"
    FATIGUE = "FATIGUE"
    LATE_ARRIVAL = "LATE_ARRIVAL"
    CROWDING = "CROWDING"           # ← new

class DisruptionSeverity(str, Enum):  # ← new
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ReoptScope(str, Enum):          # ← new
    SAME_SLOT = "SAME_SLOT"
    SAME_DAY = "SAME_DAY"
    CROSS_DAY = "CROSS_DAY"

class TaskType(str, Enum):            # ← new (from your JSON)
    REST = "rest"
    WORK = "work"
    SOCIAL = "social"
    WALKING = "walking"
    FIXED = "fixed"                   # fixed = high drop penalty