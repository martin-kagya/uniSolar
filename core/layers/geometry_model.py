import pandas as pd
import numpy as np
import pvlib
from pvlib import shading

class GeometryLayer:
    """
    Layer 0 (Spatial): Defines physical scene and calculates shading.
    Uses PVLib's infinite row shading models.
    """
    
    def __init__(self, surface_tilt=10, surface_azimuth=180, gcr=0.4):
        """
        :param gcr: Ground Coverage Ratio (0.0 to 1.0). 
                   Lower GCR means rows are further apart.
        """
        self.surface_tilt = surface_tilt
        self.surface_azimuth = surface_azimuth
        self.gcr = gcr # Ratio of row-length to pitch
        self.collector_width = 1.0 # Standard panel width in meters (portrait)

    def calculate_shading(self, solar_zenith, solar_azimuth):
        """
        Calculates the shaded fraction for one-dimensional rows.
        """
        # pitch = axis-to-axis distance
        # pitch = row_slant_length / GCR
        pitch = self.collector_width / self.gcr
        
        # PVLib shading function
        # shaded_fraction1d returns 0.0 (no shade) to 1.0 (full shade)
        f_shaded = shading.shaded_fraction1d(
            solar_zenith,
            solar_azimuth,
            self.surface_tilt,
            self.surface_azimuth,
            pitch,
            self.collector_width,
            max_shaded_fraction=1.0
        )
        
        return f_shaded.fillna(0)

    def calculate_obstacle_shading(self, solar_zenith, solar_azimuth, panels, features):
        """
        Calculates shading fraction from 3D obstacles (chimneys, trees, etc.) on specific panels.
        Synchronized with frontend atmospheric logic: includes length capping and scattering fading.
        """
        if not panels or not features:
            return pd.Series(0.0, index=solar_zenith.index)

        # 1. Project Lat/Lon to Local Meters (origin at site center)
        # This is critical because shading length h*tan(z) is in meters.
        avg_lat = np.mean([p['y'] for p in panels])
        
        # Approximate meters per degree at this latitude
        # 1 deg lat = 111,320m
        # 1 deg lon = 111,320m * cos(lat)
        m_per_lat = 111320.0
        m_per_lon = 111320.0 * np.cos(np.radians(avg_lat))

        origin_x = np.mean([p['x'] for p in panels])
        origin_y = avg_lat

        def project(lon, lat):
            return (lon - origin_x) * m_per_lon, (lat - origin_y) * m_per_lat

        # Project all panels and obstacles
        proj_panels = []
        for p in panels:
            mx, my = project(p['x'], p['y'])
            proj_panels.append({'x': mx, 'y': my})

        proj_features = []
        for f in features:
            mx, my = project(f['x'], f['y'])
            proj_features.append({
                'x': mx, 'y': my,
                'height': f.get('height', 2.5),
                'width': f.get('width', 1.0),
                'type': f.get('type', 'structure')
            })

        shading_series = pd.Series(0.0, index=solar_zenith.index)
        
        # Sun vector calculation
        is_day = solar_zenith < 88 # Sun must be above horizon
        for timestamp, zenith in solar_zenith[is_day].items():
            az = solar_azimuth[timestamp]
            
            # Atmospheric Scattering Fading (Shadows lose impact as they diffuse at sunset)
            impact_scale = 1.0
            if zenith > 85:
                # Fast vanish after 85 deg matching frontend
                impact_scale = max(0, (1 - (zenith - 85) / 4)) 
            elif zenith > 75:
                impact_scale = (1 - (zenith - 75) / 20)
                
            if impact_scale <= 0.05:
                shading_series[timestamp] = 0.0
                continue

            s_len = np.tan(np.radians(zenith)) 
            s_az_rad = np.radians(az + 180) 
            dx_unit = np.sin(s_az_rad)
            dy_unit = np.cos(s_az_rad)
            
            shaded_mask = np.zeros(len(proj_panels))
            
            for f in proj_features:
                h = f['height']
                obs_width = f['width']
                obs_type = f['type']
                
                # Shadow length capping (Strictly matching frontend realism)
                actual_slen = s_len * h
                max_len = h * 12.0
                if actual_slen > max_len:
                    actual_slen = max_len
                
                # Shadow segment endpoints (All in Meters now!)
                x0, y0 = f['x'], f['y']
                x1, y1 = x0 + (dx_unit * actual_slen), y0 + (dy_unit * actual_slen)
                
                # Intersection check
                for i, p in enumerate(proj_panels):
                    px, py = p['x'], p['y']
                    
                    # Distance to shadow segment
                    l2 = (x1-x0)**2 + (y1-y0)**2
                    if l2 == 0:
                        dist_sq = (px-x0)**2 + (py-y0)**2
                    else:
                        t = max(0, min(1, ((px-x0)*(x1-x0) + (py-y0)*(y1-y0)) / l2))
                        dist_sq = (px - (x0 + t*(x1-x0)))**2 + (py - (y0 + t*(y1-y0)))**2
                    
                    # Buffer for shadow width
                    # Trees have more diffuse 'soft' width than prisms
                    effective_radius_sq = (obs_width / 2)**2
                    if obs_type == 'tree':
                        effective_radius_sq *= 1.2 # Slighly wider influence for diffuse foliage
                        
                    if dist_sq < effective_radius_sq:
                         shaded_mask[i] = impact_scale # Factor in atmospheric fading
            
            shading_series[timestamp] = np.mean(shaded_mask)
            
        return shading_series

    def optimize_spacing(self, solar_pos_df, target_loss=0.01):
        """
        Suggests an optimal GCR/Spacing to minimize shading losses 
        for a given location.
        """
        best_gcr = 0.3
        # Optimization logic would go here
        return best_gcr

    def calculate_roof_capacity(self, length, width, margin=0.5):
        """
        Calculates how many panels fit on a 3D structure (simplified).
        """
        effective_len = length - 2*margin
        effective_width = width - 2*margin
        
        # Assume 2.2m x 1.1m large format commercial panels
        p_len = 2.2
        p_wid = 1.1
        
        # Portrait layout
        num_cols = int(effective_len / p_wid)
        num_rows = int(effective_width / p_len)
        
        return {
            "total_panels": num_cols * num_rows,
            "capacity_kwp": (num_cols * num_rows * 0.550), # 550W high-efficiency
            "layout": f"{num_rows} rows x {num_cols} columns",
            "num_rows": num_rows,
            "num_cols": num_cols,
            "panel_dims": (p_wid, p_len),
            "roof_dims": (length, width)
        }

    def visualize_layout(self, length, width, margin=0.5, output_path="reports/layout_view.png"):
        """
        Generates a visual diagram of the panel configuration.
        """
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        
        analysis = self.calculate_roof_capacity(length, width, margin)
        
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Draw Roof
        roof = patches.Rectangle((0, 0), length, width, linewidth=2, edgecolor='#333333', facecolor='#eeeeee', label='Roof Boundary')
        ax.add_patch(roof)
        
        # Draw Panels
        p_wid, p_len = analysis['panel_dims']
        start_x = margin
        start_y = margin
        
        for r in range(analysis['num_rows']):
            for c in range(analysis['num_cols']):
                x = start_x + (c * p_wid) + (c * 0.1) # 10cm gap
                y = start_y + (r * p_len) + (r * 0.2) # 20cm row spacing (shading/walkway)
                
                # Check if it fits (redundancy check)
                if x + p_wid <= length - margin and y + p_len <= width - margin:
                    panel = patches.Rectangle((x, y), p_wid, p_len, linewidth=0.5, edgecolor='#003366', facecolor='#2c3e50', alpha=0.8)
                    ax.add_patch(panel)
        
        ax.set_xlim(-1, length + 1)
        ax.set_ylim(-1, width + 1)
        ax.set_aspect('equal')
        ax.set_title(f"3D Panel Configuration: {analysis['total_panels']} Panels ({analysis['capacity_kwp']:.1f} kWp)\n{analysis['layout']}")
        ax.legend(loc='upper right')
        plt.xlabel("Length (m)")
        plt.ylabel("Width (m)")
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        return output_path
