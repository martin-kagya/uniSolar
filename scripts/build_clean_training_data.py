"""
build_clean_training_data.py
============================
Builds a clean training dataset by:
1. Fetching NASA POWER satellite data for all 40 ZINDI stations
2. Merging with ZINDI ground truth at hourly resolution
3. Adding Navrongo + Sunyani Tier-1 ground truth
4. Filtering broken stations (ratio < 0.3 or > 2.5)
5. Saving as parquet for model retraining

Usage:
    python scripts/build_clean_training_data.py
    python scripts/build_clean_training_data.py --skip-fetch  (use cached NASA data)
"""

import argparse, os, sys, json, time
import numpy as np
import pandas as pd
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
ZINDI_DIR = os.path.join(ROOT, "zindi-data")
OUTPUT_DIR = os.path.join(ROOT, "data", "processed")
CACHE_DIR = os.path.join(ROOT, "data", "measurements", "nasa_cache")

# Broken stations to exclude (pre-identified)
EXCLUDE_STATIONS = {"TA00338"}  # Kalana, Mali - dead sensor (GHI=26 W/m²)


def fetch_nasa_power(lat, lon, year, cache_dir):
    """Fetch NASA POWER hourly data, with local caching."""
    cache_file = os.path.join(cache_dir, f"nasa_{lat:.4f}_{lon:.4f}_{year}.json")
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI,ALLSKY_SFC_SW_DIFF,T2M,RH2M,WS2M,PRECTOTCORR",
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": f"{year}0101",
        "end": f"{year}1231",
        "format": "JSON"
    }

    for attempt in range(3):
        try:
            response = requests.get(NASA_POWER_URL, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache_file, 'w') as f:
                    json.dump(data, f)
                return data
            elif response.status_code == 422:
                print(f"    422 error for ({lat:.4f}, {lon:.4f}) year {year} - skipping")
                return None
            else:
                print(f"    Attempt {attempt+1}: HTTP {response.status_code}")
                time.sleep(2)
        except requests.exceptions.RequestException as e:
            print(f"    Attempt {attempt+1}: {e}")
            time.sleep(3)
    return None


def nasa_json_to_df(data):
    """Convert NASA POWER JSON to DataFrame."""
    props = data['properties']['parameter']
    records = []
    for ts_str in sorted(props['ALLSKY_SFC_SW_DWN'].keys()):
        dt = pd.to_datetime(ts_str, format='%Y%m%d%H')  # NASA POWER = Local Solar Time
        ghi = props['ALLSKY_SFC_SW_DWN'].get(ts_str)
        dni = props['ALLSKY_SFC_SW_DNI'].get(ts_str)
        dhi = props['ALLSKY_SFC_SW_DIFF'].get(ts_str)
        temp = props['T2M'].get(ts_str)
        rh = props['RH2M'].get(ts_str)
        ws = props['WS2M'].get(ts_str)
        rain = props.get('PRECTOTCORR', {}).get(ts_str, 0)

        if ghi is None or ghi < -900:
            continue

        records.append({
            'timestamp': dt,
            'ghi_satellite': max(ghi, 0),
            'dni_satellite': max(dni, 0) if dni and dni > -900 else 0,
            'dhi_satellite': max(dhi, 0) if dhi and dhi > -900 else 0,
            'temp_air': temp if temp and temp > -900 else 27.0,
            'relative_humidity': rh if rh and rh > -900 else 70.0,
            'wind_speed': ws if ws and ws > -900 else 2.0,
            'rain_mm': rain if rain and rain > -900 else 0.0,
        })

    return pd.DataFrame(records).set_index('timestamp').sort_index()


