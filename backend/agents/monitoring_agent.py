import asyncio
from datetime import datetime, timedelta
from core.event_bus import EventBus
from core.schema import SystemState, TaskStatus

class MonitoringAgent:
    def __init__(self, bus: EventBus):
        self.bus = bus
        self.running = False

    async def detect_disruptions(self, state: SystemState):
        """
        Checks the current state for anomalies.
        PURELY READ-ONLY. Emits alerts.
        """
        current_time = state.current_time
        
        for task in state.itinerary.tasks:
            # Check for missed starts (simple logic)
            if task.status == TaskStatus.PENDING:
                # If we are 15 mins past start time and it's not ACTIVE or COMPLETED
                if current_time > task.start_time + timedelta(minutes=15):
                    print(f"[Monitoring] ⚠️ Potential Disruption: Task {task.id} late start.")
                    await self.bus.publish("POTENTIAL_DISRUPTION", {
                        "type": "MISSED_START",
                        "task_id": task.id,
                        "severity": "HIGH",
                        "detected_at": current_time
                    })
    
    # Simulation Helpers
    async def inject_delay_event(self, minutes: int):
        print(f"[Monitoring] 🚦 SIMULATION: Injecting {minutes} min delay signal.")
        await self.bus.publish("POTENTIAL_DISRUPTION", {
            "type": "TRAFFIC_DELAY",
            "delay_minutes": minutes,
            "severity": "MEDIUM",
            "detected_at": datetime.now()
        })
