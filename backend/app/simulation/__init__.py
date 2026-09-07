"""Traffic simulation layer.

Everything above ``SimulationAdapter`` is engine-independent (spec section 9). The
default engine is a self-contained pure-python microsimulation (``builtin``); a
``sumo`` adapter can be swapped in without touching agents / coordination / safety.
"""

from app.simulation.adapter import SimEvent, SimulationAdapter, get_adapter

__all__ = ["SimEvent", "SimulationAdapter", "get_adapter"]
