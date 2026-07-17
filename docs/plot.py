"""Regenerate docs/force_time.png — an illustrative countermovement-jump trace.

The curve is synthetic (no subject data): quiet stance, an unweighting dip, a
braking peak, propulsion, the airborne gap, then landing. Run from the repo root:

    python docs/plot.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def synthetic_cmj() -> tuple[np.ndarray, np.ndarray, int, int]:
    def seg(v, n):
        return np.full(n, v)

    def ramp(a, b, n):
        return np.linspace(a, b, n)

    curve = np.concatenate([
        seg(1.0, 800), ramp(1.0, 0.55, 250), ramp(0.55, 2.15, 250),
        ramp(2.15, 1.0, 180), seg(0.05, 345),
        ramp(0.05, 2.6, 40), ramp(2.6, 1.0, 260), seg(1.0, 400),
    ])
    curve += np.random.default_rng(0).normal(0, 0.01, curve.size)
    t = np.arange(curve.size) / 1000.0
    start = 800 + 250 + 250 + 180
    return t, curve, start, start + 345


def main() -> None:
    t, curve, start, end = synthetic_cmj()
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(t, curve, lw=0.9, color="#1f3b5c")
    ax.axhline(1.0, color="#888", lw=0.8, ls="--")
    ax.axvspan(t[start], t[end], color="#e8a13a", alpha=0.35, label="flight")
    ax.axhline(0.2, color="#c44", lw=0.7, ls=":", label="airborne threshold")
    ax.annotate("bodyweight", (t[-1], 1.0), (t[-1] - 1.1, 1.2), fontsize=8, color="#555")
    ax.annotate("unweight -> brake -> push", (t[900], 0.55), (t[300], 2.3), fontsize=8,
                color="#555", arrowprops=dict(arrowstyle="->", color="#999"))
    ax.annotate("landing", (t[end + 120], 2.5), (t[end + 180], 2.5), fontsize=8, color="#555")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("force / bodyweight")
    ax.set_title("Countermovement jump - vertical ground reaction force (illustrative)", fontsize=10)
    ax.set_ylim(0, 3.0)
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    out = Path(__file__).resolve().parent / "force_time.png"
    fig.savefig(out, dpi=110)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
