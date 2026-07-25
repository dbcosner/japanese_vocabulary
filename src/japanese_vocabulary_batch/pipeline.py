from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ENDPOINT = "/v1/responses"
SCHEMA_NAME = "japanese_vocabulary_card"
TERMINAL_STATUSES = {"completed", "failed", "expired", "cancelled"}
HIRAGANA_RE = re.compile(r"^[\u3040-\u309fー]+$")
TAG_RE = re.compile(r"<[^>]+>")
READING_ANNOTATION_RE = re.compile(r"\[([^\[\]]+)\](?=\(な\)$|$)")
ANNOTATED_GCL_RE = re.compile(
    r"^(?P<expression>[^\[\]\(\)]+)\[(?P<reading>[ぁ-ゖー]+)\](?P<na>\(な\))?$"
)


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class GclEntry:
    source_index: int
    text: str

    @property
    def identity(self) -> str:
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:20]
        return f"gcl-{digest}"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path, json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_and_read_gcl(
    path: Path, *, require_readings: bool = True
) -> tuple[list[GclEntry], list[dict[str, Any]]]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    seen: set[str] = set()
    entries: list[GclEntry] = []
    duplicate_report: list[dict[str, Any]] = []
    cleaned_lines: list[str] = []

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            cleaned_lines.append(raw_line)
            continue
        if line in seen:
            duplicate_report.append({"line": line_number, "entry": line})
            continue
        seen.add(line)
        cleaned_lines.append(raw_line)
        entries.append(GclEntry(len(entries) + 1, line))

    if duplicate_report:
        atomic_write_text(path, "\n".join(cleaned_lines).rstrip() + "\n")
    if not entries:
        raise PipelineError(f"GCL contains no vocabulary entries: {path}")
    if require_readings:
        unresolved = [
            entry for entry in entries if not ANNOTATED_GCL_RE.fullmatch(entry.text)
        ]
        if unresolved:
            preview = ", ".join(
                f"{entry.source_index}:{entry.text}" for entry in unresolved[:5]
            )
            raise PipelineError(
                f"GCL contains {len(unresolved)} unresolved or malformed "
                f"entry/entries; every entry requires a complete [reading]. "
                f"First entries: {preview}"
            )
    return entries, duplicate_report


def card_schema() -> dict[str, Any]:
    common_properties = {
        "status": {"type": "string"},
        "issue": {"type": "string"},
        "gcl_entry": {"type": "string"},
        "resolved_gcl_entry": {"type": "string"},
        "additional_gcl_entries": {
            "type": "array",
            "items": {"type": "string"},
        },
        "reading": {"type": "string"},
        "definition": {"type": "string"},
        "examples": {
            "type": "array",
            "items": {"type": "string"},
        },
        "example_count_rationale": {"type": "string"},
        "vocabulary": {"type": "string"},
    }
    required = list(common_properties)
    card_properties = dict(common_properties)
    card_properties["status"] = {"type": "string", "enum": ["card"]}
    card_properties["examples"] = {
        "type": "array",
        "items": {"type": "string"},
        "minItems": 1,
        "maxItems": 5,
    }
    review_properties = dict(common_properties)
    review_properties["status"] = {"type": "string", "enum": ["needs_review"]}
    review_properties["examples"] = {
        "type": "array",
        "items": {"type": "string"},
        "maxItems": 0,
    }
    return {
        "type": "object",
        "properties": {
            "result": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": card_properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "properties": review_properties,
                        "required": required,
                        "additionalProperties": False,
                    },
                ]
            }
        },
        "required": ["result"],
        "additionalProperties": False,
    }


def reading_resolution_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "result": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["resolved", "needs_review"],
                    },
                    "issue": {"type": "string"},
                    "gcl_entry": {"type": "string"},
                    "readings": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["status", "issue", "gcl_entry", "readings"],
                "additionalProperties": False,
            }
        },
        "required": ["result"],
        "additionalProperties": False,
    }


def reading_resolution_instructions() -> str:
    return """Resolve the readings for one Japanese vocabulary expression.
Return only the required JSON object, with all response fields inside result.

Apply these rules:
- Copy gcl_entry byte-for-byte from the request.
- Return every useful contemporary standalone reading of the requested expression,
  ordered with the most common intended reading first.
- Exclude archaic, obsolete, markedly uncommon, compound-only, and specialist
  readings when natural standalone example sentences would be contrived.
- Each reading must be complete hiragana, including okurigana: 添う -> そう,
  嘆く -> なげく, and 継ぐ -> つぐ.
- Do not return partial stems, brackets, annotations, explanations, or duplicates
  inside readings.
- Use status resolved with an empty issue when the readings are reliable.
- Use needs_review with a concise issue and an empty readings array when reliable
  resolution is impossible."""


