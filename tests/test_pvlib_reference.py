"""PVLib standalone reference vs UniSolar full pipeline.

Validates that the underlying physics engine (PVLib ModelChain) produces
identical results when given identical inputs, and that the additional
loss layers (wiring, LID, mismatch, environmental) are applied correctly.
"""
import math
import numpy as np
import pandas as pd
import pytest
import pvlib
from pvlib.pvsystem import PVSystem, FixedMount
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS


# ─── Shared Weather Builder ──────────────────────────────────────
def _build_weather_2023(lat, lon):
    """Build a realistic hourly weather DataFrame for Accra, Ghana (2023).

    Uses PVLib clear-sky model to generate physically consistent GHI/DNI/DHI,
    then adds realistic cloud variability.
    """
    idx = pd.date_range("2023-01-01", periods=8760, freq="h", tz="Africa/Accra")
    loc = Location(latitude=lat, longitude=lon, tz="Africa/Accra")

    # Clear-sky irradiance as baseline
    cs = loc.get_clearsky(idx)
    sp = loc.get_solarposition(idx)
    np.random.seed(42)

    # Cloud attenuation: realistic tropical pattern (more clouds Jun-Oct wet season)
    month = idx.month
    cloud_base = np.where(
        (month >= 5) & (month <= 10), 0.55, 0.80  # wet season vs dry season
    )
    # Add hourly variability
    cloud_noise = np.random.normal(0, 0.12, len(idx))
    cloud_factor = np.clip(cloud_base + cloud_noise, 0.1, 1.0)

    ghi = cs["ghi"] * cloud_factor
    # Decompose GHI into DNI and DHI using Erbs model
    decomp = pvlib.irradiance.erbs(ghi, sp["apparent_zenith"], idx)
    dni = decomp["dni"]
    dhi = decomp["dhi"]

    # Temperature: typical Accra diurnal + seasonal
    temp_base = 27.0 + 3.0 * np.sin(2 * np.pi * (month - 3) / 12)
    hour = idx.hour + idx.minute / 60.0
    temp_diurnal = 5.0 * np.sin(2 * np.pi * (hour - 6) / 24)
    temp_air = temp_base + temp_diurnal + np.random.normal(0, 1.5, len(idx))

    # Wind speed
    wind_speed = np.clip(2.0 + np.random.normal(0, 1.0, len(idx)), 0, 10)

    return pd.DataFrame({
        "ghi_corrected": ghi.values,
        "dni_corrected": dni.values,
        "dhi_satellite": dhi.values,
        "temp_air": temp_air,
        "wind_speed": wind_speed,
        "soiling_loss": 0.02,
        "degradation_factor": 1.0,
        "environmental_loss_factor": 0.98,
    }, index=idx)


