"""
AREF Pillar II: Absorption — Impact containment and graceful degradation.

Mechanisms (Blueprint 3.2.1):
  - Circuit Breakers: Halt cascading calls to failing dependencies
  - Bulkheads: Partition systems so failure in one doesn't propagate
  - Rate Limiters: Prevent resource exhaustion under unexpected load
  - Graceful Degradation: Pre-defined reduced-functionality modes
  - Queue Buffers: Absorb traffic spikes and temporal imbalances
  - Data Replication: Multi-region data copies ensure availability
"""
