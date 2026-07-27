"""Tier 1: Environmental model unit tests.

Validates soiling, degradation, and rain-cleaning logic.
"""
import pytest
import pandas as pd
import numpy as np


class TestDegradationPresets:
    """Degradation presets must be within physically plausible ranges."""

    def test_all_presets_in_range(self):
        from core.layers.environmental_model import DEGRADATION_PRESETS
        for name, rate in DEGRADATION_PRESETS.items():
            assert 0.001 <= rate <= 0.01, f"{name}: {rate} out of range (0.1%-1.0%)"

    def test_premium_panels_degrade_slower(self):
        from core.layers.environmental_model import DEGRADATION_PRESETS
        premium = DEGRADATION_PRESETS["sunpower_maxeon"]
        generic = DEGRADATION_PRESETS["generic"]
        assert premium < generic


class TestSoiling:
    """Soiling model validation."""

    def test_soiling_capped_at_30pct(self):
        from core.layers.environmental_model import EnvironmentalLayer
        el = EnvironmentalLayer()
        assert el.max_soiling == 0.30

    def test_rain_cleans_panels(self):
        """Heavy rain should reduce soiling significantly."""
        from core.layers.environmental_model import EnvironmentalLayer
        el = EnvironmentalLayer()
        # Create weather with heavy rain every 6 hours
        idx = pd.date_range("2024-01-01", periods=200, freq="h")
        df = pd.DataFrame({
            "rain_mm": [5.0 if i % 6 == 0 else 0.0 for i in range(200)],
            "aod_550": 0.3,
            "pm25": 20.0,
            "pm10": 40.0,
            "relative_humidity": 60.0,
        }, index=idx)
        df["timestamp"] = df.index
        result = el.calculate_soiling_losses(df)
        # With regular heavy rain, soiling should stay low
        assert result.max() < 0.10, f"Max soiling {result.max():.3f} too high with regular rain"

    def test_no_rain_increases_soiling(self):
        """Without rain, soiling should accumulate."""
        from core.layers.environmental_model import EnvironmentalLayer
        el = EnvironmentalLayer()
        idx = pd.date_range("2024-01-01", periods=200, freq="h")
        df = pd.DataFrame({
            "rain_mm": 0.0,
            "aod_550": 0.5,
            "pm25": 50.0,
            "pm10": 100.0,
            "relative_humidity": 60.0,
        }, index=idx)
        df["timestamp"] = df.index
        result = el.calculate_soiling_losses(df)
        # Soiling should increase over time without rain
        assert result.iloc[-1] > result.iloc[10]

    def test_soiling_non_negative(self):
        from core.layers.environmental_model import EnvironmentalLayer
        el = EnvironmentalLayer()
        idx = pd.date_range("2024-01-01", periods=100, freq="h")
        df = pd.DataFrame({
            "rain_mm": 0.0, "aod_550": 0.3, "pm25": 20.0,
            "pm10": 40.0, "relative_humidity": 60.0,
        }, index=idx)
        df["timestamp"] = df.index
        result = el.calculate_soiling_losses(df)
        assert (result >= 0).all(), "Soiling should never be negative"


class TestDegradation:
    """Degradation factor validation."""

    def test_degradation_compounds(self):
        """Year 10 should have more degradation than Year 1."""
        from core.layers.environmental_model import EnvironmentalLayer
        el = EnvironmentalLayer(degradation_rate=0.005)
        ts = pd.to_datetime(["2024-01-01", "2034-01-01"])
        factor = el.calculate_degradation_factor(ts, system_start_date="2024-01-01")
        f = np.asarray(factor)
        assert f[1] < f[0]

    def test_degradation_factor_at_year_zero(self):
        """At start, degradation factor should be 1.0."""
        from core.layers.environmental_model import EnvironmentalLayer
        el = EnvironmentalLayer(degradation_rate=0.005)
        ts = pd.to_datetime(["2024-01-01"])
        factor = el.calculate_degradation_factor(ts, system_start_date="2024-01-01")
        f = np.asarray(factor)
        assert f[0] == pytest.approx(1.0, abs=0.001)

    def test_degradation_factor_at_year_25(self):
        """After 25 years with 0.5%/yr: factor = 0.995^25 ≈ 0.882."""
        from core.layers.environmental_model import EnvironmentalLayer
        el = EnvironmentalLayer(degradation_rate=0.005)
        ts = pd.to_datetime(["2024-01-01", "2049-01-01"])
        factor = el.calculate_degradation_factor(ts, system_start_date="2024-01-01")
        f = np.asarray(factor)
        expected = 0.995 ** 25
        assert f[1] == pytest.approx(expected, abs=0.01)