def load_zindi_ground():
    """Load ZINDI ground truth data, resampled to hourly."""
    train_path = os.path.join(ZINDI_DIR, "Train.csv")
    df = pd.read_csv(train_path, parse_dates=['timestamp'])
    df.rename(columns={
        'radiation (W/m2)': 'ghi_ground',
        'temperature (degrees Celsius)': 'temp_air',
        'relativehumidity (-)': 'relative_humidity',
        'precipitation (mm)': 'rain_mm',
    }, inplace=True)

    records = []
    for station, group in df.groupby('station'):
        if station in EXCLUDE_STATIONS:
            print(f"  Excluding {station} (broken sensor)")
            continue

        lat = group['latitude'].iloc[0]
        lon = group['longitude'].iloc[0]
        country = group['country'].iloc[0]
        name = group['station_name'].iloc[0]

        g = group.set_index('timestamp')[['ghi_ground']].copy()
        g = g[g.index.notna()]
        g = g.resample('h').mean().dropna()

        records.append({
            'station': station,
            'latitude': lat,
            'longitude': lon,
            'country': country,
            'station_name': name,
            'ghi_ground_hourly': g['ghi_ground'],
        })

    return records


def build_zindi_nasa_power(zindi_stations, skip_fetch=False):
    """Fetch NASA POWER data for all ZINDI stations and merge with ground truth."""
    all_records = []

    for i, station_info in enumerate(zindi_stations):
        station = station_info['station']
        lat = station_info['latitude']
        lon = station_info['longitude']
        country = station_info['country']
        name = station_info['station_name']

        print(f"\n[{i+1}/{len(zindi_stations)}] {station} ({name}, {country})")
        print(f"  Location: ({lat:.4f}, {lon:.4f})")

        # Determine year from ZINDI ground data timestamps
        g = station_info['ghi_ground_hourly']
        year = g.index[0].year
        print(f"  Year: {year}, Ground records: {len(g)}")

        # Fetch NASA POWER data
        if skip_fetch:
            cache_file = os.path.join(CACHE_DIR, f"nasa_{lat:.4f}_{lon:.4f}_{year}.json")
            if not os.path.exists(cache_file):
                print(f"  No cache file, skipping fetch")
                continue
            with open(cache_file) as f:
                nasa_data = json.load(f)
        else:
            nasa_data = fetch_nasa_power(lat, lon, year, CACHE_DIR)
            if nasa_data is None:
                print(f"  Failed to fetch NASA data, skipping")
                continue
            time.sleep(0.5)  # Rate limit

        # Convert NASA JSON to DataFrame
        nasa = nasa_json_to_df(nasa_data)
        print(f"  NASA records: {len(nasa)}")

        # Merge ground + satellite at hourly resolution
        merged = nasa.join(g, how='inner')
        if 'ghi_ground' not in merged.columns:
            print(f"  No matching timestamps between NASA and ground data, skipping")
            continue
        merged = merged.dropna(subset=['ghi_ground'])

        # Add metadata
        merged['station'] = station
        merged['latitude'] = lat
        merged['longitude'] = lon
        merged['country'] = country
        merged['station_name'] = name

        # Compute ratio for quality check
        merged['ratio'] = merged['ghi_ground'] / np.maximum(merged['ghi_satellite'], 10.0)
        # Preserve timestamp as column (currently in index)
        merged['timestamp'] = merged.index
        day_mask = merged['ghi_satellite'] > 50
        if day_mask.sum() > 100:
            mean_ratio = merged.loc[day_mask, 'ratio'].mean()
            print(f"  Merged records: {len(merged)}, Daytime ratio: {mean_ratio:.3f}")
        else:
            mean_ratio = merged['ratio'].mean()
            print(f"  Merged records: {len(merged)}, Overall ratio: {mean_ratio:.3f}")

        all_records.append(merged)

    result = pd.concat(all_records, ignore_index=True) if all_records else pd.DataFrame()
    if not result.empty and 'timestamp' not in result.columns:
        # Index was DatetimeIndex from the join, preserve as column
        pass  # Already handled - concat with ignore_index resets it
    return result


