"""Analyse a force-plate jump recording from the command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .metrics import analyse
from .parse import parse_opensignals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="forceplate",
        description="Compute vertical-jump metrics from an OpenSignals force-plate recording.",
    )
    parser.add_argument("recording", type=Path, help="OpenSignals .txt file")
    args = parser.parse_args(argv)

    rec = parse_opensignals(args.recording)
    print(
        f"{args.recording.name}: {rec.n_platforms} platform(s), "
        f"{rec.sampling_rate_hz:.0f} Hz, {rec.duration_s:.1f} s",
        file=sys.stderr,
    )

    try:
        m = analyse(rec)
    except ValueError as exc:
        print(f"not a valid vertical jump: {exc}", file=sys.stderr)
        return 1

    print(f"  flight time            {m.flight_time_s * 1000:6.0f} ms")
    print(f"  jump height (flight)   {m.height_flight_time_cm:6.1f} cm")
    print(f"  jump height (impulse)  {m.height_impulse_cm:6.1f} cm")
    print(f"  method agreement       {m.height_agreement_cm:6.1f} cm")
    if m.asymmetry_pct is not None:
        heavier = "left" if m.asymmetry_pct >= 0 else "right"
        print(f"  L/R asymmetry          {m.asymmetry_pct:+6.1f} %  ({heavier} carries more)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
