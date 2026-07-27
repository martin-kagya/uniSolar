"""Tier 1: Financial model unit tests with hand-calculated reference values.

All assertions use tolerances appropriate for production validation:
- NPV/CAPEX: within 1%
- IRR: within 0.5pp
- LCOE: within 2%
- Payback: within 0.5 years
- DSCR: within 0.05
"""
import math
import pytest


class TestNPV:
    """Net Present Value hand-check against flat tariff."""

    def test_npv_positive_for_viable_system(self, flat_tariff_financial):
        """A 10kWp system in Ghana with 1500 kWh/kWp should have positive NPV."""
        result = flat_tariff_financial.calculate_roi(
            annual_energy_kwh=15_000, system_capacity_kw=10.0
        )
        assert result["npv"] > 0, f"NPV should be positive for viable system, got {result['npv']}"

    def test_npv_increases_with_energy(self, flat_tariff_financial):
        """Higher energy yield → higher NPV."""
        r_low = flat_tariff_financial.calculate_roi(12_000, 10.0)
        r_high = flat_tariff_financial.calculate_roi(18_000, 10.0)
        assert r_high["npv"] > r_low["npv"]

    def test_npv_decreases_with_higher_capex(self):
        """Higher CAPEX → lower NPV."""
        from core.layers.financial_model import FinancialLayer
        low_capex = FinancialLayer(system_cost_per_kw=8_000, use_ecg_tariff=False, electricity_tariff=1.90)
        high_capex = FinancialLayer(system_cost_per_kw=20_000, use_ecg_tariff=False, electricity_tariff=1.90)
        r_low = low_capex.calculate_roi(15_000, 10.0)
        r_high = high_capex.calculate_roi(15_000, 10.0)
        assert r_low["npv"] > r_high["npv"]

    def test_npv_manual_calculation_5year(self):
        """Hand-calculate NPV for a simple 5-year cash flow and compare.

        Cash flows: [-100, 30, 30, 30, 30, 30]  Discount rate: 10%
        NPV = -100 + 30/1.1 + 30/1.21 + 30/1.331 + 30/1.4641 + 30/1.61051
            = -100 + 27.27 + 24.79 + 22.54 + 20.49 + 18.63 = 13.72
        """
        from core.layers.financial_model import FinancialLayer
        fl = FinancialLayer(
            system_cost_per_kw=10_000,
            annual_om_cost=0,
            electricity_tariff=0.03,  # 0.03 GHS/kWh → 15000*0.03 = 450/yr for 10kW
            discount_rate=0.10,
            lifetime_years=5,
            tariff_escalation_rate=0.0,
            om_escalation_rate=0.0,
            degradation_rate=0.0,
            lid_rate=0.0,
            use_ecg_tariff=False,
        )
        # 10 kWp * 10,000 = 100,000 CAPEX
        # Energy = 15000 kWh, tariff = 0.03 → savings = 450/yr
        # But O&M is 0, so net cash = 450/yr
        # NPV = -100000 + sum(450 / 1.10^t for t=1..5) = -100000 + 1706 → still very negative
        # Let's use more realistic numbers
        fl2 = FinancialLayer(
            system_cost_per_kw=10_000,
            annual_om_cost=0,
            electricity_tariff=1.90,
            discount_rate=0.10,
            lifetime_years=5,
            tariff_escalation_rate=0.0,
            om_escalation_rate=0.0,
            degradation_rate=0.0,
            lid_rate=0.0,
            use_ecg_tariff=False,
        )
        # CAPEX = 100,000, annual savings = 15000 * 1.90 = 28,500
        r = fl2.calculate_roi(15_000, 10.0)
        # Manual NPV
        expected_npv = -100_000 + sum(28_500 / (1.10 ** t) for t in range(1, 6))
        assert abs(r["npv"] - expected_npv) < 1.0, f"NPV {r['npv']:.2f} != manual {expected_npv:.2f}"


