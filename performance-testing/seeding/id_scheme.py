"""Synthesizes functional_record_id values without the real allocation path.

Production allocates functional_record_id asynchronously: a Celery worker
calls an external HTTP id-allocation service and writes the result back
(registry-platform/.../functional_id_allocation_worker.py). That pipeline is
not reachable/scalable for a bulk load of millions of rows, so the generator
assigns ids directly, matching the same prefix scheme
(g2p_id_generator_service.py: HH- for Household, FR- for Farmer, DEFAULT-
for everything else) with a per-mnemonic sequential counter in place of the
real allocator's sequence.
"""

from config import DEFAULT_ID_PREFIX, ID_PREFIXES

_counters: dict[str, int] = {}


def assign_functional_id(register_mnemonic: str) -> str:
    prefix = ID_PREFIXES.get(register_mnemonic, DEFAULT_ID_PREFIX)
    _counters[register_mnemonic] = _counters.get(register_mnemonic, 0) + 1
    return f"{prefix}{_counters[register_mnemonic]:09d}"
