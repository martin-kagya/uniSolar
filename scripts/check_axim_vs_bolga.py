import pandas as pd
from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer

def compare_potential():
    engine = init_db()
    session = get_session(engine)
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    l2 = EnvironmentalLayer()

    for loc_id, name in [(2, 'Bolgatanga'), (7, 'Axim')]:
        loc = session.query(Location).get(loc_id)
        query = session.query(WeatherData).filter_by(location_id=loc_id)
        df = pd.DataFrame([d.__dict__ for d in query.all()])
        df['latitude'] = loc.latitude
        df['longitude'] = loc.longitude
        df['pm25'] = df['pm25'].astype(float)
        df['albedo'] = 0.2
        
        df_l1 = l1.predict(df)
        df_l2 = l2.process(df_l1)
        
        # Operational Yield (With Soiling)
        operational_ghi_avg = (df_l1['ghi_corrected'] * (1 - df_l2['soiling_loss'])).mean()
        # Theoretical Yield (Clean)
        theoretical_ghi_avg = df_l1['ghi_corrected'].mean()
        
        print(f"\n{name}:")
        print(f"  Theoretical GHI Potential: {theoretical_ghi_avg * 8.76:.1f} kWh/m2/year")
        print(f"  Operational GHI Available: {operational_ghi_avg * 8.76:.1f} kWh/m2/year")
        print(f"  Soiling " + '"Tax"' + f": {1 - (operational_ghi_avg/theoretical_ghi_avg):.1%}")

if __name__ == "__main__":
    compare_potential()
