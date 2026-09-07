"""Deterministic priority-ladder coordinator (spec sections 20-21, docs/coordination.md).

`Coordinator.resolve(recs, state)` is a pure function: identical inputs always yield the
identical `CoordinationDecision`, with a full ladder trace. It never votes without weights
and never averages actions. Its output is only a *candidate* - the safety layer (spec
section 113) still has the final word.
"""

from __future__ import annotations

from app.agents.common.features import APPROACH_ORDER
from app.core.config import get_config
from app.logging import get_logger
from app.schemas.agents import AgentRecommendation
from app.schemas.coordination import CoordinationDecision, LadderStep, PhaseScore
from app.schemas.enums import AgentName, Phase
from app.schemas.simulation import SimulationState

log = get_logger("COORDINATION")

# fixed phase order for deterministic tie-breaks (after "prefer served phase")
_PHASE_ORDER: tuple[Phase, ...] = (
    Phase.NS, Phase.EW, Phase.N, Phase.E, Phase.S, Phase.W,
)


class Coordinator:
    """Stateless. One instance can serve every decision cycle."""

    def __init__(self) -> None:
        c = get_config().coordination
        self.emergency_threshold = float(c.emergency_override_threshold)
        self.consensus_bonus = float(c.consensus_bonus)
        self.stability_penalty = float(c.stability_penalty)
        self.throughput_bonus = float(c.throughput_bonus)

    # ------------------------------------------------------------------ public
    def resolve(self, recs: list[AgentRecommendation],
                state: SimulationState) -> CoordinationDecision:
        by_agent = {r.agent: r for r in recs}
        served = state.signal.served_phase
        trace: list[LadderStep] = []

        # -- Rung 1: safety / timing short-circuit ---------------------------
        if state.signal.transition is not None:
            trace.append(LadderStep(
                rung="safety", outcome="short_circuit",
                detail=f"mid-transition ({state.signal.transition.kind.value}); only 'continue' admissible",
            ))
            return self._decision(state.signal.transition.to_phase, "constraint",
                                  "transition_lock", trace, [], recs)

        if not state.signal.min_green_satisfied:
            trace.append(LadderStep(
                rung="safety", outcome="short_circuit",
                detail=(f"min-green not reached "
                        f"({state.signal.phase_elapsed_s:.1f}s, "
                        f"{state.signal.phase_remaining_min_s:.1f}s remaining) - hold {served.value}"),
            ))
            return self._decision(served, "constraint", "min_green_hold", trace, [], recs)

        trace.append(LadderStep(rung="safety", outcome="pass",
                                detail="phase may legally change"))

        # -- Rung 2: emergency override ------------------------------------
        a2c = by_agent.get(AgentName.A2C)
        if state.emergency.active and a2c is not None and a2c.priority >= self.emergency_threshold:
            overridden = [f"{r.agent.value}->{r.target_phase.value}"
                          for r in recs if r.agent != AgentName.A2C
                          and r.target_phase != a2c.target_phase]
            detail = f"emergency on {state.emergency.approach.value if state.emergency.approach else '?'}, " \
                     f"A2C priority {a2c.priority:.2f} >= {self.emergency_threshold:.2f}"
            if overridden:
                detail += f"; overrides {', '.join(overridden)}"
            trace.append(LadderStep(rung="emergency", outcome="override", detail=detail))
            return self._decision(a2c.target_phase, "a2c", "emergency_override", trace, [], recs)

        trace.append(LadderStep(
            rung="emergency", outcome="pass",
            detail=("no active emergency" if not state.emergency.active
                    else f"A2C priority {a2c.priority:.2f} < {self.emergency_threshold:.2f}"
                    if a2c else "no A2C recommendation"),
        ))

        # -- Rung 3: valid-phase filter -----------------------------------
        allowed = set(state.signal.allowed_next) | {served}
        candidates: list[Phase] = []
        for p in [served] + [r.target_phase for r in recs]:
            if p in allowed and p not in candidates and not p.is_transition:
                candidates.append(p)
        dropped = sorted({r.target_phase.value for r in recs
                          if r.target_phase not in allowed and not r.target_phase.is_transition})
        trace.append(LadderStep(
            rung="valid_phase", outcome="filter",
            detail=(f"candidates {[c.value for c in candidates]}"
                    + (f"; dropped {dropped} (not in allowed_next)" if dropped else "")),
        ))

        # -- Rungs 4-7: weighted score ----------------------------------
        scores = [self._score_phase(p, recs, state, served) for p in candidates]
        scores.sort(key=lambda s: (-s.total, _served_rank(s.phase, served), _phase_rank(s.phase)))
        best = scores[0]
        trace.append(LadderStep(
            rung="weighted_score", outcome="score",
            detail="; ".join(f"{s.phase.value}={s.total:+.3f}" for s in scores),
        ))

        targeting = [r.agent for r in recs if r.target_phase == best.phase]
        if len(targeting) >= 2:
            winner = "consensus"
        elif len(targeting) == 1:
            winner = targeting[0].value
        else:
            winner = "consensus"  # no agent picked it; stability retained the served phase
        return self._decision(best.phase, winner, "weighted_score", trace, scores, recs)

    # ------------------------------------------------------------------ scoring
    def _score_phase(self, p: Phase, recs: list[AgentRecommendation],
                     state: SimulationState, served: Phase) -> PhaseScore:
        by_agent = {r.agent: r for r in recs}
        ppo = by_agent.get(AgentName.PPO)
        dqn = by_agent.get(AgentName.DQN)

        congestion = ppo.score if ppo and ppo.target_phase == p else 0.0
        efficiency = dqn.score if dqn and dqn.target_phase == p else 0.0
        throughput = self.throughput_bonus if p == self._busiest_phase(state) else 0.0
        stability = -self.stability_penalty if p != served else 0.0
        agree = sum(1 for r in recs if r.target_phase == p)
        consensus = self.consensus_bonus * max(0, agree - 1)

        total = congestion + efficiency + throughput + stability + consensus
        return PhaseScore(
            phase=p, congestion=round(congestion, 4), efficiency=round(efficiency, 4),
            throughput=round(throughput, 4), stability=round(stability, 4),
            consensus_bonus=round(consensus, 4), total=round(total, 4),
        )

    @staticmethod
    def _busiest_phase(state: SimulationState) -> Phase:
        ring_load = {
            Phase.NS: sum(state.approach(a).vehicle_count for a in APPROACH_ORDER if Phase.NS.serves(a)),
            Phase.EW: sum(state.approach(a).vehicle_count for a in APPROACH_ORDER if Phase.EW.serves(a)),
        }
        return Phase.NS if ring_load[Phase.NS] >= ring_load[Phase.EW] else Phase.EW

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _decision(candidate: Phase, winner: str, basis: str, trace: list[LadderStep],
                  scores: list[PhaseScore],
                  recs: list[AgentRecommendation]) -> CoordinationDecision:
        decision = CoordinationDecision(
            candidate_phase=candidate, winner=winner, basis=basis,
            ladder_trace=trace, scores=scores, recommendations=recs,
        )
        log.info("coordination decision", winner=winner, basis=basis,
                 candidate=candidate.value,
                 recs={r.agent.value: r.target_phase.value for r in recs})
        return decision


def _served_rank(p: Phase, served: Phase) -> int:
    return 0 if p == served else 1


def _phase_rank(p: Phase) -> int:
    return _PHASE_ORDER.index(p) if p in _PHASE_ORDER else len(_PHASE_ORDER)
