import sys
import os
import pandas as pd
from sqlalchemy import func
sys.path.insert(0, os.getcwd())
from core.database import init_db, get_session, WeatherData

def check_missing_years():
    engine = init_db()
    session = get_session(engine)
    
    # Get all rows with NaN ghi_satellite for Accra
    print("Querying missing data for Accra...")
    missing_data = session.query(WeatherData.timestamp).filter(
        WeatherData.location_id == 1,
        WeatherData.ghi_satellite.is_(None)
    ).all()
    
    if not missing_data:
        print("No missing satellite data found.")
        session.close()
        return

    timestamps = [r[0] for r in missing_data]
    df = pd.DataFrame({'timestamp': timestamps})
    df['year'] = df['timestamp'].dt.year
    
    print("\nMissing Data by Year:")
    print(df['year'].value_counts().sort_index())
    
    session.close()

if __name__ == "__main__":
    check_missing_years()
