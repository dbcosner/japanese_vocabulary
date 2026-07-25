from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
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
        digest = hashlib.sha256(
            identity_compatibility_text(self.text).encode("utf-8")
        ).hexdigest()[:20]
        return f"gcl-{digest}"


GCL_FILENAME_SUFFIX = "_generation_control_file.txt"
FIELD_SEPARATOR = "\x1f"


def identity_compatibility_text(gcl_entry: str) -> str:
    """Keep identifiers stable across the U+FF5E to U+007E syntax migration."""
    return gcl_entry.replace("~", "～")


def _plain_anki_field(value: str) -> str:
    value = re.sub(r"\[sound:[^\]]+\]", "", value, flags=re.IGNORECASE)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    value = TAG_RE.sub("", value)
    return html.unescape(value).strip()


def _first_anki_field_line(value: str) -> str:
    first_line = re.split(
        r"<br\s*/?>|</?div\b[^>]*>",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return _plain_anki_field(first_line)


def _gcl_output_path(name: str, output_dir: Path) -> Path:
    if not name or Path(name).name != name:
        raise PipelineError("GCL name must be a filename or portable deck name")
    filename = name if name.endswith(GCL_FILENAME_SUFFIX) else (
        f"{name}{GCL_FILENAME_SUFFIX}"
    )
    deck_name = filename[: -len(GCL_FILENAME_SUFFIX)]
    if not deck_name:
        raise PipelineError("GCL name must not be empty")
    return output_dir / filename


def import_apkg(
    apkg_path: Path,
    gcl_name: str,
    output_dir: Path = Path("gcl"),
    *,
    decisions_path: Path | None = None,
    replace: bool = False,
) -> dict[str, Any]:
    """Create a proposed version-1 GCL and an import-review report from APKG."""
    if apkg_path.suffix.lower() != ".apkg":
        raise PipelineError(f"Import source must be an .apkg file: {apkg_path}")
    if not apkg_path.is_file():
        raise PipelineError(f"APKG file not found: {apkg_path}")

    output_path = _gcl_output_path(gcl_name, output_dir)
    review_path = output_path.with_suffix(".import-review.json")
    if output_path.exists() and not replace:
        raise PipelineError(f"Refusing to overwrite existing GCL: {output_path}")
    decisions: dict[str, Any] = {}
    if decisions_path is not None:
        decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    rules = decisions.get("rules", {})
    overrides = decisions.get("note_overrides", {})

    try:
        with zipfile.ZipFile(apkg_path) as package:
            collection_name = next(
                (
                    name
                    for name in (
                        "collection.anki21b",
                        "collection.anki21",
                        "collection.anki2",
                    )
                    if name in package.namelist()
                ),
                None,
            )
            if collection_name is None:
                raise PipelineError("APKG does not contain an Anki collection database")
            collection_bytes = package.read(collection_name)
            if collection_name.endswith("21b"):
                try:
                    import zstandard
                except ImportError as error:
                    raise PipelineError(
                        "Modern APKG import requires the 'zstandard' package"
                    ) from error
                with zstandard.ZstdDecompressor().stream_reader(
                    io.BytesIO(collection_bytes)
                ) as reader:
                    collection_bytes = reader.read()
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise PipelineError(f"Could not read APKG: {error}") from error

    fd, database_name = tempfile.mkstemp(suffix=".anki2")
    os.close(fd)
    database_path = Path(database_name)
    try:
        database_path.write_bytes(collection_bytes)
        connection = sqlite3.connect(database_path)
        try:
            model_row = connection.execute("SELECT models FROM col").fetchone()
            if not model_row:
                raise PipelineError("Anki collection has no note models")
            if model_row[0]:
                models = json.loads(model_row[0])
            else:
                models = {}
                for model_id, ordinal, field_name in connection.execute(
                    "SELECT ntid, ord, name FROM fields ORDER BY ntid, ord"
                ):
                    model = models.setdefault(str(model_id), {"flds": []})
                    while len(model["flds"]) <= ordinal:
                        model["flds"].append({"name": ""})
                    model["flds"][ordinal] = {"name": field_name}
            notes = connection.execute(
                "SELECT id, mid, flds FROM notes ORDER BY id"
            ).fetchall()
        finally:
            connection.close()
    except (sqlite3.Error, json.JSONDecodeError, OSError) as error:
        raise PipelineError(f"Could not read Anki collection database: {error}") from error
    finally:
        database_path.unlink(missing_ok=True)

    field_aliases = {
        "vocabulary": ("vocabulary", "expression", "word", "term", "front"),
        "reading": ("reading", "kana", "pronunciation"),
    }
    model_fields: dict[int, tuple[int, int]] = {}
    for model_id, model in models.items():
        names = [
            str(field.get("name", "")).strip().casefold()
            for field in model.get("flds", [])
        ]
        vocabulary_index = next(
            (names.index(alias) for alias in field_aliases["vocabulary"] if alias in names),
            0,
        )
        reading_index = next(
            (names.index(alias) for alias in field_aliases["reading"] if alias in names),
            1 if len(names) > 1 else -1,
        )
        model_fields[int(model_id)] = (vocabulary_index, reading_index)

    proposed_primary: list[tuple[int, int, str]] = []
    proposed_additional: list[tuple[int, int, str]] = []
    review_items: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []

    def review(
        note_position: int,
        note_id: int,
        reason: str,
        vocabulary: str,
        source_reading: str,
    ) -> None:
        review_items.append(
            {
                "note_position": note_position,
                "note_id": note_id,
                "reason": reason,
                "vocabulary": vocabulary,
                "source_reading": source_reading,
            }
        )

    def make_entry(vocabulary: str, reading: str) -> str | None:
        vocabulary = re.sub(r"\s+", " ", vocabulary).strip()
        vocabulary = vocabulary.replace("～", "~").replace("〜", "~")
        reading = re.sub(r"\s+", "", reading)
        reading = reading.replace("～", "~").replace("〜", "~").strip("~")
        na_marker = ""
        if vocabulary.endswith(("（な）", "(な)")):
            vocabulary = vocabulary[:-3]
            na_marker = "(な)"
        elif vocabulary.endswith("な"):
            vocabulary = vocabulary[:-1]
            if reading.endswith("な"):
                reading = reading[:-1]
            na_marker = "(な)"
        if reading.endswith(("（な）", "(な)")):
            reading = reading[:-3]
            na_marker = "(な)"
        if not vocabulary:
            return None
        if HIRAGANA_RE.fullmatch(reading):
            return f"{vocabulary}[{reading}]{na_marker}"
        return f"{vocabulary}{na_marker}"

    for note_position, (note_id, model_id, encoded_fields) in enumerate(notes, start=1):
        fields = encoded_fields.split(FIELD_SEPARATOR)
        indices = model_fields.get(model_id)
        if indices is None:
            raise PipelineError(f"Note {note_id} references unknown model {model_id}")
        vocabulary_index, reading_index = indices
        if vocabulary_index >= len(fields) or reading_index < 0 or reading_index >= len(fields):
            raise PipelineError(f"Note {note_id} does not contain vocabulary and reading fields")
        vocabulary_field = fields[vocabulary_index]
        reading_field = fields[reading_index]
        vocabulary = _plain_anki_field(vocabulary_field)
        raw_reading = re.sub(r"\s+", "", _first_anki_field_line(reading_field))
        override = overrides.get(str(note_id), ...)
        if override is not ...:
            review(
                note_position,
                note_id,
                "explicit per-import decision",
                vocabulary,
                raw_reading,
            )
            if override is not None:
                for entry in override:
                    proposed_primary.append((note_position, note_id, entry))
            continue

        possible_swapped_reading = re.sub(
            r"\s+", "", _first_anki_field_line(vocabulary_field)
        )
        possible_swapped_vocabulary = _plain_anki_field(reading_field)
        if (
            (not vocabulary or "\n" in vocabulary)
            and HIRAGANA_RE.fullmatch(possible_swapped_reading)
            and possible_swapped_vocabulary
            and "\n" not in possible_swapped_vocabulary
        ):
            vocabulary = possible_swapped_vocabulary
            raw_reading = possible_swapped_reading

        if not vocabulary or "\n" in vocabulary:
            review(
                note_position, note_id, "empty or multiline expression",
                vocabulary, raw_reading
            )
            continue

        has_unsupported_parenthetical = bool(
            re.search(r"（(?!な）)[^）]*）|\((?!な\))[^)]*\)", vocabulary)
            or re.search(r"（(?!な）)[^）]*）|\((?!な\))[^)]*\)", raw_reading)
        )
        if has_unsupported_parenthetical:
            if rules.get("strip_parentheticals_except_na"):
                vocabulary = re.sub(r"（(?!な）)[^）]*）|\((?!な\))[^)]*\)", "", vocabulary)
                raw_reading = re.sub(r"（(?!な）)[^）]*）|\((?!な\))[^)]*\)", "", raw_reading)
            else:
                review(
                    note_position, note_id, "unsupported parenthetical text",
                    vocabulary, raw_reading
                )
                continue

        editorial_pattern = re.compile(
            r"\s*(?:\((?:onyomi|kunyomi|irregular reading)\)|"
            r"[「（](?:音読み|訓読み)[」）]|-?\s*2 versions)\s*",
            re.IGNORECASE,
        )
        had_editorial_label = bool(editorial_pattern.search(vocabulary))
        had_version_instruction = bool(
            re.search(r"-?\s*2 versions", vocabulary, re.IGNORECASE)
        )
        if had_editorial_label:
            if rules.get("strip_editorial_labels"):
                vocabulary = editorial_pattern.sub("", vocabulary).strip()
            else:
                review(
                    note_position, note_id, "editorial label in expression",
                    vocabulary, raw_reading
                )
                continue

        vocabulary = vocabulary.replace("～", "~").replace("〜", "~")
        raw_reading = raw_reading.replace("～", "~").replace("〜", "~")

        if "⇔" in vocabulary:
            if not rules.get("split_comparisons"):
                review(
                    note_position, note_id, "multiple contrasted expressions",
                    vocabulary, raw_reading
                )
                continue
            expressions = [value.strip() for value in vocabulary.split("⇔")]
            readings = [value.strip() for value in raw_reading.split("⇔")]
            if not raw_reading:
                readings = [""] * len(expressions)
            if len(expressions) != len(readings):
                review(
                    note_position, note_id, "comparison sides do not align",
                    vocabulary, raw_reading
                )
                continue
            for expression, reading in zip(expressions, readings, strict=True):
                entry = make_entry(expression, reading)
                if entry:
                    proposed_primary.append((note_position, note_id, entry))
            if not raw_reading:
                review(
                    note_position, note_id, "split comparison has no readings",
                    vocabulary, raw_reading
                )
            continue

        if re.search(r"\s[/／]\s", vocabulary):
            if not rules.get("split_equivalent_spellings"):
                review(
                    note_position, note_id, "multiple written forms",
                    vocabulary, raw_reading
                )
                continue
            for expression in re.split(r"\s+[/／]\s+", vocabulary):
                entry = make_entry(expression, raw_reading)
                if entry:
                    proposed_primary.append((note_position, note_id, entry))
            continue

        reading_parts = re.split(r"[;；・]", raw_reading)
        slash_parts = re.split(r"[／/]", raw_reading)
        has_multiple_readings = len(reading_parts) > 1 or len(slash_parts) > 1
        is_affix = vocabulary.startswith("~") or vocabulary.endswith("~")
        if has_multiple_readings and not (is_affix and len(slash_parts) > 1):
            entry = make_entry(vocabulary, "")
            if entry:
                proposed_primary.append((note_position, note_id, entry))
            review(
                note_position, note_id, "multiple proposed readings",
                vocabulary, raw_reading
            )
            continue

        if is_affix and len(slash_parts) > 1:
            for index, reading in enumerate(slash_parts):
                entry = make_entry(vocabulary, reading)
                if entry:
                    target = proposed_primary if index == 0 else proposed_additional
                    target.append((note_position, note_id, entry))
            continue

        entry = make_entry(vocabulary, "" if had_version_instruction else raw_reading)
        if entry is None:
            review(
                note_position, note_id, "empty expression after normalization",
                vocabulary, raw_reading
            )
            continue
        proposed_primary.append((note_position, note_id, entry))
        if "[" not in entry:
            review(
                note_position, note_id, "missing or unusable reading",
                vocabulary, raw_reading
            )

    entries: list[str] = []
    seen: set[str] = set()
    for note_position, note_id, entry in proposed_primary + proposed_additional:
        if entry in seen:
            duplicate = {
                "note_position": note_position, "note_id": note_id, "entry": entry
            }
            duplicates.append(duplicate)
            review_items.append({**duplicate, "reason": "exact duplicate"})
            continue
        seen.add(entry)
        entries.append(entry)

    if not entries:
        raise PipelineError("APKG contains no importable vocabulary notes")
    atomic_write_text(
        output_path,
        "# GCL Version: 1\n\n" + "\n".join(entries) + "\n",
    )
    report = {
        "source": str(apkg_path.resolve()),
        "gcl_path": str(output_path.resolve()),
        "review_path": str(review_path.resolve()),
        "decisions_path": (
            str(decisions_path.resolve()) if decisions_path is not None else None
        ),
        "source_notes": len(notes),
        "entries": len(entries),
        "duplicates_removed": duplicates,
        "review_items": review_items,
    }
    atomic_write_json(review_path, report)
    return report


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


def migrate_gcl_syntax(gcl_path: Path, workspace_path: Path) -> dict[str, Any]:
    """Migrate canonical GCL syntax without changing cache identities or GUIDs."""
    project_path = workspace_path / "project.json"
    manifest_path = workspace_path / "generate-manifest.json"
    accepted_path = workspace_path / "cards" / "accepted.jsonl"
    required = (gcl_path, project_path, manifest_path, accepted_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise PipelineError(f"Migration input is missing: {', '.join(missing)}")

    original_gcl = gcl_path.read_text(encoding="utf-8-sig")
    old_gcl_sha = hashlib.sha256(gcl_path.read_bytes()).hexdigest()
    project = json.loads(project_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if Path(project["gcl_path"]).resolve() != gcl_path.resolve():
        raise PipelineError("Workspace belongs to another GCL")
    if project.get("gcl_sha256") != old_gcl_sha:
        raise PipelineError("Project GCL hash does not match the migration input")
    if manifest.get("gcl_sha256") != old_gcl_sha:
        raise PipelineError("Generate manifest GCL hash does not match the migration input")

    old_to_new: dict[str, str] = {}
    new_lines: list[str] = []
    for raw_line in original_gcl.splitlines():
        line = raw_line
        if line.strip() and not line.strip().startswith("#"):
            line = (
                line.replace("～", "~")
                .replace("〜", "~")
                .replace("（な）", "(な)")
            )
            if line != raw_line:
                old_to_new[raw_line.strip()] = line.strip()
        new_lines.append(line)
    if not old_to_new:
        raise PipelineError("GCL has no legacy syntax to migrate")
    new_gcl_text = "\n".join(new_lines).rstrip() + "\n"

    for old_entry, new_entry in old_to_new.items():
        if GclEntry(0, old_entry).identity != GclEntry(0, new_entry).identity:
            raise PipelineError(f"Migration would change cache identity: {old_entry}")
        if deterministic_guid(old_entry) != deterministic_guid(new_entry):
            raise PipelineError(f"Migration would change generated GUID: {old_entry}")

    records = list(_read_output_records(accepted_path))
    for record in records:
        try:
            output_text = record["response"]["body"]["output"][0]["content"][0]["text"]
            payload = json.loads(output_text)
            card = payload.get("result", payload)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            raise PipelineError(
                f"Could not migrate cached record {record.get('custom_id')}"
            ) from error
        old_entry = card.get("gcl_entry")
        if old_entry in old_to_new:
            new_entry = old_to_new[old_entry]
            card["gcl_entry"] = new_entry
            if card.get("resolved_gcl_entry") == old_entry:
                card["resolved_gcl_entry"] = new_entry
            record["response"]["body"]["output"][0]["content"][0]["text"] = (
                json.dumps(payload, ensure_ascii=False)
            )

    accepted_text = (
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n"
    )
    new_gcl_sha = hashlib.sha256(new_gcl_text.encode("utf-8")).hexdigest()
    accepted_sha = hashlib.sha256(accepted_text.encode("utf-8")).hexdigest()
    project["gcl_sha256"] = new_gcl_sha
    manifest["gcl_sha256"] = new_gcl_sha
    manifest["input_sha256"] = accepted_sha
    for request in manifest.get("requests", []):
        request["gcl_entry"] = old_to_new.get(
            request.get("gcl_entry"), request.get("gcl_entry")
        )

    entry_lines = [
        line.strip()
        for line in new_gcl_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    entries = [GclEntry(index, line) for index, line in enumerate(entry_lines, 1)]
    if len(entries) != len(records):
        raise PipelineError(
            f"Migration count mismatch: {len(entries)} entries, {len(records)} records"
        )
    current_by_id = {entry.identity: entry for entry in entries}
    cards = parse_output_records(records)
    findings: list[dict[str, Any]] = []
    for custom_id, entry in current_by_id.items():
        card = cards.get(custom_id)
        errors = (
            ["cached card is missing"]
            if card is None
            else validate_card(card, entry.text)
        )
        if errors:
            findings.append(
                {"custom_id": custom_id, "gcl_entry": entry.text, "errors": errors}
            )
    if findings:
        raise PipelineError(
            f"Migration validation failed for {len(findings)} cached record(s)"
        )

    backup_dir = workspace_path / "migration-backups" / old_gcl_sha[:12]
    if backup_dir.exists():
        raise PipelineError(f"Migration backup already exists: {backup_dir}")
    backup_dir.mkdir(parents=True)
    for source in required:
        shutil.copy2(source, backup_dir / source.name)

    atomic_write_text(gcl_path, new_gcl_text)
    atomic_write_text(accepted_path, accepted_text)
    atomic_write_json(project_path, project)
    atomic_write_json(manifest_path, manifest)
    return {
        "gcl_path": str(gcl_path.resolve()),
        "workspace": str(workspace_path.resolve()),
        "entries": len(entries),
        "cache_records": len(records),
        "syntax_entries_migrated": len(old_to_new),
        "identities_preserved": len(old_to_new),
        "generated_guids_preserved": len(old_to_new),
        "old_gcl_sha256": old_gcl_sha,
        "new_gcl_sha256": new_gcl_sha,
        "accepted_sha256": accepted_sha,
        "backup_dir": str(backup_dir.resolve()),
    }


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
    normalized = False

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            cleaned_lines.append(raw_line)
            continue
        canonical_line = (
            line.replace("～", "~").replace("〜", "~").replace("（な）", "(な)")
        )
        if canonical_line != line:
            normalized = True
        line = canonical_line
        if line in seen:
            duplicate_report.append({"line": line_number, "entry": line})
            continue
        seen.add(line)
        cleaned_lines.append(line)
        entries.append(GclEntry(len(entries) + 1, line))

    if duplicate_report or normalized:
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


def _project_key(deck_path: Path) -> str:
    name = deck_path.stem
    if name.endswith("_deck"):
        name = name[: -len("_deck")]
    key = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_").lower()
    if not key:
        raise PipelineError(f"Cannot derive a project name from deck path: {deck_path}")
    return key


def _population_workspace(batch_root: Path, deck_path: Path) -> Path:
    return batch_root / _project_key(deck_path)


def _write_population_batch(
    *,
    entries: list[GclEntry],
    all_entries: list[GclEntry],
    gcl_path: Path,
    work_dir: Path,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    start = entries[0].source_index
    end = entries[-1].source_index
    input_path = work_dir / f"input_{start:06d}_{end:06d}.jsonl"
    manifest_path = work_dir / f"manifest_{start:06d}_{end:06d}.json"
    atomic_write_text(
        input_path,
        "\n".join(
            json.dumps(make_request(entry, model, reasoning_effort), ensure_ascii=False)
            for entry in entries
        )
        + "\n",
    )
    manifest = {
        "version": 2,
        "operation": "populate",
        "gcl_path": str(gcl_path.resolve()),
        "gcl_sha256": sha256_file(gcl_path),
        "input_path": str(input_path.resolve()),
        "input_sha256": sha256_file(input_path),
        "model": model,
        "reasoning_effort": reasoning_effort,
        "range": {"start": start, "end": end},
        "total_gcl_entries": len(all_entries),
        "duplicate_entries_removed": [],
        "requests": [
            {
                "custom_id": entry.identity,
                "source_index": entry.source_index,
                "gcl_entry": entry.text,
            }
            for entry in entries
        ],
    }
    atomic_write_json(manifest_path, manifest)
    return {"manifest_path": str(manifest_path.resolve()), **manifest}


def prepare_population(
    *,
    gcl_path: Path,
    deck_path: Path,
    batch_root: Path = Path(".batch"),
    batch_size: int = 100,
    model: str = "gpt-5.6-terra",
    reasoning_effort: str = "medium",
) -> dict[str, Any]:
    """Create or refresh the durable population workspace for a GCL/deck pair."""
    if batch_size < 1:
        raise PipelineError("Batch size must be positive")
    if deck_path.suffix.lower() != ".apkg":
        raise PipelineError("Deck output must be an .apkg file")
    entries, duplicates = clean_and_read_gcl(gcl_path)
    workspace = _population_workspace(batch_root, deck_path)
    cards_dir = workspace / "cards"
    batches_dir = workspace / "batches"
    accepted_path = cards_dir / "accepted.jsonl"
    project_path = workspace / "project.json"

    if project_path.exists():
        project = json.loads(project_path.read_text(encoding="utf-8"))
        if Path(project["gcl_path"]).resolve() != gcl_path.resolve():
            raise PipelineError(
                f"Population workspace already belongs to another GCL: {workspace}"
            )
        project_deck_key = project.get("deck_key") or _project_key(
            Path(project["deck_path"])
        )
        if project_deck_key != _project_key(deck_path):
            raise PipelineError(
                f"Population workspace already belongs to another logical deck: "
                f"{workspace}"
            )
    else:
        project = {
            "version": 1,
            "project_id": str(uuid.uuid4()),
            "project_key": _project_key(deck_path),
            "deck_key": _project_key(deck_path),
            "gcl_path": str(gcl_path.resolve()),
            "outputs": {},
        }
    project["outputs"] = {"apkg": str(deck_path.resolve())}

    accepted_records: dict[str, dict[str, Any]] = {}
    if accepted_path.exists():
        for record in _read_output_records(accepted_path):
            custom_id = record.get("custom_id")
            if custom_id:
                accepted_records[custom_id] = record

    findings: list[dict[str, Any]] = []
    # Import valid completed outputs into the reusable cache. Retry outputs are
    # considered after base outputs so a repaired response replaces its predecessor.
    manifest_paths = sorted(batches_dir.glob("**/manifest_*.json"))
    for manifest_path in manifest_paths:
        output_path = manifest_path.with_name(
            manifest_path.name.replace("manifest_", "output_").replace(
                ".json", ".jsonl"
            )
        )
        if not output_path.exists():
            continue
        manifest = load_manifest(manifest_path)
        results = parse_output(output_path)
        raw_by_id = {
            record["custom_id"]: record for record in _read_output_records(output_path)
        }
        for request in manifest["requests"]:
            card = results.get(request["custom_id"])
            errors = (
                ["batch output did not contain this card"]
                if card is None
                else validate_card(card, request["gcl_entry"])
            )
            if errors:
                findings.append({**request, "errors": errors})
            elif request["custom_id"] in raw_by_id:
                accepted_records[request["custom_id"]] = raw_by_id[
                    request["custom_id"]
                ]

    current_by_id = {entry.identity: entry for entry in entries}
    accepted_records = {
        custom_id: record
        for custom_id, record in accepted_records.items()
        if custom_id in current_by_id
    }
    accepted_cards = parse_output_records(accepted_records.values())
    invalid_cached = []
    for custom_id, card in accepted_cards.items():
        errors = validate_card(card, current_by_id[custom_id].text)
        if errors:
            invalid_cached.append(custom_id)
            findings.append(
                {
                    "custom_id": custom_id,
                    "source_index": current_by_id[custom_id].source_index,
                    "gcl_entry": current_by_id[custom_id].text,
                    "errors": errors,
                }
            )
    for custom_id in invalid_cached:
        accepted_records.pop(custom_id, None)

    cards_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        accepted_path,
        "\n".join(
            json.dumps(accepted_records[key], ensure_ascii=False)
            for key in sorted(accepted_records)
        )
        + ("\n" if accepted_records else ""),
    )

    pending_ids: set[str] = set()
    for manifest_path in manifest_paths:
        manifest = load_manifest(manifest_path)
        output_path = manifest_path.with_name(
            manifest_path.name.replace("manifest_", "output_").replace(
                ".json", ".jsonl"
            )
        )
        if not output_path.exists():
            pending_ids.update(
                item["custom_id"]
                for item in manifest["requests"]
                if item["custom_id"] in current_by_id
            )

    missing = [
        entry
        for entry in entries
        if entry.identity not in accepted_records and entry.identity not in pending_ids
    ]
    jobs = []
    for offset in range(0, len(missing), batch_size):
        selected = missing[offset : offset + batch_size]
        selection_digest = hashlib.sha256(
            "\n".join(entry.identity for entry in selected).encode("utf-8")
        ).hexdigest()[:10]
        job_dir = batches_dir / (
            f"{selected[0].source_index:06d}_{selected[-1].source_index:06d}_"
            f"{selection_digest}"
        )
        prepared = _write_population_batch(
            entries=selected,
            all_entries=entries,
            gcl_path=gcl_path,
            work_dir=job_dir,
            model=model,
            reasoning_effort=reasoning_effort,
        )
        jobs.append(
            {
                "manifest_path": prepared["manifest_path"],
                "entries": len(selected),
                "status": "prepared",
            }
        )

    project.update(
        {
            "gcl_sha256": sha256_file(gcl_path),
            "model": model,
            "reasoning_effort": reasoning_effort,
            "accepted_path": str(accepted_path.resolve()),
        }
    )
    atomic_write_json(project_path, project)
    report = {
        "operation": "populate",
        "workspace": str(workspace.resolve()),
        "project_path": str(project_path.resolve()),
        "accepted_path": str(accepted_path.resolve()),
        "gcl_entries": len(entries),
        "accepted_cards": len(accepted_records),
        "pending_cards": len(pending_ids),
        "new_cards_prepared": len(missing),
        "jobs": jobs,
        "findings": findings,
        "duplicate_entries_removed": duplicates,
        "complete": len(accepted_records) == len(entries),
    }
    atomic_write_json(workspace / "populate-report.json", report)
    return report


def parse_output_records(
    records: Any,
) -> dict[str, dict[str, Any]]:
    """Parse already-loaded Batch API output records."""
    results: dict[str, dict[str, Any]] = {}
    for record in records:
        custom_id = record.get("custom_id")
        if not custom_id or custom_id in results:
            raise PipelineError("Missing or duplicate custom_id in accepted-card cache")
        if record.get("error"):
            raise PipelineError(f"Cached batch request {custom_id} failed")
        response = record.get("response") or {}
        if response.get("status_code") != 200:
            raise PipelineError(f"Cached batch request {custom_id} was not successful")
        parsed = json.loads(extract_response_text(response.get("body") or {}))
        results[custom_id] = parsed.get("result", parsed)
    return results


def _stable_anki_id(project_id: str, kind: str) -> int:
    digest = hashlib.sha256(f"{project_id}:{kind}".encode("utf-8")).digest()
    return (1 << 30) + (int.from_bytes(digest[:8], "big") % (1 << 30))


def _load_complete_workspace(
    workspace_path: Path,
) -> tuple[dict[str, Any], list[GclEntry], Path, dict[str, dict[str, Any]]]:
    project_path = workspace_path / "project.json"
    if not project_path.is_file():
        raise PipelineError(f"Population workspace has no project.json: {workspace_path}")
    project = json.loads(project_path.read_text(encoding="utf-8"))
    gcl_path = Path(project["gcl_path"])
    if not gcl_path.is_file():
        raise PipelineError(f"Workspace GCL is missing: {gcl_path}")
    entries, _ = clean_and_read_gcl(gcl_path)
    if sha256_file(gcl_path) != project.get("gcl_sha256"):
        raise PipelineError(
            "GCL changed after the last population check; run populate first"
        )
    accepted_path = Path(
        project.get("accepted_path") or workspace_path / "cards" / "accepted.jsonl"
    )
    if not accepted_path.is_file():
        fallback = workspace_path / "cards" / "accepted.jsonl"
        if not fallback.is_file():
            raise PipelineError(f"Workspace accepted-card cache is missing: {accepted_path}")
        accepted_path = fallback
    records = _read_output_records(accepted_path)
    raw_by_id = {record.get("custom_id"): record for record in records}
    if None in raw_by_id or len(raw_by_id) != len(records):
        raise PipelineError("Accepted-card cache has missing or duplicate identities")
    cards = parse_output_records(records)
    expected_by_id = {entry.identity: entry for entry in entries}
    missing = expected_by_id.keys() - cards.keys()
    unexpected = cards.keys() - expected_by_id.keys()
    findings = []
    for custom_id, entry in expected_by_id.items():
        if custom_id in cards:
            errors = validate_card(cards[custom_id], entry.text)
            if errors:
                findings.append(
                    {
                        "custom_id": custom_id,
                        "gcl_entry": entry.text,
                        "errors": errors,
                    }
                )
    if missing or unexpected or findings:
        raise PipelineError(
            "Population cache is not generation-ready: "
            f"{len(missing)} missing, {len(unexpected)} unexpected, "
            f"{len(findings)} invalid"
        )
    return project, entries, accepted_path, cards


def _workspace_generation_manifest(
    *,
    workspace_path: Path,
    project: dict[str, Any],
    entries: list[GclEntry],
    accepted_path: Path,
) -> Path:
    manifest_path = workspace_path / "generate-manifest.json"
    manifest = {
        "version": 2,
        "operation": "generate",
        "gcl_path": project["gcl_path"],
        "gcl_sha256": project["gcl_sha256"],
        "input_path": str(accepted_path.resolve()),
        "input_sha256": sha256_file(accepted_path),
        "model": project.get("model"),
        "reasoning_effort": project.get("reasoning_effort"),
        "range": {"start": 1, "end": len(entries)},
        "total_gcl_entries": len(entries),
        "duplicate_entries_removed": [],
        "requests": [
            {
                "custom_id": entry.identity,
                "source_index": entry.source_index,
                "gcl_entry": entry.text,
            }
            for entry in entries
        ],
    }
    atomic_write_json(manifest_path, manifest)
    return manifest_path


def _template_parts(template_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    template = json.loads(template_path.read_text(encoding="utf-8-sig"))
    note_models = template.get("note_models") or []
    if len(note_models) != 1:
        raise PipelineError("Deck template must contain exactly one note model")
    model = note_models[0]
    fields = model.get("flds") or []
    card_templates = model.get("tmpls") or []
    if not fields or not card_templates:
        raise PipelineError("Deck template has no fields or card templates")
    return template, model


def _generate_apkg(
    *,
    project: dict[str, Any],
    entries: list[GclEntry],
    cards: dict[str, dict[str, Any]],
    template_path: Path,
    output_path: Path,
    deck_name: str | None = None,
) -> dict[str, Any]:
    try:
        import genanki
    except ImportError as error:
        raise PipelineError(
            "APKG generation dependency is unavailable; reinstall the project "
            "environment from pyproject.toml"
        ) from error

    _, source_model = _template_parts(template_path)
    project_id = project["project_id"]
    deck_id = _stable_anki_id(project_id, "deck")
    model_id = _stable_anki_id(project_id, "model")
    deck_name = (
        deck_name
        or project.get("deck_name")
        or project["deck_key"].replace("_", " ").strip().title()
    ).strip()
    if not deck_name:
        raise PipelineError("Deck name must not be empty")
    model = genanki.Model(
        model_id,
        source_model.get("name", "Japanese Vocabulary Note"),
        fields=[
            {
                "name": field["name"],
                **(
                    {"font": field["font"]}
                    if isinstance(field.get("font"), str)
                    else {}
                ),
            }
            for field in source_model["flds"]
        ],
        templates=[
            {
                "name": card_template["name"],
                "qfmt": card_template["qfmt"],
                "afmt": card_template["afmt"],
            }
            for card_template in source_model["tmpls"]
        ],
        css=source_model.get("css", ""),
        sort_field_index=int(source_model.get("sortf", 0)),
    )
    deck = genanki.Deck(deck_id, deck_name)

    class StableNote(genanki.Note):
        def __init__(self, *, stable_guid: str, **kwargs: Any) -> None:
            self._stable_guid = stable_guid
            super().__init__(**kwargs)

        @property
        def guid(self) -> str:
            return self._stable_guid

    for entry in entries:
        card = cards[entry.identity]
        examples_html = "\n".join(
            f"<div>{example}</div>" for example in card["examples"]
        )
        deck.add_note(
            StableNote(
                stable_guid=deterministic_guid(entry.text),
                model=model,
                fields=[
                    card["reading"],
                    card["definition"],
                    examples_html,
                    card["vocabulary"],
                ],
            )
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_path.stem}.", dir=output_path.parent)
    )
    temporary_path = temporary_dir / output_path.name
    try:
        genanki.Package(deck).write_to_file(str(temporary_path))
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
        temporary_dir.rmdir()
    return {
        "format": "apkg",
        "output_path": str(output_path.resolve()),
        "deck_name": deck_name,
        "deck_id": deck_id,
        "model_id": model_id,
        "notes": len(entries),
        "published": True,
    }


def generate_from_workspace(
    *,
    workspace_path: Path,
    output_path: Path,
    template_path: Path,
    deck_name: str | None = None,
) -> dict[str, Any]:
    """Generate a final APKG using only one populated deck workspace."""
    if output_path.suffix.lower() != ".apkg":
        raise PipelineError("APKG output must use the .apkg extension")
    project, entries, accepted_path, cards = _load_complete_workspace(
        workspace_path
    )
    manifest_path = _workspace_generation_manifest(
        workspace_path=workspace_path,
        project=project,
        entries=entries,
        accepted_path=accepted_path,
    )
    result = _generate_apkg(
        project=project,
        entries=entries,
        cards=cards,
        template_path=template_path,
        output_path=output_path,
        deck_name=deck_name,
    )
    project["outputs"] = {"apkg": str(output_path.resolve())}
    atomic_write_json(workspace_path / "project.json", project)
    atomic_write_json(workspace_path / "generate-apkg-report.json", result)
    return result


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
    if value.startswith("~"):
        value = value[1:]
    if value.endswith("~"):
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
    boundary = r"(?<![\u3400-\u4dbf\u4e00-\u9fff々])"
    if vocabulary.endswith("する") and len(vocabulary) > 2:
        return re.compile(boundary + re.escape(vocabulary[:-2]) + r"[しすせさ]")
    ending = vocabulary[-1:] if vocabulary else ""
    initials = CONJUGATION_INITIALS.get(ending)
    stem = vocabulary[:-1]
    if initials and stem and re.search(r"[\u3400-\u4dbf\u4e00-\u9fff々]", stem):
        return re.compile(boundary + re.escape(stem) + f"[{initials}]")
    return None


def validate_bold_markup(value: str) -> bool:
    if re.search(r"</?b(?!>)", value, flags=re.IGNORECASE):
        return False
    depth = 0
    for tag in re.findall(r"</?b>", value, flags=re.IGNORECASE):
        if tag.lower() == "<b>":
            depth += 1
        else:
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


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
    if not validate_bold_markup(reading) or "<b>" not in reading:
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
    elif any(not validate_bold_markup(example) for example in examples):
        errors.append("examples must contain balanced bold markup")
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
        uuid.UUID("867c9bb2-b47e-5c77-b80c-bf10b8b65c52"),
        identity_compatibility_text(gcl_entry),
    ).hex[:16]


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
