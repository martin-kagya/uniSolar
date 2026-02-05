import sys
import os

# Create DB connection
sys.path.append(os.getcwd())
from core.database import init_db, get_session, Location
from core.services.gis import GISService
from sqlalchemy import text

def migrate():
    print("Starting GIS Migration...")
    engine = init_db()
    
    # 1. Add Columns (Idempotent-ish)
    with engine.connect() as conn:
        print("Checking/Adding new columns...")
        # SQLite doesn't support "IF NOT EXISTS" in ADD COLUMN standardly in all versions, 
        # so we try/except or just run it.
        try:
            conn.execute(text("ALTER TABLE locations ADD COLUMN dist_to_coast_km FLOAT"))
            print("Added dist_to_coast_km column.")
        except Exception as e:
            print(f"Skipping dist_to_coast_km (probably exists): {e}")

        try:
            conn.execute(text("ALTER TABLE locations ADD COLUMN climate_zone INTEGER"))
            print("Added climate_zone column.")
        except Exception as e:
            print(f"Skipping climate_zone (probably exists): {e}")
            
    # 2. Backfill with GIS Service
    session = get_session(engine)
    gis = GISService() # Will log warning if DEM missing, but coast calc will work
    
    locations = session.query(Location).all()
    print(f"Backfilling GIS data for {len(locations)} locations...")
    
    for loc in locations:
        print(f"Processing {loc.name}...")
        
        # Calculate Distance to Coast
        dist = gis.get_distance_to_coast(loc.latitude, loc.longitude)
        loc.dist_to_coast_km = dist
        
        # Calculate Climate Zone
        # We pass existing elevation if available, else None
        elev = loc.elevation
        # Try to get better elevation from DEM if possible
        dem_elev = gis.get_elevation(loc.latitude, loc.longitude)
        if dem_elev is not None:
             elev = dem_elev
             loc.elevation = dem_elev # Update elevation with ground truth!
        
        zone = gis.get_climate_zone(loc.latitude, loc.longitude, elevation=elev)
        loc.climate_zone = zone
        
        print(f"  -> Dist: {dist:.1f}km, Zone: {zone}, Elev: {elev}")
        
    session.commit()
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
