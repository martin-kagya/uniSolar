"""
fetch_cams_pm25.py
===================
Downloads actual PM2.5 surface concentration data from CAMS EAC4
reanalysis for all training locations used in uniSolar's Layer 1
weather correction model.

CAMS EAC4 provides hourly PM2.5 at ~80 km resolution, 2003–present.
This replaces the AOD-based PM2.5 estimation that was used previously.

Prerequisites
-------------
1.  Register at https://ads.atmosphere.copernicus.eu (free)
2.  Save your API key to ~/.cdsapirc:
        url: https://ads.atmosphere.copernicus.eu/api/v2
        key: <uid>:<api-key>
3.  pip install cdsapi

Output
------
    data/processed/cams_pm25.parquet    — hourly PM2.5 for all coordinates

Usage
-----
    python scripts/fetch_cams_pm25.py
"""

import argparse
import os
import sys
import time
import pandas as pd
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from core.database import init_db, get_session
from sqlalchemy import text

ZINDI_DIR = "/Users/kagya/Desktop/ZINDI-PROJECT"
OUTPUT_DIR = os.path.join(ROOT, "data", "processed")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "cams_pm25.parquet")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_db_locations():
    """Return list of (loc_id, lat, lon) pairs that have ground truth."""
    engine = init_db()
    session = get_session(engine)
    rows = session.execute(text("""
        SELECT w.location_id, l.latitude, l.longitude
        FROM weather_data w
        JOIN locations l ON l.id = w.location_id
        WHERE w.ghi_ground IS NOT NULL
        GROUP BY w.location_id
    """)).fetchall()
    session.close()
    return [{"loc_id": r.location_id, "lat": r.latitude, "lon": r.longitude} for r in rows]


def get_zindi_stations():
    """Return list of (station_id, lat, lon) pairs from ZINDI training data."""
    train_path = os.path.join(ZINDI_DIR, "Train.csv")
    if not os.path.exists(train_path):
        print(f"  [SKIP] ZINDI Train.csv not found at {train_path}")
        return []
    df = pd.read_csv(train_path)
    stations = df[["station", "latitude", "longitude"]].drop_duplicates("station")
    return [{"station": r.station, "lat": r.latitude, "lon": r.longitude}
            for r in stations.itertuples()]


