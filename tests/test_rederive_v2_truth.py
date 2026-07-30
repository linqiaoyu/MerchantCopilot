import json

from evals.rederive_v2_truth import DATA, derive_case, main, validate


def test_rederive_frozen_v2_truth_is_internally_consistent():
    assert main() == 0


def test_rederivation_matches_all_four_frozen_label_fields():
    cases = json.loads(DATA.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 60
    assert validate(cases) == []
    for case in cases:
        assert derive_case(case)["expected_provenance"] == case["expected_provenance"]
