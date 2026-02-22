from datetime import datetime, timedelta
from typing import List, Dict, Any
from core.schema import SystemState, Task, TaskStatus, ReoptimizationProposal, ProposalOption

class ReoptimizationAgent:
    """
    The deterministic planner.
    Input: Current State + Disruption Event
    Output: ReoptimizationProposal (Options)
    """
    
    def reoptimize(self, state: SystemState, disruption: Dict[str, Any]) -> ReoptimizationProposal:
        print(f"[ReOptimizer] 🧠 Calculating options for: {disruption['type']}")
        
        # 1. Base Strategy: Push Everything (Minimize Change)
        option_1_tasks = self._generate_push_plan(state, disruption)
        option_1 = ProposalOption(
            id="opt_push",
            description="Shift schedule forward. Keep all tasks.",
            affected_tasks=option_1_tasks,
            score=95.0,
            reason="Preserves all activities."
        )

        # 2. Alternative Strategy: Trade-off (e.g. if delay > 30m, maybe drop something?)
        # For prototype, let's just make a dummy 'Fast Track' option or just rely on the Push one if it fits.
        # Let's simulate a second option if delay is significant.
        
        options = [option_1]
        
        if disruption.get("delay_minutes", 0) > 30:
            option_2_tasks = self._generate_push_plan(state, disruption) # Reuse for now, but imagine it shortened a task
            # Just changing ID/Description to simulate choice
            option_2 = ProposalOption(
                id="opt_cancel_low_priority",
                description="Shift forward but shorten Dinner to 1 hour.",
                affected_tasks=option_2_tasks, # In real logic, we'd modify this list
                score=88.0,
                reason="Reduces lateness."
            )
            options.append(option_2)

        return ReoptimizationProposal(
            options=options,
            needs_confirmation=(len(options) > 1)
        )

    def _generate_push_plan(self, state: SystemState, disruption: Dict[str, Any]) -> List[Task]:
        # Get tasks that are NOT finished
        # IMPORTANT: We only re-plan PENDING/ACTIVE tasks.
        # But wait, StateAgent handles immutability. Here we just grab "Future" ones.
        
        # We copy all Pending/Active tasks
        future_tasks = [t.model_copy() for t in state.pending_tasks]
        future_tasks.sort(key=lambda x: x.start_time)
        
        if not future_tasks:
            return []
            
        delay_minutes = disruption.get('delay_minutes', 0)
        delta = timedelta(minutes=delay_minutes)
        current_time = state.current_time

        new_plan = []
        for task in future_tasks:
            duration = task.end_time - task.start_time
            
            # Simple Shift
            task.start_time += delta
            # Ensure we don't start in the past
            if task.start_time < current_time:
                 task.start_time = current_time + timedelta(minutes=5)
            
            task.end_time = task.start_time + duration
            new_plan.append(task)
            
        return new_plan

    def _apply_shift(self, tasks: List[Task], delay_minutes: int, current_time: datetime) -> List[Task]:
         # Deprecated internal helper, merged into _generate_push_plan
         pass
