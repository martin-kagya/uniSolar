import sys
import os
import pandas as pd
sys.path.insert(0, os.getcwd())
from core.database import init_db, get_session, WeatherData

def compare_locations():
    engine = init_db()
    session = get_session(engine)
    
    # IDs: 1=Accra, 2=Bolga, 3=Tamale
    locs = {1: "Accra", 2: "Bolgatanga", 3: "Tamale"}
    
    print("Fetching first 5 rows with GHI > 100 (Daytime) for each location...")
    
    data_samples = {}
    
    for lid, name in locs.items():
        # Get first 5 records with valid GHI > 100
        records = session.query(WeatherData).filter(
            WeatherData.location_id == lid,
            WeatherData.ghi_ground > 100
        ).order_by(WeatherData.timestamp).limit(5).all()
        
        data_samples[lid] = records
        
        print(f"\n--- {name} (ID {lid}) ---")
        if not records:
            print("No daytime ground truth records found.")
            continue
            
        for r in records:
            print(f"Time: {r.timestamp}, GHI: {r.ghi_ground}, DNI: {r.dni_ground}")

    # Direct Comparison
    print("\n\nAnalyzing duplication...")
    if not data_samples[3]:
        print("Tamale has no daytime data to compare.")
        session.close()
        return

    # Check against Accra
    accra_match = True
    if data_samples[1]:
        for i, val in enumerate(data_samples[3]):
            if i >= len(data_samples[1]): break
            # Compare GHI and Timestamp
            if val.ghi_ground != data_samples[1][i].ghi_ground or val.timestamp != data_samples[1][i].timestamp:
                accra_match = False
                break
    else:
        accra_match = False
        
    # Check against Bolga
    bolga_match = True
    if data_samples[2]:
        for i, val in enumerate(data_samples[3]):
            if i >= len(data_samples[2]): break
            if val.ghi_ground != data_samples[2][i].ghi_ground or val.timestamp != data_samples[2][i].timestamp:
                bolga_match = False
                break
    else:
        bolga_match = False

    if accra_match:
        print("⚠️  CONFIRMED: TAMALE DATA IS A DUPLICATE OF ACCRA DATA!")
    elif bolga_match:
        print("⚠️  CONFIRMED: TAMALE DATA IS A DUPLICATE OF BOLGATANGA DATA!")
    else:
        print("✅ Tamale data is UNIQUE (different values from Accra/Bolga).")

    session.close()

if __name__ == "__main__":
    compare_locations()
