"""Metrics aggregation (spec sections 38-39, 52; docs/metrics.md).

Every metric is computed from the live vehicle set / completed-trip records / event
counters - none is invented (spec section 84).
"""

from app.metrics.aggregator import MetricsAggregator

__all__ = ["MetricsAggregator"]
