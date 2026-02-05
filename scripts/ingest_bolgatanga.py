"""
Ingest Bolgatanga Solcast Data
Loads high-fidelity ground truth data for Bolgatanga (Northern Ghana)
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.ingest_solcast import ingest_solcast

if __name__ == "__main__":
    # Bolgatanga coordinates from database
    LAT = 10.7881
    LON = -0.8367
    CSV_PATH = "data/bolga_solcast.csv"
    
    print("=" * 70)
    print("INGESTING BOLGATANGA SOLCAST DATA")
    print("=" * 70)
    print(f"Location: Bolgatanga (Northern Ghana)")
    print(f"Coordinates: {LAT}°N, {LON}°E")
    print(f"Source: {CSV_PATH}")
    print("=" * 70)
    
    ingest_solcast(CSV_PATH, LAT, LON)
    
    print("\n" + "=" * 70)
    print("INGESTION COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Run: python scripts/check_solcast_coverage.py")
    print("2. Train multi-location model: python scripts/train_layer1.py")
