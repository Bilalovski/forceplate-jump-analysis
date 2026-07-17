"""Jump metrics from a force-plate recording.

Vertical jump height is computed two physically independent ways, and them
agreeing is the correctness check — there is no external ground truth for these
recordings, so the validation is internal:

* **Flight time.** While airborne the plates read no force, so the duration of
  that gap gives height by projectile motion, ``h = g·t²/8``. Needs nothing but
  timing — no calibration, no bodyweight.
* **Impulse–momentum.** Integrate the body's acceleration from movement onset to
  takeoff to get takeoff velocity, then ``h = v²/2g``. This is the sports-science
  gold standard and it uses the whole propulsion phase, not just the airborne
  gap.

Both are **ratiometric in the raw ADC signal**: acceleration works out to
``g·(F − bodyweight)/(bodyweight − unloaded)``, in which the unknown load-cell
scale factor cancels. So height comes straight from ADC counts, and only the
unloaded (zero-force) offset is needed — which the airborne samples hand us.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

G = 9.81

#: A platform is "airborne" (unloaded) below this fraction of bodyweight.
AIRBORNE_FRACTION = 0.2

#: Movement onset: the force first leaving the quiet-stance band, in units of the
#: quiet-stance standard deviation. 5σ is the common threshold in the literature.
ONSET_SIGMA = 5.0

#: Quiet stance is assumed to occupy at least this long at the start of a trial.
QUIET_WINDOW_S = 0.5

#: A real vertical jump is airborne at least this long (~9 cm). Shorter "flights"
#: are noise dips or a mis-detected baseline, not a jump.
MIN_FLIGHT_S = 0.15


@dataclass
class JumpMetrics:
    """Everything computed from one jump trial."""

    bodyweight_adc: float
    unloaded_adc: float
    flight_time_s: float
    height_flight_time_cm: float
    height_impulse_cm: float
    asymmetry_pct: float | None

    @property
    def height_agreement_cm(self) -> float:
        """Absolute gap between the two independent height estimates."""
        return abs(self.height_flight_time_cm - self.height_impulse_cm)


def quiet_stance(total_adc: np.ndarray, fs: float) -> tuple[float, float]:
    """Bodyweight (median) and noise (std) over the opening quiet-stance window."""
    window = total_adc[: int(QUIET_WINDOW_S * fs)]
    return float(np.median(window)), float(np.std(window))


def find_flight(total_adc: np.ndarray, bodyweight: float, fs: float) -> tuple[int, int]:
    """Return (start, end) sample indices of the airborne phase.

    The airborne phase is the longest run of samples below a small fraction of
    bodyweight — robust to the countermovement dip, which never reaches that
    floor — and it must last at least :data:`MIN_FLIGHT_S` to count as a jump.
    """
    airborne = total_adc < AIRBORNE_FRACTION * bodyweight
    if not airborne.any():
        raise ValueError("no airborne phase found — is this a jump trial?")

    idx = np.flatnonzero(airborne)
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    flight = max(runs, key=len)
    if len(flight) < MIN_FLIGHT_S * fs:
        raise ValueError(
            "airborne phase too short to be a jump — noise dip or bad baseline"
        )
    return int(flight[0]), int(flight[-1])


def height_from_flight_time(flight_time_s: float) -> float:
    """Jump height in cm from airborne time: h = g·t²/8. Calibration-free."""
    return G * flight_time_s**2 / 8 * 100


def height_from_impulse(
    total_adc: np.ndarray,
    fs: float,
    bodyweight: float,
    bodyweight_sd: float,
    unloaded: float,
    takeoff_idx: int,
) -> float:
    """Jump height in cm by the impulse–momentum method.

    Integrates ``a = g·(F − bodyweight)/(bodyweight − unloaded)`` from movement
    onset to takeoff to get takeoff velocity, then ``h = v²/2g``. The load-cell
    scale cancels in that ratio; only the unloaded offset is needed.
    """
    span = bodyweight - unloaded
    if span <= 0:
        raise ValueError("bodyweight not above the unloaded level — check the signal")

    # Movement onset: the FIRST departure from the quiet-stance band. Integration
    # must start from an instant of known zero velocity (quiet standing) and run
    # through the whole countermovement and propulsion — the net impulse over that
    # window is takeoff momentum. Starting at the last in-band sample instead
    # lands mid-jump (the force curve re-crosses bodyweight between the dip and the
    # push) and throws the velocity away.
    band = ONSET_SIGMA * bodyweight_sd
    moved = np.abs(total_adc[:takeoff_idx] - bodyweight) > band
    onset = int(np.flatnonzero(moved)[0]) if moved.any() else 0

    accel = G * (total_adc[onset:takeoff_idx] - bodyweight) / span
    takeoff_velocity = np.sum(accel) / fs  # ∫a dt, uniform sampling
    return takeoff_velocity**2 / (2 * G) * 100


def bilateral_asymmetry(platform_adc: np.ndarray, fs: float) -> float | None:
    """Left/right load imbalance at quiet stance, as a signed percentage.

    Only defined for a two-platform recording; ``None`` otherwise. Positive means
    the first platform carries more. This is the metric single-plate rigs can't
    produce — it's the injury-screening number in ACL rehab.
    """
    if platform_adc.shape[0] != 2:
        return None
    window = slice(0, int(QUIET_WINDOW_S * fs))
    p1 = float(np.median(platform_adc[0, window]))
    p2 = float(np.median(platform_adc[1, window]))
    return 100.0 * (p1 - p2) / (p1 + p2)


def analyse(recording) -> JumpMetrics:
    """Compute all jump metrics from a :class:`~forceplate.parse.Recording`."""
    total = recording.total_adc
    fs = recording.sampling_rate_hz

    bodyweight, bodyweight_sd = quiet_stance(total, fs)
    start, end = find_flight(total, bodyweight, fs)
    flight_time = (end - start + 1) / fs

    # Unloaded ADC = force reading while airborne (the load cells' zero).
    unloaded = float(np.median(total[start : end + 1]))

    return JumpMetrics(
        bodyweight_adc=bodyweight,
        unloaded_adc=unloaded,
        flight_time_s=flight_time,
        height_flight_time_cm=height_from_flight_time(flight_time),
        height_impulse_cm=height_from_impulse(
            total, fs, bodyweight, bodyweight_sd, unloaded, takeoff_idx=start
        ),
        asymmetry_pct=bilateral_asymmetry(recording.platform_adc, fs),
    )
