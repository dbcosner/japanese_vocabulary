from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import (
    PipelineError,
    apply_results,
    collect_batch,
    make_openai_client,
    prepare_batch,
    refresh_status,
    submit_batch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="batch-generate",
        description="Prepare and manage OpenAI Batch API vocabulary generation.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="Create offline JSONL requests")
    prepare.add_argument("--gcl", type=Path, required=True)
    prepare.add_argument("--work-dir", type=Path, default=Path(".batch"))
    prepare.add_argument("--start", type=int, default=1)
    prepare.add_argument("--end", type=int)
    prepare.add_argument("--model", default="gpt-5.6-terra")
    prepare.add_argument(
        "--reasoning-effort",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
        default="medium",
    )

    submit = commands.add_parser("submit", help="Upload and start a paid batch")
    submit.add_argument("--manifest", type=Path, required=True)
    submit.add_argument(
        "--confirm-cost",
        action="store_true",
        help="Required acknowledgement that batch submission can incur charges",
    )

    status = commands.add_parser("status", help="Refresh saved batch status")
    status.add_argument("--state", type=Path, required=True)

    collect = commands.add_parser("collect", help="Download completed results")
    collect.add_argument("--state", type=Path, required=True)

    apply = commands.add_parser("apply", help="Validate and build CrowdAnki JSON")
    apply.add_argument("--manifest", type=Path, required=True)
    apply.add_argument("--output", type=Path, required=True)
    apply.add_argument("--template", type=Path, required=True)
    apply.add_argument("--deck-output", type=Path, required=True)
    apply.add_argument("--allow-partial", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_batch(
                gcl_path=args.gcl,
                work_dir=args.work_dir,
                start=args.start,
                end=args.end,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
        elif args.command == "submit":
            if not args.confirm_cost:
                raise PipelineError(
                    "Submission can incur API charges; repeat with --confirm-cost"
                )
            result = submit_batch(
                args.manifest,
                client=make_openai_client(),
                confirm_cost=args.confirm_cost,
            )
        elif args.command == "status":
            result = refresh_status(args.state, client=make_openai_client())
        elif args.command == "collect":
            result = collect_batch(args.state, client=make_openai_client())
        else:
            result = apply_results(
                manifest_path=args.manifest,
                output_path=args.output,
                template_path=args.template,
                deck_output_path=args.deck_output,
                allow_partial=args.allow_partial,
            )
    except (PipelineError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
