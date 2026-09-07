"""Enumerations shared across the system."""

from __future__ import annotations

from enum import Enum


class Approach(str, Enum):
    N = "N"
    E = "E"
    S = "S"
    W = "W"

    @property
    def opposite(self) -> "Approach":
        return {Approach.N: Approach.S, Approach.S: Approach.N,
                Approach.E: Approach.W, Approach.W: Approach.E}[self]

    @property
    def axis(self) -> str:
        return "NS" if self in (Approach.N, Approach.S) else "EW"


class Movement(str, Enum):
    LEFT = "left"
    THROUGH = "through"
    RIGHT = "right"


class Phase(str, Enum):
    """Signal phases. NS/EW are the serviceable ring; N/E/S/W are emergency-only
    single-approach phases; YELLOW/ALL_RED are transition states."""

    NS = "NS"
    EW = "EW"
    N = "N"
    E = "E"
    S = "S"
    W = "W"
    YELLOW = "YELLOW"
    ALL_RED = "ALL_RED"

    @property
    def is_transition(self) -> bool:
        return self in (Phase.YELLOW, Phase.ALL_RED)

    @property
    def is_emergency_phase(self) -> bool:
        return self in (Phase.N, Phase.E, Phase.S, Phase.W)

    @property
    def is_served(self) -> bool:
        return not self.is_transition

    def serves(self, approach: Approach) -> bool:
        if self == Phase.NS:
            return approach in (Approach.N, Approach.S)
        if self == Phase.EW:
            return approach in (Approach.E, Approach.W)
        if self.is_emergency_phase:
            return self.value == approach.value
        return False


class SignalColor(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


class ControlMode(str, Enum):
    AI = "AI"
    FIXED_TIME = "FIXED_TIME"
    MANUAL = "MANUAL"


class AgentName(str, Enum):
    A2C = "a2c"
    DQN = "dqn"
    PPO = "ppo"


class ViolationType(str, Enum):
    RED_LIGHT = "red_light"
    UNSAFE_CROSSING = "unsafe_crossing"
    LANE_VIOLATION = "lane_violation"


class VehicleType(str, Enum):
    CAR = "car"
    SUV = "suv"
    BUS = "bus"
    TRUCK = "truck"
    AMBULANCE = "ambulance"
    FIRE_TRUCK = "fire_truck"
    POLICE = "police"

    @property
    def is_emergency(self) -> bool:
        return self in (VehicleType.AMBULANCE, VehicleType.FIRE_TRUCK, VehicleType.POLICE)


class EventCategory(str, Enum):
    TRAFFIC = "TRAFFIC"
    AI = "AI"
    EMERGENCY = "EMERGENCY"
    SAFETY = "SAFETY"
    VIOLATION = "VIOLATION"
    SYSTEM = "SYSTEM"


class Severity(str, Enum):
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


class SafetyAction(str, Enum):
    APPLIED = "APPLIED"
    REWRITTEN_TRANSITION = "REWRITTEN_TRANSITION"
    BLOCKED_HOLD = "BLOCKED_HOLD"
    FORCED_CHANGE = "FORCED_CHANGE"
    EMERGENCY_TIMEOUT = "EMERGENCY_TIMEOUT"


RING_PHASES: tuple[Phase, ...] = (Phase.NS, Phase.EW)
EMERGENCY_PHASES: dict[Approach, Phase] = {
    Approach.N: Phase.N, Approach.E: Phase.E, Approach.S: Phase.S, Approach.W: Phase.W,
}