def generation_instructions() -> str:
    return """You generate one Japanese vocabulary card for an advanced learner.
Return only the required JSON object, with all response fields inside result.

Apply these rules:
- Honor an authoritative [reading]. Remove all GCL annotations from vocabulary.
- Copy gcl_entry byte-for-byte from the request. In resolved_gcl_entry, a reading
  annotation always follows the complete written expression. Include the complete
  reading, including okurigana: 添う[そう], 嘆く[なげく], 赴く[おもむく],
  継ぐ[つぐ], 侵す[おかす], and 浸す[ひたす]. Never put brackets inside a
  word (添[そう]う or 継[つ]ぐ) and never use parentheses for a reading
  (嘆(なげ)く).
- Every input has one authoritative reading. Copy resolved_gcl_entry exactly from
  gcl_entry and return an empty additional_gcl_entries array.
- reading is hiragana with only kanji-corresponding portions inside <b> tags.
  Original kana and okurigana remain unbolded.
- definition is concise natural Japanese for a JLPT N1 learner.
- Prefer exactly 3 natural Japanese examples. Use 1 or 2 only when usage is so
  specific that more would be contrived or essentially duplicative. Use 4 or 5
  only when needed to demonstrate additional distinct common use patterns.
  Set example_count_rationale to an empty string for 3 examples; otherwise explain
  concisely why fewer or more are needed. This rationale is metadata, not card
  content.
- Conceal every target occurrence by replacing its complete inflected target
  portion with bold hiragana.
- For nouns, naturally demonstrate Nの or Nする when those constructions are
  common. Demonstrate both when both are genuinely useful; invent neither.
- Do not reveal the written target in reading, definition, or examples.
- Do not include <div> around examples; the local assembler adds it.
- When status is needs_review, explain the problem in issue and use empty strings
  and an empty examples array for unavailable card content."""


def make_request(entry: GclEntry, model: str, reasoning_effort: str) -> dict[str, Any]:
    return {
        "custom_id": entry.identity,
        "method": "POST",
        "url": ENDPOINT,
        "body": {
            "model": model,
            "reasoning": {"effort": reasoning_effort},
            "store": False,
            "input": [
                {"role": "developer", "content": generation_instructions()},
                {
                    "role": "user",
                    "content": f"Generate the card for this GCL entry: {entry.text}",
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": SCHEMA_NAME,
                    "strict": True,
                    "schema": card_schema(),
                }
            },
        },
    }


