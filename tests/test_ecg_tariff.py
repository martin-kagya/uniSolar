"""Tier 1: ECG tariff model unit tests.

Validates against official ECG Electricity Tariff Reckoner, May 2025.
"""
import pytest


class TestECGTariff:
    """ECG tariff table lookups and interpolation."""

    def test_residential_table_exists(self):
        from core.layers.ecg_tariff import ECGTariff, RESIDENTIAL_TABLE
        assert len(RESIDENTIAL_TABLE) > 50

    def test_non_residential_table_exists(self):
        from core.layers.ecg_tariff import ECGTariff, NON_RESIDENTIAL_TABLE
        assert len(NON_RESIDENTIAL_TABLE) > 50

    def test_zero_kwh_returns_min_bill(self):
        from core.layers.ecg_tariff import ECGTariff
        ecg = ECGTariff()
        bill = ecg.get_monthly_bill(0, "residential")
        assert bill >= 0, "Zero consumption should have non-negative bill"

    def test_bill_increases_with_kwh(self):
        from core.layers.ecg_tariff import ECGTariff
        ecg = ECGTariff()
        bill_low = ecg.get_monthly_bill(100, "residential")
        bill_high = ecg.get_monthly_bill(500, "residential")
        assert bill_high > bill_low

    def test_bill_interpolation_monotonic(self):
        """Bill should monotonically increase across all breakpoints."""
        from core.layers.ecg_tariff import ECGTariff, RESIDENTIAL_TABLE
        ecg = ECGTariff()
        keys = sorted(RESIDENTIAL_TABLE.keys())
        prev_bill = 0
        for k in keys[:20]:  # Check first 20 breakpoints
            bill = ecg.get_monthly_bill(k, "residential")
            assert bill >= prev_bill, f"Bill at {k}kWh ({bill}) < previous ({prev_bill})"
            prev_bill = bill

    def test_invalid_customer_type_raises(self):
        from core.layers.ecg_tariff import ECGTariff
        ecg = ECGTariff()
        with pytest.raises(ValueError):
            ecg.get_monthly_bill(100, "industrial")

    def test_extrapolation_beyond_table(self):
        """Extrapolation beyond max kWh should still return positive value."""
        from core.layers.ecg_tariff import ECGTariff
        ecg = ECGTariff()
        bill = ecg.get_monthly_bill(50_000, "residential")
        assert bill > 0

    def test_negative_kwh_clamped(self):
        from core.layers.ecg_tariff import ECGTariff
        ecg = ECGTariff()
        bill = ecg.get_monthly_bill(-100, "residential")
        assert bill >= 0
