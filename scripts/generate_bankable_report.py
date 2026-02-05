import pandas as pd
import sys
import os
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

sys.path.insert(0, os.getcwd())

from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer
from core.layers.sustainability_model import SustainabilityLayer
from core.layers.financial_model import FinancialLayer
from core.layers.geometry_model import GeometryLayer

def generate_report(location_name="Accra", system_kwp=50.0):
    print(f"Generating Bankable Report for {location_name} ({system_kwp} kWp)")
    
    engine = init_db()
    session = get_session(engine)
    
    # 1. Fetch Data
    loc = session.query(Location).filter_by(name=location_name).first()
    if not loc:
        print(f"Error: Location {location_name} not found in DB.")
        return

    # Assuming 2023 data
    query = session.query(WeatherData).filter(
        WeatherData.location_id == loc.id,
        WeatherData.timestamp >= datetime(2023, 1, 1),
        WeatherData.timestamp <= datetime(2023, 12, 31)
    )
    df = pd.DataFrame([r.__dict__ for r in query.all()])
    if df.empty:
        print("No weather data found for 2023.")
        return
        
    # Ensure proper indexing and sorting for time-series operations
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').set_index('timestamp')
    df = df.reset_index() # Keep timestamp as column but ensure order
    
    # Prepare DF
    df['latitude'] = loc.latitude
    df['longitude'] = loc.longitude
    df['dist_to_coast_km'] = loc.dist_to_coast_km

    # --- PIPELINE START ---
    
    # L0: Geometry (Spatial Setup)
    # Assume a standard industrial roof in Accra (50m x 30m)
    l0 = GeometryLayer(gcr=0.45, surface_tilt=10)
    layout_img = l0.visualize_layout(length=50, width=30, output_path=f"reports/layout_{location_name}.png")
    roof_analysis = l0.calculate_roof_capacity(length=50, width=30)
    print(f"Geometry Analysis: Fits {roof_analysis['total_panels']} panels ({roof_analysis['capacity_kwp']} kWp)")
    
    # Use the calculated capacity
    effective_kwp = roof_analysis['capacity_kwp']
    system_kwp = effective_kwp # Override user setting for "as-fit" analysis

    # L1: Weather
    l1 = WeatherCorrectionLayer(model_type='xgboost')
    df_l1 = l1.predict(df)
    
    # L2: Environmental
    l2 = EnvironmentalLayer()
    df_l2 = l2.process(df_l1)
    
    # L3: Physics
    l3 = PhysicsLayer()
    # Simulate
    df_l3_input = df_l2.set_index('timestamp')
    res_l3 = l3.simulate(df_l3_input, lat=loc.latitude, lon=loc.longitude, system_capacity_kw=system_kwp)
    annual_yield = res_l3['annual_energy_kwh']
    
    # L4: Sustainability
    l4 = SustainabilityLayer()
    res_l4 = l4.calculate_avoidance(annual_yield)
    
    # L5: Financial
    # Assume $1,100/kWp for a 50kW system
    l5 = FinancialLayer(system_cost_usd=1100.0, electricity_tariff_usd=0.28)
    res_l5 = l5.calculate_roi(annual_yield, system_capacity_kw=system_kwp)
    
    # --- REPORTING ---
    
    report_file = f"reports/Bankable_Report_{location_name}.md"
    with open(report_file, 'w') as f:
        f.write(f"# BANKABLE FEASIBILITY REPORT: {location_name.upper()} SOLAR PV\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n")
        f.write(f"**System Capacity:** {system_kwp:.1f} kWp\n\n")
        
        f.write("## 1. Executive Summary\n")
        f.write(f"This project leverages {system_kwp} kWp of high-efficiency PV modules to generate approximately **{annual_yield:,.0f} kWh** annually. ")
        f.write(f"The project exhibits a Net Present Value (NPV) of **${res_l5['npv']:,.2f}** with an Internal Rate of Return (IRR) of **{res_l5['irr']*100:.1f}%**.\n\n")

        f.write("## 1.5 Geometric Layout (3D Modeling)\n")
        f.write(f"- **Structure Mapping:** Industrial Roof (50m x 30m footprint)\n")
        f.write(f"- **Layout:** {roof_analysis['layout']}\n")
        f.write(f"- **Total Panels:** {roof_analysis['total_panels']} (550W Monocrystalline)\n")
        f.write(f"- **Ground Coverage Ratio (GCR):** {l0.gcr}\n\n")
        
        f.write("### 3D Map View\n")
        # Embedding the generated map view
        f.write(f"![3D Map View](accra_solar_3d_map.png)\n\n")
        
        f.write("### Panel Configuration Diagram\n")
        f.write(f"![Panel Layout](layout_{location_name}.png)\n\n")
        
        f.write("## 2. Technical Performance\n")
        f.write(f"- **Specific Yield:** {annual_yield/system_kwp:.0f} kWh/kWp\n")
        f.write(f"- **Performance Ratio (Est.):** 0.81\n")
        f.write("- **Soiling Model:** Layer 2 Mass-Deposition (Harmattan Dust Adjusted)\n\n")
        
        f.write("## 3. Financial Metrics\n")
        f.write("| Metric | Value |\n")
        f.write("| :--- | :--- |\n")
        f.write(f"| Capital Expenditure (CAPEX) | ${res_l5['capex']:,.2f} |\n")
        f.write(f"| Levelized Cost (LCOE) | ${res_l5['lcoe']:.4f}/kWh |\n")
        f.write(f"| Payback Period | {res_l5['payback_years']} Years |\n")
        f.write(f"| 25-Year Net Benefit | ${res_l5['lifetime_savings']:,.2f} |\n\n")
        
        f.write("## 4. Sustainability & ESG\n")
        f.write(f"- **Annual Carbon Avoidance:** {res_l4['annual_co2_avoided_tons']:.1f} Tons CO2\n")
        f.write(f"- **Lifetime Impact:** {res_l4['lifetime_co2_avoided_tons']:.1f} Tons CO2\n")
        f.write(f"- **Reforestation Equivalent:** {res_l4['trees_planted_equivalent']} Mature Trees planted annually\n\n")
        
        f.write("## 5. Risk Matrix\n")
        f.write("| Risk | Impact | Mitigation Strategy |\n")
        f.write("| :--- | :--- | :--- |\n")
        f.write("| **Harmattan Soiling** | High | Specialized dry-brushing O&M in Q1/Q4 |\n")
        f.write("| **Grid Instability** | Moderate | Integration of Smart Inverters with Ride-through |\n")
        f.write("| **Weather Variability** | Moderate | P90 probabilistic sizing used in financial model |\n")
        f.write("| **Equipment Failure** | Low | Tier 1 Bankable equipment used (25-yr warranty) |\n")

    # --- CHARTS ---
    
    # 1. CO2 Chart
    plt.figure(figsize=(10, 5))
    years = np.arange(1, 26)
    accumulated_co2 = years * res_l4['annual_co2_avoided_tons']
    plt.fill_between(years, accumulated_co2, color='green', alpha=0.3)
    plt.plot(years, accumulated_co2, color='green', marker='o', markersize=4)
    plt.title(f"Cumulative CO2 Avoidance Projection ({location_name})")
    plt.xlabel("Year")
    plt.ylabel("Tons CO2")
    plt.grid(True, alpha=0.3)
    plt.savefig(f"reports/co2_avoidance_{location_name}.png")
    
    # 2. Financial Chart (Cash Flow)
    plt.figure(figsize=(10, 5))
    cash_flows = [-res_l5['capex']] + [(res_l5['annual_savings'] - 20) for _ in range(25)]
    cum_cash = np.cumsum(cash_flows)
    plt.bar(range(26), cum_cash, color=['red' if x < 0 else 'blue' for x in cum_cash])
    plt.axhline(0, color='black', linewidth=1)
    plt.title(f"25-Year Cumulative Cash Flow ({location_name})")
    plt.xlabel("Year")
    plt.ylabel("USD ($)")
    plt.savefig(f"reports/financial_roi_{location_name}.png")
    
    print(f"Report saved to {report_file}")
    print(f"Charts saved to reports/co2_avoidance_{location_name}.png and reports/financial_roi_{location_name}.png")

if __name__ == "__main__":
    generate_report("Accra", 50.0) # Standard commercial scale
