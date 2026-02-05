import argparse
import pandas as pd
from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer

def run_simulation(location_id, capacity_kw, tilt, azimuth, module_name=None, inverter_name=None, modules_per_string=10):
    print(f"--- Starting Full Simulation (Loc ID: {location_id}) ---")
    
    engine = init_db()
    session = get_session(engine)
    
    # 0. Fetch Data (All rows for the location)
    print("0. Loading Satellite Data from DB...")
    query = session.query(WeatherData).filter_by(location_id=location_id)
    data = query.all()
    
    if not data:
        print("No data found for this location.")
        return

    # Convert to DataFrame
    df = pd.DataFrame([d.__dict__ for d in data])
    # Cleanup
    if '_sa_instance_state' in df.columns:
        df = df.drop('_sa_instance_state', axis=1)
        
    print(f"   Loaded {len(df)} records.")
    
    # Feature Engineering (if missing)
    if 'hour' not in df.columns: df['hour'] = df['timestamp'].apply(lambda x: x.hour)
    if 'month' not in df.columns: df['month'] = df['timestamp'].apply(lambda x: x.month)
    if 'pm25' not in df.columns: df['pm25'] = 25.0 # Default
    df['pm25'] = df['pm25'].astype(float)
    
    # Albedo - Geographic logic
    if location_id == 2: # Bolgatanga (Savanna)
        df['albedo'] = 0.25 
    elif location_id in [5, 6]: # Techiman & Kumasi (Forest/Semi-Deciduous)
        df['albedo'] = 0.20
    else: # Coastal/Axim/Accra
        df['albedo'] = 0.18
    
    # 1. Layer 1: Weather Correction (ML)
    print("1. Layer 1: Running Weather Correction (Random Forest)...")
    # Initialize with the best model type
    l1 = WeatherCorrectionLayer(model_type='lightgbm') 
    # Ensure models are loaded
    l1.load_models() 
    
    df_l1 = l1.predict(df)
    print("   Correction complete.")
    
    # 2. Layer 2: Environmental Losses
    print("2. Layer 2: Applying Environmental Losses (Soiling & Degradation)...")
    l2 = EnvironmentalLayer(rain_threshold_mm=0.5, degradation_rate=0.005)
    
    # Assuming start date is the first timestamp in data
    start_date = df_l1['timestamp'].min()
    df_l2 = l2.process(df_l1, system_start_date=start_date)
    print("   Losses calculated.")
    
    # 3. Layer 3: Physics Engine
    print(f"3. Layer 3: Simulating PV System ({capacity_kw}kW, Tilt={tilt}, Az={azimuth})...")
    l3 = PhysicsLayer()
    
    # Ensure DatetimeIndex for PVLib
    if 'timestamp' in df_l2.columns:
        df_l2['timestamp'] = pd.to_datetime(df_l2['timestamp'])
        df_l2.set_index('timestamp', inplace=True)
    
    # Get Location Lat/Lon
    loc = session.query(Location).get(location_id)
    
    results = l3.simulate(
        weather_df=df_l2, 
        lat=loc.latitude, 
        lon=loc.longitude, 
        system_capacity_kw=capacity_kw,
        tilt=tilt,
        azimuth=azimuth,
        module_name=module_name,
        inverter_name=inverter_name,
        modules_per_string=modules_per_string
    )
    
    # 4. Results
    annual_energy = results['annual_energy_kwh']
    specific_yield = annual_energy / capacity_kw
    
    # Calculate Duration in Years
    hours = len(df)
    years = hours / 8760.0
    
    avg_annual_energy = annual_energy / years
    avg_specific_yield = (annual_energy / capacity_kw) / years
    
    print("\n" + "="*40)
    print("SIMULATION RESULTS")
    print("="*40)
    print(f"Dataset Interval:    {years:.2f} years")
    print(f"Total Energy Gen:    {annual_energy:,.2f} kWh")
    print(f"Avg Annual Energy:   {avg_annual_energy:,.2f} kWh")
    print(f"Specific Yield:      {avg_specific_yield:,.2f} kWh/kWp/year")
    print("-" * 20)
    
    # Monthly Breakdown (Average)
    print("Avg Monthly Energy (kWh):")
    monthly = results['monthly_energy']
    # Group by month index 0-11 if we wanted true monthly avg, 
    # but results['monthly_energy'] is a list of sequential months.
    # Let's just print the first year's monthly data as sample
    print("Sample Monthly Output (First Year):")
    for i, e in enumerate(monthly[:12]):
         print(f"  Month {i+1}: {e:.2f}")
         
    print("="*40)
    session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run UnivSolar Full Simulation")
    parser.add_argument("--loc", type=int, default=1, help="Location ID")
    parser.add_argument("--kw", type=float, default=100.0, help="System Capacity (kW)")
    parser.add_argument("--tilt", type=float, default=10, help="Tilt Angle")
    parser.add_argument("--az", type=float, default=180, help="Azimuth (180=South)")
    parser.add_argument("--module", type=str, default=None, help="Sandia Module Name (e.g. 'Canadian_Solar_CS5P_220M___2009_')")
    parser.add_argument("--inverter", type=str, default=None, help="CEC Inverter Name")
    parser.add_argument("--string", type=int, default=10, help="Modules per String")
    
    args = parser.parse_args()
    
    run_simulation(args.loc, args.kw, args.tilt, args.az, args.module, args.inverter, args.string)
