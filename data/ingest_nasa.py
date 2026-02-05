import requests
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
from core.database import init_db, get_session, Location, WeatherData
import sys

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"

def fetch_nasa_data(lat, lon, year):
    """Fetches hourly weather data from NASA POWER API."""
    # Removed AOD_550 and PW which might not be available hourly or causing 422
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI,ALLSKY_SFC_SW_DIFF,T2M,RH2M,WS2M,PRECTOTCORR",
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": f"{year}0101",
        "end": f"{year}1231",
        "format": "JSON"
    }
    
    print(f"Fetching NASA POWER data for {lat}, {lon} (Year: {year})...")
    response = requests.get(NASA_POWER_URL, params=params)
    
    if response.status_code != 200:
        print(f"Error: NASA API failed with status {response.status_code}")
        print(f"Response: {response.text}")
        return None
        
    return response.json()

def process_and_store(session: Session, location_id: int, data: dict, year: int):
    """Parses NASA JSON and stores into WeatherData table (Upsert)."""
    try:
        properties = data['properties']['parameter']
        
        # Determine timestamps
        timestamps = list(properties['ALLSKY_SFC_SW_DWN'].keys())
        
        count = 0
        updated_count = 0
        new_count = 0
        
        # Process in chunks to manage memory/query size
        chunk_size = 1000
        for i in range(0, len(timestamps), chunk_size):
            chunk_ts = timestamps[i:i + chunk_size]
            
            # 1. Pre-fetch existing records for this chunk
            ts_objs = [datetime.strptime(ts, "%Y%m%d%H") for ts in chunk_ts]
            existing_records = session.query(WeatherData).filter(
                WeatherData.location_id == location_id,
                WeatherData.timestamp.in_(ts_objs)
            ).all()
            
            # Map timestamp -> record
            existing_map = {r.timestamp: r for r in existing_records}
            
            for ts_str in chunk_ts:
                dt = datetime.strptime(ts_str, "%Y%m%d%H")
                
                # Extract values
                ghi = properties.get('ALLSKY_SFC_SW_DWN', {}).get(ts_str)
                dni = properties.get('ALLSKY_SFC_SW_DNI', {}).get(ts_str)
                dhi = properties.get('ALLSKY_SFC_SW_DIFF', {}).get(ts_str)
                temp = properties.get('T2M', {}).get(ts_str)
                rh = properties.get('RH2M', {}).get(ts_str)
                ws = properties.get('WS2M', {}).get(ts_str)
                pw = properties.get('PW', {}).get(ts_str)
                aod = properties.get('AOD_550', {}).get(ts_str)
                rain = properties.get('PRECTOTCORR', {}).get(ts_str)
                
                if dt in existing_map:
                    # Update existing
                    rec = existing_map[dt]
                    rec.ghi_satellite = ghi
                    rec.dni_satellite = dni
                    rec.dhi_satellite = dhi
                    rec.temp_air = temp
                    rec.relative_humidity = rh
                    rec.wind_speed = ws
                    rec.precipitable_water = pw
                    rec.aod_550 = aod
                    rec.rain_mm = rain
                    updated_count += 1
                else:
                    # Create new
                    wd = WeatherData(
                        location_id=location_id,
                        timestamp=dt,
                        ghi_satellite=ghi,
                        dni_satellite=dni,
                        dhi_satellite=dhi,
                        temp_air=temp,
                        relative_humidity=rh,
                        wind_speed=ws,
                        precipitable_water=pw,
                        aod_550=aod,
                        rain_mm=rain
                    )
                    session.add(wd)
                    new_count += 1
                count += 1
            
            session.commit()
            
        print(f"Processed {count} records (New: {new_count}, Updated: {updated_count}) for Location ID {location_id}.")
        
    except KeyError as e:
        print(f"Error parsing NASA data: {e}")

def main():
    if len(sys.argv) < 4:
        print("Usage: python -m data.ingest_nasa <lat> <lon> <year> [Location_Name]")
        return
        
    lat = float(sys.argv[1])
    lon = float(sys.argv[2])
    year = int(sys.argv[3])
    loc_name = sys.argv[4] if len(sys.argv) > 4 else f"Loc_{lat}_{lon}"
    
    engine = init_db()
    session = get_session(engine)
    
    # Check if location exists, else create
    loc = session.query(Location).filter_by(latitude=lat, longitude=lon).first()
    if not loc:
        loc = Location(name=loc_name, latitude=lat, longitude=lon)
        session.add(loc)
        session.commit()
        print(f"Created new Location: {loc.name} (ID: {loc.id})")
    else:
        print(f"Using existing Location: {loc.name} (ID: {loc.id})")
        
    # Fetch
    raw_json = fetch_nasa_data(lat, lon, year)
    if raw_json:
        process_and_store(session, loc.id, raw_json, year)
        
    session.close()

if __name__ == "__main__":
    main()