def build_validation_data(skip_fetch=False):
    """Build Navrongo + Sunyani validation set with NASA POWER data."""
    stations = [
        ('navrongo', 10.876, -1.063, 'Navrongo', 'Ghana', 2022),
        ('sunyani', 7.349, -2.340, 'Sunyani', 'Ghana', 2022),
    ]

    records = []
    for file_prefix, lat, lon, name, country, year in stations:
        print(f"\nBuilding validation set for {name} ({lat:.4f}, {lon:.4f})...")

        # Load measured ground truth
        csv_path = os.path.join(ROOT, 'data', 'measurements', f'{file_prefix}_qc.csv')
        if not os.path.exists(csv_path):
            print(f"  No ground truth file: {csv_path}")
            continue

        df = pd.read_csv(csv_path, parse_dates=['Timestamp'], skiprows=[1],
                         low_memory=False, encoding='latin-1')
        df = df.rename(columns={'Timestamp': 'timestamp', 'GHI': 'ghi', 'DNI': 'dni', 'DHI': 'dhi'})
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_localize(None)
        df = df.set_index('timestamp').sort_index()
        for col in ['ghi', 'dni', 'dhi']:
            df[col] = df[col].clip(lower=0).clip(upper=1400)
        measured = df[['ghi', 'dni', 'dhi']].resample('h').mean().dropna(subset=['ghi'])
        measured = measured[measured.index.year == year]
        print(f"  Ground records: {len(measured)}")

        # Fetch NASA POWER data
        if skip_fetch:
            # Search for cache file with various precision formats
            cache_file = None
            for fmt in [f"nasa_{lat}_{lon}_{year}.json",
                       f"nasa_{lat:.4f}_{lon:.4f}_{year}.json",
                       f"nasa_{lat:.3f}_{lon:.3f}_{year}.json"]:
                p = os.path.join(CACHE_DIR, fmt)
                if os.path.exists(p):
                    cache_file = p
                    break
            if cache_file is None:
                print(f"  No cache file found")
                continue
            with open(cache_file) as f:
                nasa_data = json.load(f)
        else:
            nasa_data = fetch_nasa_power(lat, lon, year, CACHE_DIR)
            if nasa_data is None:
                print(f"  Failed to fetch NASA data")
                continue

        nasa = nasa_json_to_df(nasa_data)
        print(f"  NASA records: {len(nasa)}")

        # Merge - World Bank CSV is UTC = local time for Ghana (UTC+0)
        # NASA POWER is Local Solar Time
        merged = nasa.join(measured.rename(columns={'ghi': 'ghi_ground', 'dni': 'dni_ground', 'dhi': 'dhi_ground'}),
                          how='inner')
        merged = merged.dropna(subset=['ghi_ground'])

        # Add metadata
        merged['station'] = f"{file_prefix}_tier1"
        merged['latitude'] = lat
        merged['longitude'] = lon
        merged['country'] = country
        merged['station_name'] = name

        # Compute ratio
        merged['ratio'] = merged['ghi_ground'] / np.maximum(merged['ghi_satellite'], 10.0)
        # Preserve timestamp as column
        merged['timestamp'] = merged.index
        day_mask = merged['ghi_satellite'] > 50
        if day_mask.sum() > 0:
            mean_ratio = merged.loc[day_mask, 'ratio'].mean()
            print(f"  Merged records: {len(merged)}, Daytime ratio: {mean_ratio:.3f}")

        records.append(merged)

    return pd.concat(records, ignore_index=True) if records else pd.DataFrame()


