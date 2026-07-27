"""Shared fixtures for UniSolar backend tests."""
import pytest
import math


# ─── Hand-calculated reference values ──────────────────────────────
# System: 10 kWp, Accra (lat 5.6, lon -0.19), tilt 10°, azimuth 180°
# Module: 420W (Impo=10.8A, Vmpo=38.9V), Inverter: Generic 98%
# ECG residential tariff, 25-year lifetime
REFERENCE = {
    "capacity_kw": 10.0,
    "lat": 5.6,
    "lon": -0.19,
    "tilt_deg": 10,
    "azimuth": 180,
    "annual_energy_kwh": 15_000,  # ~1500 kWh/kWp for Ghana (conservative)
    "system_cost_per_kw": 12_000,  # GH₵ 12,000/kWp (Ghana market)
    "capex": 120_000,  # 10 * 12,000
    "annual_om_cost_per_kw": 320,
    "discount_rate": 0.08,
    "lifetime_years": 25,
    "degradation_rate": 0.005,
    "lid_rate": 0.02,
    "tariff_escalation_rate": 0.03,
    "debt_ratio": 0.65,
    "interest_rate": 0.12,
    "loan_term_years": 10,
}


@pytest.fixture
def reference_system():
    """Returns the reference system parameters dict."""
    return REFERENCE.copy()


@pytest.fixture
def flat_tariff_financial():
    """FinancialLayer with flat tariff (no ECG) for deterministic hand-checks."""
    from core.layers.financial_model import FinancialLayer
    return FinancialLayer(
        system_cost_per_kw=REFERENCE["system_cost_per_kw"],
        annual_om_cost=REFERENCE["annual_om_cost_per_kw"],
        electricity_tariff=1.90,
        discount_rate=REFERENCE["discount_rate"],
        lifetime_years=REFERENCE["lifetime_years"],
        tariff_escalation_rate=REFERENCE["tariff_escalation_rate"],
        degradation_rate=REFERENCE["degradation_rate"],
        lid_rate=REFERENCE["lid_rate"],
        debt_ratio=REFERENCE["debt_ratio"],
        interest_rate=REFERENCE["interest_rate"],
        loan_term_years=REFERENCE["loan_term_years"],
        use_ecg_tariff=False,
    )
