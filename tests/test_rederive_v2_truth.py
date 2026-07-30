from evals.rederive_v2_truth import main


def test_rederive_frozen_v2_truth_is_internally_consistent():
    assert main() == 0
