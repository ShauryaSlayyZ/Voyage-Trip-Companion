import json
from datetime import datetime
from typing import List
from core.models import Task, Itinerary
from core.enums import TaskStatus, TaskType

def load_itinerary_from_json(path: str) -> Itinerary:
    with open(path) as f:
        raw = json.load(f)

    tasks = []
    for item in raw:
        task = Task(
            id=item["id"],
            title=item.get("description", item.get("title", "")),
            location=item.get("location", ""),
            start_time=datetime.fromisoformat(item["start_time"]),
            end_time=datetime.fromisoformat(item["end_time"]),
            task_type=TaskType(item.get("type", "rest")),
            status=TaskStatus(item.get("status", "PLANNED")),
            priority=item.get("priority", 3),
            travel_time_to_next=item.get("travel_time_to_next", 0),
            venue_open=datetime.fromisoformat(item["venue_open"]) if item.get("venue_open") else None,
            venue_close=datetime.fromisoformat(item["venue_close"]) if item.get("venue_close") else None,
        )
        tasks.append(task)

    return Itinerary(tasks=tasks)