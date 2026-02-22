import os
import asyncio
import openai
from core.schema import SystemState, Task, ReoptimizationProposal

class CompanionAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        # setup

    async def present_options(self, proposal: ReoptimizationProposal):
        """
        Presentation Layer for Options.
        """
        print("\n[Companion] 🤖 We have a situation. Here are your options:")
        for idx, option in enumerate(proposal.options):
            print(f"   Option {idx+1}: {option.description}")
            print(f"     Reason: {option.reason} (Score: {option.score})")
            
    async def get_user_choice(self):
        """
        Simulates waiting for user input.
        """
        print("[Companion] (Simulating User Input)... 'I'll take Option 1'")
        await asyncio.sleep(1)
        return 0 # Index 0

    async def explain_changes(self, old_state: SystemState, new_state: SystemState, disruption_context: str) -> str:
        # Legacy method, might still be useful for auto-updates
        return "Schedule updated."
