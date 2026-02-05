import numpy as np

class FinancialLayer:
    """
    Layer 5: Financial Modeling & ROI Analysis.
    Calculates bankability metrics: NPV, IRR, LCOE, and Payback.
    """
    
    def __init__(self, system_cost_per_kw=20000.0, annual_om_cost=320.0, 
                 electricity_tariff=1.90, discount_rate=0.08, lifetime_years=25):
        """
        :param system_cost_per_kw: Initial CAPEX per kWp (Default: 20,000 GH₵)
        :param annual_om_cost: Yearly OPEX per kWp (Default: 320 GH₵)
        :param electricity_tariff: Cost of grid electricity (GH₵/kWh)
        :param discount_rate: Weighted Average Cost of Capital (WACC)
        """
        self.system_cost_per_kw = system_cost_per_kw
        self.annual_om_cost = annual_om_cost
        self.electricity_tariff = electricity_tariff
        self.discount_rate = discount_rate
        self.lifetime_years = lifetime_years

    def calculate_roi(self, annual_energy_kwh, system_capacity_kw=1.0):
        """
        Calculates financial performance metrics.
        """
        capex = self.system_cost_per_kw * system_capacity_kw
        annual_revenue = annual_energy_kwh * self.electricity_tariff
        
        # Cash Flow Projection
        cash_flows = [-capex]
        for year in range(1, self.lifetime_years + 1):
            # Simplified: Assume 0.5% degradation handled in Layer 2
            # revenue - opex
            net_cash = annual_revenue - self.annual_om_cost
            cash_flows.append(net_cash)
            
        # 1. NPV
        try:
            import numpy_financial as npf
            npv = npf.npv(self.discount_rate, cash_flows)
        except:
            npv = sum([cf / (1 + self.discount_rate)**t for t, cf in enumerate(cash_flows)])
        
        # 2. IRR (Simplified Newton-Raphson if numpy-financial missing)
        try:
             import numpy_financial as npf
             irr = npf.irr(cash_flows)
             if np.isnan(irr): irr = 0.0
        except Exception:
             # Basic fallback or reference
             irr = self._manual_irr(cash_flows)
             
        # 3. Payback Period
        cumulative_cash = -capex
        payback = 0
        for year in range(1, self.lifetime_years + 1):
            net_cash = (annual_energy_kwh * self.electricity_tariff) - (self.annual_om_cost * system_capacity_kw)
            cumulative_cash += net_cash
            if cumulative_cash >= 0:
                payback = year
                break
                
        # 4. LCOE (GH₵/kWh)
        # LCOE = (Total Life Cycle Cost) / (Total Life Cycle Energy)
        total_discounted_cost = capex + sum([self.annual_om_cost * system_capacity_kw / (1 + self.discount_rate)**t for t in range(1, self.lifetime_years + 1)])
        total_discounted_energy = sum([annual_energy_kwh / (1 + self.discount_rate)**t for t in range(1, self.lifetime_years + 1)])
        lcoe = total_discounted_cost / total_discounted_energy if total_discounted_energy > 0 else 0
        
        return {
            "capex": capex,
            "annual_savings": annual_revenue,
            "npv": npv,
            "irr": irr,
            "lcoe": lcoe,
            "payback_years": payback,
            "lifetime_savings": annual_revenue * self.lifetime_years - (self.annual_om_cost * system_capacity_kw * self.lifetime_years) - capex
        }

    def _manual_irr(self, cash_flows, iterations=100):
        """Manual IRR calculation via Newton-Raphson with overflow protection."""
        res = 0.1 # Starting guess
        for i in range(iterations):
            try:
                npv = sum([cf / (1 + res)**t for t, cf in enumerate(cash_flows)])
                d_npv = sum([-t * cf / (1 + res)**(t + 1) for t, cf in enumerate(cash_flows)])
                if abs(d_npv) < 1e-9: break
                new_res = res - npv / d_npv
                if abs(new_res - res) < 1e-6: return new_res
                res = new_res
            except OverflowError:
                return 0.0
        return res