def make_repair_request(
    entry: GclEntry,
    model: str,
    reasoning_effort: str,
    original_card: dict[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    request = make_request(entry, model, reasoning_effort)
    repair_context = {
        "gcl_entry": entry.text,
        "rejected_card": original_card,
        "validation_errors": validation_errors,
    }
    request["body"]["input"][1]["content"] = (
        "Repair the rejected card below. Return a complete replacement card. "
        "Preserve fields that already comply, but correct every listed validation "
        "error. Do not repeat a rejected value merely because it appeared in the "
        "original card.\n\n"
        + json.dumps(repair_context, ensure_ascii=False, indent=2)
    )
    return request


def make_reading_request(
    entry: GclEntry, model: str, reasoning_effort: str
) -> dict[str, Any]:
    return {
        "custom_id": entry.identity,
        "method": "POST",
        "url": ENDPOINT,
        "body": {
            "model": model,
            "reasoning": {"effort": reasoning_effort},
            "store": False,
            "input": [
                {
                    "role": "developer",
                    "content": reading_resolution_instructions(),
                },
                {
                    "role": "user",
                    "content": f"Resolve this GCL expression: {entry.text}",
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "japanese_vocabulary_readings",
                    "strict": True,
                    "schema": reading_resolution_schema(),
                }
            },
        },
    }


def prepare_reading_normalization(
    *,
    gcl_path: Path,
    work_dir: Path,
    model: str = "gpt-5.6-terra",
    reasoning_effort: str = "low",
) -> dict[str, Any]:
    entries, duplicates = clean_and_read_gcl(gcl_path, require_readings=False)
    unresolved = [
        entry for entry in entries if not ANNOTATED_GCL_RE.fullmatch(entry.text)
    ]
    if not unresolved:
        raise PipelineError("GCL is already fully annotated")
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / "input_readings.jsonl"
    manifest_path = work_dir / "manifest_readings.json"
    atomic_write_text(
        input_path,
        "\n".join(
            json.dumps(
                make_reading_request(entry, model, reasoning_effort),
                ensure_ascii=False,
            )
            for entry in unresolved
        ) + "\n",
    )
    manifest = {
        "version": 1,
        "operation": "normalize-readings",
        "gcl_path": str(gcl_path.resolve()),
        "gcl_sha256": sha256_file(gcl_path),
        "input_path": str(input_path.resolve()),
        "input_sha256": sha256_file(input_path),
        "model": model,
        "reasoning_effort": reasoning_effort,
        "range": {"start": 1, "end": len(entries)},
        "total_gcl_entries": len(entries),
        "duplicate_entries_removed": duplicates,
        "requests": [
            {
                "custom_id": entry.identity,
                "source_index": entry.source_index,
                "gcl_entry": entry.text,
            }
            for entry in unresolved
        ],
    }
    atomic_write_json(manifest_path, manifest)
    return {"manifest_path": str(manifest_path), **manifest}


def apply_reading_normalization(
    *,
    manifest_path: Path,
    output_path: Path,
    report_path: Path,
    corrections: dict[str, str] | None = None,
) -> dict[str, Any]:
    editorial_corrections = corrections or {}
    manifest = load_manifest(manifest_path)
    if manifest.get("operation") != "normalize-readings":
        raise PipelineError("Manifest is not a reading-normalization manifest")
    gcl_path = Path(manifest["gcl_path"])
    if sha256_file(gcl_path) != manifest["gcl_sha256"]:
        raise PipelineError("GCL changed after reading normalization was prepared")
    entries, _ = clean_and_read_gcl(gcl_path, require_readings=False)
    entry_texts = {entry.text for entry in entries}
    unknown_corrections = editorial_corrections.keys() - entry_texts
    if unknown_corrections:
        raise PipelineError(
            "Editorial correction source not found in GCL: "
            + ", ".join(sorted(unknown_corrections))
        )
    results = parse_output(output_path)
    expected_ids = {request["custom_id"] for request in manifest["requests"]}
    missing = expected_ids - results.keys()
    unexpected = results.keys() - expected_ids
    if missing or unexpected:
        raise PipelineError(
            f"Output reconciliation failed: {len(missing)} missing, "
            f"{len(unexpected)} unexpected"
        )
    request_by_index = {
        request["source_index"]: request for request in manifest["requests"]
    }
    findings: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    primary_by_index: dict[int, str] = {}
    alternates: list[str] = []
    for entry in entries:
        request = request_by_index.get(entry.source_index)
        if request is None:
            continue
        corrected = editorial_corrections.get(entry.text)
        if corrected is not None:
            if not ANNOTATED_GCL_RE.fullmatch(corrected):
                findings.append(
                    {
                        "custom_id": request["custom_id"],
                        "source_index": entry.source_index,
                        "gcl_entry": entry.text,
                        "errors": [
                            "editorial correction must be a complete annotated entry"
                        ],
                    }
                )
                continue
            primary_by_index[entry.source_index] = corrected
            warnings.append(
                {
                    "custom_id": request["custom_id"],
                    "source_index": entry.source_index,
                    "gcl_entry": entry.text,
                    "actions": [f"editorial correction applied: {corrected}"],
                }
            )
            continue
        result = results[request["custom_id"]]
        errors: list[str] = []
        if result.get("status") != "resolved":
            errors.append(result.get("issue") or "reading requires editorial review")
        if result.get("gcl_entry") != entry.text:
            errors.append("response gcl_entry does not match request")
        readings = result.get("readings")
        if not isinstance(readings, list):
            errors.append("readings must contain complete hiragana readings")
            valid_readings: list[str] = []
        else:
            valid_readings = []
            discarded: list[str] = []
            for reading in readings:
                if (
                    not isinstance(reading, str)
                    or not HIRAGANA_RE.fullmatch(reading)
                    or reading in valid_readings
                ):
                    discarded.append(str(reading))
                    continue
                valid_readings.append(reading)
            if not valid_readings:
                errors.append("readings must contain complete hiragana readings")
            elif discarded:
                warnings.append(
                    {
                        "custom_id": request["custom_id"],
                        "source_index": entry.source_index,
                        "gcl_entry": entry.text,
                        "actions": [
                            "discarded duplicate or malformed reading: "
                            + value
                            for value in discarded
                        ],
                    }
                )
        if errors:
            findings.append(
                {
                    "custom_id": request["custom_id"],
                    "source_index": entry.source_index,
                    "gcl_entry": entry.text,
                    "errors": errors,
                }
            )
            continue
        expression = entry.text[:-3] if entry.text.endswith("(な)") else entry.text
        suffix = "(な)" if entry.text.endswith("(な)") else ""
        resolved_entries = [
            f"{expression}[{reading}]{suffix}" for reading in valid_readings
        ]
        primary_by_index[entry.source_index] = resolved_entries[0]
        alternates.extend(resolved_entries[1:])

    report = {
        "operation": "normalize-readings",
        "manifest_path": str(manifest_path.resolve()),
        "output_path": str(output_path.resolve()),
        "gcl_path": str(gcl_path.resolve()),
        "entries_requested": len(manifest["requests"]),
        "entries_resolved": len(primary_by_index),
        "entries_requiring_review": len(findings),
        "published": False,
        "findings": findings,
        "normalization_warnings": warnings,
    }
    if findings:
        atomic_write_json(report_path, report)
        raise PipelineError(
            f"{len(findings)} reading(s) require review; see {report_path}"
        )

    proposed = [
        primary_by_index.get(entry.source_index, entry.text) for entry in entries
    ]
    proposed.extend(alternates)
    seen: set[str] = set()
    canonical: list[str] = []
    removed: list[dict[str, Any]] = []
    for position, text_value in enumerate(proposed, start=1):
        if text_value in seen:
            removed.append({"position": position, "entry": text_value})
            continue
        seen.add(text_value)
        canonical.append(text_value)
    for text_value in canonical:
        if not ANNOTATED_GCL_RE.fullmatch(text_value):
            raise PipelineError(
                f"Reading normalization produced invalid GCL entry: {text_value}"
            )
    atomic_write_text(
        gcl_path,
        "# GCL Version: 1\n\n" + "\n".join(canonical) + "\n",
    )
    report.update(
        {
            "published": True,
            "final_entries": len(canonical),
            "duplicates_removed_after_resolution": removed,
            "gcl_sha256": sha256_file(gcl_path),
        }
    )
    atomic_write_json(report_path, report)
    return {"report_path": str(report_path), **report}


def prepare_batch(
    *,
    gcl_path: Path,
    work_dir: Path,
    start: int = 1,
    end: int | None = None,
    model: str = "gpt-5.6-terra",
    reasoning_effort: str = "medium",
) -> dict[str, Any]:
    entries, duplicates = clean_and_read_gcl(gcl_path)
    last = end if end is not None else len(entries)
    if start < 1 or last < start or last > len(entries):
        raise PipelineError(
            f"Invalid range {start}-{last}; GCL has {len(entries)} entries"
        )
    selected = entries[start - 1 : last]
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / f"input_{start:06d}_{last:06d}.jsonl"
    manifest_path = work_dir / f"manifest_{start:06d}_{last:06d}.json"

    jsonl = "\n".join(
        json.dumps(make_request(entry, model, reasoning_effort), ensure_ascii=False)
        for entry in selected
    ) + "\n"
    atomic_write_text(input_path, jsonl)
    manifest = {
        "version": 1,
        "operation": "generate",
        "gcl_path": str(gcl_path.resolve()),
        "gcl_sha256": sha256_file(gcl_path),
        "input_path": str(input_path.resolve()),
        "input_sha256": sha256_file(input_path),
        "model": model,
        "reasoning_effort": reasoning_effort,
        "range": {"start": start, "end": last},
        "total_gcl_entries": len(entries),
        "duplicate_entries_removed": duplicates,
        "requests": [
            {
                "custom_id": entry.identity,
                "source_index": entry.source_index,
                "gcl_entry": entry.text,
            }
            for entry in selected
        ],
    }
    atomic_write_json(manifest_path, manifest)
    return {"manifest_path": str(manifest_path), **manifest}


def prepare_retry(
    *,
    manifest_path: Path,
    report_path: Path,
    work_dir: Path,
) -> dict[str, Any]:
    original = load_manifest(manifest_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    errors_by_id: dict[str, list[str]] = {}
    for finding in report.get("findings", []):
        custom_id = finding.get("custom_id")
        if not custom_id:
            continue
        errors = errors_by_id.setdefault(custom_id, [])
        for error in finding.get("errors", []):
            if error.startswith("no existing or generated card"):
                continue
            if error not in errors:
                errors.append(error)
    failed_ids = set(errors_by_id)
    failed_ids.discard(None)
    if not failed_ids:
        raise PipelineError("Generation report contains no failed cards to retry")
    request_by_id = {
        request["custom_id"]: request for request in original["requests"]
    }
    unknown = failed_ids - request_by_id.keys()
    if unknown:
        raise PipelineError(
            f"Generation report contains {len(unknown)} unknown custom_id value(s)"
        )
    selected = [
        request for request in original["requests"]
        if request["custom_id"] in failed_ids
    ]
    start = original["range"]["start"]
    end = original["range"]["end"]
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = work_dir / f"input_retry_{start:06d}_{end:06d}.jsonl"
    retry_manifest_path = work_dir / f"manifest_retry_{start:06d}_{end:06d}.json"
    entries = [
        GclEntry(request["source_index"], request["gcl_entry"])
        for request in selected
    ]
    if original.get("operation") == "normalize-readings":
        requests = [
            make_reading_request(
                entry, original["model"], original["reasoning_effort"]
            )
            for entry in entries
        ]
    else:
        base_output_value = report.get("output_path")
        if not base_output_value:
            raise PipelineError(
                "Generation report has no output_path; cannot construct an "
                "error-aware retry"
            )
        original_cards = parse_output(Path(base_output_value))
        missing_cards = failed_ids - original_cards.keys()
        if missing_cards:
            raise PipelineError(
                f"Base output is missing {len(missing_cards)} rejected card(s)"
            )
        requests = [
            make_repair_request(
                entry,
                original["model"],
                original["reasoning_effort"],
                original_cards[entry.identity],
                errors_by_id[entry.identity],
            )
            for entry in entries
        ]
    jsonl = "\n".join(
        json.dumps(request, ensure_ascii=False) for request in requests
    ) + "\n"
    atomic_write_text(input_path, jsonl)
    retry_manifest = {
        "version": 1,
        "operation": f'{original.get("operation", "generate")}-retry',
        "base_manifest_path": str(manifest_path.resolve()),
        "generation_report_path": str(report_path.resolve()),
        "gcl_path": original["gcl_path"],
        "gcl_sha256": original["gcl_sha256"],
        "input_path": str(input_path.resolve()),
        "input_sha256": sha256_file(input_path),
        "model": original["model"],
        "reasoning_effort": original["reasoning_effort"],
        "range": original["range"],
        "total_gcl_entries": original["total_gcl_entries"],
        "duplicate_entries_removed": [],
        "requests": [
            {
                **request,
                "validation_errors": errors_by_id[request["custom_id"]],
            }
            for request in selected
        ],
    }
    atomic_write_json(retry_manifest_path, retry_manifest)
    return {"manifest_path": str(retry_manifest_path), **retry_manifest}


def _read_output_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        record = json.loads(line)
        custom_id = record.get("custom_id")
        if not custom_id or custom_id in seen:
            raise PipelineError(
                f"Missing or duplicate custom_id in output line {line_number}"
            )
        seen.add(custom_id)
        records.append(record)
    return records


def merge_retry_output(
    *,
    base_output_path: Path,
    retry_manifest_path: Path,
    retry_output_path: Path,
    merged_output_path: Path,
) -> dict[str, Any]:
    retry_manifest = load_manifest(retry_manifest_path)
    retry_ids = {
        request["custom_id"] for request in retry_manifest["requests"]
    }
    base_records = _read_output_records(base_output_path)
    retry_records = _read_output_records(retry_output_path)
    retry_by_id = {record["custom_id"]: record for record in retry_records}
    missing = retry_ids - retry_by_id.keys()
    unexpected = retry_by_id.keys() - retry_ids
    base_ids = {record["custom_id"] for record in base_records}
    absent_from_base = retry_ids - base_ids
    if missing or unexpected or absent_from_base:
        raise PipelineError(
            "Retry reconciliation failed: "
            f"{len(missing)} missing retry result(s), "
            f"{len(unexpected)} unexpected retry result(s), "
            f"{len(absent_from_base)} absent from base output"
        )
    merged = [
        retry_by_id.get(record["custom_id"], record) for record in base_records
    ]
    atomic_write_text(
        merged_output_path,
        "\n".join(
            json.dumps(record, ensure_ascii=False) for record in merged
        ) + "\n",
    )
    return {
        "merged_output_path": str(merged_output_path.resolve()),
        "base_records": len(base_records),
        "replaced_records": len(retry_ids),
    }


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    input_path = Path(manifest["input_path"])
    if not input_path.exists():
        raise PipelineError(f"Prepared input file is missing: {input_path}")
    if sha256_file(input_path) != manifest["input_sha256"]:
        raise PipelineError("Prepared input file changed after manifest creation")
    return manifest


def submit_batch(
    manifest_path: Path,
    *,
    client: Any,
    confirm_cost: bool,
) -> dict[str, Any]:
    if not confirm_cost:
        raise PipelineError(
            "Submission can incur API charges; repeat with explicit cost confirmation"
        )
    manifest = load_manifest(manifest_path)
    input_path = Path(manifest["input_path"])
    with input_path.open("rb") as handle:
        uploaded = client.files.create(file=handle, purpose="batch")
    batch = client.batches.create(
        input_file_id=uploaded.id,
        endpoint=ENDPOINT,
        completion_window="24h",
        metadata={
            "operation": "japanese-vocabulary-generate",
            "range": (
                f'{manifest["range"]["start"]}-{manifest["range"]["end"]}'
            ),
        },
    )
    state = {
        "version": 1,
        "manifest_path": str(manifest_path.resolve()),
        "input_file_id": uploaded.id,
        "batch_id": batch.id,
        "status": getattr(batch, "status", "validating"),
        "output_file_id": None,
        "error_file_id": None,
    }
    state_path = manifest_path.with_name(
        manifest_path.name.replace("manifest_", "state_")
    )
    atomic_write_json(state_path, state)
    return {"state_path": str(state_path), **state}


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def refresh_status(state_path: Path, *, client: Any) -> dict[str, Any]:
    state = load_state(state_path)
    batch = client.batches.retrieve(state["batch_id"])
    state.update(
        {
            "status": batch.status,
            "output_file_id": getattr(batch, "output_file_id", None),
            "error_file_id": getattr(batch, "error_file_id", None),
            "request_counts": _as_plain(
                getattr(batch, "request_counts", None)
            ),
        }
    )
    atomic_write_json(state_path, state)
    return state


def _as_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool, list, dict)):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return {
            key: _as_plain(item)
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return str(value)


def _content_bytes(content: Any) -> bytes:
    if isinstance(content, bytes):
        return content
    if hasattr(content, "content"):
        raw = content.content
        return raw if isinstance(raw, bytes) else bytes(raw)
    if hasattr(content, "read"):
        raw = content.read()
        return raw if isinstance(raw, bytes) else raw.encode("utf-8")
    raise PipelineError("Unsupported file-content response from OpenAI client")


def collect_batch(state_path: Path, *, client: Any) -> dict[str, Any]:
    state = refresh_status(state_path, client=client)
    if state["status"] != "completed":
        raise PipelineError(f'Batch is not complete; status is {state["status"]}')
    output_path = state_path.with_name(
        state_path.name.replace("state_", "output_").replace(".json", ".jsonl")
    )
    atomic_write_text(
        output_path,
        _content_bytes(client.files.content(state["output_file_id"])).decode("utf-8"),
    )
    error_path = None
    if state.get("error_file_id"):
        error_path = state_path.with_name(
            state_path.name.replace("state_", "errors_").replace(".json", ".jsonl")
        )
        atomic_write_text(
            error_path,
            _content_bytes(client.files.content(state["error_file_id"])).decode(
                "utf-8"
            ),
        )
    state["output_path"] = str(output_path.resolve())
    state["error_path"] = str(error_path.resolve()) if error_path else None
    atomic_write_json(state_path, state)
    return state


def extract_response_text(body: dict[str, Any]) -> str:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    texts: list[str] = []
    for item in body.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(
                content.get("text"), str
            ):
                texts.append(content["text"])
    if not texts:
        raise PipelineError("Successful response contained no output text")
    return "".join(texts)


def parse_output(path: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        record = json.loads(line)
        custom_id = record.get("custom_id")
        if not custom_id or custom_id in results:
            raise PipelineError(
                f"Missing or duplicate custom_id in output line {line_number}"
            )
        if record.get("error"):
            raise PipelineError(f"Batch request {custom_id} failed: {record['error']}")
        response = record.get("response") or {}
        if response.get("status_code") != 200:
            raise PipelineError(
                f"Batch request {custom_id} returned HTTP "
                f"{response.get('status_code')}"
            )
        body = response.get("body") or {}
        parsed = json.loads(extract_response_text(body))
        # Outputs prepared before schema version 2 were flat. Accept them so a
        # rejected-only retry can be merged with an already-paid successful run.
        results[custom_id] = parsed.get("result", parsed)
    return results


def strip_tags(value: str) -> str:
    return TAG_RE.sub("", value)


def vocabulary_from_gcl(entry: str) -> str:
    value = READING_ANNOTATION_RE.sub("", entry)
    value = value.replace("(な)", "")
    if value.startswith("～"):
        value = value[1:]
    if value.endswith("～"):
        value = value[:-1]
    return value


def authoritative_reading_from_gcl(entry: str) -> str:
    match = READING_ANNOTATION_RE.search(entry)
    if not match:
        raise PipelineError(f"GCL entry has no authoritative reading: {entry}")
    return match.group(1)


def validate_resolved_gcl(expected_gcl: str, resolved_gcl: str) -> list[str]:
    if not resolved_gcl:
        return ["resolved_gcl_entry is empty"]
    errors: list[str] = []
    expected_vocabulary = vocabulary_from_gcl(expected_gcl)
    if vocabulary_from_gcl(resolved_gcl) != expected_vocabulary:
        errors.append("resolved_gcl_entry changes the written expression")
    bracket_count = resolved_gcl.count("[")
    if bracket_count != resolved_gcl.count("]") or bracket_count > 1:
        errors.append("resolved_gcl_entry has invalid reading brackets")
    annotation = READING_ANNOTATION_RE.search(resolved_gcl)
    if bracket_count and not annotation:
        errors.append(
            "resolved_gcl_entry reading must be a complete trailing annotation"
        )
    if annotation and not HIRAGANA_RE.fullmatch(annotation.group(1)):
        errors.append("resolved_gcl_entry reading annotation must be hiragana")
    if "(" in resolved_gcl or ")" in resolved_gcl:
        allowed = resolved_gcl.endswith("(な)") or re.search(
            r"\[[^\[\]]+\]\(な\)$", resolved_gcl
        )
        if not allowed:
            errors.append("resolved_gcl_entry uses parentheses outside the (な) marker")
    return errors


CONJUGATION_INITIALS = {
    "う": "わいうえおっ",
    "く": "かきくけこい",
    "ぐ": "がぎぐげごい",
    "す": "さしすせそ",
    "つ": "たちつてとっ",
    "ぬ": "なにぬねのん",
    "ぶ": "ばびぶべぼん",
    "む": "まみむめもん",
    "る": "らりるれろったてな",
}


def concealed_target_pattern(vocabulary: str) -> re.Pattern[str] | None:
    if vocabulary.endswith("する") and len(vocabulary) > 2:
        return re.compile(re.escape(vocabulary[:-2]) + r"[しすせさ]")
    ending = vocabulary[-1:] if vocabulary else ""
    initials = CONJUGATION_INITIALS.get(ending)
    stem = vocabulary[:-1]
    if initials and stem and re.search(r"[\u3400-\u4dbf\u4e00-\u9fff々]", stem):
        return re.compile(re.escape(stem) + f"[{initials}]")
    return None


def validate_card(card: dict[str, Any], expected_gcl: str) -> list[str]:
    errors: list[str] = []
    if card.get("status") != "card":
        errors.append(card.get("issue") or "entry requires editorial review")
        return errors
    if card.get("gcl_entry") != expected_gcl:
        errors.append("response gcl_entry does not match request")
    if card.get("resolved_gcl_entry") != expected_gcl:
        errors.append("resolved_gcl_entry must match the authoritative GCL entry")
    errors.extend(
        validate_resolved_gcl(
            expected_gcl, card.get("resolved_gcl_entry", "")
        )
    )
    reading = card.get("reading", "")
    plain_reading = strip_tags(reading)
    if not plain_reading or not HIRAGANA_RE.fullmatch(plain_reading):
        errors.append("reading must contain hiragana only after HTML removal")
    if reading.count("<b>") != reading.count("</b>") or "<b>" not in reading:
        errors.append("reading must contain balanced bold markup")
    definition = card.get("definition", "")
    examples = card.get("examples", [])
    vocabulary = card.get("vocabulary", "")
    expected_vocabulary = vocabulary_from_gcl(
        card.get("resolved_gcl_entry") or expected_gcl
    )
    if vocabulary != expected_vocabulary:
        errors.append("vocabulary does not match annotation-free GCL entry")
    if not definition:
        errors.append("definition is empty")
    if not isinstance(examples, list) or not 1 <= len(examples) <= 5:
        errors.append("examples must contain one to five items")
    elif any(not isinstance(example, str) or not example.strip() for example in examples):
        errors.append("examples must be non-empty strings")
    if isinstance(examples, list) and 1 <= len(examples) <= 5:
        rationale = card.get("example_count_rationale", "")
        if len(examples) == 3:
            if rationale:
                errors.append(
                    "example_count_rationale must be empty for the preferred "
                    "three-example count"
                )
        elif not isinstance(rationale, str) or not rationale.strip():
            errors.append(
                "a non-three example count requires example_count_rationale"
            )
    if vocabulary:
        front_values = {
            "reading": reading,
            "definition": definition,
            "examples": "\n".join(examples) if isinstance(examples, list) else "",
        }
        for field_name, value in front_values.items():
            if vocabulary in value:
                errors.append(f"{field_name} reveals the written vocabulary")
        inflected_pattern = concealed_target_pattern(vocabulary)
        if inflected_pattern:
            for field_name, value in front_values.items():
                if inflected_pattern.search(value):
                    errors.append(
                        f"{field_name} reveals an inflected written target"
                    )
    return errors


def deterministic_guid(gcl_entry: str) -> str:
    return uuid.uuid5(
        uuid.UUID("867c9bb2-b47e-5c77-b80c-bf10b8b65c52"), gcl_entry
    ).hex[:16]


def apply_results(
    *,
    manifest_path: Path,
    output_path: Path,
    template_path: Path,
    deck_output_path: Path,
    allow_partial: bool = False,
) -> dict[str, Any]:
    if deck_output_path.parent.name != deck_output_path.stem:
        raise PipelineError(
            "CrowdAnki output must be inside a directory with the same base name "
            "as the JSON file"
        )
    manifest = load_manifest(manifest_path)
    if not allow_partial and len(manifest["requests"]) != manifest["total_gcl_entries"]:
        raise PipelineError(
            "Manifest covers only part of the GCL; use a complete manifest or "
            "explicitly allow a partial proof deck"
        )
    results = parse_output(output_path)
    expected_ids = {item["custom_id"] for item in manifest["requests"]}
    missing = expected_ids - results.keys()
    unexpected = results.keys() - expected_ids
    if missing or unexpected:
        raise PipelineError(
            f"Output reconciliation failed: {len(missing)} missing, "
            f"{len(unexpected)} unexpected"
        )

    cards: list[tuple[dict[str, Any], dict[str, Any]]] = []
    findings: list[dict[str, Any]] = []
    for request in manifest["requests"]:
        card = results[request["custom_id"]]
        errors = validate_card(card, request["gcl_entry"])
        if card.get("additional_gcl_entries"):
            errors.append(
                "additional readings require GCL append and a subsequent batch"
            )
        if errors:
            findings.append(
                {
                    "custom_id": request["custom_id"],
                    "source_index": request["source_index"],
                    "gcl_entry": request["gcl_entry"],
                    "errors": errors,
                }
            )
        else:
            cards.append((request, card))

    report_path = deck_output_path.with_suffix(".generation-report.json")
    report = {
        "operation": "generate",
        "manifest_path": str(manifest_path.resolve()),
        "output_path": str(output_path.resolve()),
        "requested": len(manifest["requests"]),
        "valid_cards": len(cards),
        "failed_cards": len(findings),
        "published": False,
        "findings": findings,
    }
    if findings:
        atomic_write_json(report_path, report)
        raise PipelineError(
            f"{len(findings)} card(s) failed validation; see {report_path}"
        )

    deck = json.loads(template_path.read_text(encoding="utf-8-sig"))
    note_models = deck.get("note_models") or []
    if not note_models or not note_models[0].get("crowdanki_uuid"):
        raise PipelineError("Template does not contain a usable note model")
    note_model_uuid = note_models[0]["crowdanki_uuid"]
    deck["notes"] = []
    for request, card in cards:
        examples_html = "\n".join(
            f"<div>{example}</div>" for example in card["examples"]
        )
        deck["notes"].append(
            {
                "__type__": "Note",
                "fields": [
                    card["reading"],
                    card["definition"],
                    examples_html,
                    card["vocabulary"],
                ],
                "guid": deterministic_guid(
                    card.get("resolved_gcl_entry") or request["gcl_entry"]
                ),
                "note_model_uuid": note_model_uuid,
                "tags": [],
            }
        )
    atomic_write_json(deck_output_path, deck)
    report["published"] = True
    report["deck_output_path"] = str(deck_output_path.resolve())
    atomic_write_json(report_path, report)
    return report


def apply_update(
    *,
    manifest_path: Path,
    output_path: Path,
    deck_path: Path,
    through: int,
) -> dict[str, Any]:
    if deck_path.parent.name != deck_path.stem:
        raise PipelineError(
            "CrowdAnki output must be inside a directory with the same base name "
            "as the JSON file"
        )
    manifest = load_manifest(manifest_path)
    gcl_path = Path(manifest["gcl_path"])
    if sha256_file(gcl_path) != manifest["gcl_sha256"]:
        raise PipelineError("GCL changed after the generation batch was prepared")
    entries, _ = clean_and_read_gcl(gcl_path)
    if through < 1 or through > len(entries):
        raise PipelineError(
            f"Invalid update boundary {through}; GCL has {len(entries)} entries"
        )
    desired = entries[:through]
    desired_by_id = {entry.identity: entry for entry in desired}
    all_by_key: dict[tuple[str, str], list[GclEntry]] = {}
    for entry in entries:
        key = (
            vocabulary_from_gcl(entry.text),
            authoritative_reading_from_gcl(entry.text),
        )
        all_by_key.setdefault(key, []).append(entry)

    deck = json.loads(deck_path.read_text(encoding="utf-8-sig"))
    notes = deck.get("notes")
    if not isinstance(notes, list):
        raise PipelineError("Existing deck does not contain a notes array")
    existing_by_id: dict[str, dict[str, Any]] = {}
    removed_duplicates: list[dict[str, Any]] = []
    scheduled_removals: list[dict[str, Any]] = []
    unmatchable: list[dict[str, Any]] = []
    for position, note in enumerate(notes, start=1):
        fields = note.get("fields") if isinstance(note, dict) else None
        if not isinstance(fields, list) or len(fields) != 4:
            unmatchable.append(
                {"note_position": position, "reason": "expected four fields"}
            )
            continue
        key = (fields[3], strip_tags(fields[0]))
        candidates = all_by_key.get(key, [])
        if len(candidates) != 1:
            unmatchable.append(
                {
                    "note_position": position,
                    "vocabulary": fields[3],
                    "reading": strip_tags(fields[0]),
                    "reason": f"matched {len(candidates)} GCL entries",
                }
            )
            continue
        entry = candidates[0]
        if entry.identity not in desired_by_id:
            scheduled_removals.append(
                {
                    "note_position": position,
                    "gcl_entry": entry.text,
                    "reason": f"outside requested prefix 1-{through}",
                }
            )
            continue
        if entry.identity in existing_by_id:
            removed_duplicates.append(
                {"note_position": position, "gcl_entry": entry.text}
            )
            continue
        existing_by_id[entry.identity] = note
    if unmatchable:
        raise PipelineError(
            f"{len(unmatchable)} existing note(s) could not be matched safely"
        )

    results = parse_output(output_path)
    request_by_id = {
        request["custom_id"]: request for request in manifest["requests"]
    }
    result_ids = set(results)
    request_ids = set(request_by_id)
    if result_ids != request_ids:
        raise PipelineError(
            f"Output reconciliation failed: {len(request_ids - result_ids)} "
            f"missing, {len(result_ids - request_ids)} unexpected"
        )
    generated_by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    findings: list[dict[str, Any]] = []
    for custom_id, request in request_by_id.items():
        entry = desired_by_id.get(custom_id)
        if entry is None or request["gcl_entry"] != entry.text:
            findings.append(
                {
                    **request,
                    "errors": ["generated entry is outside the requested prefix"],
                }
            )
            continue
        card = results[custom_id]
        errors = validate_card(card, entry.text)
        if card.get("additional_gcl_entries"):
            errors.append("fully annotated GCL responses cannot add readings")
        if custom_id in existing_by_id:
            errors.append("generated output would duplicate an existing note")
        if errors:
            findings.append({**request, "errors": errors})
        else:
            generated_by_id[custom_id] = (request, card)

    missing_ids = (
        set(desired_by_id) - set(existing_by_id) - set(generated_by_id)
    )
    if missing_ids:
        findings.extend(
            {
                "custom_id": custom_id,
                "source_index": desired_by_id[custom_id].source_index,
                "gcl_entry": desired_by_id[custom_id].text,
                "errors": ["no existing or generated card for requested entry"],
            }
            for custom_id in sorted(missing_ids)
        )

    report_path = deck_path.with_suffix(".update-report.json")
    report = {
        "operation": "update",
        "manifest_path": str(manifest_path.resolve()),
        "output_path": str(output_path.resolve()),
        "deck_path": str(deck_path.resolve()),
        "through": through,
        "preserved": len(existing_by_id),
        "added": len(generated_by_id),
        "removed": len(scheduled_removals) + len(removed_duplicates),
        "scheduled_removals": scheduled_removals,
        "duplicate_notes_removed": removed_duplicates,
        "findings": findings,
        "published": False,
    }
    if findings:
        atomic_write_json(report_path, report)
        raise PipelineError(
            f"{len(findings)} update finding(s) require review; see {report_path}"
        )

    note_models = deck.get("note_models") or []
    if not note_models or not note_models[0].get("crowdanki_uuid"):
        raise PipelineError("Existing deck does not contain a usable note model")
    note_model_uuid = note_models[0]["crowdanki_uuid"]
    proposed_notes: list[dict[str, Any]] = []
    for entry in desired:
        preserved = existing_by_id.get(entry.identity)
        if preserved is not None:
            proposed_notes.append(preserved)
            continue
        _, card = generated_by_id[entry.identity]
        proposed_notes.append(
            {
                "__type__": "Note",
                "fields": [
                    card["reading"],
                    card["definition"],
                    "\n".join(
                        f"<div>{example}</div>" for example in card["examples"]
                    ),
                    card["vocabulary"],
                ],
                "guid": deterministic_guid(entry.text),
                "note_model_uuid": note_model_uuid,
                "tags": [],
            }
        )
    deck["notes"] = proposed_notes
    atomic_write_json(deck_path, deck)
    report["published"] = True
    report["final_notes"] = len(proposed_notes)
    atomic_write_json(report_path, report)
    return {"report_path": str(report_path), **report}


def read_dotenv_api_key(env_path: Path = Path(".env")) -> str:
    if not env_path.is_file():
        raise PipelineError(
            f"Required credential file is missing: {env_path}. "
            "Copy .env.example to .env and populate OPENAI_API_KEY."
        )
    values: list[str] = []
    for line_number, raw_line in enumerate(
        env_path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise PipelineError(
                f"Invalid .env syntax on line {line_number}: expected KEY=VALUE"
            )
        key, value = line.split("=", 1)
        if key.strip() != "OPENAI_API_KEY":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values.append(value.strip())
    if len(values) != 1:
        raise PipelineError(
            ".env must contain exactly one OPENAI_API_KEY assignment"
        )
    api_key = values[0]
    lowered = api_key.lower()
    if (
        not api_key
        or "replace" in lowered
        or "your-api-key" in lowered
        or api_key == "sk-..."
    ):
        raise PipelineError(
            "OPENAI_API_KEY in .env is empty or still contains a placeholder"
        )
    return api_key


def make_openai_client(env_path: Path = Path(".env")) -> Any:
    api_key = read_dotenv_api_key(env_path)
    try:
        from openai import OpenAI
    except ImportError as error:
        raise PipelineError(
            "The openai package is required for submit, status, and collect. "
            "Install the project with: python -m pip install -e ."
        ) from error
    return OpenAI(api_key=api_key)
