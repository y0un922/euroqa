"""Paired bootstrap for A/B deltas with fixed seed (stdlib only)."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from eval_methodology.mvp.paths import BOOTSTRAP_B, BOOTSTRAP_SEED


@dataclass(frozen=True)
class BootstrapCI:
    mean: float
    low: float
    high: float
    width: float
    n: int
    exploratory: bool  # width > 0.1 → trend-only per main.tex


def paired_bootstrap_ci(
    baseline: Sequence[float],
    candidate: Sequence[float],
    *,
    b: int = BOOTSTRAP_B,
    seed: int = BOOTSTRAP_SEED,
    alpha: float = 0.05,
    width_exploratory: float = 0.1,
) -> BootstrapCI:
    """Bootstrap CI for mean(candidate - baseline) with paired resampling."""
    base = list(baseline)
    cand = list(candidate)
    if len(base) != len(cand):
        raise ValueError("baseline and candidate must be paired (same length)")
    n = len(base)
    if n == 0:
        return BootstrapCI(mean=0.0, low=0.0, high=0.0, width=0.0, n=0, exploratory=True)

    delta = [c - a for a, c in zip(base, cand, strict=True)]
    mean = sum(delta) / n
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(b):
        total = 0.0
        for _i in range(n):
            total += delta[rng.randrange(n)]
        samples.append(total / n)
    samples.sort()
    lo_idx = int((alpha / 2) * (b - 1))
    hi_idx = int((1 - alpha / 2) * (b - 1))
    low = samples[lo_idx]
    high = samples[hi_idx]
    width = high - low
    return BootstrapCI(
        mean=mean,
        low=low,
        high=high,
        width=width,
        n=n,
        exploratory=width > width_exploratory,
    )


def self_noise_bound(
    run_a: Sequence[float],
    run_b: Sequence[float],
) -> float:
    """Baseline self-fluctuation: mean |run_a - run_b| as δ/ε noise floor."""
    a = list(run_a)
    b = list(run_b)
    if len(a) != len(b) or not a:
        return 0.0
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)
