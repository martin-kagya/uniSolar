from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from core.database import init_db, get_session, Location, Design
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer
from core.layers.geometry_model import GeometryLayer
from core.layers.uncertainty_model import UncertaintyLayer
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
uncertainty_layer = UncertaintyLayer()

# Database
engine = init_db()

class Panel(BaseModel):
    id: str
    x: float
    y: float
    rotation: float = 0.0

class CustomModule(BaseModel):
    name: str
    power_wp: float
    width_m: float
    length_m: float
    # Performance
    efficiency_pct: float | None = None        # Module efficiency (%)
    performance_ratio: float | None = None     # System PR (%)
    temp_coeff_pmax: float | None = None       # Temp coefficient of Pmax (%/°C)
    temp_coeff_voc: float | None = None        # Temp coefficient of Voc (%/°C)
    noct: float | None = None                  # Nominal Operating Cell Temp (°C)
    # Electrical (STC)
    voc: float | None = None                   # Open circuit voltage (V)
    isc: float | None = None                   # Short circuit current (A)
    vmp: float | None = None                   # Voltage at max power (V)
    imp: float | None = None                   # Current at max power (A)
    num_cells: int | None = None               # Number of cells
    # Build / warranty
    cell_technology: str | None = None         # e.g. Mono-PERC, Bifacial, HJT
    warranty_years: int | None = None          # Product / power warranty (years)
    # Battery
    battery_brand: str | None = None
    battery_capacity_kwh: float | None = None
    battery_voltage: float | None = None       # Nominal battery voltage (V)
    battery_chemistry: str | None = None       # e.g. LiFePO4, Lead-Acid
    # Inverter
    inverter_brand: str | None = None
    inverter_kw: float | None = None
    inverter_efficiency_pct: float | None = None  # Peak inverter efficiency (%)

# In-memory store for user-added modules (per server session)
custom_modules: list[dict] = []

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
    gcr: float = 0.40
    module_name: str = None
    inverter_name: str = None
    year: int = 2023
    panels: list[Panel] = []
    features: list[RoofFeature] = []
    electricity_rate: float = 0.25
    irradiance_bias: float = 1.0
    soiling_rate: float = 0.05
    system_cost_kw: float = 20000.0
    om_cost_kw: float = 320.0
    
    # Advanced Physics Derates
    mounting_type: str = 'open_rack'
    wiring_loss: float = 0.02
    lid_loss: float = 0.02
    mismatch_loss: float = 0.02
    inverter_efficiency: float = 0.96
    
    # Financial Dynamics
    tariff_escalation: float = 0.03
    om_escalation: float = 0.02
    degradation_rate: float = 0.005
    lid_rate: float = 0.02
    
    # Debt / Equity Structure
    debt_ratio: float = 0.65
    interest_rate: float = 0.12
    loan_term_years: int = 10

    # ECG Tariff Settings
    use_ecg_tariff: bool = True
    customer_type: str = "residential"

class SizingRequest(BaseModel):
    latitude: float
    longitude: float
    monthly_consumption_kwh: float = None
    monthly_bill_ghs: float = None
    electricity_rate: float = 1.90
    customer_type: str = "residential"  # 'residential' or 'non_residential'

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "")
    })

@app.get("/dashboard", response_class=HTMLResponse)
async def read_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "")
    })

def _safe_pm_mean(df, col):
    """Return mean PM value only if data is real (non-defaulted); None otherwise."""
    if col not in df.columns:
        return None
    vals = df[col].dropna()
    if len(vals) == 0:
        return None
    mean_val = float(vals.mean())
    # NASA POWER doesn't provide PM data; _build_features defaults pm25 to 25.0 then fillna(0.0)
    # A real measurement would have variance; a flat 0.0 or exactly 25.0 means defaulted
    if mean_val == 0.0:
        return None
    return mean_val

