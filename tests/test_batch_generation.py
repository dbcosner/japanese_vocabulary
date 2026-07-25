from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from japanese_vocabulary_batch.cli import main
from japanese_vocabulary_batch.pipeline import (
    PipelineError,
    GclEntry,
    apply_reading_normalization,
    card_schema,
    collect_batch,
    deterministic_guid,
    generate_from_workspace,
    import_apkg,
    merge_retry_output,
    migrate_gcl_syntax,
    prepare_batch,
    prepare_population,
    prepare_reading_normalization,
    prepare_retry,
    refresh_status,
    read_dotenv_api_key,
    submit_batch,
    validate_card,
)


def response_line(custom_id: str, card: dict) -> str:
    response_text = json.dumps(card, ensure_ascii=False)
    return json.dumps(
        {
            "id": f"result-{custom_id}",
            "custom_id": custom_id,
            "response": {
                "status_code": 200,
                "body": {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": response_text}
                            ],
                        }
                    ]
                },
            },
            "error": None,
        },
        ensure_ascii=False,
    )


class FakeFiles:
    def __init__(self, contents: dict[str, bytes] | None = None):
        self.contents = contents or {}
        self.created_purpose = None
        self.created_bytes = None

    def create(self, *, file, purpose):
        self.created_purpose = purpose
        self.created_bytes = file.read()
        return SimpleNamespace(id="file-input-test")

    def content(self, file_id):
        return self.contents[file_id]


class FakeBatches:
    def __init__(self):
        self.created = None
        self.batch = SimpleNamespace(
            id="batch-test",
            status="completed",
            output_file_id="file-output-test",
            error_file_id=None,
            request_counts={"total": 2, "completed": 2, "failed": 0},
        )

    def create(self, **kwargs):
        self.created = kwargs
        return SimpleNamespace(id="batch-test", status="validating")

    def retrieve(self, batch_id):
        if batch_id != "batch-test":
            raise AssertionError("unexpected batch id")
        return self.batch


class FakeClient:
    def __init__(self, contents: dict[str, bytes] | None = None):
        self.files = FakeFiles(contents)
        self.batches = FakeBatches()


class BatchGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.gcl = self.root / "deck_generation_control_file.txt"
        self.gcl.write_text(
            "# GCL Version: 1\n\n遭う[あう]\n内閣[ないかく]\n遭う[あう]\n",
            encoding="utf-8",
        )
        self.template = self.root / "template.json"
        self.template.write_text(
            json.dumps(
                {
                    "__type__": "Deck",
                    "name": "Test",
                    "note_models": [
                        {
                            "__type__": "NoteModel",
                            "name": "Vocabulary",
                            "css": ".card { font-family: sans-serif; }",
                            "flds": [
                                {"name": "Reading"},
                                {"name": "Definition"},
                                {"name": "Examples"},
                                {"name": "Vocabulary"},
                            ],
                            "sortf": 0,
                            "tmpls": [
                                {
                                    "name": "Vocabulary Card",
                                    "qfmt": "{{Reading}} {{Definition}} {{Examples}}",
                                    "afmt": "{{FrontSide}}<hr>{{Vocabulary}}",
                                }
                            ],
                        }
                    ],
                    "notes": [
                        {
                            "__type__": "Note",
                            "guid": "placeholder",
                            "fields": ["x", "x", "x", "x"],
                            "note_model_uuid": "model-test",
                            "tags": [],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_import_apkg_creates_named_deduplicated_gcl(self):
        database = self.root / "collection.anki2"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE col (models TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE notes (id INTEGER, mid INTEGER, flds TEXT NOT NULL)"
        )
        model = {
            "42": {
                "flds": [
                    {"name": "Reading"},
                    {"name": "Definition"},
                    {"name": "Vocabulary"},
                ]
            }
        }
        connection.execute("INSERT INTO col VALUES (?)", (json.dumps(model),))
        separator = "\x1f"
        connection.executemany(
            "INSERT INTO notes VALUES (?, ?, ?)",
            [
                (1, 42, separator.join(["<b>あ</b>う", "definition", "遭う"])),
                (2, 42, separator.join(["ないかく", "definition", "内閣"])),
                (3, 42, separator.join(["<b>あ</b>う", "duplicate", "遭う"])),
            ],
        )
        connection.commit()
        connection.close()
        package = self.root / "source.apkg"
        with zipfile.ZipFile(package, "w") as archive:
            archive.write(database, "collection.anki2")

        result = import_apkg(package, "study_deck", self.root / "gcl")

        output = self.root / "gcl" / "study_deck_generation_control_file.txt"
        self.assertEqual(
            output.read_text(encoding="utf-8"),
            "# GCL Version: 1\n\n遭う[あう]\n内閣[ないかく]\n",
        )
        self.assertEqual(result["source_notes"], 3)
        self.assertEqual(result["entries"], 2)
        self.assertEqual(len(result["duplicates_removed"]), 1)
        self.assertTrue(Path(result["review_path"]).is_file())
        self.assertEqual(result["review_items"][0]["reason"], "exact duplicate")

    def test_import_apkg_flags_ambiguous_structure_and_applies_decisions(self):
        database = self.root / "collection.anki2"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE col (models TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE notes (id INTEGER, mid INTEGER, flds TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO col VALUES (?)",
            (json.dumps({"1": {"flds": [{"name": "Expression"}, {"name": "Reading"}]}}),),
        )
        connection.executemany(
            "INSERT INTO notes VALUES (?, 1, ?)",
            [
                (1, "～化\x1f〜か"),
                (2, "片道 ⇔ 往復\x1fかたみち⇔おうふく"),
                (3, "無作法（な）\x1fぶさほう（な）"),
            ],
        )
        connection.commit()
        connection.close()
        package = self.root / "source.apkg"
        with zipfile.ZipFile(package, "w") as archive:
            archive.write(database, "collection.anki2")

        canonical = import_apkg(package, "canonical", self.root / "canonical")
        canonical_text = Path(canonical["gcl_path"]).read_text(encoding="utf-8")
        self.assertIn("~化[か]", canonical_text)
        self.assertNotIn("片道", canonical_text)
        self.assertIn("無作法[ぶさほう](な)", canonical_text)
        self.assertEqual(len(canonical["review_items"]), 1)

        decisions = self.root / "decisions.json"
        decisions.write_text(
            json.dumps(
                {
                    "rules": {
                        "split_comparisons": True,
                        "strip_parentheticals_except_na": True,
                    }
                }
            ),
            encoding="utf-8",
        )
        decided = import_apkg(
            package,
            "decided",
            self.root / "decided",
            decisions_path=decisions,
        )
        decided_text = Path(decided["gcl_path"]).read_text(encoding="utf-8")
        self.assertIn("片道[かたみち]", decided_text)
        self.assertIn("往復[おうふく]", decided_text)
        self.assertIn("無作法[ぶさほう](な)", decided_text)

    def test_import_apkg_cli_uses_requested_full_gcl_name(self):
        database = self.root / "collection.anki2"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE col (models TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE notes (id INTEGER, mid INTEGER, flds TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO col VALUES (?)",
            (json.dumps({"1": {"flds": [{"name": "Expression"}, {"name": "Reading"}]}}),),
        )
        connection.execute("INSERT INTO notes VALUES (1, 1, ?)", ("語彙\x1fごい",))
        connection.commit()
        connection.close()
        package = self.root / "source.apkg"
        with zipfile.ZipFile(package, "w") as archive:
            archive.write(database, "collection.anki2")

        exit_code = main(
            [
                "import-apkg",
                "--apkg",
                str(package),
                "--name",
                "custom_generation_control_file.txt",
                "--output-dir",
                str(self.root / "output"),
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(
            (self.root / "output" / "custom_generation_control_file.txt").is_file()
        )

    def test_import_apkg_prefers_modern_collection_over_compatibility_database(self):
        package = self.root / "modern.apkg"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("collection.anki21b", b"modern")
            archive.writestr("collection.anki2", b"placeholder")

        class FakeReader:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return b"database"

        fake_decompressor = SimpleNamespace(
            stream_reader=lambda value: FakeReader()
        )
        fake_zstandard = SimpleNamespace(
            ZstdDecompressor=lambda: fake_decompressor
        )
        with (
            patch.dict("sys.modules", {"zstandard": fake_zstandard}),
            patch("sqlite3.connect", side_effect=sqlite3.DatabaseError("checked modern")),
        ):
            with self.assertRaisesRegex(PipelineError, "checked modern"):
                import_apkg(package, "modern", self.root / "gcl")

    def test_migrate_gcl_syntax_preserves_cache_identity_and_guid(self):
        gcl = self.root / "gcl" / "deck_generation_control_file.txt"
        gcl.parent.mkdir()
        old_entry = "～化[か]"
        new_entry = "~化[か]"
        gcl.write_text(f"# GCL Version: 1\n\n{old_entry}\n", encoding="utf-8")
        workspace = self.root / ".batch" / "deck"
        cards = workspace / "cards"
        cards.mkdir(parents=True)
        custom_id = GclEntry(1, old_entry).identity
        accepted = cards / "accepted.jsonl"
        accepted.write_text(
            response_line(custom_id, self.card(old_entry, "か", "化")) + "\n",
            encoding="utf-8",
        )
        old_hash = hashlib.sha256(gcl.read_bytes()).hexdigest()
        (workspace / "project.json").write_text(
            json.dumps(
                {"gcl_path": str(gcl.resolve()), "gcl_sha256": old_hash}
            ),
            encoding="utf-8",
        )
        (workspace / "generate-manifest.json").write_text(
            json.dumps(
                {
                    "gcl_sha256": old_hash,
                    "input_sha256": hashlib.sha256(accepted.read_bytes()).hexdigest(),
                    "requests": [
                        {
                            "custom_id": custom_id,
                            "source_index": 1,
                            "gcl_entry": old_entry,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        old_guid = deterministic_guid(old_entry)
        result = migrate_gcl_syntax(gcl, workspace)

        self.assertIn(new_entry, gcl.read_text(encoding="utf-8"))
        self.assertEqual(GclEntry(1, new_entry).identity, custom_id)
        self.assertEqual(deterministic_guid(new_entry), old_guid)
        self.assertEqual(result["cache_records"], 1)
        self.assertTrue(Path(result["backup_dir"]).is_dir())

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self):
        return prepare_batch(
            gcl_path=self.gcl,
            work_dir=self.root / "work",
            model="gpt-test",
            reasoning_effort="low",
        )

    @staticmethod
    def card(gcl_entry: str, reading: str, vocabulary: str) -> dict:
        return {
            "status": "card",
            "issue": "",
            "gcl_entry": gcl_entry,
            "resolved_gcl_entry": gcl_entry,
            "additional_gcl_entries": [],
            "reading": f"<b>{reading}</b>",
            "definition": "簡潔な定義。",
            "examples": [
                f"<b>{reading}</b>の例文一。",
                f"<b>{reading}</b>の例文二。",
                f"<b>{reading}</b>の例文三。",
            ],
            "example_count_rationale": "",
            "vocabulary": vocabulary,
        }

    def test_prepare_is_offline_and_deduplicates_gcl(self):
        prepared = self.prepare()
        self.assertEqual(prepared["total_gcl_entries"], 2)
        self.assertEqual(len(prepared["requests"]), 2)
        self.assertEqual(
            prepared["duplicate_entries_removed"],
            [{"line": 5, "entry": "遭う[あう]"}],
        )
        cleaned = self.gcl.read_text(encoding="utf-8")
        self.assertEqual(cleaned.count("遭う[あう]"), 1)
        input_lines = Path(prepared["input_path"]).read_text(
            encoding="utf-8"
        ).splitlines()
        requests = [json.loads(line) for line in input_lines]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["url"], "/v1/responses")
        self.assertEqual(requests[0]["body"]["model"], "gpt-test")
        self.assertTrue(
            requests[0]["body"]["text"]["format"]["strict"]
        )

    def test_population_uses_a_deck_specific_workspace(self):
        deck_path = self.root / "decks" / "test.apkg"
        result = prepare_population(
            gcl_path=self.gcl,
            deck_path=deck_path,
            batch_root=self.root / ".batch",
            batch_size=1,
            model="gpt-test",
            reasoning_effort="low",
        )
        workspace = self.root / ".batch" / "test"
        self.assertEqual(Path(result["workspace"]), workspace.resolve())
        self.assertEqual(result["new_cards_prepared"], 2)
        self.assertEqual(len(result["jobs"]), 2)
        project = json.loads(
            (workspace / "project.json").read_text(encoding="utf-8")
        )
        self.assertEqual(Path(project["gcl_path"]), self.gcl.resolve())
        self.assertEqual(
            Path(project["outputs"]["apkg"]), deck_path.resolve()
        )

    def test_population_reuses_cached_cards_and_prepares_only_new_entries(self):
        self.gcl.write_text(
            "# GCL Version: 1\n\n遭う[あう]\n", encoding="utf-8"
        )
        deck_path = self.root / "deck" / "deck.apkg"
        first = prepare_population(
            gcl_path=self.gcl,
            deck_path=deck_path,
            batch_root=self.root / ".batch",
        )
        manifest_path = Path(first["jobs"][0]["manifest_path"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_path = manifest_path.with_name(
            manifest_path.name.replace("manifest_", "output_").replace(
                ".json", ".jsonl"
            )
        )
        output_path.write_text(
            response_line(
                manifest["requests"][0]["custom_id"],
                self.card("遭う[あう]", "あう", "遭う"),
            )
            + "\n",
            encoding="utf-8",
        )
        second = prepare_population(
            gcl_path=self.gcl,
            deck_path=deck_path,
            batch_root=self.root / ".batch",
        )
        self.assertTrue(second["complete"], second)
        self.assertEqual(second["accepted_cards"], 1)
        self.assertEqual(second["new_cards_prepared"], 0)

        self.gcl.write_text(
            "# GCL Version: 1\n\n内閣[ないかく]\n遭う[あう]\n",
            encoding="utf-8",
        )
        third = prepare_population(
            gcl_path=self.gcl,
            deck_path=deck_path,
            batch_root=self.root / ".batch",
        )
        self.assertEqual(third["accepted_cards"], 1)
        self.assertEqual(third["new_cards_prepared"], 1)
        new_manifest = json.loads(
            Path(third["jobs"][0]["manifest_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(
            [request["gcl_entry"] for request in new_manifest["requests"]],
            ["内閣[ないかく]"],
        )

    def test_workspace_generates_apkg_with_stable_ids(self):
        deck_path = self.root / "published.apkg"
        populated = prepare_population(
            gcl_path=self.gcl,
            deck_path=deck_path,
            batch_root=self.root / ".batch",
        )
        for job in populated["jobs"]:
            manifest_path = Path(job["manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            output_path = manifest_path.with_name(
                manifest_path.name.replace("manifest_", "output_").replace(
                    ".json", ".jsonl"
                )
            )
            output_path.write_text(
                "\n".join(
                    response_line(
                        request["custom_id"],
                        self.card(
                            request["gcl_entry"],
                            "あう" if "遭う" in request["gcl_entry"] else "ないかく",
                            "遭う" if "遭う" in request["gcl_entry"] else "内閣",
                        ),
                    )
                    for request in manifest["requests"]
                )
                + "\n",
                encoding="utf-8",
            )
        complete = prepare_population(
            gcl_path=self.gcl,
            deck_path=deck_path,
            batch_root=self.root / ".batch",
        )
        workspace = Path(complete["workspace"])

        first = generate_from_workspace(
            workspace_path=workspace,
            output_path=deck_path,
            template_path=self.template,
        )
        second = generate_from_workspace(
            workspace_path=workspace,
            output_path=deck_path,
            template_path=self.template,
            deck_name="N2 Vocabulary",
        )
        self.assertEqual(first["deck_id"], second["deck_id"])
        self.assertEqual(first["model_id"], second["model_id"])
        self.assertEqual(first["notes"], 2)
        self.assertEqual(first["deck_name"], "Published")
        self.assertEqual(second["deck_name"], "N2 Vocabulary")
        with zipfile.ZipFile(deck_path) as package:
            self.assertIn("collection.anki2", package.namelist())
            database_path = self.root / "collection.anki2"
            database_path.write_bytes(package.read("collection.anki2"))
        connection = sqlite3.connect(database_path)
        try:
            self.assertEqual(
                connection.execute("select count(*) from notes").fetchone()[0], 2
            )
            self.assertEqual(
                connection.execute("select count(*) from cards").fetchone()[0], 2
            )
        finally:
            connection.close()

    def test_generate_rejects_unannotated_gcl_entries(self):
        self.gcl.write_text(
            "# GCL Version: 1\n\n遭う\n内閣[ないかく]\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(PipelineError, "every entry requires"):
            self.prepare()

    def test_identity_does_not_depend_on_line_number(self):
        self.assertEqual(
            GclEntry(1, "遭う[あう]").identity,
            GclEntry(999, "遭う[あう]").identity,
        )

    def test_reading_normalization_annotates_expands_and_deduplicates(self):
        self.gcl.write_text(
            "# GCL Version: 1\n\n煙る\n煙る[けぶる]\n内閣\n",
            encoding="utf-8",
        )
        prepared = prepare_reading_normalization(
            gcl_path=self.gcl,
            work_dir=self.root / "readings",
            model="gpt-test",
            reasoning_effort="low",
        )
        self.assertEqual(len(prepared["requests"]), 2)
        resolved = {
            "煙る": ["けむる", "けむる", "けぶる", "け煙"],
            "内閣": [],
        }
        lines = []
        for request in prepared["requests"]:
            result = {
                "status": (
                    "needs_review"
                    if request["gcl_entry"] == "内閣"
                    else "resolved"
                ),
                "issue": (
                    "editorial correction required"
                    if request["gcl_entry"] == "内閣"
                    else ""
                ),
                "gcl_entry": request["gcl_entry"],
                "readings": resolved[request["gcl_entry"]],
            }
            lines.append(
                response_line(request["custom_id"], {"result": result})
            )
        output = self.root / "reading-output.jsonl"
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = apply_reading_normalization(
            manifest_path=Path(prepared["manifest_path"]),
            output_path=output,
            report_path=self.root / "reading-report.json",
            corrections={"内閣": "内閣[ないかく]"},
        )
        self.assertTrue(report["published"])
        self.assertEqual(
            self.gcl.read_text(encoding="utf-8"),
            (
                "# GCL Version: 1\n\n"
                "煙る[けむる]\n"
                "煙る[けぶる]\n"
                "内閣[ないかく]\n"
            ),
        )
        self.assertEqual(len(report["duplicates_removed_after_resolution"]), 1)
        self.assertEqual(len(report["normalization_warnings"]), 2)

    def test_schema_requires_examples_only_for_cards(self):
        alternatives = card_schema()["properties"]["result"]["anyOf"]
        card_examples = alternatives[0]["properties"]["examples"]
        review_examples = alternatives[1]["properties"]["examples"]
        self.assertEqual(card_examples["minItems"], 1)
        self.assertEqual(card_examples["maxItems"], 5)
        self.assertEqual(review_examples["maxItems"], 0)

    def test_submit_requires_explicit_cost_confirmation(self):
        prepared = self.prepare()
        client = FakeClient()
        with self.assertRaisesRegex(PipelineError, "cost confirmation"):
            submit_batch(
                Path(prepared["manifest_path"]),
                client=client,
                confirm_cost=False,
            )
        self.assertIsNone(client.files.created_bytes)

    def test_cli_does_not_create_client_without_cost_confirmation(self):
        prepared = self.prepare()
        with patch(
            "japanese_vocabulary_batch.cli.make_openai_client"
        ) as make_client:
            result = main(
                ["submit", "--manifest", prepared["manifest_path"]]
            )
        self.assertEqual(result, 1)
        make_client.assert_not_called()

    def test_dotenv_is_required_and_placeholders_are_rejected(self):
        missing = self.root / ".env"
        with self.assertRaisesRegex(PipelineError, "credential file is missing"):
            read_dotenv_api_key(missing)
        missing.write_text(
            "OPENAI_API_KEY=replace-with-your-openai-api-key\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(PipelineError, "placeholder"):
            read_dotenv_api_key(missing)

    def test_dotenv_value_is_used_instead_of_os_environment(self):
        env_file = self.root / ".env"
        env_file.write_text(
            "# local credential\nOPENAI_API_KEY=file-value-for-test\n",
            encoding="utf-8",
        )
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "operating-system-value"}, clear=False
        ):
            self.assertEqual(
                read_dotenv_api_key(env_file), "file-value-for-test"
            )

    def test_submit_and_status_use_fake_client_only(self):
        prepared = self.prepare()
        client = FakeClient()
        submitted = submit_batch(
            Path(prepared["manifest_path"]),
            client=client,
            confirm_cost=True,
        )
        self.assertEqual(client.files.created_purpose, "batch")
        self.assertEqual(
            client.batches.created["endpoint"], "/v1/responses"
        )
        state = refresh_status(Path(submitted["state_path"]), client=client)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["request_counts"]["completed"], 2)

    def test_collect_downloads_fake_output(self):
        prepared = self.prepare()
        client = FakeClient({"file-output-test": b'{"custom_id":"one"}\n'})
        submitted = submit_batch(
            Path(prepared["manifest_path"]),
            client=client,
            confirm_cost=True,
        )
        state = collect_batch(Path(submitted["state_path"]), client=client)
        self.assertEqual(
            Path(state["output_path"]).read_text(encoding="utf-8"),
            '{"custom_id":"one"}\n',
        )

    def test_example_count_policy(self):
        card = {
            "status": "card",
            "issue": "",
            "gcl_entry": "内閣[ないかく]",
            "resolved_gcl_entry": "内閣[ないかく]",
            "additional_gcl_entries": [],
            "reading": "<b>ないかく</b>",
            "definition": "国の行政を担う最高機関。",
            "examples": ["新しい<b>ないかく</b>が発足した。"],
            "example_count_rationale": "用法が限定的で追加例は重複するため。",
            "vocabulary": "内閣",
        }
        self.assertEqual(validate_card(card, "内閣[ないかく]"), [])

        card["example_count_rationale"] = ""
        self.assertIn(
            "a non-three example count requires example_count_rationale",
            validate_card(card, "内閣[ないかく]"),
        )

        card["examples"] = [
            "新しい<b>ないかく</b>が発足した。",
            "<b>ないかく</b>の方針が示された。",
            "<b>ないかく</b>は法案を決定した。",
        ]
        self.assertEqual(validate_card(card, "内閣[ないかく]"), [])

        card["example_count_rationale"] = "不要な理由"
        self.assertIn(
            "example_count_rationale must be empty for the preferred "
            "three-example count",
            validate_card(card, "内閣[ないかく]"),
        )

        card["examples"] *= 2
        card["example_count_rationale"] = "六例"
        self.assertIn(
            "examples must contain one to five items",
            validate_card(card, "内閣[ないかく]"),
        )

        card["examples"] = [
            "新しい<b>ないかく</b、方針が示された。",
            "<b>ないかく</b>が発足した。",
            "<b>ないかく</b>は法案を決定した。",
        ]
        card["example_count_rationale"] = ""
        self.assertIn(
            "examples must contain balanced bold markup",
            validate_card(card, "内閣[ないかく]"),
        )

    def test_resolved_gcl_requires_complete_trailing_reading(self):
        card = {
            "status": "card",
            "issue": "",
            "gcl_entry": "添う",
            "resolved_gcl_entry": "添[そう]う",
            "additional_gcl_entries": [],
            "reading": "<b>そ</b>う",
            "definition": "目的などに合う。",
            "examples": [
                "方針に<b>そう</b>。",
                "希望に<b>そった</b>案だ。",
                "期待に<b>そえる</b>よう努める。",
            ],
            "example_count_rationale": "",
            "vocabulary": "添う",
        }
        errors = validate_card(card, "添う")
        self.assertIn(
            "resolved_gcl_entry reading must be a complete trailing annotation",
            errors,
        )
        card["resolved_gcl_entry"] = "添う[そう]"
        self.assertNotIn(
            "resolved_gcl_entry reading must be a complete trailing annotation",
            validate_card(card, "添う"),
        )

    def test_concealment_is_contextual_for_inflected_targets(self):
        card = {
            "status": "card",
            "issue": "",
            "gcl_entry": "値する",
            "resolved_gcl_entry": "値する[あたいする]",
            "additional_gcl_entries": [],
            "reading": "<b>あたい</b>する",
            "definition": "それだけの価値や意義がある。",
            "examples": [
                "検討に<b>あたいする</b>案だ。",
                "称賛に<b>あたいする</b>行為だ。",
                "記憶に<b>あたいする</b>出来事だ。",
            ],
            "example_count_rationale": "",
            "vocabulary": "値する",
        }
        card["gcl_entry"] = "値する[あたいする]"
        self.assertEqual(validate_card(card, "値する[あたいする]"), [])
        card["definition"] = "十分に値する内容だ。"
        self.assertIn(
            "definition reveals the written vocabulary",
            validate_card(card, "値する[あたいする]"),
        )
        card["definition"] = "検討に値している。"
        self.assertIn(
            "definition reveals an inflected written target",
            validate_card(card, "値する[あたいする]"),
        )

    def test_concealment_allows_a_target_stem_inside_a_compound(self):
        card = self.card("履く[はく]", "はく", "履く")
        card["examples"][1] = "会場では室内用の上履きを<b>はいて</b>ください。"
        self.assertEqual(validate_card(card, "履く[はく]"), [])

    def test_prepare_retry_and_merge_replace_only_findings(self):
        prepared = self.prepare()
        failed_id = prepared["requests"][1]["custom_id"]
        base_output = self.root / "base.jsonl"
        base_records = []
        for item in prepared["requests"]:
            card = {
                "status": "card",
                "issue": "",
                "gcl_entry": item["gcl_entry"],
                "resolved_gcl_entry": item["gcl_entry"],
                "additional_gcl_entries": [],
                "reading": "<b>あ</b>う",
                "definition": "original definition",
                "examples": ["original example"],
                "example_count_rationale": "",
                "vocabulary": "original vocabulary",
            }
            base_records.append(response_line(item["custom_id"], card))
        base_output.write_text("\n".join(base_records) + "\n", encoding="utf-8")
        report_path = self.root / "generation-report.json"
        report_path.write_text(
            json.dumps(
                {
                    "output_path": str(base_output),
                    "findings": [
                        {
                            "custom_id": failed_id,
                            "source_index": 2,
                            "gcl_entry": prepared["requests"][1]["gcl_entry"],
                            "errors": ["examples must contain one to five items"],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        retry = prepare_retry(
            manifest_path=Path(prepared["manifest_path"]),
            report_path=report_path,
            work_dir=self.root / "work",
        )
        self.assertEqual(
            [item["custom_id"] for item in retry["requests"]], [failed_id]
        )
        retry_input = json.loads(
            Path(retry["input_path"]).read_text(encoding="utf-8").splitlines()[0]
        )
        repair_prompt = retry_input["body"]["input"][1]["content"]
        self.assertIn("rejected_card", repair_prompt)
        self.assertIn("examples must contain one to five items", repair_prompt)
        self.assertIn(
            "examples must contain one to five items",
            retry["requests"][0]["validation_errors"],
        )

        merge_base_output = self.root / "merge-base.jsonl"
        merge_base_records = [
            {"custom_id": item["custom_id"], "value": "base"}
            for item in prepared["requests"]
        ]
        merge_base_output.write_text(
            "\n".join(json.dumps(item) for item in merge_base_records) + "\n",
            encoding="utf-8",
        )
        retry_output = self.root / "retry.jsonl"
        retry_output.write_text(
            json.dumps({"custom_id": failed_id, "value": "retry"}) + "\n",
            encoding="utf-8",
        )
        merged_output = self.root / "merged.jsonl"
        result = merge_retry_output(
            base_output_path=merge_base_output,
            retry_manifest_path=Path(retry["manifest_path"]),
            retry_output_path=retry_output,
            merged_output_path=merged_output,
        )
        merged = [
            json.loads(line)
            for line in merged_output.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(result["replaced_records"], 1)
        self.assertEqual(merged[0]["value"], "base")
        self.assertEqual(merged[1]["value"], "retry")

if __name__ == "__main__":
    unittest.main()
