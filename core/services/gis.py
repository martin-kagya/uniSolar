import rasterio
import numpy as np
import os
import logging
from shapely.geometry import Point, LineString
from shapely.ops import nearest_points

logger = logging.getLogger(__name__)

# Comprehensive West Africa Coastline (approximate LineString from Senegal to Nigeria)
WEST_AFRICA_COASTLINE_COORDS = [
    (-17.51, 14.72), # Dakar, Senegal
    (-16.63, 13.45), # Banjul, Gambia
    (-15.60, 11.85), # Guinea-Bissau
    (-13.23, 9.48),  # Conakry, Guinea
    (-11.69, 7.30),  # Sierra Leone / Liberia border
    (-10.80, 6.31),  # Monrovia, Liberia
    (-7.72, 4.38),   # Cape Palmas, Liberia
    (-4.03, 5.33),   # Abidjan, Côte d'Ivoire
    (-2.98, 5.08),   # Western Border, Ghana
    (-2.24, 4.87),   # Axim, Ghana
    (-1.25, 5.10),   # Cape Coast, Ghana
    (0.20, 5.60),    # Accra, Ghana
    (1.10, 6.13),    # Aflao, Ghana
    (1.24, 6.12),    # Lomé, Togo
    (2.43, 6.35),    # Cotonou, Benin
    (3.40, 6.45),    # Lagos, Nigeria
    (7.00, 4.40),    # Port Harcourt, Nigeria
    (8.50, 4.00)     # Cross River, Nigeria border
]

class GISService:
    def __init__(self, dem_path='data/ghana_dem.tif'):
        self.dem_path = dem_path
        self.dem_dataset = None
        self.coastline = LineString(WEST_AFRICA_COASTLINE_COORDS)
        
        self._load_dem()

    def _load_dem(self):
        """Loads the Digital Elevation Model if available."""
        if os.path.exists(self.dem_path):
            try:
                self.dem_dataset = rasterio.open(self.dem_path)
                logger.info(f"Loaded DEM from {self.dem_path}")
            except Exception as e:
                logger.error(f"Failed to load DEM: {e}")
        else:
            logger.warning(f"DEM file not found at {self.dem_path}. Elevation lookups will be unavailable.")

    def get_elevation(self, lat, lon):
        """
        Returns elevation in meters at the given coordinate.
        Returns None if DEM is not loaded or out of bounds.
        """
        if not self.dem_dataset:
            return None

        try:
            # Sample the raster
            # index() returns (row, col)
            row, col = self.dem_dataset.index(lon, lat)
            
            # Read the value
            # Note: read(1) reads the first band
            data = self.dem_dataset.read(1, window=((row, row+1), (col, col+1)))
            
            if data.size > 0:
                val = data[0][0]
                # Check for nodata
                if val == self.dem_dataset.nodata:
                    return None
                return float(val)
        except Exception as e:
            logger.debug(f"Error reading elevation for {lat}, {lon}: {e}")
        
        return None

    def get_distance_to_coast(self, lat, lon):
        """
        Calculates distance to the coast in km.
        Uses a simplified vector geometry for now.
        """
        point = Point(lon, lat)
        
        # Calculate minimum distance from point to the coastline string
        dist_degrees = self.coastline.distance(point)
        dist_km = dist_degrees * 111.0
        
        return dist_km

    def get_climate_zone(self, lat, lon, elevation=None):
        """
        Determines climate zone based on lat/lon and optional elevation.
        Returns: 0 (Coastal), 1 (Forest), 2 (Savanna)
        
        Improved logic from the original hardcoded if/else.
        """
        # 1. Coastal Strip
        dist_km = self.get_distance_to_coast(lat, lon)
        if dist_km < 30: # Within 30km of coast
            return 0
            
        # 2. Savanna (North)
        # Generally North of Latitude 8.0, but excluding high mountains if we had better data
        if lat > 8.0:
            return 2
            
        # 3. Forest (Middle)
        return 1

    def close(self):
        if self.dem_dataset:
            self.dem_dataset.close()