def filter_broken_stations(df, min_ratio=0.3, max_ratio=2.5):
    """Remove stations with corrupted ground data."""
    print("\n=== Station quality filter ===")
    keep_stations = []

    for station, group in df.groupby('station'):
        day_mask = group['ghi_satellite'] > 50
        if day_mask.sum() < 100:
            print(f"  EXCLUDE {station}: too few daytime records ({day_mask.sum()})")
            continue

        ratio = group.loc[day_mask, 'ratio'].values
        mean_ratio = np.mean(ratio)
        std_ratio = np.std(ratio)
        n_below = (ratio < min_ratio).sum()
        n_above = (ratio > max_ratio).sum()
        pct_bad = (n_below + n_above) / len(ratio) * 100

        if mean_ratio < min_ratio or mean_ratio > max_ratio:
            print(f"  EXCLUDE {station}: mean ratio={mean_ratio:.3f} (outside {min_ratio}-{max_ratio})")
            continue

        if pct_bad > 20:
            print(f"  EXCLUDE {station}: {pct_bad:.1f}% extreme ratios (mean={mean_ratio:.3f})")
            continue

        print(f"  KEEP    {station}: ratio={mean_ratio:.3f}±{std_ratio:.3f}, extreme={pct_bad:.1f}%")
        keep_stations.append(station)

    return df[df['station'].isin(keep_stations)].copy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-fetch', action='store_true', help='Use cached NASA data')
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # Step 1: Load ZINDI ground data
    print("=" * 65)
    print("STEP 1: Loading ZINDI ground truth data")
    print("=" * 65)
    zindi_records = load_zindi_ground()
    print(f"Loaded {len(zindi_records)} stations")

    # Step 2: Fetch NASA POWER and merge for ZINDI stations
    print("\n" + "=" * 65)
    print("STEP 2: Fetching NASA POWER data for ZINDI stations")
    print("=" * 65)
    zindi_df = build_zindi_nasa_power(zindi_records, skip_fetch=args.skip_fetch)

    # Step 3: Build validation data (Navrongo + Sunyani)
    print("\n" + "=" * 65)
    print("STEP 3: Building validation data (Navrongo + Sunyani)")
    print("=" * 65)
    val_df = build_validation_data(skip_fetch=args.skip_fetch)

    # Step 4: Combine
    print("\n" + "=" * 65)
    print("STEP 4: Combining datasets")
    print("=" * 65)
    # Ensure timestamp is a column (not just index) before concat
    for df_part in [zindi_df, val_df]:
        if df_part is not None and not df_part.empty:
            if 'timestamp' not in df_part.columns:
                df_part['timestamp'] = df_part.index
    combined = pd.concat([zindi_df, val_df], ignore_index=True)
    print(f"Combined: {len(combined):,} records, {combined['station'].nunique()} stations")

    # Step 5: Filter broken stations
    print("\n" + "=" * 65)
    print("STEP 5: Filtering broken stations")
    print("=" * 65)
    clean = filter_broken_stations(combined)
    print(f"\nClean dataset: {len(clean):,} records, {clean['station'].nunique()} stations")

    # Step 6: Save
    print("\n" + "=" * 65)
    print("STEP 6: Saving clean training data")
    print("=" * 65)
    output_path = os.path.join(OUTPUT_DIR, "training_clean.parquet")
    clean.to_parquet(output_path, index=False)
    print(f"Saved to {output_path}")

    # Summary stats
    print("\n" + "=" * 65)
    print("SUMMARY")
    print("=" * 65)
    for station in sorted(clean['station'].unique()):
        s = clean[clean['station'] == station]
        day_mask = s['ghi_satellite'] > 50
        if day_mask.sum() > 0:
            ratio = s.loc[day_mask, 'ratio'].mean()
        else:
            ratio = s['ratio'].mean()
        print(f"  {station:>20}: {len(s):>6} records, ratio={ratio:.3f}")

    # Also save metadata
    meta = {
        'total_records': len(clean),
        'total_stations': clean['station'].nunique(),
        'stations': {}
    }
    for station in clean['station'].unique():
        s = clean[clean['station'] == station]
        meta['stations'][station] = {
            'latitude': float(s['latitude'].iloc[0]),
            'longitude': float(s['longitude'].iloc[0]),
            'country': str(s['country'].iloc[0]),
            'records': len(s),
            'is_validation': '_tier1' in station,
        }
    meta_path = os.path.join(OUTPUT_DIR, "training_clean_meta.json")
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)
    print(f"Metadata saved to {meta_path}")


if __name__ == '__main__':
    main()
