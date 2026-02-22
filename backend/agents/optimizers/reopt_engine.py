# backend/agents/optimizers/reopt_engine.py

from typing import Dict, Optional, Tuple

from core.models import StateSnapshot
from core.events import DisruptionEvent, ReoptimizationProposal
from core.enums import DisruptionSeverity

from agents.optimizers.preprocessor import DisruptionPreprocessor
from agents.optimizers.phase_runner import PhaseRunner
from agents.optimizers.objective import ObjectiveWeights, DEFAULT_WEIGHTS


class ReoptEngine:
    """
    Public entry point for the re-optimization pipeline.

    Façade over: Preprocessor → PhaseRunner → SolutionExtractor

    Responsibilities:
    - Own the transition matrix
    - Own preprocessor and phase runner instances
    - Handle top-level exceptions gracefully (never raises)
    - Return ReoptimizationProposal always

    Called by: ReoptimizationAgent
    Never calls: Orchestrator, StateAgent, CompanionAgent
    Never mutates: StateSnapshot
    """

    def __init__(
        self,
        weights: ObjectiveWeights = DEFAULT_WEIGHTS,
        planning_horizon_minutes: int = 2880, # 48 hours to allow Cross Day
    ):
        self.preprocessor             = DisruptionPreprocessor()
        self.phase_runner             = PhaseRunner()
        self.weights                  = weights
        self.planning_horizon_minutes = planning_horizon_minutes

        # Transition matrix: (task_id_from, task_id_to) → travel minutes
        # Populated externally via set_transition_matrix()
        # Defaults to empty (zero travel times)
        self.transition_matrix: Dict[Tuple[str, str], int] = {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def reoptimize(
        self,
        snapshot: StateSnapshot,
        disruption: DisruptionEvent,
    ) -> ReoptimizationProposal:
        """
        Main entry point. Always returns a ReoptimizationProposal.
        Never raises — exceptions are caught and returned as infeasible proposals.
        """
        try:
            return self._run(snapshot, disruption)
        except Exception as e:
            print(f"[ReoptEngine] ❌ Unexpected error: {e}")
            return self._emergency_proposal(disruption, str(e))

    def set_transition_matrix(
        self,
        matrix: Dict[Tuple[str, str], int],
    ) -> None:
        """
        Inject travel times between task locations.

        Format: {("task_id_a", "task_id_b"): minutes, ...}

        Example:
            engine.set_transition_matrix({
                ("t1", "t2"): 15,
                ("t2", "t3"): 20,
            })
        """
        self.transition_matrix = matrix
        print(f"[ReoptEngine] 🗺️ Transition matrix loaded: {len(matrix)} pairs")

    def set_weights(self, weights: ObjectiveWeights) -> None:
        """Override objective weights at runtime."""
        self.weights = weights
        print(f"[ReoptEngine] ⚖️ Objective weights updated.")

    # -----------------------------------------------------------------------
    # Internal Pipeline
    # -----------------------------------------------------------------------

    def _run(
        self,
        snapshot: StateSnapshot,
        disruption: DisruptionEvent,
    ) -> ReoptimizationProposal:

        print(f"[ReoptEngine] 🚀 Starting re-optimization "
              f"| disruption={disruption.type.value} "
              f"| severity={disruption.severity.value} "
              f"| delay={disruption.delay_minutes}min")

        # Phase 0: Preprocess
        pre_out = self.preprocessor.run(
            snapshot=snapshot,
            disruption=disruption,
            planning_horizon_minutes=self.planning_horizon_minutes,
        )

        # Log classification summary
        c = pre_out.classification
        print(
            f"[ReoptEngine] 📋 Tasks: "
            f"{len(c.fixed_tasks)} fixed | "
            f"{len(c.future_tasks)} future | "
            f"{len(pre_out.trivially_infeasible)} infeasible | "
            f"active={'yes' if c.active_task else 'no'}"
        )

        if pre_out.cascade.affected_ids:
            print(
                f"[ReoptEngine] 🌊 Cascade: "
                f"{len(pre_out.cascade.affected_ids)} tasks affected "
                f"| boundary={pre_out.cascade.cascade_boundary_id}"
            )

        # Phase 1-3: Multi-phase solving
        proposal = self.phase_runner.run(
            snapshot=snapshot,
            disruption=disruption,
            preprocessor_output=pre_out,
            transition_matrix=self.transition_matrix,
            weights=self.weights,
        )

        # Log result summary
        self._log_proposal(proposal)

        return proposal

    # -----------------------------------------------------------------------
    # Logging
    # -----------------------------------------------------------------------

    def _log_proposal(self, proposal: ReoptimizationProposal) -> None:

        if proposal.infeasible:
            print(
                f"[ReoptEngine] ❌ Infeasible: "
                f"{proposal.infeasibility_reason}"
            )
            return

        print(
            f"[ReoptEngine] ✅ Proposal ready: "
            f"{len(proposal.options)} option(s) | "
            f"confirmation={'required' if proposal.needs_confirmation else 'auto'}"
        )

        for i, opt in enumerate(proposal.options, 1):
            print(
                f"[ReoptEngine]    Option {i}: "
                f"scope={opt.scope.value} | "
                f"score={int(opt.objective_value)} | "
                f"shift={opt.total_shift_minutes}min | "
                f"dropped={len(opt.dropped_task_ids)}"
            )

    # -----------------------------------------------------------------------
    # Emergency Fallback
    # -----------------------------------------------------------------------

    def _emergency_proposal(
        self,
        disruption: DisruptionEvent,
        error_message: str,
    ) -> ReoptimizationProposal:
        """
        Returns a safe infeasible proposal when an unexpected
        exception occurs. Prevents system crash.
        """
        from agents.optimizers.solution_extractor import SolutionExtractor
        extractor = SolutionExtractor()
        proposal = extractor.build_infeasible_proposal(
            disruption=disruption,
            future_tasks=[],
        )
        # Override reason with actual error
        object.__setattr__(
            proposal,
            'infeasibility_reason',
            f"Internal error: {error_message}"
        ) if hasattr(proposal, '__dataclass_fields__') else None

        return proposal