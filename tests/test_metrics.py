"""Validate the jump metrics on a synthetic jump with a known height.

Real recordings have no ground-truth height, so the algorithms are pinned here
against a physically-constructed squat jump: quiet stance, a constant-force
propulsion phase sized to a known takeoff velocity, then the exact airborne time
that velocity implies. Both independent methods must recover the height it was
built to have.
"""

import numpy as np
import pytest

from forceplate.metrics import (
    G,
    JumpMetrics,
    analyse,
    bilateral_asymmetry,
    height_from_flight_time,
)
from forceplate.parse import Recording

FS = 1000.0
BODYWEIGHT = 30000.0  # ADC counts at quiet stance
UNLOADED = 4000.0     # ADC counts airborne (clearly below the 0.2*BW floor)


def synthetic_jump(height_m: float, n_platforms: int = 2) -> Recording:
    """Build a squat jump (no countermovement) with a known height.

    Propulsion is a constant force giving acceleration ``a`` for the time needed
    to reach takeoff velocity ``v = sqrt(2·g·h)``; the airborne gap is the flight
    time ``t = sqrt(8h/g)`` that same height implies. So both methods should read
    back ``height_m``.
    """
    v_takeoff = np.sqrt(2 * G * height_m)
    accel = 10.0  # m/s^2, arbitrary constant propulsion
    t_push = v_takeoff / accel
    t_flight = np.sqrt(8 * height_m / G)

    # accel = g·(F − BW)/(BW − U)  ->  F for the target acceleration
    push_force = BODYWEIGHT + accel / G * (BODYWEIGHT - UNLOADED)

    quiet = np.full(500, BODYWEIGHT)
    push = np.full(int(round(t_push * FS)), push_force)
    flight = np.full(int(round(t_flight * FS)), UNLOADED)
    landing = np.full(300, BODYWEIGHT * 2.0)  # heavy impact, then settle
    settle = np.full(500, BODYWEIGHT)
    total = np.concatenate([quiet, push, flight, landing, settle])

    # split across platforms (evenly, so asymmetry is ~0)
    per = np.vstack([total / n_platforms] * n_platforms)
    return Recording(sampling_rate_hz=FS, platform_adc=per)


class TestHeightRecovery:
    @pytest.mark.parametrize("height_cm", [10, 20, 35, 50])
    def test_both_methods_recover_a_known_height(self, height_cm):
        m = analyse(synthetic_jump(height_cm / 100))

        # rounding of the sample counts limits precision; 1 cm is comfortable
        assert m.height_flight_time_cm == pytest.approx(height_cm, abs=1.0)
        assert m.height_impulse_cm == pytest.approx(height_cm, abs=1.0)

    def test_the_two_methods_agree(self):
        # The whole validation strategy: independent methods converging.
        m = analyse(synthetic_jump(0.30))
        assert m.height_agreement_cm < 1.0


class TestFlightTime:
    def test_projectile_formula(self):
        # 0.4 s airborne -> g·0.16/8 = 0.196 m
        assert height_from_flight_time(0.4) == pytest.approx(19.6, abs=0.1)


class TestBilateralAsymmetry:
    def test_even_split_is_symmetric(self):
        m = analyse(synthetic_jump(0.25, n_platforms=2))
        assert m.asymmetry_pct == pytest.approx(0.0, abs=0.5)

    def test_uneven_split_is_measured(self):
        # 60/40 load split -> +20% asymmetry
        p1 = np.full(1000, 0.6 * BODYWEIGHT)
        p2 = np.full(1000, 0.4 * BODYWEIGHT)
        rec = Recording(sampling_rate_hz=FS, platform_adc=np.vstack([p1, p2]))
        assert bilateral_asymmetry(rec.platform_adc, FS) == pytest.approx(20.0, abs=0.5)

    def test_single_platform_has_no_asymmetry(self):
        one = np.full((1, 1000), BODYWEIGHT)
        assert bilateral_asymmetry(one, FS) is None


class TestRejectsNonJumps:
    def test_flat_signal_is_not_a_jump(self):
        flat = np.full((2, 3000), BODYWEIGHT / 2)
        with pytest.raises(ValueError, match="airborne"):
            analyse(Recording(sampling_rate_hz=FS, platform_adc=flat))

    def test_result_type(self):
        assert isinstance(analyse(synthetic_jump(0.2)), JumpMetrics)
