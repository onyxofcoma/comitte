#!/usr/bin/env python3
"""Fetch committee membership and render a static HTML table."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

from comitte.scraper import BudgetSubcommitteeMember, fetch_budget_subcommittee_members, render_html_table


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("budget_subcommittee_members.html"),
        help="Path to write the HTML table (default: %(default)s)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip network calls and assume an empty table (useful for dry runs)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.4,
        help="Delay between committee requests in seconds (default: %(default)s)",
    )
    return parser.parse_args()


def write_html(output: Path, rows: Iterable[BudgetSubcommitteeMember]) -> None:
    table = render_html_table(rows)
    html = """<!doctype html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\">
  <title>국회 예산소위원회 명단</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: left; }
    thead { background: #f2f2f2; }
    tbody tr:nth-child(even) { background: #fafafa; }
  </style>
</head>
<body>
  <h1>국회 예산소위원회 명단</h1>
  <p>각 상임위원회 웹사이트에서 가져온 예산 소위원회 명단입니다.</p>
  {table}
</body>
</html>
""".format(table=table)
    output.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))

    if args.no_fetch:
        rows: list[BudgetSubcommitteeMember] = []
    else:
        rows = fetch_budget_subcommittee_members(sleep_seconds=args.sleep)

    write_html(args.output, rows)
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
