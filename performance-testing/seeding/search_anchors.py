"""Search anchors embedded into Farmer.first_name / search_text.

Prefer a baked-in term file (same 50k list in the image and on disk) so every
pod round-robins the identical terms. 50M farmers / 50_000 terms = 1_000 hits
per term. With 5 pods of 10M, each pod contributes 200 hits per term.

Fallback: generate a deterministic unique list with Random(42) if the file is
missing (local smoke only).
"""

import os
import random
import string
from pathlib import Path

from config import SEARCH_ANCHOR_COUNT, SEARCH_ANCHOR_LENGTH

_ANCHOR_FILE_CANDIDATES = (
    os.environ.get("SEED_ANCHORS_FILE", ""),
    "/perf-seed/register_search_terms.txt",
    str(Path(__file__).resolve().parent.parent.parent.parent / "perf-seed" / "register_search_terms.txt"),
)

_round_robin_index = 0


def _parse_anchor_file(path: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.lstrip().startswith("#"):
                continue
            term = line.lower()
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def load_anchors_from_file() -> tuple[list[str], str | None]:
    for candidate in _ANCHOR_FILE_CANDIDATES:
        if not candidate:
            continue
        if os.path.isfile(candidate):
            terms = _parse_anchor_file(candidate)
            if terms:
                return terms, candidate
    return [], None


def generate_anchors(count: int = SEARCH_ANCHOR_COUNT, length: int = SEARCH_ANCHOR_LENGTH) -> list[str]:
    rng = random.Random(42)
    anchors: set[str] = set()
    while len(anchors) < count:
        anchors.add("".join(rng.choices(string.ascii_lowercase, k=length)))
    return sorted(anchors)


def load_or_generate_anchors() -> tuple[list[str], str]:
    """Return (anchors, source_description)."""
    from_file, path = load_anchors_from_file()
    if from_file:
        return from_file, path or "file"
    generated = generate_anchors()
    return generated, f"generated Random(42) count={len(generated)}"


def next_anchor(anchors: list[str]) -> str:
    global _round_robin_index
    if not anchors:
        raise RuntimeError("search anchor list is empty")
    anchor = anchors[_round_robin_index % len(anchors)]
    _round_robin_index += 1
    return anchor


def embed_anchor(base_name: str, anchor: str) -> str:
    position = random.randint(0, len(base_name))
    return base_name[:position] + anchor + base_name[position:]
