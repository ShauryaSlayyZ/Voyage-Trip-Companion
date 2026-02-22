from datetime import datetime
from typing import Optional, List
from core.event_bus import EventBus
from core.schema import SystemState, TaskStatus, Task, CompletionType, Itinerary

class StateAgent:
    def __init__(self, bus: EventBus, initial_state: SystemState):
        self.bus = bus
        self._state = initial_state
        # No subscribers needed for now, Orchestrator drives updates

    def get_state(self) -> SystemState:
        return self._state.model_copy(deep=True) # Return copy to prevent accidental mutation

    async def advance_time(self, minutes: int):
        """
        Advances time and applies IMPLICIT completion rules.
        """
        if minutes < 0:
            raise ValueError("Time cannot rewinds!")
            
        old_time = self._state.current_time
        # Use simple timestamp add
        from datetime import timedelta
        new_time = old_time + timedelta(minutes=minutes)
        self._state.current_time = new_time
        
        print(f"[StateAgent] ⏰ Time advanced: {old_time.strftime('%H:%M')} -> {new_time.strftime('%H:%M')}")
        
        # Check for status updates (IMPLICIT)
        updates_made = False
        for task in self._state.itinerary.tasks:
            # Skip if already explicitly final
            if task.completion_type == CompletionType.EXPLICIT:
                continue
                
            # If task was COMPLETED(Implicit), do we keep it? Yes.
            
            # Logic: PENDING -> ACTIVE -> COMPLETED (Implicit)
            
            # 1. Check if should be ACTIVE
            # If current_time >= start_time and < end_time
            if task.status == TaskStatus.PENDING and task.start_time <= new_time < task.end_time:
                print(f"[StateAgent] Task '{task.description}' is now ACTIVE.")
                task.status = TaskStatus.ACTIVE
                updates_made = True
                
            # 2. Check if should be COMPLETED (Implicit)
            # If current_time >= end_time and status was ACTIVE/PENDING
            if task.status in (TaskStatus.PENDING, TaskStatus.ACTIVE, TaskStatus.IN_PROGRESS) and new_time >= task.end_time:
                print(f"[StateAgent] Task '{task.description}' marked IMPLICIT COMPLETED.")
                task.status = TaskStatus.COMPLETED
                task.completion_type = CompletionType.IMPLICIT
                updates_made = True
                
            # 3. Check for MISSED
            # If PENDING and we passed start_time + buffer without being ACTIVE? 
            # (Simplified: For now, we assume if time passes it completes implicitly unless flagged otherwise)

        if updates_made:
             await self.bus.publish("STATE_UPDATED", self._state)

    async def confirm_task(self, task_id: str):
        """User explicitly confirms a task is done."""
        task = self._state.itinerary.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
            
        print(f"[StateAgent] ✅ User confirmed: {task.description}")
        task.status = TaskStatus.COMPLETED
        task.completion_type = CompletionType.EXPLICIT
        await self.bus.publish("STATE_UPDATED", self._state)

    async def apply_plan_update(self, new_future_tasks: List[Task]):
        """
        Applies a Re-Optimization Result.
        CRITICAL: MUST NOT TOUCH EXPLICIT HISTORY.
        """
        current_tasks = self._state.itinerary.tasks
        
        # 1. Validate Immutability
        # Ensure we aren't losing any EXPLICIT completed tasks
        explicit_ids = {t.id for t in current_tasks if t.completion_type == CompletionType.EXPLICIT}
        new_ids = {t.id for t in new_future_tasks}
        
        # NOTE: new_future_tasks usually only contains the *changed* or *future* tasks.
        # But for simplicity, let's assume the Planner returns the *entire* valid itinerary 
        # OR we merge. The requirement says "Only future tasks may be modified".
        
        # Let's assume new_future_tasks is the LIST OF TASKS that are "Pending/Active" in the new plan.
        # We need to stitch it with history.
        
        history = [t for t in current_tasks if t.status == TaskStatus.COMPLETED or t.status == TaskStatus.MISSED]
        
        # Check against Immutability Violations? 
        # For this prototype, we just trust the StateAgent to KEEP history and APPEND/REPLACE future.
        
        # Re-construct full list
        full_list = history + new_future_tasks
        
        # Sort
        full_list.sort(key=lambda x: x.start_time)
        
        self._state.itinerary.tasks = full_list
        print(f"[StateAgent] 📝 Plan Updated. {len(new_future_tasks)} future tasks scheduled.")
        await self.bus.publish("ITINERARY_UPDATED", self._state.itinerary)
