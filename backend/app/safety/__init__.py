"""Safety constraint layer - authoritative (spec sections 22, 82, 113).

No RL recommendation, however advantageous, may bypass this layer. The
`SignalController` only ever executes a `SafetyResult.command`.
"""

from app.safety.validator import SafetyValidator
from app.safety.rules import RULES, RuleId

__all__ = ["SafetyValidator", "RULES", "RuleId"]
