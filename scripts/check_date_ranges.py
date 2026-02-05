import sys
import os
from sqlalchemy import func
sys.path.insert(0, os.getcwd())
from core.database import init_db, get_session, WeatherData, Location

def check_date_range():
    engine = init_db()
    session = get_session(engine)
    
    locations = session.query(Location).filter(Location.id.in_([1, 2])).all()
    
    print(f"{'Location':<15} {'Start Date':<20} {'End Date':<20} {'Duration (Days)':<15}")
    print("-" * 75)
    
    for loc in locations:
        min_ts = session.query(func.min(WeatherData.timestamp)).filter_by(location_id=loc.id).scalar()
        max_ts = session.query(func.max(WeatherData.timestamp)).filter_by(location_id=loc.id).scalar()
        
        if min_ts and max_ts:
            duration = (max_ts - min_ts).days
            print(f"{loc.name:<15} {str(min_ts):<20} {str(max_ts):<20} {duration:<15}")
        else:
            print(f"{loc.name:<15} {'No Data':<20} {'-':<20} {'-':<15}")
            
    session.close()

if __name__ == "__main__":
    check_date_range()
