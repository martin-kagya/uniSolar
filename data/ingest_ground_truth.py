import random
from sqlalchemy.orm import Session
from core.database import init_db, get_session, Location, WeatherData
import sys

def simulate_ground_truth(session: Session, location_id: int):
    """
    Simulates 'Ground Truth' data by adding realistic noise/bias to NASA data.
    In a real scenario, this would import from a CSV/API (e.g. TAHMO).
    """
    print(f"Simulating Ground Truth validation data for Location ID {location_id}...")
    
    # Fetch all records for this location (satellite data)
    records = session.query(WeatherData).filter_by(location_id=location_id).all()
    
    if not records:
        print("No weather data found. Run ingest_nasa.py first.")
        return

    updated_count = 0
    
    for wd in records:
        # SIMULATION LOGIC:
        # 1. Bias: Satellite often overestimates GHI in West Africa by 5-10%
        # 2. Harmattan: During Dec/Jan/Feb, if AOD is high, Ground is MUCH lower than Satellite
        
        month = wd.timestamp.month
        bias = 0.95 # Base bias (Ground is 95% of Satellite)
        
        # Simulate Harmattan Dust Effect
        # If we have AOD, use it. Else infer from month.
        is_harmattan = month in [12, 1, 2]
        
        if is_harmattan:
            # Satellite misses low-altitude dust. 
            # Ground GHI drops significantly.
            # Randomize the severity
            dust_severity = random.uniform(0.75, 0.90) 
            bias = dust_severity
            
        # Add random sensor noise (+/- 2%)
        noise = random.uniform(0.98, 1.02)
        
        true_factor = bias * noise
        
        if wd.ghi_satellite is not None:
             wd.ghi_ground = wd.ghi_satellite * true_factor
             
        if wd.dni_satellite is not None:
             # DNI is hit harder by dust than GHI
             wd.dni_ground = wd.dni_satellite * (true_factor * 0.9) 
             
        updated_count += 1
        
    session.commit()
    print(f"Updated {updated_count} records with simulated Ground Truth.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m data.ingest_ground_truth <lat> <lon>")
        return
        
    lat = float(sys.argv[1])
    lon = float(sys.argv[2])
    
    engine = init_db()
    session = get_session(engine)
    
    loc = session.query(Location).filter_by(latitude=lat, longitude=lon).first()
    if not loc:
        print("Location not found in DB.")
        return
        
    simulate_ground_truth(session, loc.id)
    session.close()

if __name__ == "__main__":
    main()
