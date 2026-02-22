from core.event_bus import EventBus, Event
from core.schema import SystemState
from agents.state_agent import StateAgent
from agents.reoptimization_agent import ReoptimizationAgent
from agents.companion_agent import CompanionAgent

class OrchestratorAgent:
    def __init__(self, 
                 bus: EventBus, 
                 state_agent: StateAgent, 
                 planner: ReoptimizationAgent, 
                 companion: CompanionAgent):
        self.bus = bus
        self.state_agent = state_agent
        self.planner = planner
        self.companion = companion
        
        self.bus.subscribe("POTENTIAL_DISRUPTION", self.handle_disruption)

    async def handle_disruption(self, event: Event):
        disruption = event.payload
        print(f"\n[Orchestrator] 🔔 Received Alert: {disruption['type']}")
        
        # 1. Capture current state
        current_state = self.state_agent.get_state()
        
        # 2. Ask Planner for PROPOSALS (not just a list of tasks)
        proposal = self.planner.reoptimize(current_state, disruption)
        
        if not proposal.options:
            print("[Orchestrator] Plan is robust. No changes needed.")
            return

        selected_option = None

        # 3. Confirmation Gate
        if proposal.needs_confirmation:
            print("\n[Orchestrator] ✋ HOLD: User confirmation required.")
            
            # 4. Companion Presents Options
            await self.companion.present_options(proposal)
            
            # 5. Wait for User Choice (Mocking the interaction loop)
            # In a real app, this would be an async await on a "USER_RESPONSE" event.
            # Here we simulate the user picking Option 1.
            print("[Orchestrator] ...Waiting for user...")
            await self.companion.get_user_choice() # This prints the simulation
            
            # Assume User picked 0 for now
            selected_option = proposal.options[0]
            print(f"[Orchestrator] User selected: {selected_option.description}")
            
        else:
            print("[Orchestrator] ✅ Auto-applying best option (No trade-offs detected).")
            selected_option = proposal.options[0]

        # 6. Apply Execution
        if selected_option:
             await self.state_agent.apply_plan_update(selected_option.affected_tasks)
             
             # Explanation of result
             final_state = self.state_agent.get_state()
             # await self.companion.explain_changes(current_state, final_state, disruption['type']) 
             # (Optionally explain the final state again, or just leave it at the selection)
