from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from core.database import init_db, get_session, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer
from core.layers.geometry_model import GeometryLayer
from data.ingest_nasa import fetch_nasa_data, process_and_store
from datetime import datetime
import pandas as pd
import numpy as np
import pvlib
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="UniSolar API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Templates
templates = Jinja2Templates(directory="static")

# Initialize Layers
weather_layer = WeatherCorrectionLayer()
env_layer = EnvironmentalLayer()
physics_layer = PhysicsLayer()
geo_layer = GeometryLayer()

# Database
engine = init_db()

class Panel(BaseModel):
    id: str
    x: float
    y: float
    rotation: float = 0.0

class RoofFeature(BaseModel):
    type: str # 'chimney', 'vent'
    x: float
    y: float
    width: float
    height: float
    depth: float = 0.0

class SimulationRequest(BaseModel):
    latitude: float
    longitude: float
    capacity_kw: float = 5.0
    tilt: float = 10.0
    azimuth: float = 180.0
    module_name: str = None
    year: int = 2023
    panels: list[Panel] = []
    features: list[RoofFeature] = []
    electricity_rate: float = 0.25

class SizingRequest(BaseModel):
    latitude: float
    longitude: float
    monthly_consumption_kwh: float = None
    monthly_bill_ghs: float = None
    electricity_rate: float = 1.90

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "")
    })

@app.post("/simulate")
def run_simulation(req: SimulationRequest):
    session = get_session(engine)
    try:
        # 1. Resolve Location
        loc = session.query(Location).filter_by(latitude=req.latitude, longitude=req.longitude).first()
        
        # 2. Ensure Data Exists
        # If no location, create it
        if not loc:
            loc = Location(name=f"Auto_{req.latitude},{req.longitude}", latitude=req.latitude, longitude=req.longitude)
            session.add(loc)
            session.commit()
            
        # Check if we have data for the requested year
        df = weather_layer.load_data(session, location_id=loc.id, require_ground_truth=False)
        if not df.empty:
            df['year'] = pd.to_datetime(df['timestamp']).dt.year
            df = df[df['year'] == req.year]
        
        if df.empty:
            # Fetch and ingest
            print(f"Data missing for {req.latitude}, {req.longitude}, fetching from NASA...")
            raw = fetch_nasa_data(req.latitude, req.longitude, req.year)
            if not raw:
                raise HTTPException(status_code=502, detail="NASA API failed")
            process_and_store(session, loc.id, raw, req.year)
            
            # Re-load with new data
            df = weather_layer.load_data(session, location_id=loc.id, require_ground_truth=False)
            df['year'] = pd.to_datetime(df['timestamp']).dt.year
            df = df[df['year'] == req.year]

        # 3. Layer 1: Weather Correction
        # Run ML Prediction
        df_l1 = weather_layer.predict(df)
        
        # 4. Layer 2: Environmantal Loss
        df_l2 = env_layer.process(df_l1)
        
        # Ensure DatetimeIndex for PVLib
        if 'timestamp' in df_l2.columns:
            df_l2['timestamp'] = pd.to_datetime(df_l2['timestamp'])
            df_l2.set_index('timestamp', inplace=True)
        
        # 5. Layer 0: Spatial (Obstacle Shading)
        # Calculate sun position for the simulation period
        location = pvlib.location.Location(latitude=req.latitude, longitude=req.longitude)
        solar_pos = location.get_solarposition(df_l2.index)
        
        # Calculate shading penalty from obstacles
        panels_dict = [p.dict() for p in req.panels]
        features_dict = [f.dict() for f in req.features]
        shading_penalty = geo_layer.calculate_obstacle_shading(
            solar_pos['zenith'], solar_pos['azimuth'], 
            panels_dict, features_dict
        )
        
        # 6. Layer 3: Physics
        result = physics_layer.simulate(
            df_l2, 
            req.latitude, 
            req.longitude, 
            req.capacity_kw, 
            req.tilt, 
            req.azimuth,
            module_name=req.module_name,
            shading_penalty=shading_penalty
        )
        
        # 6. Layer 4: Financials
        from core.layers.financial_model import FinancialLayer
        fin_layer = FinancialLayer(electricity_tariff=req.electricity_rate)
        financials = fin_layer.calculate_roi(result['annual_energy_kwh'], req.capacity_kw)
        
        # 7. Prepare Hourly Power Curve (Daily average or specific day)
        # We'll send back the average daily curve for each month
        series = result['ac_series']
        hourly_curves = series.groupby(series.index.hour).mean().tolist()
        
        # CLEANUP: Remove non-serializable Pandas objects
        if 'ac_series' in result:
             del result['ac_series']

        return {
            "status": "success",
            "config": req.dict(),
            "results": result,
            "financials": financials,
            "hourly_curve": hourly_curves
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

@app.post("/report")
def generate_report(data: dict):
    from io import BytesIO
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas
    from fastapi.responses import StreamingResponse
    import datetime

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=LETTER)
    width, height = LETTER

    # Header
    p.setFillColorRGB(0.96, 0.62, 0.04) # Amber-500
    p.rect(0, height-80, width, 80, fill=1)
    p.setFillColorRGB(1, 1, 1)
    p.setFont("Helvetica-Bold", 24)
    p.drawString(50, height - 50, "UniSolar Design Proposal")
    
    p.setFont("Helvetica", 10)
    p.drawRightString(width - 50, height - 50, f"Generated: {datetime.date.today().strftime('%B %d, %Y')}")

    # Content Area
    p.setFillColorRGB(0, 0, 0)
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 120, "SYSTEM PERFORMANCE SUMMARY")
    
    p.setFont("Helvetica", 12)
    res = data.get('results', {})
    fin = data.get('financials', {})
    config = data.get('config', {})
    
    y = height - 150
    p.drawString(50, y, f"Project Location: {config.get('latitude')}, {config.get('longitude')}")
    p.drawString(50, y-20, f"Total System Size: {config.get('capacity_kw', 0):.2f} kWp")
    p.drawString(50, y-40, f"Annual Energy Production: {round(res.get('annual_energy_kwh', 0)):,} kWh/yr")
    
    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, y-80, "FINANCIAL KPI ANALYSIS")
    
    p.setFont("Helvetica", 12)
    p.drawString(50, y-110, f"Net Present Value (NPV): GH₵ {round(fin.get('npv', 0)):,}")
    p.drawString(50, y-130, f"Payback Period: {fin.get('payback_years', 'N/A')} years")
    p.drawString(50, y-150, f"LCOE: GH₵ {fin.get('lcoe', 0):.3f} / kWh")

    p.setFont("Helvetica-Oblique", 8)
    p.drawCentredString(width/2, 30, "Report generated via UniSolar Solar-Light Dashboard. Scientific data powered by NASA & PVLib.")

    p.showPage()
    p.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type='application/pdf', headers={
        "Content-Disposition": f"attachment; filename=UniSolar_Report_{datetime.date.today().isoformat()}.pdf"
    })


