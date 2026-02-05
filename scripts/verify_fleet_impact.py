
import pandas as pd
import sys
import os

sys.path.insert(0, os.getcwd())

from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.services.gis import GISService

def verify_fleet():
    print("--- Verifying Fleet-Wide Calibration Impact ---")
    engine = init_db()
    session = get_session(engine)
    
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    
    # Check key locations
    # 1: Accra (Coastal)
    # 2: Bolga (North)
    # 6: Kumasi (Middle)
    # 7: Axim (Coastal/West)
    
    locations = [1, 2, 6, 7]
    
    for loc_id in locations:
        loc = session.get(Location, loc_id)
        if not loc: continue
        
        # Get raw data (simulated dataframe)
        query = session.query(WeatherData).filter_by(location_id=loc_id).limit(100) # Fast check
        recs = query.all()
        if not recs: continue
        
        df = pd.DataFrame([r.__dict__ for r in recs])
        
        # Inject Lat/Lon (simulating what happens in a real run)
        df['latitude'] = loc.latitude
        df['longitude'] = loc.longitude
        
        # Run Predict (which should now trigger calibration)
        df_pred = l1.predict(df)
        
        # Calculate Ratio (Corrected / Satellite)
        # We look at the ratio of sums to see the bias effect
        ratio_ghi = df_pred['ghi_corrected'].sum() / df_pred['ghi_satellite'].sum()
        
        print(f"\nLocation: {loc.name} (ID: {loc_id})")
        print(f"  Lat: {loc.latitude}, Lon: {loc.longitude}")
        
        # Determine expected behavior manually
        gis = GISService()
        dist = gis.get_distance_to_coast(loc.latitude, loc.longitude)
        print(f"  Dist to Coast: {dist:.1f} km")
        
        print(f"  GHI Ratio (Corrected/Sat): {ratio_ghi:.3f}")
        
        if loc.latitude > 9.0:
            if abs(ratio_ghi - 1.07) < 0.05: # Allow for ML drift, but calibration adds 0.07 bias
                 print("  [PASS] Northern Boost applied.")
            else:
                 print("  [WARN] Northern Boost unclear (ML might be fighting it, or calibration failed).")
                 
        if dist < 5.0:
            if ratio_ghi < 0.90:
                 print("  [PASS] Severe Coastal Penalty applied.")
            else:
                 print(f"  [WARN] Severe Coastal Penalty unclear (Ratio: {ratio_ghi}).")
        elif dist < 20.0:
            if ratio_ghi < 0.98:
                 print("  [PASS] Coastal Belt Penalty applied.")
            else:
                 print(f"  [WARN] Coastal Belt Penalty unclear (Ratio: {ratio_ghi}).")
        
    session.close()

if __name__ == "__main__":
    verify_fleet()
