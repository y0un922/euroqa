"""Build weak-supervision gold with independent Codex and Claude CLI agents.

Codex reads ``data/parsed`` directly and creates a draft. Claude independently
reads the same corpus and reviews it. Deterministic or Claude review failures
are returned to Codex for at most two complete repair rounds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.metrics.judges.cli_backend import (  # noqa: E402
    infer_model_family,
    run_claude_json,
    run_codex_json,
)
from eval_methodology.mvp.dataset.gold_corpus import (  # noqa: E402
    MIN_QUOTE_CHARS,
    corpus_manifest,
    validate_gold,
)
from eval_methodology.mvp.paths import (  # noqa: E402
    DATA_DIR,
    GOLD_JSON,
    LABELS_JSON,
    PARSED_CORPUS_DIR,
    REVIEW_DIR,
    SCHEMAS_DIR,
)

GOLD_SCHEMA_PATH = SCHEMAS_DIR / "gold_output.schema.json"
VERIFY_SCHEMA_PATH = SCHEMAS_DIR / "gold_verify.schema.json"
GOLD_PROMPT_VERSION = "gold-direct-corpus-v3"
VERIFY_PROMPT_VERSION = "gold-independent-review-v2"
MAX_REPAIR_ROUNDS = 2
GOLD_CODEX_MODEL = "gpt-5.6-terra"
GOLD_CLI_TIMEOUT_S = 900.0

GOLD_OUTPUT_RULES = f"""这是已获用户授权的非交互批处理任务。立即检索并输出 schema JSON；不得输出 HelloAGENTS 状态栏、需求评分、确认选项、解释或等待用户回复。
- document_path 必须是相对语料根目录的规范路径，禁止绝对路径和 `..`。
- section 必须逐字等于 quote 前最近出现的 Markdown heading（即实际包围 quote 的最深层 heading）可见文本：去掉行首 `#` 和空格后再填写；不得用父章节标题代替最近 heading；section 中禁止包含 `#`，禁止把两个 heading 用分号或其他方式合并。
- quote 必须从该 section 范围内复制一个连续的原文片段，至少 {MIN_QUOTE_CHARS} 字符；不得改写、拼接不连续段落、改变 LaTeX/HTML/标点或自行补空格。输出前必须用文件搜索确认整个 quote 能在文档中逐字找到。
- 每条 claim 只表达一个可独立核验的事实。若一句话需要不同段落或不同公式支持，必须拆成多条 claims。
- claim 的每个事实子句都必须被其 evidence_ids 所指 quote 直接覆盖；不要只引用公式或列表前的引导句，必须把实际公式、数值或列表项包含进 quote。
- supported claim 必须引用至少一个 evidence_id；corpus_gap 的 evidence_ids 必须为空。
- evidence_id/claim_id 在本题内唯一；不要输出未被 claim 使用的 evidence。
- reference_answer 只能陈述 claims 覆盖且语料支持的内容；对 corpus_gap 明确说明语料不足。"""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _generation_prompt(
    question: str, manifest: dict[str, Any], corpus_root: Path
) -> str:
    files = "\n".join(f"- {row['path']}" for row in manifest["files"])
    return f"""你是 Eurocode 评测集的 gold 生成员。当前工作目录是中立空目录；只读语料挂载在绝对路径：{corpus_root}。
必须直接使用文件读取/搜索能力，完整检索该绝对路径下的 Markdown 规范和指南；不得假设当前目录含语料，不得调用本项目 RAG、检索器、Milvus、Elasticsearch 或复用候选池。

任务：针对问题生成中文参考答案和原子 claims，并从实际 Markdown 文件中给出最小充分证据集。
{GOLD_OUTPUT_RULES}

问题：{question}

可用 Markdown 文件（manifest sha256={manifest["sha256"]}）：
{files}
"""


def _review_prompt(
    question: str,
    gold: dict[str, Any],
    manifest: dict[str, Any],
    corpus_root: Path,
) -> str:
    clean = {k: v for k, v in gold.items() if not k.startswith("_")}
    return f"""你是独立 gold 审查员。当前工作目录是中立空目录；只读语料挂载在绝对路径：{corpus_root}。必须自行使用 Read/Grep/Glob 搜索该绝对路径的完整语料，不得仅相信 Codex 给出的 quote，也不得调用项目 RAG、Milvus 或 Elasticsearch。

核验以下内容：参考答案是否准确完整；每条 claim 是否原子且状态正确；每个 quote 是否来自所列文件并直接支持 claim；证据是否是最小充分集；是否存在 Codex 漏检却错误标为 corpus_gap 的证据。
per_claim 必须恰好覆盖所有 claim_id。任何事实错误、漏证、伪造路径/引文、证据不足或非最小集都应 agree=false，并令 overall_agree=false。不要用模型记忆代替语料证据。

