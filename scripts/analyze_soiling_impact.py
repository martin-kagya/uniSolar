from core.database import init_db, get_session, WeatherData
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
import pandas as pd

def analyze_soiling():
    engine = init_db()
    session = get_session(engine)
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    l2 = EnvironmentalLayer()

    for loc_id in [1, 2]:
        name = "Accra" if loc_id == 1 else "Bolgatanga"
        query = session.query(WeatherData).filter_by(location_id=loc_id)
        df = pd.DataFrame([d.__dict__ for d in query.all()])
        df_l1 = l1.predict(df)
        df_l2 = l2.process(df_l1)
        
        avg_soiling = df_l2['soiling_loss'].mean()
        max_soiling = df_l2['soiling_loss'].max()
        
        print(f"{name} (Loc {loc_id}):")
        print(f"  Avg Soiling Loss: {avg_soiling:.2%}")
        print(f"  Max Soiling Loss: {max_soiling:.2%}")

if __name__ == "__main__":
    analyze_soiling()
