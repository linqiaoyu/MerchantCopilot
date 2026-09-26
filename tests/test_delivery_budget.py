import json

import pytest

from app.api.delivery_budget import DeliveryBudget, DeliveryBudgetExceeded


def test_budget_reserves_all_pending_calls_and_charges_unknown(tmp_path):
    budget = DeliveryBudget(tmp_path / "budget.json", historical_spent=99.9)
    with pytest.raises(DeliveryBudgetExceeded):
        budget.reserve("r1", {"call_id": "large", "model": "deepseek-v4-flash", "input": {"user": "x" * 100000}, "max_tokens": 10000})
    assert not (tmp_path / "budget.json").exists()
    budget = DeliveryBudget(tmp_path / "budget.json", historical_spent=3.4)
    payload = {"call_id": "c1", "model": "deepseek-v4-flash", "input": {"user": "hello"}, "max_tokens": 100}
    budget.reserve("r1", payload)
    first = json.loads((tmp_path / "budget.json").read_text())
    assert first["calls"]["r1:c1"]["status"] == "reserved"
    budget.fail_run("r1")
    final = json.loads((tmp_path / "budget.json").read_text())
    assert final["calls"]["r1:c1"]["usage_unknown"] is True
    assert final["total_cny"] > 3.4


def test_budget_records_actual_usage_once_and_preserves_restart_reservations(tmp_path):
    path = tmp_path / "budget.json"
    budget = DeliveryBudget(path, historical_spent=3.4)
    budget.reserve("r1", {"call_id": "c1", "model": "deepseek-v4-flash", "input": {}, "max_tokens": 100})
    budget.complete("r1", {"call_id": "c1", "usage": {"prompt_tokens": 12, "completion_tokens": 5}})
    value = json.loads(path.read_text())
    assert value["calls"]["r1:c1"]["actual_cny"] == pytest.approx((12 * 3.52 + 5 * 10.56) / 1000000)
    budget.complete("r1", {"call_id": "c1", "usage": {"prompt_tokens": 12, "completion_tokens": 5}})
    assert json.loads(path.read_text()) == value
    budget.reserve("r2", {"call_id": "c2", "model": "deepseek-v4-flash", "input": {}, "max_tokens": 100})
    restarted = DeliveryBudget(path)
    restarted.recover()
    assert json.loads(path.read_text())["calls"]["r2:c2"]["usage_unknown"] is True
