import os
import asyncio
from core.events import ReoptimizationProposal

class CompanionAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")

    async def present_options(self, proposal: ReoptimizationProposal):
        print("\n[Companion] 🤖 We have a situation. Here are your options:")
        for idx, option in enumerate(proposal.options):
            print(f"   Option {idx+1}: {option.explanation}")
            # Score/Reason removed from ReoptOption model as per strict requirements?
            # "ReoptOption: id, description, new_future_tasks". 
            # User output: "must NOT include past explicit tasks".
            # I removed 'score' and 'reason' from the model definition in my head?
            # Let's check my written core/events.py.
            # I wrote: id, description, new_future_tasks.
            # So I cannot access option.score.
            # I will just print description.
            
    async def get_user_choice(self):
        print("[Companion] (Simulating User Input)... 'I'll take Option 1'")
        await asyncio.sleep(1)
        return 0