def _count_rain_events(df):
    """Count distinct rain events (consecutive hours with rain > 0.5mm = 1 event), return monthly rate."""
    if 'rain_mm' not in df.columns:
        return 0.0
    rain = df['rain_mm'].dropna()
    if len(rain) == 0:
        return 0.0
    is_raining = (rain > 0.5).astype(int)
    # Count transitions: an event starts when is_raining goes from 0→1
    transitions = is_raining.diff().fillna(0)
    event_starts = (transitions == 1).sum()
    # Also count if the first hour is raining (that's an event start)
    if is_raining.iloc[0] == 1:
        event_starts += 1
    total_events = max(int(event_starts), 0)
    # Determine time span in months from the index
    if hasattr(df.index, 'to_series'):
        try:
            span = (df.index.max() - df.index.min())
            months = max(span.days / 30.44, 1.0)
        except Exception:
            months = 12.0
    else:
        months = 12.0
    return round(total_events / months, 1)

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
        df_l2 = env_layer.process(df_l1, climate_zone=loc.climate_zone if loc else None)
        
        # Apply Soiling Rate Tuning
        if req.soiling_rate != 0.05:
            df_l2['soiling_loss'] *= (req.soiling_rate / 0.05)
        
        # Ensure DatetimeIndex for PVLib
        if 'timestamp' in df_l2.columns:
            df_l2['timestamp'] = pd.to_datetime(df_l2['timestamp'])
            df_l2.set_index('timestamp', inplace=True)
        
        # 5. Layer 0: Spatial (Obstacle Shading)
        # Calculate sun position for the simulation period
        location = pvlib.location.Location(latitude=req.latitude, longitude=req.longitude)
        solar_pos = location.get_solarposition(df_l2.index)
        
        # Calculate shading penalty from obstacles
        from core.layers.geometry_model import GeometryLayer
        geom_layer = GeometryLayer()
        shading_series = geom_layer.calculate_obstacle_shading(
            solar_pos['zenith'], solar_pos['azimuth'], 
            [p.dict() for p in req.panels], 
            [f.dict() for f in req.features]
        )
        # Apply Tuning Bias to Irradiance
        if req.irradiance_bias != 1.0:
            if 'ghi_corrected' in df_l2.columns:
                df_l2['ghi_corrected'] *= req.irradiance_bias
            if 'dni_corrected' in df_l2.columns:
                df_l2['dni_corrected'] *= req.irradiance_bias
            if 'dhi_corrected' in df_l2.columns:
                df_l2['dhi_corrected'] *= req.irradiance_bias
            elif 'dhi_satellite' in df_l2.columns:
                df_l2['dhi_satellite'] *= req.irradiance_bias

        # 6. Layer 3: Physics
        # Align shading_series index with df_l2 for element-wise multiplication
        shading_aligned = shading_series.reindex(df_l2.index, method='ffill').fillna(0.0)
        result = physics_layer.simulate(
            df_l2, 
            req.latitude, 
            req.longitude, 
            req.capacity_kw, 
            req.tilt, 
            req.azimuth,
            gcr=req.gcr,
            module_name=req.module_name,
            inverter_name=req.inverter_name,
            shading_penalty=shading_aligned,
            mounting_type=req.mounting_type,
            wiring_loss=req.wiring_loss,
            lid_loss=req.lid_loss,
            mismatch_loss=req.mismatch_loss,
            inverter_efficiency=req.inverter_efficiency
        )
        
        # 7. Layer 4: Financials
        from core.layers.financial_model import FinancialLayer
        fin_layer = FinancialLayer(
            electricity_tariff=req.electricity_rate,
            system_cost_per_kw=req.system_cost_kw,
            annual_om_cost=req.om_cost_kw,
            tariff_escalation_rate=req.tariff_escalation,
            om_escalation_rate=req.om_escalation,
            degradation_rate=req.degradation_rate,
            lid_rate=req.lid_rate,
            debt_ratio=req.debt_ratio,
            interest_rate=req.interest_rate,
            loan_term_years=req.loan_term_years,
            use_ecg_tariff=req.use_ecg_tariff,
            customer_type=req.customer_type,
        )
        financials = fin_layer.calculate_roi(result['annual_energy_kwh'], req.capacity_kw)
        
        # 8. Monte Carlo Layer (Probabilistic Yield + Financial Risk Analysis)
        # 1,000 runs to determine P50/P90 yield AND NPV risk metrics.
        # Uncertainties model real-world variance in the West African context.
        mc_iterations = 1000
        # ML-B: calibrated resource+model uncertainty (interannual variability combined
        # in quadrature with the validated systematic model uncertainty) replaces the
        # old hand-set 5%. See core/layers/uncertainty_model.py / uncertainty_calib.json.
        energy_px = uncertainty_layer.energy_percentiles(result['annual_energy_kwh'])
        # Yield uncertainties
        irradiance_std = energy_px['breakdown']['total_cov']  # calibrated (was hard-coded 0.05)
        soiling_std = 0.12      # 12% uncertainty in Harmattan deposition rates
        hardware_std = 0.03     # 3% tolerance in manufacturer specs/wiring
        # Financial / operational uncertainties
        tariff_std = 0.15       # 15% — ECG tariffs are politically regulated, can jump
        degradation_std = 0.002 # ±0.2% absolute on the 0.5%/yr assumption
        grid_std = 0.05         # 5% — Ghana grid outages reduce export/consumption
        
        base_yield = result['annual_energy_kwh']
        stochastic_yields = []
        stochastic_npvs = []
        
        for _ in range(mc_iterations):
            # Yield uncertainties (multiplicative on energy)
            s_irrad = np.random.normal(1.0, irradiance_std)
            s_soil = np.random.normal(1.0, soiling_std)
            s_hard = np.random.normal(1.0, hardware_std)
            s_grid = np.random.normal(1.0, grid_std)
            
            s_yield = base_yield * s_irrad * s_soil * s_hard * s_grid
            stochastic_yields.append(s_yield)
            
            # Financial uncertainty: perturb tariff escalation + degradation
            s_tariff_esc = np.random.normal(req.tariff_escalation, tariff_std * req.tariff_escalation)
            s_deg = max(0, req.degradation_rate + np.random.normal(0, degradation_std))
            
            fin_stochastic = FinancialLayer(
                electricity_tariff=req.electricity_rate,
                system_cost_per_kw=req.system_cost_kw,
                annual_om_cost=req.om_cost_kw,
                tariff_escalation_rate=s_tariff_esc,
                om_escalation_rate=req.om_escalation,
                degradation_rate=s_deg,
                lid_rate=req.lid_rate,
                debt_ratio=req.debt_ratio,
                interest_rate=req.interest_rate,
                loan_term_years=req.loan_term_years,
                use_ecg_tariff=req.use_ecg_tariff,
                customer_type=req.customer_type,
            )
            s_financials = fin_stochastic.calculate_roi(s_yield, req.capacity_kw)
            stochastic_npvs.append(s_financials['npv'])
            
        # Probabilistic Metrics
        p50_yield = float(np.percentile(stochastic_yields, 50))
        p90_yield = float(np.percentile(stochastic_yields, 10))
        p50_npv = float(np.percentile(stochastic_npvs, 50))
        p90_npv = float(np.percentile(stochastic_npvs, 10))
        
        # Build Distribution Histogram for UI
        hist_counts, hist_bins = np.histogram(stochastic_yields, bins=25)
        prob_distribution = [
            {"bin": float((hist_bins[i] + hist_bins[i+1]) / 2), "count": int(hist_counts[i])}
            for i in range(len(hist_counts))
        ]

        # 9. Prepare Hourly Power Curve
        series = result['ac_series']
        hourly_curves = series.groupby(series.index.hour).mean().tolist()

        # CLEANUP: Remove non-serializable Pandas objects
        if 'ac_series' in result:
             del result['ac_series']

        # Helper to recursively clean NaN/Inf values
        def sanitize_json(obj):
            if isinstance(obj, dict):
                return {k: sanitize_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [sanitize_json(x) for x in obj]
            elif isinstance(obj, float):
                if not np.isfinite(obj): return 0.0
                return obj
            return obj

        return sanitize_json({
            "status": "success",
            "config": req.dict(),
            "results": result,
            "financials": financials,
            "loss_params": {
                "degradation_rate_pct": req.degradation_rate * 100,
                "lid_rate_pct": req.lid_rate * 100,
                "soiling_rate_pct": req.soiling_rate * 100,
                "wiring_loss_pct": req.wiring_loss * 100,
                "lid_loss_pct": req.lid_loss * 100,
                "mismatch_loss_pct": req.mismatch_loss * 100,
                "inverter_efficiency_pct": req.inverter_efficiency * 100,
                "actual_inverter_efficiency_pct": result.get('actual_inverter_efficiency', req.inverter_efficiency) * 100,
                "irradiance_bias": req.irradiance_bias,
                "gcr": req.gcr,
            },
            "hourly_curve": hourly_curves,
            "probabilistic_results": {
                "p50_yield": p50_yield,
                "p90_yield": p90_yield,
                "p50_npv": p50_npv,
                "p90_npv": p90_npv,
                "distribution": prob_distribution,
                # ML-B calibrated analytic energy percentiles (bankable, auditable)
                "energy_p50_kwh": energy_px["p50"],
                "energy_p90_kwh": energy_px["p90"],
                "energy_p99_kwh": energy_px["p99"],
                "uncertainty_breakdown": energy_px["breakdown"],
                "p90_calibration": (uncertainty_layer.calib or {}).get("hourly_coverage"),
            },
            "environmental_metrics": {
                "mean_pm25": _safe_pm_mean(df_l2, 'pm25'),
                "mean_pm10": _safe_pm_mean(df_l2, 'pm10'),
                "mean_cleaning_events_monthly": _count_rain_events(df_l2),
                "pm_data_available": False  # NASA POWER does not provide PM2.5/PM10
            }
        })

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


BUILTIN_MODULES = [
    {
        "id": "jinko_420_residential",
        "name": "Jinko Tiger Pro 420W (Residential bundle)",
        "power_wp": 420,
        "width_m": 1.134,
        "length_m": 1.722,
        "efficiency_pct": 21.0,
        "performance_ratio": 78.5,
        "cell_technology": "Mono-PERC",
        "battery_brand": "Pylontech US3000C",
        "battery_capacity_kwh": 3.5,
        "inverter_brand": "Fronius Primo",
        "inverter_kw": 5.0
    },
    {
        "id": "canadian_440_standard",
        "name": "Canadian Solar HiKu 440W",
        "power_wp": 440,
        "width_m": 1.134,
        "length_m": 1.762,
        "efficiency_pct": 21.3,
        "performance_ratio": 79.0,
        "cell_technology": "Mono-PERC",
        "battery_brand": "Tesla Powerwall 2",
        "battery_capacity_kwh": 13.5,
        "inverter_brand": "Tesla",
        "inverter_kw": 5.0
    },
    {
        "id": "longi_550_commercial",
        "name": "Longi Hi-MO 5 550W (Commercial bundle)",
        "power_wp": 550,
        "width_m": 1.134,
        "length_m": 2.278,
        "efficiency_pct": 21.5,
        "performance_ratio": 80.0,
        "cell_technology": "Bifacial PERC",
        "battery_brand": "Dyness",
        "battery_capacity_kwh": 10.0,
        "inverter_brand": "Huawei SUN2000",
        "inverter_kw": 10.0
    },
    {
        "id": "trina_700_industrial",
        "name": "Trina Vertex N 700W (Industrial)",
        "power_wp": 700,
        "width_m": 1.303,
        "length_m": 2.384,
        "efficiency_pct": 22.5,
        "performance_ratio": 82.0,
        "cell_technology": "TOPCon Bifacial",
        "battery_brand": "BYD Battery-Box Commercial",
        "battery_capacity_kwh": 60.0,
        "inverter_brand": "Sungrow",
        "inverter_kw": 125.0
    },
    {
        "id": "sunpower_400_maxeon",
        "name": "SunPower Maxeon 3 400W (Premium)",
        "power_wp": 400,
        "width_m": 1.046,
        "length_m": 1.690,
        "efficiency_pct": 22.6,
        "performance_ratio": 81.5,
        "cell_technology": "IBC Core",
        "battery_brand": "Enphase IQ Battery",
        "battery_capacity_kwh": 10.5,
        "inverter_brand": "Enphase Microinverters",
        "inverter_kw": 3.8
    },
    {
        "id": "qcells_qpeak_500",
        "name": "Q.CELLS Q.PEAK DUO 500W",
        "power_wp": 500,
        "width_m": 1.134,
        "length_m": 2.216,
        "efficiency_pct": 21.2,
        "performance_ratio": 79.5,
        "cell_technology": "Mono-PERC Half-Cell",
        "battery_brand": "Growatt ARK",
        "battery_capacity_kwh": 7.6,
        "inverter_brand": "Growatt MIN",
        "inverter_kw": 6.0
    }
]

@app.get("/modules")
def get_modules():
    return BUILTIN_MODULES + custom_modules

@app.post("/modules")
def add_module(module: CustomModule):
    import re, time
    # Generate a stable id from name + timestamp
    slug = re.sub(r'[^a-z0-9]+', '_', module.name.lower()).strip('_')
    module_id = f"custom_{slug}_{int(time.time())}"
    entry = {
        "id": module_id,
        "name": module.name,
        "power_wp": module.power_wp,
        "width_m": module.width_m,
        "length_m": module.length_m,
        "custom": True,
    }
    # Store all optional fields compactly
    optional_fields = [
        "efficiency_pct", "performance_ratio", "temp_coeff_pmax", "temp_coeff_voc", "noct",
        "voc", "isc", "vmp", "imp", "num_cells",
        "cell_technology", "warranty_years",
        "battery_brand", "battery_capacity_kwh", "battery_voltage", "battery_chemistry",
        "inverter_brand", "inverter_kw", "inverter_efficiency_pct",
    ]
    for field in optional_fields:
        val = getattr(module, field, None)
        if val is not None:
            entry[field] = val
    custom_modules.append(entry)
    return entry


@app.get("/inverters")
def get_inverters():
    return physics_layer.get_representative_inverters()


@app.get("/ecg-tariff-info")
def ecg_tariff_info():
    """Returns a summary of ECG May 2025 effective tariff rates at common consumption levels."""
    from core.layers.ecg_tariff import ECGTariff
    ecg = ECGTariff()
    return ecg.get_tariff_summary()


@app.post("/size-system")
def size_system(req: SizingRequest):
    from core.layers.ecg_tariff import ECGTariff
    ecg = ECGTariff()
    customer_type = getattr(req, 'customer_type', 'residential')

    # Determine Monthly kWh
    monthly_kwh = req.monthly_consumption_kwh
    if monthly_kwh is None and req.monthly_bill_ghs is not None:
        # Use ECG tariff reverse-lookup for accurate kWh from bill (tiered billing)
        monthly_kwh = ecg.get_kwh_from_bill(req.monthly_bill_ghs, customer_type)

    if not monthly_kwh:
        raise HTTPException(status_code=400, detail="Must provide consumption or bill")

    daily_kwh = monthly_kwh / 30.0

    # Scientific Sizing: Pdc = E_daily / (PSH * PR)
    psh = 4.8
    pr = 0.78  # Conservative PR for Ghana

    required_kwp = daily_kwh / (psh * pr)

    # Effective tariff for the user's consumption level
    effective_rate = ecg.get_effective_rate(monthly_kwh, customer_type)
    monthly_bill = ecg.get_monthly_bill(monthly_kwh, customer_type)

    # Return recommendations for common panel sizes
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
        "monthly_kwh": round(monthly_kwh, 2),
        "daily_kwh": round(daily_kwh, 3),
        "required_kwp": round(required_kwp, 2),
        "psh_used": psh,
        "pr_used": pr,
        "recommendations": recommendations,
        "suggested_inverter_kw": round(required_kwp * 1.1, 1),
        "tariff_info": {
            "customer_type": customer_type,
            "monthly_bill_ghs": round(monthly_bill, 2),
            "effective_rate_ghs_per_kwh": round(effective_rate, 4),
            "tariff_source": "ECG May 2025 Reckoner",
        }
    }

