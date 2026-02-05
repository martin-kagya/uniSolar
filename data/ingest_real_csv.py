import pandas as pd
from sqlalchemy.orm import Session
from core.database import init_db, get_session, Location, WeatherData
import sys
from datetime import datetime

def ingest_real_data(csv_path: str, location_id: int):
    """
    Ingests REAL Ground Truth data from a CSV file.
    Expected CSV Format:
    timestamp, ghi_measured, dni_measured
    2023-01-01 08:00:00, 450.5, 300.2
    ...
    """
    print(f"Loading real data from {csv_path} for Location ID {location_id}...")
    
    # Load CSV
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    session = get_session(init_db())
    count = 0
    
    for _, row in df.iterrows():
        # Find the matching record (Syncing with Satellite Data)
        record = session.query(WeatherData).filter_by(
            location_id=location_id, 
            timestamp=row['timestamp']
        ).first()
        
        if record:
            # Update with REAL values
            record.ghi_ground = row['ghi_measured']
            if 'dni_measured' in row:
                record.dni_ground = row['dni_measured']
            count += 1
        else:
            print(f"Warning: No matching satellite record for {row['timestamp']}")
            
    session.commit()
    print(f"Successfully updated {count} records with REAL ground truth.")
    session.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m data.ingest_real_csv <path_to_csv> <location_id>")
    else:
        ingest_real_data(sys.argv[1], int(sys.argv[2]))
