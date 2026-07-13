"""Fixed stratified split: dev16 / test9 / holdout6, bound to MVP version."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval_methodology.mvp.paths import (  # noqa: E402
    DATA_DIR,
    DATASET_JSON,
    LABELS_JSON,
    MVP_DATASET_VERSION,
    SPLIT_JSON,
)

DEV_N = 16
TEST_N = 9
HOLDOUT_N = 6
# Fixed seed string — split is deterministic across machines.
SPLIT_SEED = "euroqa-mvp-split-20260613"


def _stable_key(item: dict[str, Any]) -> str:
    raw = f"{SPLIT_SEED}|{item['id']}|{item['question']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stratified_split(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Assign ids to dev/test/holdout with stratum balancing.

    Targets: 16 / 9 / 6. If n != 31, scale proportionally but keep order stable.
    """
    n = len(items)
    if n == 0:
        return {"dev": [], "test": [], "holdout": []}

    # Target counts (exact when n==31).
    if n == DEV_N + TEST_N + HOLDOUT_N:
        targets = {"dev": DEV_N, "test": TEST_N, "holdout": HOLDOUT_N}
    else:
        dev = max(1, round(n * DEV_N / 31))
        hold = max(1, round(n * HOLDOUT_N / 31))
        test = max(0, n - dev - hold)
        targets = {"dev": dev, "test": test, "holdout": hold}

    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        stratum = (item.get("labels") or {}).get("stratum") or "unknown"
        by_stratum[stratum].append(item)

    for stratum in by_stratum:
        by_stratum[stratum].sort(key=_stable_key)

    assigned: dict[str, list[str]] = {"dev": [], "test": [], "holdout": []}
    # Round-robin fill per stratum to balance.
    buckets = ["dev", "test", "holdout"]
    # Prefer filling holdout sparingly: ratio 16:9:6.
    weights = {"dev": DEV_N, "test": TEST_N, "holdout": HOLDOUT_N}

    # Flatten with interleave.
    stratum_iters = {
        s: list(rows) for s, rows in sorted(by_stratum.items(), key=lambda kv: kv[0])
    }
    remaining = sum(len(v) for v in stratum_iters.values())
    while remaining > 0:
        progress = False
        for s in list(stratum_iters.keys()):
            if not stratum_iters[s]:
                continue
            # Pick bucket with largest remaining quota relative to weight.
            best = None
            best_score = -1e9
            for b in buckets:
                need = targets[b] - len(assigned[b])
                if need <= 0:
                    continue
                # Prefer underfilled relative to weight.
                filled_ratio = len(assigned[b]) / max(weights[b], 1)
                score = need - filled_ratio
                if score > best_score:
                    best_score = score
                    best = b
            if best is None:
                # All targets met — dump to dev.
                best = "dev"
            item = stratum_iters[s].pop(0)
            assigned[best].append(item["id"])
            remaining -= 1
            progress = True
        if not progress:
            break

    # Enforce exact sizes when n==31 by moving overflow.
    if n == DEV_N + TEST_N + HOLDOUT_N:
        pool: list[str] = []
        for b in buckets:
            while len(assigned[b]) > targets[b]:
                pool.append(assigned[b].pop())
        for b in buckets:
            while len(assigned[b]) < targets[b] and pool:
                assigned[b].append(pool.pop())
        # residual
        while pool:
            assigned["dev"].append(pool.pop())

    for b in assigned:
        assigned[b] = sorted(assigned[b], key=lambda i: i)
    return assigned


def build_split(labels_path: Path = LABELS_JSON) -> dict[str, Any]:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    items = labels["items"]
    split = stratified_split(items)
    payload = {
        "version": MVP_DATASET_VERSION,
        "seed": SPLIT_SEED,
        "counts": {k: len(v) for k, v in split.items()},
        "split": split,
    }
    return payload


def assemble_dataset(
    labels_path: Path = LABELS_JSON,
    split_path: Path = SPLIT_JSON,
    gold_path: Path | None = None,
) -> dict[str, Any]:
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    gold_by_id: dict[str, Any] = {}
    if gold_path and gold_path.is_file():
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        for g in gold.get("items", []):
            gold_by_id[g["id"]] = g

    id_to_split = {}
    for name, ids in split["split"].items():
        for qid in ids:
            id_to_split[qid] = name

    dataset_items = []
    for item in labels["items"]:
        g = gold_by_id.get(item["id"], {})
        dataset_items.append(
            {
                **item,
                "split": id_to_split.get(item["id"], "unassigned"),
                "gold": g.get("gold"),
                "gold_status": g.get("status"),
                "gold_human_review": g.get("human_review"),
            }
        )

    return {
        "version": MVP_DATASET_VERSION,
        "split_version": split.get("version"),
        "n": len(dataset_items),
        "counts": split.get("counts"),
        "items": dataset_items,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build fixed stratified split")
    parser.add_argument("--labels", type=Path, default=LABELS_JSON)
    parser.add_argument("--out", type=Path, default=SPLIT_JSON)
    parser.add_argument("--dataset-out", type=Path, default=DATASET_JSON)
    parser.add_argument("--gold", type=Path, default=None)
    args = parser.parse_args(argv)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = build_split(args.labels)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {args.out} counts={payload['counts']}")

    dataset = assemble_dataset(args.labels, args.out, args.gold)
    args.dataset_out.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {args.dataset_out} n={dataset['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
