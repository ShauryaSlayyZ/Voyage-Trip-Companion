from core.models import StateSnapshot, Task, TaskStatus
from core.events import ReoptimizationProposal, ReoptOption, DisruptionEvent
from core.enums import ReoptScope

from agents.optimizers.reopt_engine import ReoptEngine

class ReoptimizationAgent:
    def __init__(self):
        self.engine = ReoptEngine()
        # Transition matrix placeholder - should be loaded from config/external source
        # For now, we pass an empty one, or the engine defaults to empty.
        self.transition_matrix = {} 
        self.engine.set_transition_matrix(self.transition_matrix)

    def reoptimize(self, state: StateSnapshot, disruption: DisruptionEvent) -> ReoptimizationProposal:
        # Delegate entirely to the engine
        return self.engine.reoptimize(state, disruption)
