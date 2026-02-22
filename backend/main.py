import asyncio
from datetime import datetime, timedelta
from core.event_bus import EventBus
from core.schema import SystemState, Itinerary, Task, TaskStatus
from agents.state_agent import StateAgent
from agents.monitoring_agent import MonitoringAgent
from agents.reoptimization_agent import ReoptimizationAgent
from agents.companion_agent import CompanionAgent
from agents.orchestrator import OrchestratorAgent

import sys

# Redirect stdout to a file to capture all logs clearly
sys.stdout = open("e:/tbo/execution.log", "w", encoding="utf-8")

async def main():
    print("=== Agentic Itinerary System (Phase 2) Initializing ===")
    
    # 1. Setup Infrastructure
    bus = EventBus()
    
    # 2. Create Initial Data
    start_time = datetime.now()
    initial_tasks = [
        Task(id="1", description="Breakfast at Tiffany's", start_time=start_time + timedelta(hours=1), end_time=start_time + timedelta(hours=2), location="Downtown"),
        Task(id="2", description="Museum Tour", start_time=start_time + timedelta(hours=3), end_time=start_time + timedelta(hours=5), location="Museum District"),
        Task(id="3", description="Dinner Reservation", start_time=start_time + timedelta(hours=6), end_time=start_time + timedelta(hours=8), location="Italian Restaurant"),
    ]
    initial_state = SystemState(
        current_time=start_time,
        itinerary=Itinerary(tasks=initial_tasks)
    )
    
    # 3. Initialize Agents
    state_agent = StateAgent(bus, initial_state)
    monitor_agent = MonitoringAgent(bus)
    planner_agent = ReoptimizationAgent()
    companion_agent = CompanionAgent()
    
    orchestrator = OrchestratorAgent(bus, state_agent, planner_agent, companion_agent)
    
    print(f"=== System Ready. Start Time: {start_time.strftime('%H:%M')} ===")
    for t in initial_state.itinerary.tasks:
          print(f"  - {t.start_time.strftime('%H:%M')} {t.description} ({t.status})")

    # 4. Simulation Step 1: Normal Execution (Task 1 Complete)
    print("\n--- ⏩ Advancing Time by 2.5 Hours ---")
    await state_agent.advance_time(150) # +2.5 hours. Should cover Task 1.
    
    # Verify Task 1 is COMPLETED (IMPLICIT)
    s = state_agent.get_state()
    t1 = s.itinerary.get_task("1")
    print(f"Task 1 Status: {t1.status} ({t1.completion_type})")
    
    # 5. Simulation Step 2: Explicit Confirmation
    print("\n--- ✅ User Confirms Task 1 ---")
    await state_agent.confirm_task("1")
    s = state_agent.get_state()
    t1 = s.itinerary.get_task("1")
    print(f"Task 1 Status: {t1.status} ({t1.completion_type})")
    
    # 6. Simulation Step 3: Major Disruption (Traffic)
    # This should trigger the Confirmation Gate because we inject > 30 mins
    print("\n--- 💥 Injecting Major Disruption (45m Delay) ---")
    await monitor_agent.inject_delay_event(45)
    
    # Allow async events to propagate
    await asyncio.sleep(2)
    
    # 7. Final Verification
    final_state = state_agent.get_state()
    print("\n=== Final Schedule ===")
    for t in final_state.itinerary.tasks:
        print(f"{t.start_time.strftime('%H:%M')} - {t.description} ({t.status})")

if __name__ == "__main__":
    asyncio.run(main())
