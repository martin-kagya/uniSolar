from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class Location(Base):
    __tablename__ = 'locations'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation = Column(Float, nullable=True) # Can be manually set or from GIS
    
    # GIS Derived Properties (Cached)
    dist_to_coast_km = Column(Float, nullable=True)
    climate_zone = Column(Integer, nullable=True) # 0: Coastal, 1: Forest, 2: Savanna
    
    country = Column(String, default="Ghana")
    
    weather_data = relationship("WeatherData", back_populates="location")

class WeatherData(Base):
    __tablename__ = 'weather_data'
    
    id = Column(Integer, primary_key=True)
    location_id = Column(Integer, ForeignKey('locations.id'), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    
    # Satellite Data (The "Fuel" for ML)
    ghi_satellite = Column(Float) # Global Horizontal Irradiance
    dni_satellite = Column(Float) # Direct Normal Irradiance
    dhi_satellite = Column(Float) # Diffuse Horizontal Irradiance
    
    # Environmental Features
    temp_air = Column(Float)
    relative_humidity = Column(Float)
    wind_speed = Column(Float)
    precipitable_water = Column(Float)
    rain_mm = Column(Float, nullable=True) # Rainfall (PRECTOTCORR)
    aod_550 = Column(Float) # Aerosol Optical Depth (Critical for Harmattan)
    
    # Solcast Specific Features
    pm25 = Column(Float, nullable=True) # Particulate Matter 2.5
    pm10 = Column(Float, nullable=True) # Particulate Matter 10
    albedo = Column(Float, nullable=True) # Surface Albedo
    
    # Ground Truth (The "Target" for ML - sparse)
    ghi_ground = Column(Float, nullable=True)
    dni_ground = Column(Float, nullable=True)
    gti = Column(Float, nullable=True) # Solcast Global Tilted Irradiance (Reference)
    
    location = relationship("Location", back_populates="weather_data")

    # Composite index for fast lookups
    __table_args__ = (
        Index('idx_location_time', 'location_id', 'timestamp', unique=True),
    )

class SimulationRun(Base):
    __tablename__ = 'simulation_runs'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    location_id = Column(Integer, ForeignKey('locations.id'))
    
    # Configuration Snapshot
    system_capacity_kw = Column(Float)
    module_model = Column(String)
    inverter_model = Column(String)
    
    # Results
    annual_energy_kwh = Column(Float)
    performance_ratio = Column(Float)
    
    # JSON blob for detailed monthly/daily results if needed
    detailed_results_json = Column(String, nullable=True)

# Database Setup
def init_db(db_path='solar_platform.db'):
    # Use absolute path if relative path is provided
    if not os.path.isabs(db_path):
        # Get the project root directory (parent of 'core')
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        db_path = os.path.join(project_root, db_path)
    
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    return engine

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()
