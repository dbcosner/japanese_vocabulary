from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import (
    PipelineError,
    apply_reading_normalization,
    collect_batch,
    generate_from_workspace,
    import_apkg,
    make_openai_client,
    merge_retry_output,
    prepare_batch,
    prepare_population,
    prepare_reading_normalization,
    prepare_retry,
    refresh_status,
    submit_batch,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="batch-generate",
        description="Prepare and manage OpenAI Batch API vocabulary generation.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    import_command = commands.add_parser(
        "import-apkg", help="Create a named GCL from an Anki .apkg package"
    )
    import_command.add_argument("--apkg", type=Path, required=True)
    import_command.add_argument(
        "--name",
        required=True,
        help="Deck name, or a full *_generation_control_file.txt filename",
    )

    import_command.add_argument("--output-dir", type=Path, default=Path("gcl"))
    import_command.add_argument(
        "--decisions",
        type=Path,
        help="Optional explicit per-import cleanup decisions JSON",
    )
    import_command.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing proposed GCL and its review report",
    )

    populate = commands.add_parser(
        "populate",
        help="Prepare only missing cards in the workspace for a GCL/deck pair",
    )
    populate.add_argument("--gcl", type=Path, required=True)
    populate.add_argument("--deck", type=Path, required=True)
    populate.add_argument("--batch-root", type=Path, default=Path(".batch"))
    populate.add_argument("--batch-size", type=int, default=100)
    populate.add_argument("--model", default="gpt-5.6-terra")
    populate.add_argument(
        "--reasoning-effort",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
        default="medium",
    )

    generate = commands.add_parser(
        "generate",
        help="Generate APKG from a populated deck workspace",
    )
    generate.add_argument("--workspace", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--template", type=Path, required=True)
    generate.add_argument(
        "--deck-name",
        help="Anki deck name; defaults to the logical deck name from Populate",
    )

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

    prepare_readings = commands.add_parser(
        "prepare-readings",
        help="Prepare reading resolution for manually added bare GCL entries",
    )
    prepare_readings.add_argument("--gcl", type=Path, required=True)
    prepare_readings.add_argument("--work-dir", type=Path, default=Path(".batch"))
    prepare_readings.add_argument("--model", default="gpt-5.6-terra")
    prepare_readings.add_argument(
        "--reasoning-effort",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
        default="low",
    )

    retry = commands.add_parser(
        "prepare-retry", help="Prepare requests only for rejected cards"
    )
    retry.add_argument("--manifest", type=Path, required=True)
    retry.add_argument("--report", type=Path, required=True)
    retry.add_argument("--work-dir", type=Path, default=Path(".batch"))

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

    merge = commands.add_parser(
        "merge-retry", help="Replace rejected base results with retry results"
    )
    merge.add_argument("--base-output", type=Path, required=True)
    merge.add_argument("--retry-manifest", type=Path, required=True)
    merge.add_argument("--retry-output", type=Path, required=True)
    merge.add_argument("--merged-output", type=Path, required=True)

    apply_readings = commands.add_parser(
        "apply-readings",
        help="Validate reading results and atomically publish the annotated GCL",
    )
    apply_readings.add_argument("--manifest", type=Path, required=True)
    apply_readings.add_argument("--output", type=Path, required=True)
    apply_readings.add_argument("--report", type=Path, required=True)
    apply_readings.add_argument(
        "--correction",
        action="append",
        default=[],
        metavar="SOURCE=ANNOTATED_ENTRY",
        help="Apply an explicit editorial correction during publication",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "import-apkg":
            result = import_apkg(
                apkg_path=args.apkg,
                gcl_name=args.name,
                output_dir=args.output_dir,
                decisions_path=args.decisions,
                replace=args.replace,
            )
        elif args.command == "populate":
            result = prepare_population(
                gcl_path=args.gcl,
                deck_path=args.deck,
                batch_root=args.batch_root,
                batch_size=args.batch_size,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
        elif args.command == "generate":
            result = generate_from_workspace(
                workspace_path=args.workspace,
                output_path=args.output,
                template_path=args.template,
                deck_name=args.deck_name,
            )
        elif args.command == "prepare":
            result = prepare_batch(
                gcl_path=args.gcl,
                work_dir=args.work_dir,
                start=args.start,
                end=args.end,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
        elif args.command == "prepare-readings":
            result = prepare_reading_normalization(
                gcl_path=args.gcl,
                work_dir=args.work_dir,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
        elif args.command == "prepare-retry":
            result = prepare_retry(
                manifest_path=args.manifest,
                report_path=args.report,
                work_dir=args.work_dir,
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
        elif args.command == "merge-retry":
            result = merge_retry_output(
                base_output_path=args.base_output,
                retry_manifest_path=args.retry_manifest,
                retry_output_path=args.retry_output,
                merged_output_path=args.merged_output,
            )
        elif args.command == "apply-readings":
            corrections: dict[str, str] = {}
            for value in args.correction:
                if "=" not in value:
                    raise PipelineError(
                        "--correction must use SOURCE=ANNOTATED_ENTRY"
                    )
                source, corrected = value.split("=", 1)
                if not source or not corrected or source in corrections:
                    raise PipelineError(
                        "--correction sources and values must be non-empty and unique"
                    )
                corrections[source] = corrected
            result = apply_reading_normalization(
                manifest_path=args.manifest,
                output_path=args.output,
                report_path=args.report,
                corrections=corrections,
            )
    except (PipelineError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
