"""Coordination engine - arbitrates between the three agents' recommendations.

PPT slide 19: agents are "coordinated at the traffic-signal level, not merged into
one shared network." This package never averages or blends actions (spec section 21).
"""

from app.coordination.engine import Coordinator

__all__ = ["Coordinator"]
