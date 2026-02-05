import sys
import os
sys.path.insert(0, os.getcwd())
from core.database import init_db, get_session, Location, WeatherData
engine = init_db()
session = get_session(engine)
locs = session.query(Location).all()
print("Locations in DB:")
for l in locs:
    count = session.query(WeatherData).filter_by(location_id=l.id).count()
    gt_count = session.query(WeatherData).filter(WeatherData.location_id == l.id, WeatherData.ghi_ground.isnot(None)).count()
    print(f"ID: {l.id}, Name: {l.name}, Total Records: {count}, Ground Truth Records: {gt_count}")
session.close()