@app.post("/export-csv")
def export_csv(data: dict):
    import csv
    from io import StringIO
    from fastapi.responses import StreamingResponse

    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(["UniSolar Professional Yield Report"])
    writer.writerow(["Generated At", datetime.now().isoformat()])
    writer.writerow(["Location", f"{data.get('config', {}).get('latitude')}, {data.get('config', {}).get('longitude')}"])
    writer.writerow(["System Capacity", f"{data.get('config', {}).get('capacity_kw')} kWp"])
    writer.writerow(["Total Annual Energy", f"{round(data.get('results', {}).get('annual_energy_kwh', 0), 2)} kWh"])
    writer.writerow([])
    writer.writerow(["Date", "Time", "Power Output (kW)"])
    
    # Extract full hourly data
    results = data.get('results', {})
    ac_list = results.get('ac_list', []) # Values in Watts
    timestamps = results.get('timestamps', []) # Strings 'YYYY-MM-DD HH:MM'
    
    if not ac_list or not timestamps:
        # Fallback to hourly curve if full data missing (should not happen in proper sim)
        hourly = data.get('hourly_curve', [])
        for i, val in enumerate(hourly):
             writer.writerow([f"Typical Day", f"{i}:00", round(val / 1000.0, 4)])
    else:
        # Write 8760 rows
        for ts, power_w in zip(timestamps, ac_list):
            try:
                date_part, time_part = ts.split(' ')
            except:
                date_part, time_part = ts, ""
                
            power_kw = power_w / 1000.0
            writer.writerow([date_part, time_part, round(power_kw, 4)])
        
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=UniSolar_Professional_Export.csv"}
    )


@app.get("/modules")
def get_modules():
    return [
        {"id": "jinko_420", "name": "Jinko 420W", "power_wp": 420, "width_m": 1.134, "length_m": 1.722},
        {"id": "canadian_440", "name": "Canadian 440W", "power_wp": 440, "width_m": 1.134, "length_m": 1.762},
        {"id": "trina_700", "name": "Trina 700W", "power_wp": 700, "width_m": 1.303, "length_m": 2.384}
    ]


@app.post("/size-system")
def size_system(req: SizingRequest):
    # Determine Monthly kWh
    monthly_kwh = req.monthly_consumption_kwh
    if monthly_kwh is None and req.monthly_bill_ghs is not None:
        monthly_kwh = req.monthly_bill_ghs / req.electricity_rate
    
    if not monthly_kwh:
        raise HTTPException(status_code=400, detail="Must provide consumption or bill")

    daily_kwh = monthly_kwh / 30.0
    
    # Scientific Sizing: Pdc = E_daily / (PSH * PR)
    psh = 4.8 
    pr = 0.78 # Conservative PR for Ghana
    
    required_kwp = daily_kwh / (psh * pr)
    
    # Return recommendations for common panel sizes (using hardcoded db for now)
    panel_types = get_modules()
    
    recommendations = []
    for p in panel_types:
        count = int(np.ceil((required_kwp * 1000) / p['power_wp']))
        recommendations.append({
            "panel": p['name'],
            "count": count,
            "total_kwp": (count * p['power_wp']) / 1000.0
        })
        
    return {
        "status": "success",
        "monthly_kwh": monthly_kwh,
        "daily_kwh": daily_kwh,
        "required_kwp": round(required_kwp, 2),
        "psh_used": psh,
        "pr_used": pr,
        "recommendations": recommendations,
        "suggested_inverter_kw": round(required_kwp * 1.1, 1) # 1.1 DC/AC ratio
    }

# Mount static files (HTML=False so we serve index via template)
app.mount("/", StaticFiles(directory="static", html=False), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
