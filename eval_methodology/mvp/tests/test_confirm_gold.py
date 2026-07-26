"""Gold human-confirmation workflow tests (packet, apply, CRec gating)."""

from __future__ import annotations

import pytest

from eval_methodology.mvp.dataset.confirm_gold import (
    apply_review,
    build_packet,
    review_state,
    supported_items,
    verify_evidence,
)
from eval_methodology.mvp.metrics.run_eval import (
    _evidence_for_crec,
    _gold_confirmed,
    metrics_from_answers,
)

QUOTE = "a sufficiently long exact evidence quotation for gold"


def _dataset() -> dict:
    return {
        "items": [
            {
                "id": "Q1",
                "question": "q1",
                "gold": {
                    "gold_claim_status": "supported",
                    "claims": [{"claim_id": "c1", "text": "claim one", "status": "supported"}],
                    "evidence": [
                        {
                            "evidence_id": "ev1",
                            "document_path": "DOC/doc.md",
                            "section": "S1",
                            "quote": QUOTE,
                        }
                    ],
                },
            },
            {
                "id": "Q2",
                "question": "q2",
                "gold": {
                    "gold_claim_status": "supported",
                    "claims": [],
                    "evidence": [
                        {
                            "evidence_id": "ev2",
                            "document_path": "DOC/doc.md",
                            "section": "S2",
                            "quote": "this quotation does not exist in the corpus",
                        }
                    ],
                },
            },
            {"id": "Q3", "question": "q3", "gold": {"gold_claim_status": "mixed"}},
        ]
    }


@pytest.fixture()
def parsed_dir(tmp_path):
    doc = tmp_path / "DOC" / "doc.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(f"# heading\n\nprefix {QUOTE} suffix\n", encoding="utf-8")
    return tmp_path


def test_supported_items_excludes_non_supported():
    assert [item["id"] for item in supported_items(_dataset())] == ["Q1", "Q2"]


def test_verify_evidence_checks_quote_presence(parsed_dir):
    data = _dataset()
    ok = verify_evidence(data["items"][0], parsed_dir)
    missing = verify_evidence(data["items"][1], parsed_dir)
    assert ok[0]["quote_found"] and ok[0]["file_exists"]
    assert missing[0]["file_exists"] and not missing[0]["quote_found"]


def test_apply_review_confirm_and_reject():
    data = _dataset()
    updated = apply_review(data, ["Q1"], reviewer="youngz", confirmed=True)
    assert updated == ["Q1"]
    review = data["items"][0]["gold"]["human_review"]
    assert review["confirmed"] is True and review["reviewer"] == "youngz"
    assert review_state(data["items"][0]) == "confirmed"

    apply_review(data, ["Q2"], reviewer="youngz", confirmed=False, note="not minimal")
    assert review_state(data["items"][1]) == "rejected"


def test_apply_review_all_and_unknown_id():
    data = _dataset()
    assert sorted(apply_review(data, ["all"], reviewer="r", confirmed=True)) == ["Q1", "Q2"]
    with pytest.raises(ValueError):
        apply_review(_dataset(), ["Q3"], reviewer="r", confirmed=True)
    with pytest.raises(ValueError):
        apply_review(_dataset(), ["Q1"], reviewer=" ", confirmed=True)


def test_rejected_gold_leaves_crec_denominator():
    data = _dataset()
    assert _evidence_for_crec(data["items"][0])
    apply_review(data, ["Q1"], reviewer="r", confirmed=False, note="bad evidence")
    assert _evidence_for_crec(data["items"][0]) == []
    apply_review(data, ["Q2"], reviewer="r", confirmed=True)
    assert _evidence_for_crec(data["items"][1])
    assert _gold_confirmed(data["items"][1])


def test_confirmed_count_flows_into_aggregate():
    data = _dataset()
    apply_review(data, ["Q1"], reviewer="r", confirmed=True)
    answer = {
        "id": "Q1",
        "status": "ok",
        "answer": "answer",
        "context_chunk_ids": ["c1"],
        "context_chunks": [{"chunk_id": "c1", "content": f"prefix {QUOTE} suffix"}],
        "unresolved_refs": [],
        "resolved_refs": [],
        "elapsed_ms": 1,
    }
    result = metrics_from_answers({"Q1": answer}, [data["items"][0]], use_llm_judge=False)
    assert result["aggregate"]["crec_eligible_n"] == 1
    assert result["aggregate"]["crec_confirmed_n"] == 1
    assert result["per_question"][0]["gold_confirmed"] is True


def test_packet_marks_verified_and_missing_quotes(parsed_dir):
    packet = build_packet(_dataset(), parsed_dir)
    assert "Q1" in packet and "Q2" in packet and "Q3" not in packet
    assert "✓" in packet and "✗" in packet
    assert "有引用未通过语料校验" in packet
