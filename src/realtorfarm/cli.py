from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .ingest import load_leads, load_records
from .output import render_data
from .scoring import qualify_property
from .signals import load_signal_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="realtorfarm", description="Distressed-property signal hunter")
    sub = parser.add_subparsers(dest="command", required=True)

    hunt = sub.add_parser("hunt", help="Score input records and emit data= JSON")
    hunt.add_argument("--input", required=True, help="CSV or JSON records exported from public-record collectors")
    hunt.add_argument("--output", help="Optional output file")
    hunt.add_argument("--all", action="store_true", help="Include non-qualifying watch/context leads")
    hunt.add_argument("--evidence", action="store_true", help="Include evidence and qualification fields")
    hunt.add_argument("--accessed-date", help="Override accessed date as YYYY-MM-DD for reproducible tests")

    sub.add_parser("signals", help="Print configured tiers and signal aliases")

    validate = sub.add_parser("validate", help="Validate an input file can be parsed and scored")
    validate.add_argument("--input", required=True)

    return parser


def cmd_hunt(args: argparse.Namespace) -> int:
    leads = load_leads(args.input)
    accessed = date.fromisoformat(args.accessed_date) if args.accessed_date else date.today()
    text = render_data(leads, accessed=accessed, qualified_only=not args.all, include_research=args.evidence)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def cmd_signals(_: argparse.Namespace) -> int:
    print(json.dumps(load_signal_config(), indent=2))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    records = load_records(args.input)
    leads = load_leads(args.input)
    qualifying = sum(1 for lead in leads if qualify_property(lead).outreach_qualifying)
    print(json.dumps({"records": len(records), "properties": len(leads), "outreach_qualifying": qualifying}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "hunt":
        return cmd_hunt(args)
    if args.command == "signals":
        return cmd_signals(args)
    if args.command == "validate":
        return cmd_validate(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