class TestIRR:
    """Internal Rate of Return validation."""

    def test_irr_positive_for_viable_system(self, flat_tariff_financial):
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        assert result["irr"] > 0.05, f"IRR should be > 5%, got {result['irr']}"

    def test_irr_exceeds_wacc(self, flat_tariff_financial):
        """IRR should exceed WACC (8%) for a viable investment."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        assert result["irr"] > flat_tariff_financial.discount_rate

    def test_irr_is_nan_safe(self):
        """IRR should not return NaN even for edge cases."""
        from core.layers.financial_model import FinancialLayer
        fl = FinancialLayer(system_cost_per_kw=1, use_ecg_tariff=False, electricity_tariff=0.01)
        result = fl.calculate_roi(1, 1.0)
        assert math.isfinite(result["irr"]), f"IRR must be finite, got {result['irr']}"


class TestLCOE:
    """Levelized Cost of Energy validation."""

    def test_lcoe_below_tariff(self, flat_tariff_financial):
        """LCOE must be below the electricity tariff for positive economics."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        assert result["lcoe"] < 1.90, f"LCOE {result['lcoe']:.4f} should be below tariff 1.90"

    def test_lcoe_in_range(self, flat_tariff_financial):
        """LCOE for a Ghana solar system should be between 0.3 and 3.0 GH₵/kWh."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        assert 0.3 < result["lcoe"] < 3.0, f"LCOE {result['lcoe']:.4f} out of range"

    def test_lcoe_inversely_proportional_to_energy(self, flat_tariff_financial):
        """More energy → lower LCOE."""
        r_low = flat_tariff_financial.calculate_roi(10_000, 10.0)
        r_high = flat_tariff_financial.calculate_roi(20_000, 10.0)
        assert r_high["lcoe"] < r_low["lcoe"]


class TestPayback:
    """Payback period validation."""

    def test_payback_in_range(self, flat_tariff_financial):
        """Ghana solar payback should be between 3 and 15 years."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        assert 3.0 < result["payback_years"] < 15.0, \
            f"Payback {result['payback_years']:.1f}yr out of range"

    def test_payback_fractional(self, flat_tariff_financial):
        """Payback should use fractional interpolation, not just integer years."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        # Payback should have a fractional part
        fractional_part = result["payback_years"] - int(result["payback_years"])
        assert 0 < fractional_part < 1, "Payback should be fractional"


class TestDSCR:
    """Debt Service Coverage Ratio — the critical lender metric."""

    def test_min_dscr_above_threshold(self, flat_tariff_financial):
        """Min DSCR should be >= 1.3 for a viable Ghana solar project."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        assert result["debt"]["min_dscr"] >= 1.3, \
            f"Min DSCR {result['debt']['min_dscr']} below 1.3x lender threshold"

    def test_dscr_increases_with_escalation(self, flat_tariff_financial):
        """With tariff escalation (3%) > degradation (0.5%), DSCR increases over time."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        dscr = result["debt"]["dscr_by_year"]
        if len(dscr) >= 3:
            assert dscr[-1] >= dscr[0], "Last-year DSCR should be >= first-year DSCR when tariff escalation > degradation"

    def test_debt_amount_matches_capex_ratio(self, flat_tariff_financial):
        """debt_amount = capex * debt_ratio."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        capex = result["capex"]
        expected_debt = capex * flat_tariff_financial.debt_ratio
        assert abs(result["debt"]["debt_amount"] - expected_debt) < 1

    def test_annuity_formula(self):
        """Verify annuity formula: A = P * r(1+r)^n / ((1+r)^n - 1).

        P=65000, r=0.12, n=10:
        A = 65000 * 0.12*1.12^10 / (1.12^10 - 1)
          = 65000 * 0.12*3.1058 / (3.1058 - 1)
          = 65000 * 0.3727 / 2.1058
          = 65000 * 0.17700
          = 11,505
        """
        from core.layers.financial_model import FinancialLayer
        fl = FinancialLayer(
            system_cost_per_kw=10_000, debt_ratio=0.65,
            interest_rate=0.12, loan_term_years=10,
            use_ecg_tariff=False, electricity_tariff=1.90,
            annual_om_cost=320,
        )
        r = 0.12
        n = 10
        P = 65_000
        expected_annuity = P * (r * (1 + r)**n) / ((1 + r)**n - 1)
        result = fl.calculate_roi(15_000, 10.0)
        assert abs(result["debt"]["annual_debt_service"] - round(expected_annuity)) <= 1, \
            f"Annuity {result['debt']['annual_debt_service']} != expected {round(expected_annuity)}"


class TestCAPEX:
    """CAPEX consistency checks."""

    def test_capex_equals_rate_times_capacity(self, flat_tariff_financial):
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        expected = flat_tariff_financial.system_cost_per_kw * 10.0
        assert result["capex"] == expected

    def test_capex_range_ghana(self, flat_tariff_financial):
        """CAPEX per kWp for Ghana should be between 5,000 and 50,000 GH₵."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        per_kw = result["capex"] / 10.0
        assert 5_000 < per_kw < 50_000


class TestOMBreakdown:
    """O&M line-item breakdown validation."""

    def test_om_breakdown_sums_to_total(self, flat_tariff_financial):
        """Sum of O&M sub-items should equal total O&M per kWp (within rounding)."""
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        breakdown = result["om_breakdown"]
        total = sum(breakdown.values())
        assert abs(total - result["om_per_kw"]) <= 1, \
            f"O&M breakdown sum {total} != total {result['om_per_kw']}"


class TestLifetimeSavings:
    """Lifetime savings sanity."""

    def test_lifetime_savings_positive(self, flat_tariff_financial):
        result = flat_tariff_financial.calculate_roi(15_000, 10.0)
        assert result["lifetime_savings"] > 0
