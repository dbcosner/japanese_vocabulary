from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ENDPOINT = "/v1/responses"
SCHEMA_NAME = "japanese_vocabulary_card"
TERMINAL_STATUSES = {"completed", "failed", "expired", "cancelled"}
HIRAGANA_RE = re.compile(r"^[\u3040-\u309fー]+$")
KANJI_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff々]")
TAG_RE = re.compile(r"<[^>]+>")
READING_ANNOTATION_RE = re.compile(r"\[([^\[\]]+)\]$")


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class GclEntry:
    source_index: int
    text: str

    @property
    def identity(self) -> str:
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:12]
        return f"gcl-{self.source_index:06d}-{digest}"


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


def clean_and_read_gcl(path: Path) -> tuple[list[GclEntry], list[dict[str, Any]]]:
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
    return entries, duplicate_report


def card_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["card", "needs_review"]},
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
                "minItems": 0,
                "maxItems": 5,
            },
            "example_count_rationale": {"type": "string"},
            "vocabulary": {"type": "string"},
        },
        "required": [
            "status",
            "issue",
            "gcl_entry",
            "resolved_gcl_entry",
            "additional_gcl_entries",
            "reading",
            "definition",
            "examples",
            "example_count_rationale",
            "vocabulary",
        ],
        "additionalProperties": False,
    }


def generation_instructions() -> str:
    return """You generate one Japanese vocabulary card for an advanced learner.
Return only the required JSON object.

Apply these rules:
- Honor an authoritative [reading]. Remove all GCL annotations from vocabulary.
- If an unannotated expression has several useful contemporary readings, use the
  most common one and list the remaining qualifying annotated entries in
  additional_gcl_entries. Exclude archaic, uncommon, compound-only, or unnatural
  readings. Return needs_review when a reliable decision is impossible.
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
        results[custom_id] = json.loads(extract_response_text(body))
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


def validate_card(card: dict[str, Any], expected_gcl: str) -> list[str]:
    errors: list[str] = []
    if card.get("status") != "card":
        errors.append(card.get("issue") or "entry requires editorial review")
        return errors
    if card.get("gcl_entry") != expected_gcl:
        errors.append("response gcl_entry does not match request")
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
        for target_kanji in set(KANJI_RE.findall(vocabulary)):
            for field_name, value in front_values.items():
                if target_kanji in value:
                    errors.append(
                        f"{field_name} contains target kanji {target_kanji}"
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
