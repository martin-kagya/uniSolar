import numpy as np

class FinancialLayer:
    """
    Layer 5: Financial Modeling & ROI Analysis.
    Calculates bankability metrics: NPV, IRR, LCOE, and Payback.

    Supports two tariff modes:
    - use_ecg_tariff=True (default): Uses the official ECG May 2025 Tariff Reckoner
      (tiered tariff with all levies/taxes) — recommended for Ghana projects.
    - use_ecg_tariff=False: Uses a flat electricity_tariff (GH₵/kWh) for custom scenarios.
    """

    def __init__(self, system_cost_per_kw=20000.0, annual_om_cost=320.0,
                 electricity_tariff=1.90, discount_rate=0.08, lifetime_years=25,
                 tariff_escalation_rate=0.03, om_escalation_rate=0.02,
                 degradation_rate=0.005, lid_rate=0.02,
                 debt_ratio=0.65, interest_rate=0.12, loan_term_years=10,
                 use_ecg_tariff=True, customer_type="residential"):
        """
        :param system_cost_per_kw:     Initial CAPEX per kWp (Default: 20,000 GH₵)
        :param annual_om_cost:         Yearly OPEX per kWp (Default: 320 GH₵)
        :param electricity_tariff:     Flat tariff (GH₵/kWh) — used only when use_ecg_tariff=False
        :param discount_rate:          Weighted Average Cost of Capital (WACC)
        :param tariff_escalation_rate: Annual increase in electricity cost (fraction)
        :param om_escalation_rate:     Annual inflation in O&M costs (fraction)
        :param degradation_rate:       Annual solar panel degradation after Year 1 (fraction)
        :param lid_rate:               Year 1 Light Induced Degradation (fraction, default 2%)
        :param debt_ratio:             Fraction of CAPEX financed via debt (default 65%)
        :param interest_rate:          Annual interest rate on debt (default 12%)
        :param loan_term_years:        Debt repayment period in years (default 10)
        :param use_ecg_tariff:         If True, use ECG official tariff reckoner for savings
        :param customer_type:          'residential' or 'non_residential' (ECG tariff mode)
        """
        self.system_cost_per_kw = system_cost_per_kw
        self.annual_om_cost = annual_om_cost
        self.electricity_tariff = electricity_tariff
        self.discount_rate = discount_rate
        self.lifetime_years = lifetime_years
        self.tariff_escalation_rate = tariff_escalation_rate
        self.om_escalation_rate = om_escalation_rate
        self.degradation_rate = degradation_rate
        self.lid_rate = lid_rate
        self.debt_ratio = debt_ratio
        self.interest_rate = interest_rate
        self.loan_term_years = loan_term_years
        self.use_ecg_tariff = use_ecg_tariff
        self.customer_type = customer_type

        if self.use_ecg_tariff:
            from core.layers.ecg_tariff import ECGTariff
            self._ecg = ECGTariff()
        else:
            self._ecg = None

    def _year1_annual_savings(self, annual_energy_kwh: float) -> float:
        """Return the Year 1 annual savings in GH₵ for the given energy production."""
        if self.use_ecg_tariff and self._ecg:
            monthly_kwh = annual_energy_kwh / 12.0
            monthly_bill = self._ecg.get_monthly_bill(monthly_kwh, self.customer_type)
            return monthly_bill * 12.0
        else:
            return annual_energy_kwh * self.electricity_tariff

    def _effective_rate_y1(self, annual_energy_kwh: float) -> float:
        """Return the blended effective rate (GH₵/kWh) for Year 1."""
        if annual_energy_kwh <= 0:
            return 0.0
        return self._year1_annual_savings(annual_energy_kwh) / annual_energy_kwh

    def calculate_roi(self, annual_energy_kwh, system_capacity_kw=1.0):
        """
        Calculates financial performance metrics with dynamic escalation and degradation.
        """
        capex = self.system_cost_per_kw * system_capacity_kw

        # Base Year-1 annual savings
        base_annual_savings = self._year1_annual_savings(annual_energy_kwh)

        # Cash Flow Projection
        cash_flows = [-capex]
        total_energy_life = 0
        total_om_life = 0

        for year in range(1, self.lifetime_years + 1):
            # 1. Panel Degradation — LID in Year 1, then linear degradation
            if year == 1:
                degradation_factor = (1.0 - self.lid_rate)
            else:
                degradation_factor = (1.0 - self.lid_rate) * (1.0 - self.degradation_rate) ** (year - 1)
            year_energy = annual_energy_kwh * degradation_factor
            total_energy_life += year_energy / ((1 + self.discount_rate) ** year)

            # 2. Tariff Escalation — electricity becomes more expensive each year
            escalation_factor = (1.0 + self.tariff_escalation_rate) ** (year - 1)
            year_savings = base_annual_savings * degradation_factor * escalation_factor

            # 3. O&M Escalation (Inflation)
            year_om = (self.annual_om_cost * system_capacity_kw) * ((1.0 + self.om_escalation_rate) ** (year - 1))
            total_om_life += year_om / ((1 + self.discount_rate) ** year)

            net_cash = year_savings - year_om
            cash_flows.append(net_cash)

        # 1. NPV
        try:
            import numpy_financial as npf
            npv = npf.npv(self.discount_rate, cash_flows)
        except Exception:
            npv = sum([cf / (1 + self.discount_rate)**t for t, cf in enumerate(cash_flows)])

        # 2. IRR
        try:
            import numpy_financial as npf
            irr = npf.irr(cash_flows)
            if np.isnan(irr):
                irr = 0.0
        except Exception:
            irr = self._manual_irr(cash_flows)

        # 3. Payback Period (fractional interpolation)
        cumulative_cash = -capex
        payback = 0.0
        prev_cumulative = cumulative_cash
        for year in range(1, self.lifetime_years + 1):
            net_cash = cash_flows[year]
            prev_cumulative = cumulative_cash
            cumulative_cash += net_cash
            if cumulative_cash >= 0:
                if prev_cumulative < 0:
                    fraction = -prev_cumulative / net_cash
                    payback = (year - 1) + fraction
                else:
                    payback = float(year)
                break

        # 4. LCOE (GH₵/kWh)
        # LCOE = (Total Lifecycle Cost discounted) / (Total Lifecycle Energy discounted)
        total_discounted_cost = capex + total_om_life
        lcoe = total_discounted_cost / total_energy_life if total_energy_life > 0 else 0

        # 5. Effective tariff info
        effective_rate_y1 = self._effective_rate_y1(annual_energy_kwh)

        # 6. Debt Service & DSCR
        debt_amount = capex * self.debt_ratio
        equity_amount = capex * (1.0 - self.debt_ratio)
        
        # Constant annual debt service (annuity)
        if self.interest_rate > 0 and self.loan_term_years > 0:
            r = self.interest_rate
            n = self.loan_term_years
            annual_debt_service = debt_amount * (r * (1 + r)**n) / ((1 + r)**n - 1)
        else:
            annual_debt_service = debt_amount / max(self.loan_term_years, 1)
        
        # DSCR for each year of the loan (minimum DSCR is the critical metric)
        min_dscr = float('inf')
        dscr_by_year = []
        for year in range(1, min(self.lifetime_years, self.loan_term_years) + 1):
            net_cash = cash_flows[year]
            if annual_debt_service > 0:
                dscr = net_cash / annual_debt_service
            else:
                dscr = float('inf')
            dscr_by_year.append(round(dscr, 2))
            if dscr < min_dscr:
                min_dscr = dscr
        
        if min_dscr == float('inf'):
            min_dscr = 0.0

        # 7. O&M Line-Item Breakdown (per kWp/year, transparent assumptions)
        om_per_kw = self.annual_om_cost
        om_breakdown = {
            "cleaning": round(om_per_kw * 0.25, 0),
            "inverter_reserve": round(om_per_kw * 0.19, 0),
            "monitoring": round(om_per_kw * 0.12, 0),
            "insurance": round(om_per_kw * 0.16, 0),
            "spare_parts": round(om_per_kw * 0.28, 0),
        }

        return {
            "capex": capex,
            "annual_savings_y1": base_annual_savings,
            "effective_tariff_y1": float(effective_rate_y1),
            "npv": float(npv),
            "irr": float(irr),
            "lcoe": float(lcoe),
            "payback_years": payback,
            "lifetime_savings": sum(cash_flows[1:]) - capex,
            "tariff_mode": "ecg_official" if self.use_ecg_tariff else "flat_rate",
            "customer_type": self.customer_type if self.use_ecg_tariff else None,
            "om_breakdown": om_breakdown,
            "om_per_kw": om_per_kw,
            "debt": {
                "debt_amount": round(debt_amount),
                "equity_amount": round(equity_amount),
                "debt_ratio_pct": self.debt_ratio * 100,
                "interest_rate_pct": self.interest_rate * 100,
                "loan_term_years": self.loan_term_years,
                "annual_debt_service": round(annual_debt_service),
                "min_dscr": round(min_dscr, 2),
                "dscr_by_year": dscr_by_year,
            },
        }

    def _manual_irr(self, cash_flows, iterations=100):
        """Manual IRR calculation via Newton-Raphson with overflow protection."""
        res = 0.1
        for i in range(iterations):
            try:
                npv = sum([cf / (1 + res)**t for t, cf in enumerate(cash_flows)])
                d_npv = sum([-t * cf / (1 + res)**(t + 1) for t, cf in enumerate(cash_flows)])
                if abs(d_npv) < 1e-9:
                    break
                new_res = res - npv / d_npv
                if abs(new_res - res) < 1e-6:
                    return new_res
                res = new_res
            except OverflowError:
                return 0.0
        return res
