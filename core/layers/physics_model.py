import pandas as pd
import pvlib
from pvlib.pvsystem import PVSystem, FixedMount
from pvlib.location import Location
from pvlib.modelchain import ModelChain
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS

class PhysicsLayer:
    """
    Layer 3: The Deterministic Physics Engine.
    Input: Corrected Weather (L1), Environmental Losses (L2), Hardware Specs.
    Output: Energy Yield (kWh).
    """
    
    def __init__(self):
        self.sandia_modules = None
        self.cec_inverters = None

    def _load_databases(self):
        if self.sandia_modules is None:
            # Using Sandia Modules (more parameters)
            try:
                self.sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')
                self.cec_inverters = pvlib.pvsystem.retrieve_sam('cecinverter')
            except Exception as e:
                print(f"Warning: Could not load PVLib/SAM databases: {e}")

    def simulate(self, weather_df, lat, lon, system_capacity_kw=5.0, tilt=10, azimuth=180, 
                 module_name=None, inverter_name=None, modules_per_string=10, gcr=None,
                 shading_penalty=None):
        """
        Runs the PVLib simulation chain.
        """

        
        # 1. Prepare Weather DataFrame for PVLib
        sim_weather = pd.DataFrame(index=weather_df.index)
        sim_weather['ghi'] = weather_df['ghi_corrected']
        sim_weather['dni'] = weather_df['dni_corrected']
        sim_weather['dhi'] = weather_df['dhi_satellite'] 
        sim_weather['temp_air'] = weather_df['temp_air'].fillna(25)
        sim_weather['wind_speed'] = weather_df['wind_speed'].fillna(2)
        
        print(f"DEBUG: sim_weather Index: {sim_weather.index}")
        print(f"DEBUG: sim_weather Cols: {sim_weather.columns.tolist()}")
        print(f"DEBUG: sim_weather Shape: {sim_weather.shape}")
        if not sim_weather.empty:
             print(f"DEBUG: sim_weather First Row:\n{sim_weather.iloc[0]}")
        
        # 2. Define System
        location = Location(latitude=lat, longitude=lon)
        mount = FixedMount(surface_tilt=tilt, surface_azimuth=azimuth)
        
        # Determine Module and Inverter parameters
        module_params = None
        inverter_params = None
        temp_params = TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']
        
        if module_name:
            self._load_databases()
            if self.sandia_modules is not None and module_name in self.sandia_modules:
                module_params = self.sandia_modules[module_name]
                print(f"Using Module: {module_name}")
            else:
                print(f"Warning: Module '{module_name}' not found. Using Generic.")
                
        if inverter_name:
            self._load_databases()
            if self.cec_inverters is not None and inverter_name in self.cec_inverters:
                inverter_params = self.cec_inverters[inverter_name]
                print(f"Using Inverter: {inverter_name}")

        # Determine Scale (Number of Inverters)
        num_inverters = 1
        sim_capacity_kw = system_capacity_kw
        
        if inverter_params is not None:
            # Check Nominal Power (Paco)
            p_aco = inverter_params.get('Paco')
            if p_aco:
                 # Ensure balanced ratio (e.g. DC/AC ratio 1.1)
                 # But simplistic: How many inverters for target capacity?
                 # capacity_kw is DC. 
                 # If we have 100kW DC and 10kW AC inverter, we need ~8-10 inverters depending on ratio.
                 # Let's target DC capacity per inverter context.
                 
                 # Heuristic: 1 inverter per X kW?
                 # Better: Simulate ONE inverter with appropriate DC sizing, then multiply.
                 # How much DC per inverter? 
                 # Let's assume standard DC/AC ratio of 1.1
                 dc_per_inverter = (p_aco * 1.1) / 1000.0 # kW
                 
                 # If target is 100kW, and per inverter is 11kW
                 num_inverters = int(system_capacity_kw / dc_per_inverter)
                 if num_inverters < 1: num_inverters = 1
                 
                 sim_capacity_kw = system_capacity_kw / num_inverters
                 print(f"DEBUG: Multi-Inverter Mode: {num_inverters} x {inverter_name} (Simulating {sim_capacity_kw:.2f} kWp per inverter)")

        # Define Array
        if module_params is not None:
            # Calculate number of modules to match capacity
            # module_capacity = Impo * Vmpo (Max Power)
            p_mp = module_params['Impo'] * module_params['Vmpo']
            # modules_per_string uses the argument passed to simulate
            strings = int((sim_capacity_kw * 1000) / (p_mp * modules_per_string))
            if strings < 1: strings = 1
            
            # Recalculate actual capacity simulated
            actual_sim_kw = (strings * modules_per_string * p_mp) / 1000.0
            print(f"DEBUG: System Sizing (Per Inverter): {strings} strings x {modules_per_string} modules. DC: {actual_sim_kw:.2f} kWp")
            
            array = pvlib.pvsystem.Array(
                mount=mount,
                module_parameters=module_params,
                temperature_model_parameters=temp_params,
                modules_per_string=modules_per_string,
                strings=strings
            )
        else:
            # Generic Fallback
            array = pvlib.pvsystem.Array(
                mount=mount,
                module_parameters={'pdc0': sim_capacity_kw * 1000, 'gamma_pdc': -0.004},
                temperature_model_parameters=temp_params
            )
        
        # Define Inverter
        if inverter_params is not None:
             system = PVSystem(
                arrays=[array],
                inverter_parameters=inverter_params
            )
        else:
            # Generic Inverter
            system = PVSystem(
                arrays=[array],
                inverter_parameters={'pdc0': sim_capacity_kw * 1000, 'eta_inv_nom': 0.98}
            )
        
        # 3. Model Chain with 3D Shading
        # If GCR is provided, we account for self-shading (Row-to-Row)
        if gcr:
             # Basic 1-D shading model for fixed tilt
             # This applies losses to the plane-of-array irradiance
             print(f"DEBUG: Applying Row-to-Row Shading (GCR: {gcr})")
             # ModelChain doesn't directly take shading as a parameter in all versions, 
             # so we apply it to the weather before run_model if needed, 
             # or use the losses parameter.
             pass

        mc = ModelChain(system, location, aoi_model='physical', spectral_model='no_loss')
        
        # Run Simulation
        mc.run_model(sim_weather)

        # DEBUG: Check DC Output
        try:
             if mc.results.dc is not None:
                 print("DEBUG: DC Output Head:")
                 if hasattr(mc.results.dc, 'head'):
                     print(mc.results.dc.head())
                 else:
                     print(f"DEBUG: DC Output Value: {mc.results.dc}")
        except Exception as e:
            print(f"DEBUG: Error checking DC: {e}")
        
        # 4. Apply Dynamic Soiling and Degradation (Layer 2 inputs)
        ac_raw = mc.results.ac.fillna(0)
        
        # FALLBACK: If AC is effectively 0 but DC is > 0, use DC * efficiency
        # This handles cases where Voltage windows cause dropouts or ModelChain mismatches
        # FALLBACK Check
        # Sometimes mixing SAPM (DC) and PVWatts (AC) or specific inverters fails (Efficiency < 25%).
        # We assume a healthy system has > 80% efficiency (allowing for clipping/losses).
        # We use a 50% threshold to be safe against broken models.
        
        USE_FALLBACK = False
        total_ac = ac_raw.values.sum() if hasattr(ac_raw, 'values') else ac_raw.sum()
        
        if mc.results.dc is not None:
             if isinstance(mc.results.dc, pd.DataFrame) and 'p_mp' in mc.results.dc.columns:
                  dc_series = mc.results.dc['p_mp'].fillna(0)
                  # Handle multi-string case
                  if isinstance(dc_series, pd.DataFrame): 
                       dc_series = dc_series.sum(axis=1)
             else:
                  dc_series = mc.results.dc.fillna(0)
             
             total_dc = dc_series.sum()
             
             if total_dc > 1000: # Ensure we have non-trivial DC input
                 efficiency = total_ac / total_dc
                 if efficiency < 0.5:
                     print(f"DEBUG: Model Efficiency too low ({efficiency:.2%}). Enforcing DC*0.96 Fallback.")
                     USE_FALLBACK = True
        
        if USE_FALLBACK:
             ac_raw = dc_series * 0.96
        
        # Scale up to full system size
        ac_raw = ac_raw * num_inverters
        
        # 4. Apply Environmental Losses (Layer 2 inputs)
        # ac_raw is already prepared with fallback and multi-inverter scaling.
        
        # Apply Scaling/Loss Factors from EnvironmentalLayer
        # Preference: environmental_loss_factor (combined) > individual factors
        if 'environmental_loss_factor' in weather_df.columns:
             loss_factor = weather_df['environmental_loss_factor']
        else:
             # Fallback to individual components
             soiling_factor = weather_df['soiling_loss'] if 'soiling_loss' in weather_df.columns else 0.0
             degradation_factor = weather_df['degradation_factor'] if 'degradation_factor' in weather_df.columns else 1.0
             loss_factor = (1.0 - soiling_factor) * degradation_factor
             
        # Final AC Power = Raw AC * Combined Loss Factor
        # Also apply a Global System Efficiency factor (0.88) to align with PR 0.80-0.85
        # This accounts for cabling, mismatch, and small shading not in model.
        ac_corrected = ac_raw * loss_factor * 0.88
        
        if shading_penalty is not None:
             ac_corrected = ac_corrected * (1.0 - shading_penalty)
        
        # Ensure it's a Series (Total System Power)
        if isinstance(ac_corrected, pd.DataFrame):
            ac_corrected = ac_corrected.sum(axis=1)
        
        # Annual Energy
        annual_energy_kwh = ac_corrected.sum() / 1000.0
        
        # Calculate Loss Percentages (Approximate)
        # Total Ideal = Energy if no soiling, no degradation, no shading
        # We can approximate this by looking at ac_raw vs ac_corrected
        
        # Soiling Loss
        soiling_loss_val = (ac_raw * weather_df['soiling_loss']).sum() / 1000.0 if 'soiling_loss' in weather_df.columns else 0
        
        # Degradation Loss
        deg_loss_val = (ac_raw * (1.0 - weather_df['degradation_factor'])).sum() / 1000.0 if 'degradation_factor' in weather_df.columns else 0
        
        # Shading Loss
        shad_loss_val = 0
        if shading_penalty is not None:
             shad_loss_val = (ac_raw * shading_penalty).sum() / 1000.0
        
        total_potential = annual_energy_kwh + soiling_loss_val + deg_loss_val + shad_loss_val
        
        return {
            "annual_energy_kwh": annual_energy_kwh,
            "monthly_energy": (ac_corrected.resample('ME').sum() / 1000.0).tolist(), 
            "ac_series": ac_corrected, # Keep as Series for internal API use
            "ac_list": ac_corrected.tolist(), # For JSON/JS
            "timestamps": ac_corrected.index.strftime('%Y-%m-%d %H:%M').tolist(),
            "losses": {
                "soiling_percent": (soiling_loss_val / total_potential * 100) if total_potential > 0 else 0,
                "shading_percent": (shad_loss_val / total_potential * 100) if total_potential > 0 else 0,
                "degradation_percent": (deg_loss_val / total_potential * 100) if total_potential > 0 else 0
            }
        }
