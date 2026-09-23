"""Synthesizes functional_record_id values without the real allocation path.

Production allocates functional_record_id asynchronously: a Celery worker
calls an external HTTP id-allocation service and writes the result back
(registry-platform/.../functional_id_allocation_worker.py). That pipeline is
not reachable/scalable for a bulk load of millions of rows, so the generator
assigns ids directly, matching the same prefix scheme
(g2p_id_generator_service.py: HH- for Household, FR- for Farmer, DEFAULT-
for everything else) with a per-mnemonic sequential counter in place of the
real allocator's sequence.

Each pod (or in-pod worker shard) owns a disjoint numeric block per mnemonic
so pods never coordinate and never collide:

    start = shard_index * SEED_ID_BLOCK   # default 100_000_000
    first id = start + 1

Five shards use 0, 100M, 200M, 300M, 400M. A 9-digit suffix fits through
pod 4 + ~60M crops. Prefixes (FR-/HH-/DEFAULT-) keep mnemonics distinct
even when they share the same numeric start.
"""

import os

from config import DEFAULT_ID_PREFIX, ID_PREFIXES

_counters: dict[str, int] = {}
_pod_index: int = 0
_total_pods: int = 1
_id_block: int = 100_000_000


def _id_block_size() -> int:
    return int(os.environ.get("SEED_ID_BLOCK", str(_id_block)))


def init_pod_id_scheme(pod_index: int, total_pods: int, target_farmers: int):
    """Initialize ID scheme for a specific shard in a parallel execution.

    Args:
        pod_index: Zero-based shard index (pod, or pod*workers+worker).
        total_pods: Total shards running in parallel.
        target_farmers: Total farmers across all shards (logged only; block
            size is SEED_ID_BLOCK, not derived from this, so child-table
            counters cannot spill into the next shard).
    """
    global _pod_index, _total_pods, _id_block, _counters
    _pod_index = pod_index
    _total_pods = total_pods
    _id_block = _id_block_size()
    start = pod_index * _id_block
    _counters = {
        "Farmer": start,
        "Household": start,
        "default": start,
    }
    _ = target_farmers  # kept for call-site compatibility


def assign_functional_id(register_mnemonic: str) -> str:
    prefix = ID_PREFIXES.get(register_mnemonic, DEFAULT_ID_PREFIX)
    counter_key = register_mnemonic if register_mnemonic in ID_PREFIXES else "default"
    _counters[counter_key] = _counters.get(counter_key, 0) + 1
    return f"{prefix}{_counters[counter_key]:09d}"
