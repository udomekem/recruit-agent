"""`python -m evals run --suite fast [--update-baseline] [--no-langfuse]`"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import asdict

from evals.harness import REPORTS, HarnessError, push_to_langfuse, run_suite, to_markdown, write


def main() -> int:
    parser = argparse.ArgumentParser(prog="evals")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--suite", required=True)
    run.add_argument(
        "--update-baseline",
        action="store_true",
        help="save this run as the baseline (only when it passes)",
    )
    run.add_argument("--no-langfuse", action="store_true")
    args = parser.parse_args()

    try:
        report = run_suite(args.suite)
    except HarnessError as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # anything unexpected is a harness error, never a pass
        print(f"HARNESS ERROR (unexpected): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if not args.no_langfuse and report.expect_gate == "PASS":
        try:
            from app.config import get_settings

            settings = get_settings()
            if settings.tracing_configured:
                report.langfuse_runs = push_to_langfuse(report, settings)
        except Exception as exc:
            logging.warning("langfuse push skipped: %s", exc)

    json_path, md_path = write(report)
    print(to_markdown(report))
    print(f"report: {md_path}")
    for url in report.langfuse_runs:
        print(f"langfuse dataset run: {url}")

    if args.update_baseline:
        if report.outcome != "PASS":
            print("not updating baseline: run did not pass", file=sys.stderr)
            return 1
        shutil.copy(json_path, REPORTS / f"baseline-{report.suite}.json")
        print(f"baseline updated: baseline-{report.suite}.json")

    _ = json, asdict
    return 0 if report.outcome == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
