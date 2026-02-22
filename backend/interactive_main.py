import asyncio
import json
import sys
from datetime import datetime
from typing import List

# Fix path
sys.path.append("e:/tbo")

from infrastructure.event_bus import InfrastructureEventBus as EventBus
from core.models import StateSnapshot, Itinerary, Task, TaskStatus
from agents.state_agent import StateAgent
from agents.monitoring_agent import MonitoringAgent
from agents.reoptimization_agent import ReoptimizationAgent
from agents.companion_agent import CompanionAgent
from orchestrator.orchestrator import OrchestratorAgent

class CLICompanionAgent(CompanionAgent):
    async def get_user_choice(self):
        while True:
            try:
                choice = input("\n👉 Enter Option Number (1 or 2): ")
                idx = int(choice) - 1
                if idx in [0, 1]:
                    return idx
                print("Invalid choice. Try again.")
            except ValueError:
                print("Please enter a number.")

from core.loader import load_itinerary_from_json

def load_itinerary(filepath="e:/tbo/itinerary.json") -> List[Task]:
    return load_itinerary_from_json(filepath).tasks

async def interactive_loop():
    print("=== 🎮 Agentic System: Interactive Mode (Strict Domain) ===")
    
    bus = EventBus()
    tasks = load_itinerary()
    
    start_time = tasks[0].start_time 
    initial_snapshot = StateSnapshot(
        current_time=start_time,
        itinerary=Itinerary(tasks=tasks)
    )
    
    state_agent = StateAgent(initial_snapshot)
    monitor_agent = MonitoringAgent()
    planner_agent = ReoptimizationAgent()
    companion_agent = CLICompanionAgent()
    
    orchestrator = OrchestratorAgent(bus, state_agent, monitor_agent, planner_agent, companion_agent)
    
    print(f"✅ Loaded {len(tasks)} tasks.")
    
    while True:
        await orchestrator.process_cycle()
        
        print("\n> ", end="", flush=True)
        cmd_str = await asyncio.to_thread(sys.stdin.readline)
        if not cmd_str: break
        cmd_str = cmd_str.strip()
        
        parts = cmd_str.split()
        if not parts: continue
        cmd = parts[0].lower()
        
        try:
            if cmd == "quit": break
            elif cmd == "status":
                s = state_agent.get_state_snapshot()
                print(f"🕒 Time: {s.current_time.strftime('%H:%M')}")
                for t in s.itinerary.tasks:
                    symbol = "⬜"
                    if t.status == TaskStatus.COMPLETED: symbol = "✅"
                    elif t.status == TaskStatus.ACTIVE: symbol = "▶️"
                    elif t.status == TaskStatus.PLANNED: symbol = "⏳"
                    print(f"{symbol} [{t.id}] {t.start_time.strftime('%H:%M')} {t.title} ({t.status})")
                    
            elif cmd == "step":
                mins = int(parts[1]) if len(parts) > 1 else 30
                state_agent.advance_time(mins)
                
            elif cmd == "confirm":
                if len(parts) < 2:
                     print("Usage: confirm <task_id>")
                     continue
                state_agent.confirm_task(parts[1])
                
            elif cmd == "rollback":
                if len(parts) < 2:
                     print("Usage: rollback <task_id>")
                     continue
                state_agent.rollback_implicit(parts[1])
                print(f"Task {parts[1]} rolled back to PLANNED.")

            elif cmd == "delay":
                 mins = int(parts[1]) if len(parts) > 1 else 30
                 current_sim_time = state_agent.get_state_snapshot().current_time
                 d = monitor_agent.detect_external_delay(None, mins, current_sim_time)
                 await bus.publish("INJECT_DISRUPTION", d)
                 print(f"Injected {mins}m delay.")
                 await orchestrator.process_cycle()
                 
            else:
                print("Unknown command.")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(interactive_loop())
