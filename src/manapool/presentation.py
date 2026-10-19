"""Pure formatting helpers that turn a Status into display strings or JSON."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from manapool.models import ClaimResult, Status


def format_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_mana(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{int(value):,}"
    return "unknown"


def render_status(status: Status) -> list[str]:
    """Render a status snapshot as the lines to print to the user."""
    lines = [
        "Mana Pool - Daily Reward status",
        f"  Extra Mana available:   {format_mana(status.extra_mana_available)}",
    ]
    if status.pending_extra_mana is not None:
        lines.append(
            f"  Available next month:   {format_mana(status.pending_extra_mana)}"
        )
    lines.append(f"  Eligible (recent order): {'yes' if status.eligible else 'no'}")
    lines.append(
        f"  Claimed today (UTC):     {'yes' if status.already_claimed else 'no'}"
    )
    lines.append(
        f"  Time until reset (UTC):  {format_duration(status.seconds_until_reset)}"
    )
    return lines


def status_to_dict(status: Status) -> dict[str, Any]:
    """Convert a status snapshot to a JSON-serializable mapping."""
    data: dict[str, Any] = {
        "extra_mana_available": status.extra_mana_available,
        "eligible": status.eligible,
        "already_claimed": status.already_claimed,
        "seconds_until_reset": status.seconds_until_reset,
    }
    if status.pending_extra_mana is not None:
        data["pending_extra_mana"] = status.pending_extra_mana
    return data


def claim_to_dict(result: ClaimResult) -> dict[str, Any]:
    """Convert a claim outcome to a JSON-serializable mapping."""
    return {
        "award_amount": result.award_amount,
        "award_title": result.award_title,
    }


def render_json(payload: Any) -> str:
    """Serialize a payload as pretty-printed JSON."""
    return json.dumps(payload, indent=2)


def payload_to_prometheus(payload: Mapping[str, Any]) -> str:
    """Render a ``--json`` payload as Prometheus text exposition format."""
    lines: list[str] = []
    _gauge(
        lines,
        "manapool_error",
        "1 when the last run failed, otherwise 0.",
        int("error" in payload),
    )

    status = payload.get("status")
    if isinstance(status, Mapping):
        _gauge(
            lines,
            "manapool_eligible",
            "1 when a recent order makes the account eligible.",
            int(bool(status.get("eligible"))),
        )
        _gauge(
            lines,
            "manapool_already_claimed",
            "1 when today's reward was already claimed before the run.",
            int(bool(status.get("already_claimed"))),
        )
        _optional_gauge(
            lines,
            "manapool_extra_mana_available",
            "Extra Mana currently available.",
            status.get("extra_mana_available"),
        )
        _optional_gauge(
            lines,
            "manapool_pending_extra_mana",
            "Extra Mana pending for next month.",
            status.get("pending_extra_mana"),
        )
        _optional_gauge(
            lines,
            "manapool_seconds_until_reset",
            "Seconds until the 00:00 UTC daily reset.",
            status.get("seconds_until_reset"),
        )

    _gauge(
        lines,
        "manapool_claimed",
        "1 when this run claimed the reward, otherwise 0.",
        int(bool(payload.get("claimed"))),
    )

    claim = payload.get("claim")
    if isinstance(claim, Mapping):
        _optional_gauge(
            lines,
            "manapool_claim_award_amount",
            "Extra Mana awarded by the last successful claim.",
            claim.get("award_amount"),
        )

    after = payload.get("status_after")
    if isinstance(after, Mapping):
        _optional_gauge(
            lines,
            "manapool_status_after_extra_mana_available",
            "Extra Mana available after the last claim.",
            after.get("extra_mana_available"),
        )

    return "\n".join(lines) + "\n"


def _gauge(lines: list[str], name: str, help_text: str, value: int) -> None:
    lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} gauge")
    lines.append(f"{name} {value}")


def _optional_gauge(lines: list[str], name: str, help_text: str, value: Any) -> None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        _gauge(lines, name, help_text, int(value))
