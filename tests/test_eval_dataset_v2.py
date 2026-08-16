from __future__ import annotations

import json
from pathlib import Path

from evals.validate_v2_dataset import DATASET, validate


def test_v2_memory_dataset_is_frozen_and_valid():
    assert validate(json.loads(Path(DATASET).read_text(encoding="utf-8"))) == []