问题：{question}
语料 manifest sha256：{manifest["sha256"]}
待审 gold：
{json.dumps(clean, ensure_ascii=False, indent=2)}
"""


def _repair_prompt(
    question: str,
    gold: dict[str, Any],
    validation_errors: list[str],
    review: dict[str, Any],
    manifest: dict[str, Any],
    corpus_root: Path,
) -> str:
    clean_review = {k: v for k, v in review.items() if not k.startswith("_")}
    clean_gold = {k: v for k, v in gold.items() if not k.startswith("_")}
    return f"""你是 Eurocode gold 返修员。Claude 审查或确定性校验发现问题。
当前工作目录是中立空目录；只读语料挂载在绝对路径：{corpus_root}。请重新直接搜索该绝对路径的 Markdown 全语料并输出一份完整替换版 gold。不得假设当前目录含语料，不得调用项目 RAG、Milvus、Elasticsearch，不得只局部打补丁。
必须针对下面每条确定性错误和 Claude 分歧逐项修复，不得原样重复上一版定位符。
{GOLD_OUTPUT_RULES}

问题：{question}
语料 manifest sha256：{manifest["sha256"]}
确定性错误：{json.dumps(validation_errors, ensure_ascii=False)}
Claude 审查：{json.dumps(clean_review, ensure_ascii=False, indent=2)}
上一版 gold：{json.dumps(clean_gold, ensure_ascii=False, indent=2)}
"""


def _review_passed(review: dict[str, Any], claim_ids: set[str]) -> bool:
    verdicts = review.get("per_claim") or []
    reviewed_ids = {str(v.get("claim_id") or "") for v in verdicts}
    return bool(
        review.get("overall_agree")
        and review.get("reference_answer_accurate")
        and review.get("minimum_sufficient_evidence")
        and reviewed_ids == claim_ids
        and len(verdicts) == len(claim_ids)
        and all(v.get("agree") for v in verdicts)
    )


def _codex(prompt: str, corpus_dir: Path) -> dict[str, Any]:
    # Neutral cwd prevents repository AGENTS.md inheritance.
    with tempfile.TemporaryDirectory(prefix="mvp_gold_codex_") as temp_dir:
        return run_codex_json(
            prompt,
            schema_path=GOLD_SCHEMA_PATH,
            workdir=Path(temp_dir),
            ignore_rules=True,
            add_dirs=(corpus_dir,),
            reasoning_effort="low",
            model=GOLD_CODEX_MODEL,
            timeout_s=GOLD_CLI_TIMEOUT_S,
        )


def _claude(prompt: str, corpus_dir: Path) -> dict[str, Any]:
    # Neutral cwd prevents project CLAUDE.md discovery without breaking OAuth.
    with tempfile.TemporaryDirectory(prefix="mvp_gold_claude_") as temp_dir:
        return run_claude_json(
            prompt,
            schema_path=VERIFY_SCHEMA_PATH,
            workdir=Path(temp_dir),
            tools=("Read", "Grep", "Glob"),
            add_dirs=(corpus_dir,),
            permission_mode="dontAsk",
            timeout_s=GOLD_CLI_TIMEOUT_S,
        )


def _stage_corpus(source: Path, destination: Path) -> Path:
    """Copy Markdown corpus outside the project tree for CLI isolation."""
    staged = destination / "corpus"
    for source_file in source.resolve().rglob("*.md"):
        relative = source_file.relative_to(source.resolve())
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)
    corpus_manifest(staged)
    return staged


def build_one(
    item: dict[str, Any],
    *,
    corpus_dir: Path = PARSED_CORPUS_DIR,
    max_repair_rounds: int = MAX_REPAIR_ROUNDS,
) -> dict[str, Any]:
    """Run Codex generation, Claude review, and bounded Codex repair."""
    question = str(item["question"])
    manifest = corpus_manifest(corpus_dir)
    history: list[dict[str, Any]] = []
    converged = False
    with tempfile.TemporaryDirectory(prefix="mvp_gold_corpus_") as stage_dir:
        staged_corpus = _stage_corpus(corpus_dir, Path(stage_dir))
        gold = _codex(
            _generation_prompt(question, manifest, staged_corpus), staged_corpus
        )
        for round_index in range(max_repair_rounds + 1):
            validation_errors = validate_gold(gold, corpus_dir)
            review = _claude(
                _review_prompt(question, gold, manifest, staged_corpus), staged_corpus
            )
            claim_ids = {str(c.get("claim_id") or "") for c in gold.get("claims") or []}
            converged = not validation_errors and _review_passed(review, claim_ids)
            history.append(
                {
                    "round": round_index,
                    "kind": "draft" if round_index == 0 else "repair",
                    "validation_errors": validation_errors,
                    "review": {
                        k: v for k, v in review.items() if not k.startswith("_")
                    },
                    "codex_model": gold.get("_resolved_model"),
                    "claude_model": review.get("_resolved_model"),
                    "gold_sha256": hashlib.sha256(
                        json.dumps(
                            {k: v for k, v in gold.items() if not k.startswith("_")},
                            ensure_ascii=False,
                            sort_keys=True,
                        ).encode("utf-8")
                    ).hexdigest(),
                    "passed": converged,
                }
            )
            if converged or round_index == max_repair_rounds:
                break
            gold = _codex(
                _repair_prompt(
                    question,
                    gold,
                    validation_errors,
                    review,
                    manifest,
                    staged_corpus,
                ),
                staged_corpus,
            )

    evidence = list(gold.get("evidence") or [])
    claims = list(gold.get("claims") or [])
    e_plus = sorted(
        {
            str(eid)
            for claim in claims
            if claim.get("status") == "supported"
            for eid in claim.get("evidence_ids") or []
        }
    )
    statuses = {c.get("status") for c in claims}
    claim_status = (
        "none"
        if not claims
        else next(iter(statuses))
        if len(statuses) == 1
        else "mixed"
    )
    gold_model = history[-1]["codex_model"]
    verify_model = history[-1]["claude_model"]
    return {
        "id": item["id"],
        "question": question,
        "status": "needs_human_review" if converged else "review_not_converged",
        "built_at": _utc_now(),
        "prompt_versions": {
            "gold": GOLD_PROMPT_VERSION,
            "verify": VERIFY_PROMPT_VERSION,
        },
        "corpus_manifest": manifest,
        "models": {
            "gold_interface": "codex-cli",
            "verify_interface": "claude-cli",
            "gold_family": infer_model_family(gold_model),
            "verify_family": infer_model_family(verify_model),
            "gold_model": gold_model,
            "verify_model": verify_model,
        },
        "revision_history": history,
        "gold": {
            "reference_answer": gold.get("reference_answer", ""),
            "claims": claims,
            "evidence": evidence,
            "E_plus": e_plus,
            "eligible_for_crec": False,
            "gold_claim_status": claim_status,
        },
        "disputes": [
            verdict
            for verdict in (history[-1]["review"].get("per_claim") or [])
            if not verdict.get("agree")
        ],
        "human_review": {
            "required": True,
            "task": "confirm_minimum_sufficient_evidence_set",
            "confirmed": False,
            "confirmed_by": "",
            "confirmed_at": "",
        },
    }


def write_human_review_packet(
    results: list[dict[str, Any]], *, review_dir: Path = REVIEW_DIR
) -> Path:
    """Write the required minimum-sufficient-evidence review for all items."""
    review_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = review_dir / f"gold_min_evidence_review_{stamp}.md"
    lines = [
        f"# Gold 最小充分证据集人工复核 ({stamp})",
        "",
        "范围：全部题目。只有人工确认后该题才可进入正式 CRec。",
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"## {result['id']}: {result.get('question', '')}",
                f"- status: {result.get('status')}",
            ]
        )
        gold = result.get("gold") or {}
        lines.append(f"- reference_answer: {gold.get('reference_answer', '')}")
        for claim in gold.get("claims") or []:
            lines.append(
                f"- `{claim.get('claim_id')}` [{claim.get('status')}]: {claim.get('text')}"
            )
            lines.append(
                f"  evidence: {', '.join(claim.get('evidence_ids') or []) or '(none)'}"
            )
        for evidence in gold.get("evidence") or []:
            lines.append(
                f"  - `{evidence.get('evidence_id')}` {evidence.get('document_path')}"
                f" / {evidence.get('section')}: {evidence.get('quote')}"
            )
        for dispute in result.get("disputes") or []:
            lines.append(
                f"- [DISPUTED] `{dispute.get('claim_id')}`: {dispute.get('note')}"
            )
        if result.get("error"):
            lines.append(f"- error: {result['error']}")
        lines.extend(["- [ ] 人工确认最小充分证据集", ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    disputed = [
        result
        for result in results
        if result.get("disputes") or result.get("status") == "review_not_converged"
    ]
    if disputed:
        disputes_path = review_dir / f"disputes_{stamp}.md"
        dispute_lines = [f"# Gold model disputes ({stamp})", ""]
        for result in disputed:
            dispute_lines.append(f"## {result['id']}: {result.get('question', '')}")
            for row in result.get("disputes") or []:
                dispute_lines.append(f"- `{row.get('claim_id')}`: {row.get('note')}")
            history = result.get("revision_history") or []
            for error in (
                history[-1].get("validation_errors") if history else []
            ) or []:
                dispute_lines.append(f"- deterministic: {error}")
            dispute_lines.append("")
        disputes_path.write_text("\n".join(dispute_lines), encoding="utf-8")
    return path


def build_all(
    labels_path: Path,
    *,
    corpus_dir: Path = PARSED_CORPUS_DIR,
    limit: int | None = None,
    ids: list[str] | None = None,
    review_dir: Path = REVIEW_DIR,
) -> dict[str, Any]:
    """Build selected labels sequentially and retain per-item failures."""
    corpus_manifest(corpus_dir)
    items = json.loads(labels_path.read_text(encoding="utf-8"))["items"]
    if ids:
        selected = set(ids)
        items = [item for item in items if item["id"] in selected]
    if limit is not None:
        items = items[:limit]
    results = []
    for index, item in enumerate(items, 1):
        print(f"[{index}/{len(items)}] gold {item['id']}")
        try:
            results.append(build_one(item, corpus_dir=corpus_dir))
        except Exception as exc:  # noqa: BLE001
            results.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                    "gold": {
                        "reference_answer": "",
                        "claims": [],
                        "evidence": [],
                        "E_plus": [],
                    },
                }
            )
    review_path = write_human_review_packet(results, review_dir=review_dir)
    return {
        "built_at": _utc_now(),
        "n": len(results),
        "n_errors": sum(result.get("status") == "error" for result in results),
        "review_path": str(review_path),
        "items": results,
    }


def confirm_human_reviews(
    payload: dict[str, Any],
    *,
    ids: set[str] | None,
    reviewer: str,
    corpus_dir: Path,
) -> int:
    """Persist human minimum-sufficient-evidence confirmation."""
    confirmed = 0
    for item in payload.get("items") or []:
        if ids is not None and item.get("id") not in ids:
            continue
        if item.get("status") not in {"needs_human_review", "confirmed"}:
            raise ValueError(
                f"cannot confirm {item.get('id')}: status={item.get('status')}"
            )
        errors = validate_gold(item.get("gold") or {}, corpus_dir)
        if errors:
            raise ValueError(f"cannot confirm {item.get('id')}: {errors}")
        review = item.setdefault("human_review", {})
        review.update(
            {
                "required": True,
                "task": "confirm_minimum_sufficient_evidence_set",
                "confirmed": True,
                "confirmed_by": reviewer,
                "confirmed_at": _utc_now(),
            }
        )
        item["status"] = "confirmed"
        item["gold"]["eligible_for_crec"] = True
        confirmed += 1
    if confirmed == 0:
        raise ValueError("no matching gold items to confirm")
    return confirmed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build gold through Codex and Claude CLIs"
    )
    parser.add_argument("--labels", type=Path, default=LABELS_JSON)
    parser.add_argument("--corpus", type=Path, default=PARSED_CORPUS_DIR)
    parser.add_argument("--out", type=Path, default=GOLD_JSON)
    parser.add_argument("--review-dir", type=Path, default=REVIEW_DIR)
    parser.add_argument(
        "--force", action="store_true", help="overwrite an existing output"
    )
    parser.add_argument(
        "--confirm",
        type=str,
        default=None,
        help="persist human review for comma-separated IDs or 'all' in --out",
    )
    parser.add_argument("--reviewer", type=str, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ids", type=str, default=None, help="comma-separated ids")
    args = parser.parse_args(argv)
    if args.confirm is not None:
        if not args.out.is_file():
            parser.error(f"gold output does not exist: {args.out}")
        if not args.reviewer or not args.reviewer.strip():
            parser.error("--reviewer is required with --confirm")
        payload = json.loads(args.out.read_text(encoding="utf-8"))
        confirm_ids = None
        if args.confirm.strip().lower() != "all":
            confirm_ids = {
                value.strip() for value in args.confirm.split(",") if value.strip()
            }
        try:
            count = confirm_human_reviews(
                payload,
                ids=confirm_ids,
                reviewer=args.reviewer.strip(),
                corpus_dir=args.corpus,
            )
        except ValueError as exc:
            parser.error(str(exc))
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"confirmed {count} gold item(s) in {args.out}")
        return 0
    if args.out.exists() and not args.force:
        parser.error(f"output already exists: {args.out}; pass --force to overwrite")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ids = [value.strip() for value in args.ids.split(",")] if args.ids else None
    payload = build_all(
        args.labels,
        corpus_dir=args.corpus,
        limit=args.limit,
        ids=ids,
        review_dir=args.review_dir,
    )
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {args.out} n={payload['n']} review={payload['review_path']}")
    return 1 if payload["n_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