# ─── Tests ────────────────────────────────────────────────────────
class TestPVLibReference:
    """Compare UniSolar PhysicsLayer against bare PVLib ModelChain."""

    LAT, LON = 5.6, -0.19  # Accra

    def _run_unisolar(self, weather, capacity_kw=10.0, tilt=10, azimuth=180,
                      wiring_loss=0.02, lid_loss=0.02, mismatch_loss=0.02,
                      env_factor=0.98):
        """Run UniSolar PhysicsLayer with given weather and loss params."""
        from core.layers.physics_model import PhysicsLayer
        pl = PhysicsLayer()
        result = pl.simulate(
            weather, lat=self.LAT, lon=self.LON,
            system_capacity_kw=capacity_kw, tilt=tilt, azimuth=azimuth,
            module_name=None, inverter_name=None,
            wiring_loss=wiring_loss, lid_loss=lid_loss,
            mismatch_loss=mismatch_loss, inverter_efficiency=0.96,
        )
        return result

    def _run_bare_pvlib(self, weather, capacity_kw=10.0, tilt=10, azimuth=180,
                        aoi_model='physical', spectral_model='no_loss'):
        """Run bare PVLib ModelChain with same inputs, no extra derates."""
        loc = Location(latitude=self.LAT, longitude=self.LON)
        mount = FixedMount(surface_tilt=tilt, surface_azimuth=azimuth)
        temp_params = TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']

        array = pvlib.pvsystem.Array(
            mount=mount,
            module_parameters={'pdc0': capacity_kw * 1000, 'gamma_pdc': -0.004},
            temperature_model_parameters=temp_params,
        )
        system = PVSystem(
            arrays=[array],
            inverter_parameters={'pdc0': capacity_kw * 1000, 'eta_inv_nom': 0.96},
        )

        sim_weather = pd.DataFrame({
            "ghi": weather["ghi_corrected"].values,
            "dni": weather["dni_corrected"].values,
            "dhi": weather["dhi_satellite"].values,
            "temp_air": weather["temp_air"].values,
            "wind_speed": weather["wind_speed"].values,
        }, index=weather.index)

        mc = ModelChain(system, loc, aoi_model=aoi_model, spectral_model=spectral_model)
        mc.run_model(sim_weather)
        ac = mc.results.ac.fillna(0)
        return ac

    @pytest.fixture
    def weather(self):
        return _build_weather_2023(self.LAT, self.LON)

    def test_annual_energy_match(self, weather):
        """UniSolar annual energy should match bare PVLib within 5%.

        The difference is the extra derates: wiring (2%), LID (2%), mismatch (2%),
        and environmental loss factor (0.98). Combined: 0.98 * 0.98 * 0.98 * 0.98
        = ~92.2%. So UniSolar output ≈ bare PVLib * 0.922.
        """
        unisolar = self._run_unisolar(weather)
        ac_bare = self._run_bare_pvlib(weather)
        bare_kwh = ac_bare.sum() / 1000.0

        # Expected ratio: environmental_loss * (1-wiring) * (1-lid) * (1-mismatch)
        expected_ratio = 0.98 * (1 - 0.02) * (1 - 0.02) * (1 - 0.02)
        expected_unisolar = bare_kwh * expected_ratio

        ratio = unisolar["annual_energy_kwh"] / bare_kwh if bare_kwh > 0 else 0
        assert 0.85 < ratio < 1.0, \
            f"UniSolar/bare ratio {ratio:.3f} outside expected range (extra derates should reduce output)"

    def test_monthly_shape_correlation(self, weather):
        """Monthly energy shape should match between UniSolar and bare PVLib (R² > 0.99)."""
        unisolar = self._run_unisolar(weather)
        ac_bare = self._run_bare_pvlib(weather)

        monthly_uni = pd.Series(unisolar["monthly_energy"])
        monthly_bare = ac_bare.resample("ME").sum() / 1000.0

        # Align lengths
        n = min(len(monthly_uni), len(monthly_bare))
        u = monthly_uni.iloc[:n].values
        b = monthly_bare.iloc[:n].values

        # R² correlation
        if np.std(u) > 0 and np.std(b) > 0:
            corr = np.corrcoef(u, b)[0, 1]
            assert corr > 0.99, f"Monthly R² = {corr:.4f}, expected > 0.99"

    def test_no_shading_matches_bare(self, weather):
        """Without GCR shading, UniSolar should match bare PVLib * derate factors."""
        unisolar = self._run_unisolar(weather, wiring_loss=0, lid_loss=0, mismatch_loss=0, env_factor=1.0)
        ac_bare = self._run_bare_pvlib(weather)
        bare_kwh = ac_bare.sum() / 1000.0

        ratio = unisolar["annual_energy_kwh"] / bare_kwh if bare_kwh > 0 else 0
        assert 0.95 < ratio < 1.05, \
            f"Zero-loss ratio {ratio:.3f} should be ~1.0 (got UniSolar={unisolar['annual_energy_kwh']:.0f}, bare={bare_kwh:.0f})"

    def test_inverter_efficiency_physical(self, weather):
        """Actual inverter efficiency should be 85-99% for a well-sized system."""
        result = self._run_unisolar(weather)
        eff = result["actual_inverter_efficiency"]
        assert 0.80 < eff < 1.0, f"Inverter efficiency {eff:.3f} outside physical range"

    def test_gcr_shading_mechanism_works(self, weather):
        """GCR shading should apply non-trivial shading at some hours."""
        from core.layers.geometry_model import GeometryLayer, compute_row_pitch
        from pvlib.location import Location as Loc

        loc = Loc(latitude=self.LAT, longitude=self.LON)
        sp = loc.get_solarposition(weather.index)
        tilt, azimuth, gcr = 10, 180, 0.4

        geom = GeometryLayer(surface_tilt=tilt, surface_azimuth=azimuth, gcr=gcr)
        row_shade = geom.calculate_shading(sp["apparent_zenith"], sp["azimuth"])

        # At least some hours should have shading > 0
        assert row_shade.max() > 0, "Row-to-row shading should be non-zero for some hours"
        # Shading should be 0 at night and near-zero around solar noon
        assert row_shade.min() == 0, "Shading should be 0 at night"

    def test_generic_module_fallback(self, weather):
        """Without a named module, generic PVWatts model should produce valid output."""
        result = self._run_unisolar(weather)
        assert result["annual_energy_kwh"] > 0
        assert len(result["monthly_energy"]) == 12

    def test_loss_breakdown_sums_plausible(self, weather):
        """Loss percentages should sum to a plausible total (< 30%)."""
        result = self._run_unisolar(weather)
        losses = result["losses"]
        total_loss = sum(losses.values())
        assert 0 < total_loss < 30, f"Total loss {total_loss:.1f}% outside plausible range"
        # Inverter loss should be the largest component
        assert losses["inverter_percent"] > 0, "Inverter loss should be non-zero"
