"""Direct-corpus gold CLI state machine and evidence locator tests."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from eval_methodology.mvp.dataset import build_gold as bg
from eval_methodology.mvp.metrics.judges import cli_backend
from eval_methodology.mvp.metrics.run_eval import _evidence_for_crec


QUOTE = "The characteristic value shall be determined from the documented standard procedure."


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "parsed"
    path = root / "standard" / "standard.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"# Clause 1\n\n{QUOTE}\n", encoding="utf-8")
    return root


def _gold(*, bad_path: bool = False) -> dict:
    return {
        "reference_answer": "The procedure is defined by the standard.",
        "evidence": [
            {
                "evidence_id": "e1",
                "document_path": "../escape.md" if bad_path else "standard/standard.md",
                "section": "Clause 1",
                "quote": QUOTE,
            }
        ],
        "claims": [
            {
                "claim_id": "c1",
                "text": "The standard defines a procedure.",
                "status": "supported",
                "evidence_ids": ["e1"],
            }
        ],
        "_resolved_model": "gpt-test",
    }


def _review(agree: bool) -> dict:
    return {
        "overall_agree": agree,
        "reference_answer_accurate": agree,
        "minimum_sufficient_evidence": agree,
        "per_claim": [
            {"claim_id": "c1", "agree": agree, "note": "ok" if agree else "fix"}
        ],
        "_resolved_model": "claude-test",
    }


def test_first_pass_order_is_codex_then_claude(tmp_path, monkeypatch):
    corpus = _corpus(tmp_path)
    calls = []
    monkeypatch.setattr(
        bg, "_codex", lambda prompt, root: calls.append("codex") or _gold()
    )
    monkeypatch.setattr(
        bg, "_claude", lambda prompt, root: calls.append("claude") or _review(True)
    )

    result = bg.build_one({"id": "Q1", "question": "question"}, corpus_dir=corpus)

    assert calls == ["codex", "claude"]
    assert result["status"] == "needs_human_review"
    assert result["gold"]["eligible_for_crec"] is False
    assert len(result["revision_history"]) == 1
    assert result["models"]["gold_interface"] == "codex-cli"
    assert result["models"]["verify_interface"] == "claude-cli"
    assert result["models"]["gold_family"] == "openai"
    assert result["models"]["verify_family"] == "anthropic"


def test_model_family_uses_resolved_model_not_cli_name():
    assert cli_backend.infer_model_family("gpt-5.6-sol") == "openai"
    assert cli_backend.infer_model_family("claude-opus-4") == "anthropic"
    assert cli_backend.infer_model_family("glm-5.2:cloud[1m]") == "zhipu"


def test_failed_review_triggers_codex_repair_then_claude_review(tmp_path, monkeypatch):
    corpus = _corpus(tmp_path)
    calls = []
    reviews = iter([_review(False), _review(True)])
    monkeypatch.setattr(
        bg, "_codex", lambda prompt, root: calls.append("codex") or _gold()
    )
    monkeypatch.setattr(
        bg, "_claude", lambda prompt, root: calls.append("claude") or next(reviews)
    )

    result = bg.build_one({"id": "Q1", "question": "question"}, corpus_dir=corpus)

    assert calls == ["codex", "claude", "codex", "claude"]
    assert result["status"] == "needs_human_review"
    assert [row["kind"] for row in result["revision_history"]] == ["draft", "repair"]


def test_validation_failure_triggers_repair_even_when_claude_agrees(
    tmp_path, monkeypatch
):
    corpus = _corpus(tmp_path)
    calls = []
    drafts = iter([_gold(bad_path=True), _gold()])
    monkeypatch.setattr(
        bg, "_codex", lambda prompt, root: calls.append("codex") or next(drafts)
    )
    monkeypatch.setattr(
        bg, "_claude", lambda prompt, root: calls.append("claude") or _review(True)
    )

    result = bg.build_one({"id": "Q1", "question": "question"}, corpus_dir=corpus)

    assert calls == ["codex", "claude", "codex", "claude"]
    assert result["status"] == "needs_human_review"
    assert result["revision_history"][0]["validation_errors"]


def test_two_failed_repairs_are_not_crec_eligible(tmp_path, monkeypatch):
    corpus = _corpus(tmp_path)
    calls = []
    monkeypatch.setattr(
        bg, "_codex", lambda prompt, root: calls.append("codex") or _gold()
    )
    monkeypatch.setattr(
        bg, "_claude", lambda prompt, root: calls.append("claude") or _review(False)
    )

    result = bg.build_one({"id": "Q1", "question": "question"}, corpus_dir=corpus)

    assert calls == ["codex", "claude", "codex", "claude", "codex", "claude"]
    assert result["status"] == "review_not_converged"
    assert len(result["revision_history"]) == 3


def test_validation_rejects_escape_short_fabricated_and_broken_refs(tmp_path):
    corpus = _corpus(tmp_path)
    gold = _gold(bad_path=True)
    gold["evidence"][0]["quote"] = "too short"
    gold["claims"][0]["evidence_ids"] = ["unknown"]

    errors = bg.validate_gold(gold, corpus)

    assert any("canonical relative path" in error for error in errors)
    assert any("shorter" in error for error in errors)
    assert any("unknown evidence_ids" in error for error in errors)


def test_validation_rejects_absolute_document_path(tmp_path):
    corpus = _corpus(tmp_path)
    gold = _gold()
    gold["evidence"][0]["document_path"] = str(corpus / "standard" / "standard.md")
    assert any(
        "canonical relative path" in error for error in bg.validate_gold(gold, corpus)
    )


def test_validation_rejects_quote_not_in_document(tmp_path):
    corpus = _corpus(tmp_path)
    gold = _gold()
    gold["evidence"][0]["quote"] = (
        "This fabricated quotation is definitely long enough but absent."
    )
    assert any(
        "not found verbatim" in error for error in bg.validate_gold(gold, corpus)
    )


def test_validation_rejects_quote_outside_declared_section(tmp_path):
    corpus = _corpus(tmp_path)
    gold = _gold()
    gold["evidence"][0]["section"] = "Clause 999"
    assert any("outside section" in error for error in bg.validate_gold(gold, corpus))


def test_validation_requires_exact_heading_not_prefix(tmp_path):
    corpus = _corpus(tmp_path)
    gold = _gold()
    gold["evidence"][0]["section"] = "Clause"
    assert any("outside section" in error for error in bg.validate_gold(gold, corpus))


def test_corpus_gap_cannot_reference_evidence(tmp_path):
    corpus = _corpus(tmp_path)
    gold = _gold()
    gold["claims"][0]["status"] = "corpus_gap"
    assert any(
        "corpus_gap claim references evidence" in error
        for error in bg.validate_gold(gold, corpus)
    )


def test_duplicate_claim_ids_are_rejected(tmp_path):
    corpus = _corpus(tmp_path)
    gold = _gold()
    gold["claims"].append(dict(gold["claims"][0]))
    assert any(
        "duplicate claim_id" in error for error in bg.validate_gold(gold, corpus)
    )


def test_empty_corpus_fails_fast(tmp_path):
    with pytest.raises(RuntimeError, match="no Markdown corpus files"):
        bg.corpus_manifest(tmp_path / "empty")


def test_corpus_manifest_rejects_markdown_symlink_escape(tmp_path):
    corpus = tmp_path / "parsed"
    corpus.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text(QUOTE, encoding="utf-8")
    (corpus / "escape.md").symlink_to(outside)
    with pytest.raises(RuntimeError, match="symlink escapes root"):
        bg.corpus_manifest(corpus)


def test_crec_requires_explicit_human_confirmation():
    item = {
        "gold_status": "needs_human_review",
        "gold_human_review": {"confirmed": False},
        "gold": {"evidence": _gold()["evidence"]},
    }
    assert _evidence_for_crec(item) == []
    item["gold_human_review"]["confirmed"] = True
    assert _evidence_for_crec(item) == _gold()["evidence"]
    item["gold_status"] = "review_not_converged"
    assert _evidence_for_crec(item) == []


def test_gold_builder_has_no_rag_or_index_dependency():
    source = Path(bg.__file__).read_text(encoding="utf-8")
    forbidden = (
        "from server.core.retrieval",
        "import HybridRetriever",
        "from pymilvus",
        "from elasticsearch",
    )
    assert all(token not in source for token in forbidden)


def test_cli_gold_permissions_are_explicit(tmp_path, monkeypatch):
    schema = tmp_path / "schema.json"
    schema.write_text(json.dumps({"type": "object"}), encoding="utf-8")
    corpus = _corpus(tmp_path)
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout='{"value": true}', stderr="")

    monkeypatch.setattr(cli_backend, "_run_cli_process", fake_run)
    cli_backend.run_codex_json(
        "prompt",
        schema_path=schema,
        workdir=tmp_path,
        ignore_rules=True,
        add_dirs=(corpus,),
        reasoning_effort="low",
    )
    cli_backend.run_claude_json(
        "prompt",
        schema_path=schema,
        workdir=tmp_path,
        tools=("Read", "Grep", "Glob"),
        add_dirs=(corpus,),
        permission_mode="dontAsk",
    )

    codex_cmd, codex_kwargs = seen[0]
    claude_cmd, claude_kwargs = seen[1]
    assert "--ephemeral" in codex_cmd and "read-only" in codex_cmd
    assert "--output-schema" in codex_cmd and "--ignore-rules" in codex_cmd
    assert codex_cmd[codex_cmd.index("-C") + 1] == str(tmp_path)
    assert codex_cmd[codex_cmd.index("--add-dir") + 1] == str(corpus)
    assert 'model_reasoning_effort="low"' in codex_cmd
    assert codex_kwargs == {"cwd": str(tmp_path), "timeout_s": 300.0}
    assert claude_cmd[claude_cmd.index("--tools") + 1] == "Read,Grep,Glob"
    assert "--json-schema" in claude_cmd and "--no-session-persistence" in claude_cmd
    assert "--bare" not in claude_cmd
    assert "--add-dir" in claude_cmd and "dontAsk" in claude_cmd
    assert claude_kwargs == {"cwd": str(tmp_path), "timeout_s": 300.0}


def test_cli_process_starts_new_session_and_kills_group_on_timeout(monkeypatch):
    seen = {"communicate_calls": 0}

    class FakeProcess:
        pid = 4242
        # The CLI wrapper can exit while its descendant still holds the pipe.
        returncode = 0

        def communicate(self, timeout=None):
            seen["communicate_calls"] += 1
            if timeout is not None:
                raise subprocess.TimeoutExpired(["cli"], timeout)
            return "", ""

    def fake_popen(cmd, **kwargs):
        seen["popen"] = kwargs
        return FakeProcess()

    kill_calls = []
    monkeypatch.setattr(cli_backend.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        os,
        "killpg",
        lambda process_group, sig: kill_calls.append((process_group, sig)),
    )

    with pytest.raises(subprocess.TimeoutExpired):
        cli_backend._run_cli_process(["cli"], cwd=None, timeout_s=0.01)

    assert seen["popen"]["start_new_session"] is True
    assert seen["popen"]["stdin"] is subprocess.DEVNULL
    assert seen["communicate_calls"] == 3
    assert kill_calls == [
        (4242, signal.SIGTERM),
        (4242, signal.SIGKILL),
    ]


def test_cli_process_timeout_reaps_pipe_holding_descendant():
    if not hasattr(os, "killpg"):
        pytest.skip("POSIX process groups are required")
    grandchild = "import time; time.sleep(60)"
    wrapper = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); "
        "sys.exit(0)"
    )
    started = time.monotonic()

    with pytest.raises(subprocess.TimeoutExpired):
        cli_backend._run_cli_process(
            [sys.executable, "-c", wrapper], cwd=None, timeout_s=0.1
        )

    assert time.monotonic() - started < 3.0


def test_gold_codex_uses_neutral_cwd_and_mounts_corpus(tmp_path, monkeypatch):
    corpus = _corpus(tmp_path)
    seen = {}

    def fake_codex(prompt, **kwargs):
        seen.update(kwargs)
        assert kwargs["workdir"] != corpus
        assert kwargs["workdir"].is_dir()
        return _gold()

    monkeypatch.setattr(bg, "run_codex_json", fake_codex)
    bg._codex("prompt", corpus)
    assert seen["add_dirs"] == (corpus,)
    assert seen["ignore_rules"] is True
    assert seen["model"] == "gpt-5.6-terra"
    assert seen["timeout_s"] == 900.0


def test_gold_claude_uses_neutral_cwd_and_mounts_corpus(tmp_path, monkeypatch):
    corpus = _corpus(tmp_path)
    seen = {}

    def fake_claude(prompt, **kwargs):
        seen.update(kwargs)
        assert kwargs["workdir"] != corpus
        assert kwargs["workdir"].is_dir()
        return _review(True)

    monkeypatch.setattr(bg, "run_claude_json", fake_claude)
    bg._claude("prompt", corpus)
    assert seen["add_dirs"] == (corpus,)
    assert seen["tools"] == ("Read", "Grep", "Glob")
    assert seen["timeout_s"] == 900.0


def test_generation_prompt_uses_selected_corpus_root(tmp_path):
    corpus = _corpus(tmp_path)
    mounted = tmp_path / "staged" / "corpus"
    prompt = bg._generation_prompt("question", bg.corpus_manifest(corpus), mounted)
    assert str(mounted) in prompt
    assert "当前工作目录是中立空目录" in prompt
    assert "不得假设当前目录含语料" in prompt


def test_staged_corpus_is_outside_source_and_preserves_manifest(tmp_path):
    corpus = _corpus(tmp_path)
    destination = tmp_path / "neutral"
    staged = bg._stage_corpus(corpus, destination)
    assert staged != corpus
    assert (staged / "standard" / "standard.md").read_text(encoding="utf-8")
    assert bg.corpus_manifest(staged)["sha256"] == bg.corpus_manifest(corpus)["sha256"]


def test_main_refuses_to_overwrite_without_force(tmp_path):
    output = tmp_path / "gold.json"
    output.write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        bg.main(["--out", str(output)])
    assert exc.value.code == 2
    assert output.read_text(encoding="utf-8") == "do not overwrite"


def test_confirm_human_review_persists_gate(tmp_path):
    corpus = _corpus(tmp_path)
    payload = {
        "items": [
            {
                "id": "Q1",
                "status": "needs_human_review",
                "gold": _gold(),
                "human_review": {"confirmed": False},
            }
        ]
    }
    count = bg.confirm_human_reviews(
        payload, ids={"Q1"}, reviewer="reviewer", corpus_dir=corpus
    )
    assert count == 1
    assert payload["items"][0]["status"] == "confirmed"
    assert payload["items"][0]["human_review"]["confirmed"] is True
    assert payload["items"][0]["gold"]["eligible_for_crec"] is True


def test_build_all_reports_errors(tmp_path, monkeypatch):
    corpus = _corpus(tmp_path)
    labels = tmp_path / "labels.json"
    labels.write_text(
        json.dumps({"items": [{"id": "Q1", "question": "question"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        bg, "_codex", lambda prompt, root: (_ for _ in ()).throw(RuntimeError("fail"))
    )
    payload = bg.build_all(labels, corpus_dir=corpus, review_dir=tmp_path / "review")
    assert payload["n_errors"] == 1


def test_main_returns_nonzero_when_any_item_failed(tmp_path, monkeypatch):
    output = tmp_path / "gold.json"
    monkeypatch.setattr(
        bg,
        "build_all",
        lambda *args, **kwargs: {
            "n": 1,
            "n_errors": 1,
            "review_path": "review.md",
            "items": [],
        },
    )
    assert bg.main(["--out", str(output)]) == 1
    assert json.loads(output.read_text(encoding="utf-8"))["n_errors"] == 1