# ---- Design Save/Load endpoints --------------------------------------------

class DesignSaveRequest(BaseModel):
    name: str
    latitude: float
    longitude: float
    map_zoom: float = 18
    config_json: dict
    polygon_areas_json: list
    obstacles_json: list = []
    panel_config_json: dict
    electrical_json: dict
    placed_panels_json: list | None = None

@app.get("/designs")
def list_designs():
    engine = init_db()
    session = get_session(engine)
    try:
        designs = session.query(Design).order_by(Design.updated_at.desc()).all()
        return [
            {
                "id": d.id,
                "name": d.name,
                "latitude": d.latitude,
                "longitude": d.longitude,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
                "panel_count": len(d.placed_panels_json) if d.placed_panels_json else 0,
            }
            for d in designs
        ]
    finally:
        session.close()

@app.post("/designs")
def save_design(req: DesignSaveRequest):
    engine = init_db()
    session = get_session(engine)
    try:
        import json
        design = Design(
            name=req.name,
            latitude=req.latitude,
            longitude=req.longitude,
            map_zoom=req.map_zoom,
            config_json=json.dumps(req.config_json),
            polygon_areas_json=json.dumps(req.polygon_areas_json),
            obstacles_json=json.dumps(req.obstacles_json),
            panel_config_json=json.dumps(req.panel_config_json),
            electrical_json=json.dumps(req.electrical_json),
            placed_panels_json=json.dumps(req.placed_panels_json) if req.placed_panels_json else None,
        )
        session.add(design)
        session.commit()
        session.refresh(design)
        return {"id": design.id, "name": design.name, "status": "saved"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

@app.get("/designs/{design_id}")
def load_design(design_id: int):
    engine = init_db()
    session = get_session(engine)
    try:
        import json
        design = session.query(Design).filter(Design.id == design_id).first()
        if not design:
            raise HTTPException(status_code=404, detail="Design not found")
        return {
            "id": design.id,
            "name": design.name,
            "latitude": design.latitude,
            "longitude": design.longitude,
            "map_zoom": design.map_zoom,
            "config_json": json.loads(design.config_json),
            "polygon_areas_json": json.loads(design.polygon_areas_json),
            "obstacles_json": json.loads(design.obstacles_json),
            "panel_config_json": json.loads(design.panel_config_json),
            "electrical_json": json.loads(design.electrical_json),
            "placed_panels_json": json.loads(design.placed_panels_json) if design.placed_panels_json else None,
            "created_at": design.created_at.isoformat() if design.created_at else None,
            "updated_at": design.updated_at.isoformat() if design.updated_at else None,
        }
    finally:
        session.close()

@app.put("/designs/{design_id}")
def update_design(design_id: int, req: DesignSaveRequest):
    engine = init_db()
    session = get_session(engine)
    try:
        import json
        design = session.query(Design).filter(Design.id == design_id).first()
        if not design:
            raise HTTPException(status_code=404, detail="Design not found")
        design.name = req.name
        design.latitude = req.latitude
        design.longitude = req.longitude
        design.map_zoom = req.map_zoom
        design.config_json = json.dumps(req.config_json)
        design.polygon_areas_json = json.dumps(req.polygon_areas_json)
        design.obstacles_json = json.dumps(req.obstacles_json)
        design.panel_config_json = json.dumps(req.panel_config_json)
        design.electrical_json = json.dumps(req.electrical_json)
        design.placed_panels_json = json.dumps(req.placed_panels_json) if req.placed_panels_json else None
        design.updated_at = datetime.utcnow()
        session.commit()
        return {"id": design.id, "name": design.name, "status": "updated"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

@app.delete("/designs/{design_id}")
def delete_design(design_id: int):
    engine = init_db()
    session = get_session(engine)
    try:
        design = session.query(Design).filter(Design.id == design_id).first()
        if not design:
            raise HTTPException(status_code=404, detail="Design not found")
        session.delete(design)
        session.commit()
        return {"status": "deleted"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()

# Mount static files (HTML=False so we serve index via template)
app.mount("/", StaticFiles(directory="static", html=False), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
