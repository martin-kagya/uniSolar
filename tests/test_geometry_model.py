"""Tier 1: Geometry model unit tests.

Validates row pitch formula, shading geometry, and roof capacity calculations.
Row pitch must match frontend panelGeometry.ts rowPitch() exactly.
"""
import math
import pytest


class TestRowPitch:
    """compute_row_pitch = collector_width * cos(tilt) / gcr"""

    def test_flat_tilt_full_coverage(self):
        """At 0° tilt, projected = collector_width. Pitch = width / gcr."""
        from core.layers.geometry_model import compute_row_pitch
        pitch = compute_row_pitch(2.0, tilt_deg=0, gcr=0.5)
        assert pitch == pytest.approx(4.0, abs=0.01)

    def test_pitch_decreases_with_gcr(self):
        """Higher GCR → rows closer together → smaller pitch."""
        from core.layers.geometry_model import compute_row_pitch
        p_low = compute_row_pitch(2.0, 10, gcr=0.3)
        p_high = compute_row_pitch(2.0, 10, gcr=0.6)
        assert p_high < p_low

    def test_pitch_increases_with_tilt(self):
        """Higher tilt → shorter projected length → smaller pitch (rows closer)."""
        from core.layers.geometry_model import compute_row_pitch
        p_flat = compute_row_pitch(2.0, tilt_deg=0, gcr=0.4)
        p_tilted = compute_row_pitch(2.0, tilt_deg=30, gcr=0.4)
        assert p_tilted < p_flat

    def test_exact_match_at_10_degrees(self):
        """Specific hand-calculation: 2.1m module, 10° tilt, GCR 0.4.
        projected = 2.1 * cos(10°) = 2.1 * 0.9848 = 2.0681
        pitch = 2.0681 / 0.4 = 5.1702
        """
        from core.layers.geometry_model import compute_row_pitch
        pitch = compute_row_pitch(2.1, tilt_deg=10, gcr=0.4)
        assert pitch == pytest.approx(5.17, abs=0.01)

    def test_gcr_of_one_equals_projected_length(self):
        """GCR=1.0 means rows touch: pitch = projected length."""
        from core.layers.geometry_model import compute_row_pitch
        pitch = compute_row_pitch(2.0, tilt_deg=15, gcr=1.0)
        projected = 2.0 * math.cos(math.radians(15))
        assert pitch == pytest.approx(projected, abs=0.01)

    def test_gcr_zero_raises(self):
        from core.layers.geometry_model import compute_row_pitch
        with pytest.raises(ValueError):
            compute_row_pitch(2.0, 10, gcr=0.0)

    def test_gcr_negative_raises(self):
        from core.layers.geometry_model import compute_row_pitch
        with pytest.raises(ValueError):
            compute_row_pitch(2.0, 10, gcr=-0.5)

    def test_gcr_above_one_raises(self):
        from core.layers.geometry_model import compute_row_pitch
        with pytest.raises(ValueError):
            compute_row_pitch(2.0, 10, gcr=1.5)

    @pytest.mark.parametrize("tilt,gcr", [
        (0, 0.3), (0, 0.5), (10, 0.4), (15, 0.35),
        (30, 0.3), (45, 0.25), (60, 0.2),
    ])
    def test_parity_with_frontend(self, tilt, gcr):
        """These values MUST match frontend panelGeometry.ts rowPitch()."""
        from core.layers.geometry_model import compute_row_pitch
        collector_width = 2.1  # standard portrait module
        pitch = compute_row_pitch(collector_width, tilt, gcr)
        # Frontend: projectedLength = moduleLength * cos(tilt * PI/180)
        # rowPitch = projectedLength / gcr
        frontend_projected = collector_width * math.cos(tilt * math.pi / 180)
        frontend_pitch = frontend_projected / gcr
        assert pitch == pytest.approx(frontend_pitch, abs=1e-10)


class TestRoofCapacity:
    """Roof capacity estimation sanity checks."""

    def test_roof_fits_panels(self):
        from core.layers.geometry_model import GeometryLayer
        geom = GeometryLayer()
        result = geom.calculate_roof_capacity(length=20, width=10, margin=0.5)
        assert result["total_panels"] > 0
        assert result["capacity_kwp"] > 0

    def test_larger_roof_more_panels(self):
        from core.layers.geometry_model import GeometryLayer
        geom = GeometryLayer()
        small = geom.calculate_roof_capacity(10, 5)
        large = geom.calculate_roof_capacity(20, 10)
        assert large["total_panels"] > small["total_panels"]
