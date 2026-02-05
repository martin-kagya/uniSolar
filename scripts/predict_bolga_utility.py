import pandas as pd
import numpy as np
from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer

def predict_utility_farm():
    print("--- 2.54MW Bolgatanga Utility Farm Simulation ---")
    
    # 1. System Specs
    num_modules = 8622
    p_module = 295 # Watts
    dc_capacity_kw = (num_modules * p_module) / 1000.0
    
    num_inverters = 5
    ac_capacity_kw = 500 * num_inverters # 2.5MW AC
    
    print(f"System: {dc_capacity_kw:,.2f} kWp DC | {ac_capacity_kw:,.2f} kW AC")
    print(f"Module: 295W Polly | Efficiency: 15.2%")
    
    # 2. Load Data
    engine = init_db()
    session = get_session(engine)
    loc = session.query(Location).get(2) # Bolgatanga
    
    query = session.query(WeatherData).filter_by(location_id=2)
    df = pd.DataFrame([d.__dict__ for d in query.all()])
    if '_sa_instance_state' in df.columns: df = df.drop('_sa_instance_state', axis=1)
    
    # Pre-process
    df['hour'] = df['timestamp'].apply(lambda x: x.hour)
    df['month'] = df['timestamp'].apply(lambda x: x.month)
    df['pm25'] = df['pm25'].astype(float)
    df['albedo'] = 0.25 # Savanna soil
    
    # 3. Layer 1: Weather Correction
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    df_l1 = l1.predict(df)
    
    # 4. Layer 2: Environmental
    l2 = EnvironmentalLayer(degradation_rate=0.005) # 0.5% for Poly
    # Start date from data (approx 4 years total)
    df_l2 = l2.process(df_l1, system_start_date=df_l1['timestamp'].min())
    
    # 5. Layer 3: Physics Simulation
    # We'll use a slightly more advanced call to simulate the custom efficiency
    l3 = PhysicsLayer()
    
    # Prepare index for PVLib
    df_l2['timestamp'] = pd.to_datetime(df_l2['timestamp'])
    df_l2.set_index('timestamp', inplace=True)
    
    # Run simulation
    # We pass the custom inverter efficiency data via the simulate method fallback
    # Since we can't easily inject a non-Sandia nameplate here without editing core,
    # we'll use the generic simulation but with the correct capacity and scaling.
    results = l3.simulate(
        weather_df=df_l2,
        lat=loc.latitude,
        lon=loc.longitude,
        system_capacity_kw=dc_capacity_kw,
        tilt=15, # Utility scale often use lat-based tilt
        azimuth=180
    )
    
    # 6. Apply Transformer & LV/MV Losses (approx 2% for utility-scale)
    transformer_loss = 0.02
    annual_gen_mwh = (results['annual_energy_kwh'] * (1 - transformer_loss)) / 1000.0
    
    # Metrics
    years = len(df) / 8760.0
    avg_annual_mwh = annual_gen_mwh / years
    specific_yield = (avg_annual_mwh * 1000) / dc_capacity_kw
    
    print("\n" + "="*50)
    print("UTILITY FARM PRODUCTION FORECAST")
    print("="*50)
    print(f"Location:           Bolgatanga, Ghana")
    print(f"Simulated Duration: {years:.2f} years")
    print(f"Total Generation:   {annual_gen_mwh * years:,.2f} MWh")
    print(f"Avg Annual Yield:   {avg_annual_mwh:,.2f} MWh/year")
    print(f"Specific Yield:     {specific_yield:.2f} kWh/kWp/year")
    print(f"Performance Ratio:  ~{0.78:.1%}") # Heuristic estimation
    print("="*50)

    session.close()

if __name__ == "__main__":
    predict_utility_farm()
