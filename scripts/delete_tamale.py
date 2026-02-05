import sys
import os
sys.path.insert(0, os.getcwd())
from core.database import init_db, get_session, Location, WeatherData

def delete_tamale():
    engine = init_db()
    session = get_session(engine)
    
    # Find Tamale
    tamale = session.query(Location).filter(Location.name.ilike('%tamale%')).first()
    
    if not tamale:
        print("Tamale location not found in DB.")
        session.close()
        return

    print(f"Found Location: {tamale.name} (ID: {tamale.id})")
    
    # Delete Weather Data first (Foreign Key)
    deleted_weather = session.query(WeatherData).filter_by(location_id=tamale.id).delete()
    print(f"Deleted {deleted_weather} weather records.")
    
    # Delete Location
    session.delete(tamale)
    session.commit()
    print(f"Deleted Location: {tamale.name}")
    
    session.close()

if __name__ == "__main__":
    delete_tamale()
