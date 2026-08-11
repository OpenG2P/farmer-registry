"""Builds seed_manifest.json (see README.md "Seed manifest").

record_ids/household_ids use reservoir sampling so the manifest stays a
fixed size (SAMPLE_SIZE) even at the 100M tier, instead of holding every id
generated in memory.
"""

import json
import random
from datetime import datetime, timezone

SAMPLE_SIZE = 10_000


class ReservoirSample:
    def __init__(self, capacity: int = SAMPLE_SIZE):
        self.capacity = capacity
        self.items: list[str] = []
        self._seen = 0

    def add(self, item: str):
        self._seen += 1
        if len(self.items) < self.capacity:
            self.items.append(item)
        else:
            j = random.randint(0, self._seen - 1)
            if j < self.capacity:
                self.items[j] = item


class ManifestBuilder:
    def __init__(self, search_terms: list[str], data_volume: str):
        self.search_terms = search_terms
        self.data_volume = data_volume
        self.record_ids = ReservoirSample()
        self.household_ids = ReservoirSample()

    def observe_farmer(self, internal_record_id: str):
        self.record_ids.add(internal_record_id)

    def observe_household(self, internal_record_id: str):
        self.household_ids.add(internal_record_id)

    def write(self, path: str):
        payload = {
            "record_ids": self.record_ids.items,
            "search_terms": self.search_terms,
            "household_ids": self.household_ids.items,
            "data_volume": self.data_volume,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
