"""Apply the editorial resolutions for the final eight N1 remainder cards."""

from __future__ import annotations

import json
from pathlib import Path

from japanese_vocabulary_batch.pipeline import (
    apply_update,
    atomic_write_json,
    atomic_write_text,
    clean_and_read_gcl,
    deterministic_guid,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
GCL_PATH = ROOT / "gcl" / "n1_vocabulary_generation_control_file.txt"
DECK_PATH = (
    ROOT
    / "n1_vocabulary_crowdanki_deck"
    / "n1_vocabulary_crowdanki_deck.json"
)
WORK_DIR = ROOT / ".batch" / "editorial-resolution"


CARDS = [
    {
        "status": "card",
        "issue": "",
        "gcl_entry": "厳か[おごそかな](な)",
        "resolved_gcl_entry": "厳か[おごそかな](な)",
        "additional_gcl_entries": [],
        "reading": "<b>おごそ</b>かな",
        "definition": "重々しく、気高く、改まった感じがあるさま。",
        "examples": [
            "式典は<b>おごそか</b>な雰囲気のうちに始まった。",
            "参列者は<b>おごそか</b>に黙祷をささげた。",
            "神前で<b>おごそか</b>な誓いを立てた。",
        ],
        "example_count_rationale": "",
        "vocabulary": "厳か",
    },
    {
        "status": "card",
        "issue": "",
        "gcl_entry": "哀れ[あわれな](な)",
        "resolved_gcl_entry": "哀れ[あわれな](な)",
        "additional_gcl_entries": [],
        "reading": "<b>あわれ</b>な",
        "definition": "不幸で、同情や悲しみを感じさせるさま。",
        "examples": [
            "彼の境遇は、聞く者の胸を締めつけるほど<b>あわれな</b>ものだった。",
            "戦争で家族を失った人々の姿は、あまりにも<b>あわれだった</b>。",
            "誤りを認めず言い訳を重ねる姿が、かえって<b>あわれに</b>見えた。",
        ],
        "example_count_rationale": "",
        "vocabulary": "哀れ",
    },
    {
        "status": "card",
        "issue": "",
        "gcl_entry": "器[うつわ]",
        "resolved_gcl_entry": "器[うつわ]",
        "additional_gcl_entries": [],
        "reading": "<b>うつわ</b>",
        "definition": "料理などを入れたり盛り付けたりするために使う、食卓上の道具。",
        "examples": [
            "この<b>うつわ</b>は、手になじむ形と落ち着いた色合いが魅力だ。",
            "料理に合わせて<b>うつわ</b>を選ぶと、食卓の印象が大きく変わる。",
            "作家の<b>うつわ</b>を少しずつ集めるのが楽しみになっている。",
        ],
        "example_count_rationale": "",
        "vocabulary": "器",
    },
    {
        "status": "card",
        "issue": "",
        "gcl_entry": "柄[え]",
        "resolved_gcl_entry": "柄[え]",
        "additional_gcl_entries": [],
        "reading": "<b>え</b>",
        "definition": "道具や武器などで、手に持つために取り付けた細長い部分。",
        "examples": [
            "包丁の<b>え</b>が緩んでいたので、修理に出した。",
            "傘の<b>え</b>をしっかり握って、強風に備えた。",
            "このほうきは<b>え</b>が長く、腰を曲げずに掃除できる。",
        ],
        "example_count_rationale": "",
        "vocabulary": "柄",
    },
    {
        "status": "card",
        "issue": "",
        "gcl_entry": "頭[かしら]",
        "resolved_gcl_entry": "頭[かしら]",
        "additional_gcl_entries": [],
        "reading": "<b>かしら</b>",
        "definition": "人の体で首より上の部分。また、集団を率いる者。",
        "examples": [
            "転んで<b>かしら</b>を強く打った。",
            "彼は職人たちの<b>かしら</b>として、現場を取り仕切っている。",
            "行列の<b>かしら</b>に立ち、参加者を先導した。",
        ],
        "example_count_rationale": "",
        "vocabulary": "頭",
    },
    {
        "status": "card",
        "issue": "",
        "gcl_entry": "志[こころざし]",
        "resolved_gcl_entry": "志[こころざし]",
        "additional_gcl_entries": [],
        "reading": "<b>こころざし</b>",
        "definition": "将来実現したいと強く願う目標や決意。",
        "examples": [
            "若い頃から海外で働くという<b>こころざし</b>を抱いていた。",
            "研究者としての<b>こころざし</b>を貫くには、長い努力が必要だ。",
            "高い<b>こころざし</b>を共有する仲間と、新しい事業を始めた。",
        ],
        "example_count_rationale": "",
        "vocabulary": "志",
    },
    {
        "status": "card",
        "issue": "",
        "gcl_entry": "影[かげ]",
        "resolved_gcl_entry": "影[かげ]",
        "additional_gcl_entries": [],
        "reading": "<b>かげ</b>",
        "definition": "光が遮られてできる暗い部分。転じて、表に出ない事情や好ましくない作用。",
        "examples": [
            "夕日を受けて、木の<b>かげ</b>が長く伸びている。",
            "彼の成功の<b>かげ</b>には、長年の努力があった。",
            "華やかな発展の<b>かげ</b>で、環境問題が深刻化していた。",
        ],
        "example_count_rationale": "",
        "vocabulary": "影",
    },
    {
        "status": "card",
        "issue": "",
        "gcl_entry": "詳しい[くわしい]",
        "resolved_gcl_entry": "詳しい[くわしい]",
        "additional_gcl_entries": [],
        "reading": "<b>くわ</b>しい",
        "definition": "細かな点までよく分かっていて、内容が具体的であるさま。",
        "examples": [
            "事故の経緯について<b>くわしく</b>説明してください。",
            "調査結果は報告書に<b>くわしく</b>記されている。",
            "彼はこの地域の歴史に<b>くわしい</b>。",
        ],
        "example_count_rationale": "",
        "vocabulary": "詳しい",
    },
]


def main() -> None:
    entries, _ = clean_and_read_gcl(GCL_PATH)
    entries_by_text = {entry.text: entry for entry in entries}
    deck = json.loads(DECK_PATH.read_text(encoding="utf-8-sig"))
    existing_guids = {note.get("guid") for note in deck["notes"]}
    cards = [
        card
        for card in CARDS
        if card["gcl_entry"] in entries_by_text
        and deterministic_guid(card["gcl_entry"]) not in existing_guids
    ]
    missing = {card["gcl_entry"] for card in cards} - entries_by_text.keys()
    if missing:
        raise RuntimeError(f"Editorial entries are missing from the GCL: {missing}")

    requests = [
        {
            "custom_id": entries_by_text[card["gcl_entry"]].identity,
            "source_index": entries_by_text[card["gcl_entry"]].source_index,
            "gcl_entry": card["gcl_entry"],
        }
        for card in cards
    ]
    input_path = WORK_DIR / "input_editorial.jsonl"
    output_path = WORK_DIR / "output_editorial.jsonl"
    manifest_path = WORK_DIR / "manifest_editorial.json"
    atomic_write_text(input_path, "\n")
    atomic_write_text(
        output_path,
        "\n".join(
            json.dumps(
                {
                    "custom_id": request["custom_id"],
                    "response": {
                        "status_code": 200,
                        "body": {"output_text": json.dumps({"result": card}, ensure_ascii=False)},
                    },
                },
                ensure_ascii=False,
            )
            for request, card in zip(requests, cards, strict=True)
        )
        + "\n",
    )
    atomic_write_json(
        manifest_path,
        {
            "version": 1,
            "operation": "editorial-resolution",
            "gcl_path": str(GCL_PATH.resolve()),
            "gcl_sha256": sha256_file(GCL_PATH),
            "input_path": str(input_path.resolve()),
            "input_sha256": sha256_file(input_path),
            "range": {"start": 1, "end": len(entries)},
            "total_gcl_entries": len(entries),
            "requests": requests,
        },
    )

    result = apply_update(
        manifest_path=manifest_path,
        output_path=output_path,
        deck_path=DECK_PATH,
        through=len(entries),
        allow_partial=False,
    )
    if result["final_notes"] != len(entries):
        raise RuntimeError(
            f"Expected {len(entries)} notes, published {result['final_notes']}"
        )

    plan_path = ROOT / ".batch" / "remainder-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan.update(
        {
            "gcl_sha256": sha256_file(GCL_PATH),
            "status": "completed",
            "accepted_cards": len(entries) - int(plan["starting_notes"]),
            "final_notes": len(entries),
            "review_queue": [],
            "editorially_resolved_cards": len(CARDS),
            "editorial_resolution_manifest": str(manifest_path.resolve()),
        }
    )
    for job in plan["jobs"]:
        if job.get("status") == "needs_review":
            job["status"] = "accepted_with_editorial_resolution"
    atomic_write_json(plan_path, plan)
    atomic_write_json(ROOT / ".batch" / "remainder-review.json", [])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
