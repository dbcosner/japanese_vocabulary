from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from japanese_vocabulary_batch.cli import main
from japanese_vocabulary_batch.pipeline import (
    PipelineError,
    GclEntry,
    apply_reading_normalization,
    apply_results,
    apply_update,
    card_schema,
    collect_batch,
    merge_retry_output,
    prepare_batch,
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
                    "crowdanki_uuid": "deck-test",
                    "note_models": [
                        {
                            "__type__": "NoteModel",
                            "crowdanki_uuid": "model-test",
                            "name": "Vocabulary",
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

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self):
        return prepare_batch(
            gcl_path=self.gcl,
            work_dir=self.root / "work",
            model="gpt-test",
            reasoning_effort="low",
        )

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

    def test_apply_builds_complete_deck_and_removes_placeholder(self):
        prepared = self.prepare()
        records = []
        cards = [
            {
                "status": "card",
                "issue": "",
                "gcl_entry": "遭う[あう]",
                "resolved_gcl_entry": "遭う[あう]",
                "additional_gcl_entries": [],
                "reading": "<b>あ</b>う",
                "definition": "好ましくない出来事を思いがけず経験する。",
                "examples": [
                    "旅行中に事故に<b>あった</b>。",
                    "同じ目に<b>あわない</b>よう注意した。",
                    "帰宅途中で災難に<b>あった</b>。",
                ],
                "example_count_rationale": "",
                "vocabulary": "遭う",
            },
            {
                "status": "card",
                "issue": "",
                "gcl_entry": "内閣[ないかく]",
                "resolved_gcl_entry": "内閣[ないかく]",
                "additional_gcl_entries": [],
                "reading": "<b>ないかく</b>",
                "definition": "国の行政を担う最高機関。",
                "examples": [
                    "新しい<b>ないかく</b>が発足した。",
                    "法案は<b>ないかく</b>の決定を経た。",
                    "<b>ないかく</b>は政策を見直した。",
                ],
                "example_count_rationale": "",
                "vocabulary": "内閣",
            },
        ]
        for request, card in zip(prepared["requests"], cards):
            records.append(response_line(request["custom_id"], card))
        output = self.root / "output.jsonl"
        output.write_text("\n".join(records) + "\n", encoding="utf-8")
        deck_dir = self.root / "test_crowdanki_deck"
        deck_output = deck_dir / "test_crowdanki_deck.json"
        report = apply_results(
            manifest_path=Path(prepared["manifest_path"]),
            output_path=output,
            template_path=self.template,
            deck_output_path=deck_output,
        )
        self.assertTrue(report["published"])
        deck = json.loads(deck_output.read_text(encoding="utf-8"))
        self.assertEqual(len(deck["notes"]), 2)
        self.assertNotEqual(deck["notes"][0]["guid"], "placeholder")
        self.assertEqual(deck["notes"][0]["note_model_uuid"], "model-test")
        self.assertEqual(deck["notes"][1]["fields"][3], "内閣")
        self.assertIn("<div>", deck["notes"][0]["fields"][2])

    def test_apply_refuses_review_items_without_publishing(self):
        prepared = self.prepare()
        lines = []
        for request in prepared["requests"]:
            card = {
                "status": "needs_review",
                "issue": "reading is ambiguous",
                "gcl_entry": request["gcl_entry"],
                "resolved_gcl_entry": "",
                "additional_gcl_entries": [],
                "reading": "",
                "definition": "",
                "examples": [],
                "example_count_rationale": "",
                "vocabulary": "",
            }
            lines.append(response_line(request["custom_id"], card))
        output = self.root / "output.jsonl"
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        deck_dir = self.root / "must_not_exist"
        deck_output = deck_dir / "must_not_exist.json"
        with self.assertRaisesRegex(PipelineError, "failed validation"):
            apply_results(
                manifest_path=Path(prepared["manifest_path"]),
                output_path=output,
                template_path=self.template,
                deck_output_path=deck_output,
            )
        self.assertFalse(deck_output.exists())
        self.assertTrue(
            deck_output.with_suffix(".generation-report.json").exists()
        )

    def test_update_preserves_existing_note_and_adds_only_missing_card(self):
        prepared = prepare_batch(
            gcl_path=self.gcl,
            work_dir=self.root / "update-work",
            start=2,
            end=2,
            model="gpt-test",
            reasoning_effort="low",
        )
        existing_note = {
            "__type__": "Note",
            "guid": "preserve-this-guid",
            "fields": [
                "<b>あ</b>う",
                "既存の定義。",
                (
                    "<div>事故に<b>あった</b>。</div>"
                    "<div>災難に<b>あわない</b>。</div>"
                    "<div>盗難に<b>あった</b>。</div>"
                ),
                "遭う",
            ],
            "note_model_uuid": "model-test",
            "tags": ["preserved"],
        }
        deck = json.loads(self.template.read_text(encoding="utf-8"))
        deck["notes"] = [existing_note]
        deck_dir = self.root / "update_deck"
        deck_dir.mkdir()
        deck_path = deck_dir / "update_deck.json"
        deck_path.write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8"
        )
        card = {
            "status": "card",
            "issue": "",
            "gcl_entry": "内閣[ないかく]",
            "resolved_gcl_entry": "内閣[ないかく]",
            "additional_gcl_entries": [],
            "reading": "<b>ないかく</b>",
            "definition": "国の行政を担う最高機関。",
            "examples": [
                "新しい<b>ないかく</b>が発足した。",
                "<b>ないかく</b>の方針が示された。",
                "<b>ないかく</b>は政策を改めた。",
            ],
            "example_count_rationale": "",
            "vocabulary": "内閣",
        }
        output = self.root / "update-output.jsonl"
        output.write_text(
            response_line(prepared["requests"][0]["custom_id"], card) + "\n",
            encoding="utf-8",
        )
        result = apply_update(
            manifest_path=Path(prepared["manifest_path"]),
            output_path=output,
            deck_path=deck_path,
            through=2,
        )
        updated = json.loads(deck_path.read_text(encoding="utf-8"))
        self.assertTrue(result["published"])
        self.assertEqual(result["preserved"], 1)
        self.assertEqual(result["added"], 1)
        self.assertEqual(updated["notes"][0], existing_note)
        self.assertEqual(updated["notes"][1]["fields"][3], "内閣")

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

    def test_prepare_retry_and_merge_replace_only_findings(self):
        prepared = self.prepare()
        failed_id = prepared["requests"][1]["custom_id"]
        report_path = self.root / "generation-report.json"
        report_path.write_text(
            json.dumps(
                {
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
        base_output = self.root / "base.jsonl"
        base_records = [
            {"custom_id": item["custom_id"], "value": "base"}
            for item in prepared["requests"]
        ]
        base_output.write_text(
            "\n".join(json.dumps(item) for item in base_records) + "\n",
            encoding="utf-8",
        )
        retry_output = self.root / "retry.jsonl"
        retry_output.write_text(
            json.dumps({"custom_id": failed_id, "value": "retry"}) + "\n",
            encoding="utf-8",
        )
        merged_output = self.root / "merged.jsonl"
        result = merge_retry_output(
            base_output_path=base_output,
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
