from typing import List
from core.models import StateSnapshot, Task, TaskStatus
from core.enums import DisruptionType
from core.events import DisruptionEvent
from agents.state_agent import StateAgent
from agents.monitoring_agent import MonitoringAgent
from agents.reoptimization_agent import ReoptimizationAgent
from agents.companion_agent import CompanionAgent
# Infrastructure
from infrastructure.event_bus import InfrastructureEventBus

class OrchestratorAgent:
    def __init__(self, 
                 bus: InfrastructureEventBus, 
                 state_agent: StateAgent, 
                 monitor_agent: MonitoringAgent,
                 planner: ReoptimizationAgent, 
                 companion: CompanionAgent):
        
        self.bus = bus
        self.state_agent = state_agent
        self.monitor = monitor_agent
        self.planner = planner
        self.companion = companion
        
        self.pending_disruptions: List[DisruptionEvent] = []
        
        self.bus.subscribe("INJECT_DISRUPTION", self.handle_external_disruption)

    async def handle_external_disruption(self, event):
        payload = event.payload
        # Payload should be DisruptionEvent
        if isinstance(payload, DisruptionEvent):
             self.pending_disruptions.append(payload)
             print(f"[Orchestrator] 📥 Received external disruption signal: {payload.type}")
        else:
             print(f"[Orchestrator] ⚠️ Received invalid payload: {type(payload)}")

    async def process_cycle(self):
        # 1. Capture current state
        current_state = self.state_agent.get_state_snapshot()
        
        # 2. Detect Internal Disruptions
        disruptions = self.monitor.detect(current_state)
        
        # Add External
        if self.pending_disruptions:
            disruptions.extend(self.pending_disruptions)
            self.pending_disruptions = []
            
        if not disruptions:
            return

        print(f"[Orchestrator] ⚠️ Processing {len(disruptions)} disruptions...")
        
        for disruption in disruptions:
            await self.handle_disruption_resolution(current_state, disruption)

    async def handle_disruption_resolution(self, state: StateSnapshot, disruption: DisruptionEvent):
        # 3. Ask Planner
        proposal = self.planner.reoptimize(state, disruption)
        
        selected_option = None

        # 4. Confirmation Gate
        if proposal.needs_confirmation:
            print("\n[Orchestrator] ✋ HOLD: User confirmation required.")
            await self.companion.present_options(proposal)
            print("[Orchestrator] ...Waiting for user...")
            choice_idx = await self.companion.get_user_choice()
            selected_option = proposal.options[choice_idx]
            print(f"[Orchestrator] User selected: {selected_option.explanation}")
            
        else:
            print("[Orchestrator] ✅ Auto-applying best option.")
            selected_option = proposal.options[0]

        # 5. Apply
        if selected_option:
             # Synchronous call
             self.state_agent.apply_proposal(selected_option)
