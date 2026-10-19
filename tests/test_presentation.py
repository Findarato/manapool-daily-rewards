"""Tests for status formatting."""

from __future__ import annotations

import json

from prometheus_client.metrics_core import Metric
from prometheus_client.parser import text_string_to_metric_families

from manapool.models import ClaimResult, Status
from manapool.presentation import (
    claim_to_dict,
    format_duration,
    format_mana,
    payload_to_prometheus,
    render_json,
    render_status,
    status_to_dict,
)


def test_format_duration():
    assert format_duration(3661) == "01:01:01"
    assert format_duration(-5) == "00:00:00"


def test_format_mana():
    assert format_mana(1396) == "1,396"
    assert format_mana(10.0) == "10"
    assert format_mana(True) == "unknown"
    assert format_mana(None) == "unknown"


def test_render_status_includes_pending_when_present():
    status = Status(
        already_claimed=False,
        eligible=True,
        seconds_until_reset=3600,
        extra_mana_available=16,
        pending_extra_mana=1396,
    )
    lines = render_status(status)
    assert lines[0] == "Mana Pool - Daily Reward status"
    assert any("Available next month:   1,396" in line for line in lines)
    assert any("Eligible (recent order): yes" in line for line in lines)
    assert any("Time until reset (UTC):  01:00:00" in line for line in lines)


def test_render_status_omits_pending_when_none():
    status = Status(
        already_claimed=True,
        eligible=False,
        seconds_until_reset=0,
        extra_mana_available=None,
        pending_extra_mana=None,
    )
    lines = render_status(status)
    assert not any("Available next month" in line for line in lines)
    assert any("Claimed today (UTC):     yes" in line for line in lines)


def test_status_to_dict_includes_pending_when_present():
    status = Status(
        already_claimed=False,
        eligible=True,
        seconds_until_reset=3600,
        extra_mana_available=16,
        pending_extra_mana=1396,
    )
    assert status_to_dict(status) == {
        "extra_mana_available": 16,
        "eligible": True,
        "already_claimed": False,
        "seconds_until_reset": 3600,
        "pending_extra_mana": 1396,
    }


def test_status_to_dict_omits_pending_when_none():
    status = Status(
        already_claimed=True,
        eligible=False,
        seconds_until_reset=0,
        extra_mana_available=None,
    )
    data = status_to_dict(status)
    assert "pending_extra_mana" not in data
    assert data["extra_mana_available"] is None


def test_claim_to_dict():
    assert claim_to_dict(ClaimResult(award_amount=10, award_title="Daily")) == {
        "award_amount": 10,
        "award_title": "Daily",
    }
    assert claim_to_dict(ClaimResult()) == {
        "award_amount": None,
        "award_title": None,
    }


def test_render_json_round_trips():
    payload = {"eligible": True, "amount": 16}
    assert json.loads(render_json(payload)) == payload


def _families(text: str) -> dict[str, Metric]:
    # Parsed with the official client library so the exposition format itself
    # is validated, not just the substrings we happen to assert on.
    return {family.name: family for family in text_string_to_metric_families(text)}


def _samples(text: str) -> dict[str, float]:
    return {
        sample.name: sample.value
        for family in _families(text).values()
        for sample in family.samples
    }


def test_prometheus_metrics_for_claim():
    payload = {
        "status": {
            "extra_mana_available": 16,
            "eligible": True,
            "already_claimed": False,
            "seconds_until_reset": 21238,
            "pending_extra_mana": 1396,
        },
        "claimed": True,
        "claim": {"award_amount": 10, "award_title": "Daily"},
        "status_after": {
            "extra_mana_available": 26,
            "eligible": True,
            "already_claimed": True,
            "seconds_until_reset": 21238,
        },
    }
    text = payload_to_prometheus(payload)
    families = _families(text)
    samples = _samples(text)

    assert samples == {
        "manapool_error": 0.0,
        "manapool_eligible": 1.0,
        "manapool_already_claimed": 0.0,
        "manapool_extra_mana_available": 16.0,
        "manapool_pending_extra_mana": 1396.0,
        "manapool_seconds_until_reset": 21238.0,
        "manapool_claimed": 1.0,
        "manapool_claim_award_amount": 10.0,
        "manapool_status_after_extra_mana_available": 26.0,
    }
    assert all(family.type == "gauge" for family in families.values())
    assert all(family.documentation for family in families.values())


def test_prometheus_error_payload_has_no_status_metrics():
    samples = _samples(payload_to_prometheus({"error": "sign-in failed"}))

    assert samples == {"manapool_error": 1.0, "manapool_claimed": 0.0}


def test_prometheus_omits_missing_values():
    payload = {
        "status": {
            "extra_mana_available": None,
            "eligible": False,
            "already_claimed": False,
            "seconds_until_reset": 0,
        },
        "claimed": False,
    }
    samples = _samples(payload_to_prometheus(payload))

    assert "manapool_extra_mana_available" not in samples
    assert "manapool_pending_extra_mana" not in samples
    assert "manapool_claim_award_amount" not in samples
    assert samples["manapool_seconds_until_reset"] == 0.0
