import pandas as pd
import sys
from datetime import datetime
from core.database import init_db, get_session, Location, WeatherData
import dateutil.parser

def ingest_solcast(csv_path: str, lat: float, lon: float):
    """
    Ingests Solcast High-Fidelity Data as 'Ground Truth' and extra features.
    """
    print(f"Reading Solcast data from {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # Initialize DB
    engine = init_db()
    session = get_session(engine)
    
    # Find Location
    # Float precision might be tricky, so we look for 'close enough' or just exact.
    # For now, let's assume exact match or use a small epsilon if needed.
    # Given the previous context, the user likely has one main location.
    # Let's try to find it, or create if missing (though we should probably attach to existing).
    
    location = session.query(Location).filter_by(latitude=lat, longitude=lon).first()
    if not location:
        print(f"Location {lat}, {lon} not found. Please run ingest_nasa.py first to create the location.")
        return

    print(f"Found Location ID: {location.id}")
    
    updated_count = 0
    new_count = 0
    
    for _, row in df.iterrows():
        # Parse Timestamp
        # Solcast: 2022-01-01T01:00:00+00:00 (ISO 8601)
        ts_str = row['period_end']
        timestamp = dateutil.parser.parse(ts_str)
        
        # Convert to naive UTC if your DB expects it (SQLAlchemy often stores naive datetime)
        # Check existing data format. Usually best to store as UTC naive.
        timestamp = timestamp.replace(tzinfo=None) 
        
        # Find existing record
        weather_record = session.query(WeatherData).filter_by(
            location_id=location.id, 
            timestamp=timestamp
        ).first()
        
        if not weather_record:
            # Create new record if it doesn't exist (though usually we expect NASA data to be there)
            weather_record = WeatherData(
                location_id=location.id,
                timestamp=timestamp
            )
            session.add(weather_record)
            new_count += 1
        else:
            updated_count += 1
            
        # MAP COLUMNS
        # Ground Truth targets
        weather_record.ghi_ground = row['ghi']
        weather_record.dni_ground = row['dni']
        
        # Improved/New Features
        weather_record.pm25 = row.get('pm2.5') or row.get('pm25')
        weather_record.pm10 = row.get('pm10')
        weather_record.albedo = row.get('albedo')
        weather_record.gti = row.get('gti')
        
        # Solcast also provides DHI, Temp, etc. 
        # We can overwrite our "Satellite" data with this if we want Solcast to be the Input too?
        # NO. The User wants to TRAIN the ML model.
        # So we keep NASA data in 'ghi_satellite' (Input) and Solcast in 'ghi_ground' (Output).
        
    session.commit()
    print(f"Ingestion Complete.")
    print(f"Updated Records: {updated_count}")
    print(f"New Records: {new_count}")
    session.close()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python -m data.ingest_solcast <csv_path> <lat> <lon>")
        print("Example: python -m data.ingest_solcast data/solcast.csv 6.6666 -1.6163") # CNRE coords approx
    else:
        path = sys.argv[1]
        lat = float(sys.argv[2])
        lon = float(sys.argv[3])
        ingest_solcast(path, lat, lon)
