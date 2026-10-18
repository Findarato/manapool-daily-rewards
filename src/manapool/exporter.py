"""Render a ``manapool --json`` payload as a Prometheus scrape endpoint."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from manapool.presentation import payload_to_prometheus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manapool-metrics",
        description="Convert a manapool --json payload to Prometheus text format.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="File holding the JSON payload (reads stdin when omitted).",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr

    payload: Any
    try:
        if args.path:
            with open(args.path, encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            payload = json.load(stdin)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read payload: {exc}", file=stderr)
        return 1

    stdout.write(payload_to_prometheus(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
