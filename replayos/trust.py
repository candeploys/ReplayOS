from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    risk_level: str
    requires_explicit_approval: bool


def evaluate_risk(action_type: str, payload: dict) -> RiskDecision:
    high_risk_actions = {"send_email", "delete_file", "run_shell"}
    medium_risk_actions = {"write_file", "create_note"}

    if action_type in high_risk_actions:
        return RiskDecision(risk_level="high", requires_explicit_approval=True)
    if action_type in medium_risk_actions:
        return RiskDecision(risk_level="medium", requires_explicit_approval=False)
    return RiskDecision(risk_level="low", requires_explicit_approval=False)
