"""Read OpenSignals force-plate recordings.

The rig is two custom force platforms, four load cells each, logged by a
biosignalsplux DAQ in OpenSignals text format: a couple of ``#`` header lines
(the second is a JSON blob of device metadata), an ``# EndOfHeader`` marker, then
tab-separated integer samples. Each device contributes six columns —
``nSeq, DI, CH1, CH2, CH3, CH4`` — so a two-platform recording is twelve columns
wide, and one platform's vertical force is the sum of its four load-cell channels.

Values are raw 16-bit ADC counts, not newtons. That is deliberate and fine: the
jump metrics that matter here are ratiometric (see :mod:`forceplate.metrics`), so
they never need the load-cell calibration constant — only the sampling rate,
which the header provides.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HEADER_MARKER = "# EndOfHeader"
CHANNELS_PER_PLATFORM = 4


@dataclass
class Recording:
    """One force-plate recording."""

    sampling_rate_hz: float
    platform_adc: np.ndarray  # shape (n_platforms, n_samples), summed load cells
    date: str | None = None

    @property
    def n_samples(self) -> int:
        return self.platform_adc.shape[1]

    @property
    def n_platforms(self) -> int:
        return self.platform_adc.shape[0]

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.sampling_rate_hz

    @property
    def total_adc(self) -> np.ndarray:
        """Combined force across all platforms (bodyweight signal), in ADC counts."""
        return self.platform_adc.sum(axis=0)


def _parse_header(lines: list[str]) -> dict:
    """Pull the sampling rate and date out of the JSON header line.

    The header describes one metadata object per device; every device on this
    rig logs at the same rate, so the first is representative.
    """
    for line in lines:
        stripped = line.lstrip("#").strip()
        if stripped.startswith("{"):
            blob = json.loads(stripped)
            first = next(iter(blob.values()))
            return {
                "sampling_rate_hz": float(first.get("sampling rate", 1000)),
                "date": first.get("date"),
            }
    return {"sampling_rate_hz": 1000.0, "date": None}


def parse_opensignals(path: str | Path) -> Recording:
    """Read an OpenSignals ``.txt`` recording into a :class:`Recording`.

    Each device's four load-cell channels (``CH1..CH4``) are summed into one
    per-platform force signal. The number of platforms is inferred from the data
    width, so this handles the one- and two-platform recordings the rig produced.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    header_lines = [ln for ln in lines if ln.startswith("#")]
    meta = _parse_header(header_lines)

    body = []
    in_data = False
    for line in lines:
        if line.startswith(HEADER_MARKER):
            in_data = True
            continue
        if not in_data or not line.strip():
            continue
        body.append([int(x) for x in line.split()])

    if not body:
        raise ValueError(f"{path} has no data rows after the header")

    data = np.asarray(body, dtype=float)
    cols_per_device = 2 + CHANNELS_PER_PLATFORM  # nSeq, DI, CH1..CH4
    n_platforms, remainder = divmod(data.shape[1], cols_per_device)
    if n_platforms == 0 or remainder != 0:
        raise ValueError(
            f"{path}: {data.shape[1]} columns is not a whole number of "
            f"{cols_per_device}-column devices"
        )

    platforms = []
    for p in range(n_platforms):
        base = p * cols_per_device
        # channels are the last 4 of each device's 6 columns
        platforms.append(data[:, base + 2 : base + 6].sum(axis=1))

    return Recording(
        sampling_rate_hz=meta["sampling_rate_hz"],
        platform_adc=np.vstack(platforms),
        date=meta["date"],
    )
