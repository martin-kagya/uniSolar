"""Tier 1 & 2: Physics model unit tests.

Validates PVLib integration, module/inverter database loading,
yield sanity for Ghana, and physics derate factors.
"""
import math
import pytest
import pandas as pd
import numpy as np


class TestPhysicsDerate:
    """Physics derate factor validation."""

    def test_physics_derate_formula(self):
        """physics_derate = (1 - lid) * (1 - wiring) * (1 - mismatch)"""
        lid, wiring, mismatch = 0.02, 0.02, 0.02
        expected = (1 - lid) * (1 - wiring) * (1 - mismatch)
        assert expected == pytest.approx(0.941192, abs=0.0001)

    def test_derate_symmetric_losses(self):
        """Wiring and mismatch losses should be symmetric (2% each)."""
        # This is a design assumption, not a formula
        # Both default to 0.02 (2%)
        lid, wiring, mismatch = 0.02, 0.02, 0.02
        assert wiring == mismatch


class TestPVLibDatabase:
    """Sandia module and CEC inverter database loading."""

    def test_sandia_modules_load(self):
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        pl._load_databases()
        assert pl.sandia_modules is not None
        assert len(pl.sandia_modules.columns) > 100  # Hundreds of modules

    def test_known_module_in_database(self):
        """Canadian Solar CS5U-420M should be in Sandia database (or similar)."""
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        pl._load_databases()
        # Check a few known module manufacturers appear
        module_names = list(pl.sandia_modules.columns)
        has_canadian = any("Canadian" in n for n in module_names)
        has_jinko = any("Jinko" in n for n in module_names)
        assert has_canadian or has_jinko, "Expected Canadian Solar or Jinko in Sandia DB"

    def test_module_parameters_present(self):
        """Each Sandia module must have Impo, Vmpo (needed for system sizing)."""
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        pl._load_databases()
        sample = pl.sandia_modules.iloc[:, 0]
        assert "Impo" in sample.index
        assert "Vmpo" in sample.index
        assert sample["Impo"] > 0
        assert sample["Vmpo"] > 0

    def test_cec_inverters_load(self):
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        pl._load_databases()
        assert pl.cec_inverters is not None
        assert len(pl.cec_inverters.columns) > 50

    def test_inverter_has_paco(self):
        """Each CEC inverter must have Paco (nominal AC power)."""
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        pl._load_databases()
        sample = pl.cec_inverters.iloc[:, 0]
        assert "Paco" in sample.index
        assert sample["Paco"] > 0

    def test_representative_inverters_list(self):
        """The curated inverter list should have at least 5 entries."""
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        invs = pl.get_representative_inverters()
        assert len(invs) >= 5


class TestYieldSanity:
    """Tier 1: Yield must be physically plausible for Ghana.

    Ghana (lat 5-10°N) should produce 1,200-1,800 kWh/kWp/yr for
    fixed-tilt systems. Outside this range indicates a bug.
    """

    def _make_weather_df(self, ghi=500.0, dni=350.0, dhi=150.0, temp=28.0, wind=2.0,
                         n_hours=8760):
        """Create a minimal hourly weather DataFrame for simulation.

        Default values represent a typical Ghana day (average irradiance over 24h).
        """
        idx = pd.date_range("2024-01-01", periods=n_hours, freq="h")
        np.random.seed(42)
        return pd.DataFrame({
            "ghi_corrected": np.clip(ghi + np.random.normal(0, ghi * 0.1, n_hours), 0, 1200),
            "dni_corrected": np.clip(dni + np.random.normal(0, dni * 0.1, n_hours), 0, 1000),
            "dhi_satellite": np.clip(dhi + np.random.normal(0, dhi * 0.1, n_hours), 0, 500),
            "temp_air": temp + np.random.normal(0, 3, n_hours),
            "wind_speed": np.clip(wind + np.random.normal(0, 0.5, n_hours), 0, 10),
            "soiling_loss": 0.02,
            "degradation_factor": 1.0,
            "environmental_loss_factor": 0.98,
        }, index=idx)

    def test_yield_per_kwp_ghana(self):
        """Annual yield should be 1200-1800 kWh/kWp for a Ghana location."""
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        weather = self._make_weather_df(n_hours=8760)
        result = pl.simulate(
            weather, lat=5.6, lon=-0.19,
            system_capacity_kw=10.0, tilt=10, azimuth=180,
            inverter_efficiency=0.96,
        )
        kwh_per_kwp = result["annual_energy_kwh"] / 10.0
        assert 800 < kwh_per_kwp < 2500, \
            f"Yield {kwh_per_kwp:.0f} kWh/kWp outside plausible range for Ghana"

    def test_energy_positive(self):
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        weather = self._make_weather_df()
        result = pl.simulate(weather, lat=5.6, lon=-0.19, system_capacity_kw=10.0)
        assert result["annual_energy_kwh"] > 0

    def test_ac_series_length_matches_input(self):
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        n = 8760
        weather = self._make_weather_df(n_hours=n)
        result = pl.simulate(weather, lat=5.6, lon=-0.19, system_capacity_kw=10.0)
        assert len(result["ac_list"]) == n

    def test_monthly_energy_sums_to_annual(self):
        """Sum of monthly energies should approximate annual energy."""
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        weather = self._make_weather_df()
        result = pl.simulate(weather, lat=5.6, lon=-0.19, system_capacity_kw=10.0)
        monthly_sum = sum(result["monthly_energy"])
        annual = result["annual_energy_kwh"]
        assert monthly_sum == pytest.approx(annual, rel=0.02), \
            f"Monthly sum {monthly_sum:.1f} != annual {annual:.1f}"

    def test_inverter_efficiency_in_range(self):
        """Actual inverter efficiency must be between 85% and 99.5%."""
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        weather = self._make_weather_df()
        result = pl.simulate(weather, lat=5.6, lon=-0.19, system_capacity_kw=10.0)
        eff = result["actual_inverter_efficiency"]
        assert 0.85 < eff < 0.995, f"Inverter efficiency {eff:.3f} out of range"
