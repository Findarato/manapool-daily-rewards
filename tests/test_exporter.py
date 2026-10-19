"""Tests for the Prometheus exporter command."""

from __future__ import annotations

import io
import json

from prometheus_client.metrics_core import Metric
from prometheus_client.parser import text_string_to_metric_families

from manapool import exporter

# Mirrors the JSON the container seeds into index.html before the first run.
PENDING_PAYLOAD = '{"status":"pending","message":"first run has not completed yet"}'


def _families(text: str) -> dict[str, Metric]:
    return {family.name: family for family in text_string_to_metric_families(text)}


def test_parser_defaults_to_stdin():
    args = exporter.build_parser().parse_args([])
    assert args.path is None


def test_parser_accepts_path():
    args = exporter.build_parser().parse_args(["payload.json"])
    assert args.path == "payload.json"


def test_main_reads_file(tmp_path):
    payload = {
        "status": {
            "extra_mana_available": 16,
            "eligible": True,
            "already_claimed": False,
            "seconds_until_reset": 100,
        },
        "claimed": False,
    }
    path = tmp_path / "payload.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    out = io.StringIO()
    code = exporter.main([str(path)], stdout=out)

    assert code == 0
    assert "manapool_extra_mana_available 16" in out.getvalue()


def test_main_reads_stdin():
    payload = {"error": "nope"}
    out = io.StringIO()
    code = exporter.main([], stdin=io.StringIO(json.dumps(payload)), stdout=out)

    assert code == 0
    assert "manapool_error 1" in out.getvalue()


def test_main_invalid_json_returns_1(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    err = io.StringIO()
    code = exporter.main([str(path)], stdout=io.StringIO(), stderr=err)

    assert code == 1
    assert "could not read payload" in err.getvalue()


def test_main_missing_file_returns_1(tmp_path):
    err = io.StringIO()
    code = exporter.main(
        [str(tmp_path / "absent.json")], stdout=io.StringIO(), stderr=err
    )

    assert code == 1
    assert "could not read payload" in err.getvalue()


def test_pending_placeholder_payload_parses_as_metrics():
    out = io.StringIO()
    code = exporter.main([], stdin=io.StringIO(PENDING_PAYLOAD), stdout=out)

    assert code == 0
    families = _families(out.getvalue())
    samples = {
        sample.name: sample.value
        for family in families.values()
        for sample in family.samples
    }
    assert samples == {"manapool_error": 0.0, "manapool_claimed": 0.0}
    assert all(family.type == "gauge" for family in families.values())
