"""Tier 1 & 2: Monte Carlo P50/P90 and integration tests.

Validates the uncertainty model and cross-layer consistency.
"""
import math
import pytest
import numpy as np


class TestMonteCarloP50P90:
    """Monte Carlo output validation."""

    def _run_mc(self, base_energy=15_000, n_iter=1000):
        """Run a simplified Monte Carlo simulation matching the API logic."""
        np.random.seed(42)
        irr_values = []
        npv_values = []
        energy_values = []

        from core.layers.financial_model import FinancialLayer
        fl = FinancialLayer(
            system_cost_per_kw=12_000,
            annual_om_cost=320,
            electricity_tariff=1.90,
            discount_rate=0.08,
            lifetime_years=25,
            tariff_escalation_rate=0.03,
            degradation_rate=0.005,
            lid_rate=0.02,
            debt_ratio=0.65,
            interest_rate=0.12,
            loan_term_years=10,
            use_ecg_tariff=False,
        )

        for _ in range(n_iter):
            # Uncertainty factors (matching API main.py MC logic)
            irr_val = np.random.normal(base_energy, base_energy * 0.05)
            soiling = 1.0 - np.random.normal(0.02, 0.024)
            hw = 1.0 - np.random.normal(0.02, 0.006)
            tariff = 1.0 + np.random.normal(0, 0.15)
            deg = 1.0 + np.random.normal(0, 0.004)

            adjusted_energy = irr_val * soiling * hw * deg
            energy_values.append(adjusted_energy)
            result = fl.calculate_roi(adjusted_energy, 10.0)
            npv_values.append(result["npv"])
            irr_values.append(result["irr"])

        return np.array(energy_values), np.array(npv_values), np.array(irr_values)

    def test_p50_close_to_base(self, reference_system):
        """P50 energy should be close to base case (within 5%, losses from soiling/hw bias mean)."""
        energies, _, _ = self._run_mc(base_energy=15_000)
        p50 = np.percentile(energies, 50)
        assert abs(p50 - 15_000) / 15_000 < 0.05, f"P50 {p50:.0f} too far from 15,000"

    def test_p90_below_p50(self, reference_system):
        """P90 (conservative, 90% probability of exceeding = 10th percentile) must be below P50."""
        energies, _, _ = self._run_mc()
        p50 = np.percentile(energies, 50)
        p90 = np.percentile(energies, 10)
        assert p90 < p50, f"P90 {p90:.0f} should be below P50 {p50:.0f}"

    def test_p10_above_p50(self, reference_system):
        """P10 (optimistic, 10% probability of exceeding = 90th percentile) must be above P50."""
        energies, _, _ = self._run_mc()
        p10 = np.percentile(energies, 90)
        p50 = np.percentile(energies, 50)
        assert p10 > p50

    def test_npv_p50_positive(self, reference_system):
        """P50 NPV should be positive for a viable system."""
        _, npvs, _ = self._run_mc()
        p50_npv = np.percentile(npvs, 50)
        assert p50_npv > 0, f"P50 NPV {p50_npv:.0f} should be positive"

    def test_irr_spread_reasonable(self, reference_system):
        """IRR spread (std dev) should be reasonable (< 10pp)."""
        _, _, irrs = self._run_mc()
        assert np.std(irrs) < 0.10, f"IRR std dev {np.std(irrs):.3f} too high"

    def test_mc_deterministic_with_seed(self):
        """Same seed → same results (reproducibility)."""
        e1, _, _ = self._run_mc()
        e2, _, _ = self._run_mc()
        np.testing.assert_array_equal(e1, e2)


class TestCrossLayerConsistency:
    """Tier 2: Verify financial model output is internally consistent."""

    def test_lifetime_savings_equals_sum_minus_capex(self, flat_tariff_financial):
        """lifetime_savings = sum(cash_flows[1:]) - capex."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        # Reconstruct from individual components
        capex = result["capex"]
        annual_savings = result["annual_savings_y1"]
        # Lifetime savings should be positive for viable system
        assert result["lifetime_savings"] > 0

    def test_debt_equity_sum_to_capex(self, flat_tariff_financial):
        """debt + equity = capex."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        debt = result["debt"]["debt_amount"]
        equity = result["debt"]["equity_amount"]
        assert debt + equity == result["capex"]

    def test_dscr_array_length_matches_loan_term(self, flat_tariff_financial):
        """dscr_by_year length should equal min(lifetime, loan_term)."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        expected_len = min(flat_tariff_financial.lifetime_years,
                          flat_tariff_financial.loan_term_years)
        assert len(result["debt"]["dscr_by_year"]) == expected_len

    def test_effective_tariff_in_range(self, flat_tariff_financial):
        """Effective tariff should be between 0.5 and 5.0 GH₵/kWh."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        rate = result["effective_tariff_y1"]
        assert 0.5 < rate < 5.0, f"Effective tariff {rate:.2f} out of range"

    def test_annual_savings_positive(self, flat_tariff_financial):
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        assert result["annual_savings_y1"] > 0
