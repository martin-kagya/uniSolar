import pandas as pd

class SustainabilityLayer:
    """
    Layer 4: Environmental & Sustainability Reporting.
    Calculates carbon avoidance and equivalent green metrics.
    """
    
    def __init__(self, grid_emission_factor=0.54):
        """
        :param grid_emission_factor: kg CO2 per kWh (Ghana Grid Default: 0.54)
                                     Source: Our World in Data 2023 (540 gCO₂eq/kWh)
        """
        self.grid_emission_factor = grid_emission_factor
        # Sources for equivalents: EPA Greenhouse Gas Equivalencies Calculator
        self.tree_absorption_annual = 21.0 # kg CO2 per year for a mature tree
        self.car_miles_per_kg_co2 = 2.5 # Roughly 2.5 miles per kg CO2 saved
        
    def calculate_avoidance(self, annual_energy_kwh, lifetime_years=25):
        """
        Calculates CO2 avoidance metrics.
        """
        annual_co2_kg = annual_energy_kwh * self.grid_emission_factor
        lifetime_co2_kg = annual_co2_kg * lifetime_years
        
        # Equivalent metrics
        trees_equivalent = annual_co2_kg / self.tree_absorption_annual
        
        return {
            "annual_co2_avoided_kg": annual_co2_kg,
            "annual_co2_avoided_tons": annual_co2_kg / 1000.0,
            "lifetime_co2_avoided_tons": lifetime_co2_kg / 1000.0,
            "trees_planted_equivalent": round(trees_equivalent),
            "grid_emission_factor": self.grid_emission_factor
        }

    def get_avoidance_series(self, energy_series):
        """
        Converts an energy time series to a CO2 avoidance time series.
        """
        return energy_series * self.grid_emission_factor
