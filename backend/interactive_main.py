import asyncio
import json
import sys
from datetime import datetime
from typing import List

# Fix path to ensure we can import modules
sys.path.append("e:/tbo")

from core.event_bus import EventBus
from core.schema import SystemState, Itinerary, Task, TaskStatus
from agents.state_agent import StateAgent
from agents.monitoring_agent import MonitoringAgent
from agents.reoptimization_agent import ReoptimizationAgent
from agents.companion_agent import CompanionAgent
from agents.orchestrator import OrchestratorAgent

# --- OVERRIDE COMPANION FOR CLI INPUT ---
class CLICompanionAgent(CompanionAgent):
    async def get_user_choice(self):
        """
        Real interactive input from the user in the terminal.
        """
        while True:
            try:
                choice = input("\n👉 Enter Option Number (1 or 2): ")
                idx = int(choice) - 1
                if idx in [0, 1]:
                    return idx
                print("Invalid choice. Try again.")
            except ValueError:
                print("Please enter a number.")

def load_itinerary(filepath="e:/tbo/itinerary.json") -> List[Task]:
    with open(filepath, "r") as f:
        data = json.load(f)
        tasks = []
        for t in data:
            # Parse ISO strings back to datetime
            t["start_time"] = datetime.fromisoformat(t["start_time"])
            t["end_time"] = datetime.fromisoformat(t["end_time"])
            tasks.append(Task(**t))
        return tasks

async def interactive_loop():
    print("=== 🎮 Agentic System: Interactive Mode ===")
    
    bus = EventBus()
    tasks = load_itinerary()
    
    # Init State
    # Start time is set to the start of the first task - 30 mins
    start_time = tasks[0].start_time 
    
    initial_state = SystemState(
        current_time=start_time,
        itinerary=Itinerary(tasks=tasks)
    )
    
    state_agent = StateAgent(bus, initial_state)
    monitor_agent = MonitoringAgent(bus)
    planner_agent = ReoptimizationAgent()
    companion_agent = CLICompanionAgent() # Use our CLI version
    
    orchestrator = OrchestratorAgent(bus, state_agent, planner_agent, companion_agent)
    
    print(f"✅ Loaded {len(tasks)} tasks.")
    print(f"🕒 Current Time: {start_time.strftime('%Y-%m-%d %H:%M')}")
    print("\ncommands: [step <mins>] [delay <mins>] [confirm <id>] [status] [quit]")
    
    while True:
        # Simple blocking input for commands
        # Note: In a real async app we'd use aioconsole, but for this prototype strict blocking is safer to avoid race conditions with logs.
        cmd_str = await asyncio.to_thread(input, "\n> ")
        parts = cmd_str.split()
        if not parts: continue
        
        cmd = parts[0].lower()
        
        try:
            if cmd == "quit":
                break
                
            elif cmd == "status":
                s = state_agent.get_state()
                print(f"🕒 Time: {s.current_time.strftime('%H:%M')}")
                for t in s.itinerary.tasks:
                    symbol = "⬜"
                    if t.status == TaskStatus.COMPLETED: symbol = "✅"
                    elif t.status == TaskStatus.ACTIVE: symbol = "▶️"
                    elif t.status == TaskStatus.PENDING: symbol = "⏳"
                    
                    print(f"{symbol} [{t.id}] {t.start_time.strftime('%H:%M')}-{t.end_time.strftime('%H:%M')} {t.description} ({t.status} {t.completion_type})")

            elif cmd == "step":
                mins = int(parts[1]) if len(parts) > 1 else 30
                await state_agent.advance_time(mins)
                
            elif cmd == "confirm":
                if len(parts) < 2:
                    print("Usage: confirm <task_id>")
                    continue
                await state_agent.confirm_task(parts[1])
                
            elif cmd == "delay":
                 mins = int(parts[1]) if len(parts) > 1 else 30
                 print(f"💥 Injecting {mins}m Traffic Delay...")
                 await monitor_agent.inject_delay_event(mins)
                 # Give async loop a moment to process the event chain
                 await asyncio.sleep(0.5)
                 
            else:
                print("Unknown command.")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    # Windows SelectorEventLoop policy fix if needed, but python 3.10+ usually handles it.
    asyncio.run(interactive_loop())