def build_request(lat, lon, start_year, end_year):
    """
    Build the CDS API request dictionary for a single point.
    CAMS EAC4 grid is ~0.75°, so we request a small area around the point.
    """
    return {
        "date": f"{start_year}-01-01/{end_year}-12-31",
        "type": "reanalysis",
        "format": "netcdf",
        "variable": "particulate_matter_2.5um",
        "area": [
            lat + 0.5,  # north
            lon - 0.5,  # west
            lat - 0.5,  # south
            lon + 0.5,  # east
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch CAMS EAC4 PM2.5 for training locations")
    parser.add_argument("--max-locations", type=int, default=None,
                        help="Max locations to process (for testing)")
    args = parser.parse_args()

    # Collect all coordinates that need PM2.5
    print("=" * 60)
    print("STEP 1 — Collecting training locations")
    print("=" * 60)

    locations = get_db_locations()
    print(f"  DB locations with ground truth: {len(locations)}")

    zindi_stations = get_zindi_stations()
    print(f"  ZINDI stations: {len(zindi_stations)}")

    all_points = []
    for loc in locations:
        all_points.append({
            "name": f"loc_{loc['loc_id']}",
            "lat": loc["lat"],
            "lon": loc["lon"],
            "source": "db",
        })
    for st in zindi_stations:
        all_points.append({
            "name": st["station"],
            "lat": st["lat"],
            "lon": st["lon"],
            "source": "zindi",
        })

    if args.max_locations:
        all_points = all_points[:args.max_locations]

    print(f"  Total unique coordinates: {len(all_points)}")

    # Check if cdsapi is available
    try:
        import cdsapi
    except ImportError:
        print("\nERROR: cdsapi not installed.")
        print("  pip install cdsapi")
        print("  Then register at https://ads.atmosphere.copernicus.eu")
        print("  and save your API key to ~/.cdsapirc")
        sys.exit(1)

    # Check for ~/.cdsapirc
    cdsrc = os.path.expanduser("~/.cdsapirc")
    if not os.path.exists(cdsrc):
        print(f"\nERROR: {cdsrc} not found.")
        print("  Register at https://ads.atmosphere.copernicus.eu")
        print("  Create ~/.cdsapirc with:")
        print("    url: https://ads.atmosphere.copernicus.eu/api/v2")
        print("    key: <uid>:<api-key>")
        sys.exit(1)

    # Determine date ranges
    # DB data: 2022-2025, ZINDI data: 2016-2020
    # We'll do one request per (year, lat, lon) triplet to avoid huge payloads
    years = list(range(2016, 2021))

    c = cdsapi.Client()

    all_records = []

    print("\n" + "=" * 60)
    print("STEP 2 — Downloading CAMS EAC4 PM2.5")
    print("=" * 60)
    print(f"  {len(all_points)} locations × {len(years)} years")
    print(f"  This will take a while on first run (caching helps).\n")

    # Compute bounding box covering all points with ~1° padding
    lats = [p["lat"] for p in all_points]
    lons = [p["lon"] for p in all_points]
    north = max(lats) + 1.0
    south = min(lats) - 1.0
    east = max(lons) + 1.0
    west = min(lons) - 1.0

    for year in years:
        # Skip years where we don't have data for any source
        has_zindi = any(p["source"] == "zindi" for p in all_points)
        has_db = any(p["source"] == "db" for p in all_points)
        if year < 2016 or year > 2025:
            continue

        cache_path = os.path.join(OUTPUT_DIR, f"cams_region_{year}.grib")

        if os.path.exists(cache_path):
            print(f"  [CACHED] {year}")
        else:
            print(f"  [FETCH]  {year} (region [{south:.1f}, {west:.1f}, {north:.1f}, {east:.1f}])")
            try:
                c.retrieve("cams-global-reanalysis-eac4", {
                    "variable": ["particulate_matter_2.5um"],
                    "date": f"{year}-01-01/{year}-12-31",
                    "time": ["00:00", "03:00", "06:00", "09:00", "12:00", "15:00", "18:00", "21:00"],
                    "area": [north, west, south, east],
                }, cache_path)
            except Exception as e:
                print(f"    ERROR: {e}")
                continue

        # Parse grib and extract data for each point
        try:
            import xarray as xr
        except ImportError:
            print("    Installing xarray...")
            os.system(f"{sys.executable} -m pip install xarray netCDF4 cfgrib")
            import xarray as xr

        try:
            ds = xr.open_dataset(cache_path, engine="cfgrib")
            for pt in all_points:
                if pt["source"] == "zindi" and (year < 2016 or year > 2020):
                    continue
                if pt["source"] == "db" and (year < 2022 or year > 2025):
                    continue
                # Select nearest grid point
                ds_point = ds.sel(latitude=pt["lat"], longitude=pt["lon"], method="nearest")
                times = pd.to_datetime(ds_point.time.values)
                vals = ds_point["pm2p5"].values.flatten() * 1e9
                for t, v in zip(times, vals):
                    all_records.append({
                        "name": pt["name"],
                        "latitude": pt["lat"],
                        "longitude": pt["lon"],
                        "source": pt["source"],
                        "timestamp": t,
                        "pm25_cams": float(v),
                    })
            ds.close()
        except Exception as e:
            print(f"    PARSE ERROR for {year}: {e}")

    if not all_records:
        print("\nNo data downloaded. Check your CAMS API setup.")
        sys.exit(1)

    # Save to parquet
    df_out = pd.DataFrame(all_records)
    df_out = df_out.drop_duplicates(subset=["name", "timestamp"])
    df_out.to_parquet(OUTPUT_PATH, index=False)
    print(f"\n  Saved {len(df_out):,} records to {OUTPUT_PATH}")
    print(f"  Date range: {df_out['timestamp'].min()} — {df_out['timestamp'].max()}")
    print(f"  Locations: {df_out['name'].nunique()}")
    print(f"  PM2.5 range: [{df_out['pm25_cams'].min():.1f}, {df_out['pm25_cams'].max():.1f}] µg/m³")
    print("\nDone.")


if __name__ == "__main__":
    main()
