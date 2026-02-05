// UniSolar 2D Map Engine
// Uses standard Google Maps Polygons for guaranteed visibility and performance
// Replaces the complex 3D WebGL overlay

class MapEngine {
    constructor(map) {
        this.map = map;
        this.panels = []; // Array of google.maps.Polygon
        this.modules = []; // Database of real-world modules
        this.obstacles = []; // Array of {marker, shadow, data}
        this.sunPosition = { azimuth: 180, zenith: 45 }; // Default Sun
        console.log('MapEngine (2D) initialized');
    }

    setSunPosition(azimuth, zenith) {
        this.sunPosition = { azimuth, zenith };
        this.refreshShadows();
    }

    refreshShadows() {
        this.obstacles.forEach(o => this.updateShadow(o));
    }

    setModules(modules) {
        this.modules = modules;
    }

    getModuleById(id) {
        return this.modules.find(m => m.id === id);
    }

    /**
     * Add a solar panel (represented as a 2D Polygon)
     * @param {number} lng - Center Longitude
     * @param {number} lat - Center Latitude
     * @param {number} height - Metadata only (not used for 2D render)
     * @param {number} tilt - Metadata only
     * @param {number} azimuth - Orientation (0=N, 90=E, 180=S)
     */
    addPanel(lng, lat, height = 0, tilt = 15, azimuth = 180, orientation = 'portrait', moduleSpec = null) {
        // Dimensions (meters)
        let len = 1.7;
        let wid = 1.0;

        if (moduleSpec) {
            len = (orientation === 'portrait') ? moduleSpec.length_m : moduleSpec.width_m;
            wid = (orientation === 'portrait') ? moduleSpec.width_m : moduleSpec.length_m;
        } else {
            len = (orientation === 'portrait') ? 1.7 : 1.0;
            wid = (orientation === 'portrait') ? 1.0 : 1.7;
        }

        // Calculate the 4 corners of the panel based on azimuth
        const path = this.calculateRectCorners(lat, lng, wid, len, azimuth);

        // Create the polygon
        const panelPoly = new google.maps.Polygon({
            paths: path,
            strokeColor: '#C0C0C0', // Silver/Aluminum Frame
            strokeOpacity: 1.0,
            strokeWeight: 1, // Thin frame
            fillColor: '#0f172a',   // Dark Blue/Black (Monocrystalline look)
            fillOpacity: 0.9,
            map: this.map,
            zIndex: 10, // Above base map
            draggable: true, // User Request: Drag & Drop
            geodesic: true
        });

        // Event: Right-click to delete
        panelPoly.addListener('rightclick', () => {
            panelPoly.setMap(null);
            // Remove from array (inefficient but fine for <1000 items)
            const idx = this.panels.indexOf(panelPoly);
            if (idx > -1) this.panels.splice(idx, 1);
        });

        // Event: Drag end to update metadata (for simulations)
        panelPoly.addListener('dragend', () => {
            const newCenter = this.getPolygonCenter(panelPoly);
            panelPoly.userData.lat = newCenter.lat;
            panelPoly.userData.lng = newCenter.lng;
            console.log(`Panel moved to: ${newCenter.lat.toFixed(6)}, ${newCenter.lng.toFixed(6)}`);
        });

        // Store metadata
        panelPoly.userData = {
            id: `panel_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
            lat,
            lng,
            height,
            tilt,
            azimuth,
            orientation
        };

        // Add to list
        this.panels.push(panelPoly);

        return panelPoly;
    }

    /**
     * Updates all existing panels with new global configurations (tilt, azimuth, module, orientation)
     */
    updateConfigurations(config) {
        const { tilt, azimuth, orientation, moduleSpec } = config;

        this.panels.forEach(panelPoly => {
            const data = panelPoly.userData;
            if (tilt !== undefined) data.tilt = tilt;
            if (azimuth !== undefined) data.azimuth = azimuth;
            if (orientation !== undefined) data.orientation = orientation;

            // Recalculate geometry
            this.updatePanelGeometry(panelPoly, moduleSpec);
        });
    }

    updatePanelGeometry(panelPoly, moduleSpec = null) {
        const { lat, lng, azimuth, orientation } = panelPoly.userData;

        let len = 1.7;
        let wid = 1.0;

        if (moduleSpec) {
            len = (orientation === 'portrait') ? moduleSpec.length_m : moduleSpec.width_m;
            wid = (orientation === 'portrait') ? moduleSpec.width_m : moduleSpec.length_m;
        } else {
            len = (orientation === 'portrait') ? 1.7 : 1.0;
            wid = (orientation === 'portrait') ? 1.0 : 1.7;
        }

        const newPath = this.calculateRectCorners(lat, lng, wid, len, azimuth);
        panelPoly.setPath(newPath);
    }

    getPolygonCenter(poly) {
        const path = poly.getPath();
        let sumLat = 0, sumLng = 0;
        path.forEach(p => {
            sumLat += p.lat();
            sumLng += p.lng();
        });
        return { lat: sumLat / path.getLength(), lng: sumLng / path.getLength() };
    }

    /**
     * Add a 3D obstacle (chimney, tree, neighbor)
     */
    addObstacle(lng, lat, type = 'chimney', height = 2.0, width = 1.0) {
        // 1. Create Base Footprint (Representing the physical volume)
        let footprint;
        if (type === 'tree') {
            footprint = new google.maps.Circle({
                map: this.map,
                center: { lat, lng },
                radius: width / 2,
                fillColor: '#22c55e',
                fillOpacity: 0.6,
                strokeWeight: 1,
                strokeColor: '#ffffff',
                draggable: true,
                zIndex: 100
            });
        } else {
            // Prism (Rectangular Structure)
            const path = this.calculateRectCorners(lat, lng, width, width, 0); // Square footprint
            footprint = new google.maps.Polygon({
                map: this.map,
                paths: path,
                fillColor: '#64748b',
                fillOpacity: 0.8,
                strokeWeight: 1,
                strokeColor: '#ffffff',
                draggable: true,
                zIndex: 100
            });
        }

        // 2. Create Shadow Layers (Umbra and Penumbra for Soft Shadows)
        const penumbra = new google.maps.Polygon({
            map: this.map,
            fillColor: '#000000',
            fillOpacity: 0.15,
            strokeWeight: 0,
            clickable: false,
            zIndex: 4
        });

        const umbra = new google.maps.Polygon({
            map: this.map,
            fillColor: '#000000',
            fillOpacity: 0.25,
            strokeWeight: 0,
            clickable: false,
            zIndex: 5
        });

        const entry = {
            id: `obs_${Date.now()}`,
            base: footprint,
            shadows: [penumbra, umbra], // Multi-layer shadow
            data: { lat, lng, type, height, width }
        };

        // Update shadow on drag
        if (type === 'tree') {
            footprint.addListener('drag', () => {
                const pos = footprint.getCenter();
                entry.data.lat = pos.lat();
                entry.data.lng = pos.lng();
                this.updateShadow(entry);
            });
        } else {
            footprint.addListener('dragend', () => {
                const center = this.getPolygonCenter(footprint);
                entry.data.lat = center.lat;
                entry.data.lng = center.lng;

                // Keep the path synchronized with the new center for shadows
                const newPath = this.calculateRectCorners(center.lat, center.lng, width, width, 0);
                footprint.setPath(newPath);
                this.updateShadow(entry);
            });
        }

        footprint.addListener('rightclick', () => {
            footprint.setMap(null);
            shadowPoly.setMap(null);
            this.obstacles = this.obstacles.filter(o => o.id !== entry.id);
        });

        this.updateShadow(entry);
        this.obstacles.push(entry);
        return entry;
    }

    /**
     * Calculate and update shadow for a specific obstacle
     */
    updateShadow(entry) {
        const { lat, lng, height, width, type } = entry.data;
        const { zenith, azimuth } = this.sunPosition;

        const sRad = np_radians(zenith);
        let slen = Math.tan(sRad) * height;

        // 1. Cap shadow length and handle sunset/sunrise disappearance
        const maxLen = height * 12; // Capped more aggressively for realism
        if (slen > maxLen) slen = maxLen;
        if (zenith > 89.0) slen = 0;

        // 2. Atmospheric Scattering (Shadows vanish as sun sets)
        let baseOpacity = 0.3;
        if (zenith > 85) {
            baseOpacity = 0.3 * Math.max(0, (1 - (zenith - 85) / 4)); // Fast vanish after 85 deg
        } else if (zenith > 75) {
            baseOpacity = 0.3 * (1 - (zenith - 75) / 20); // Gradual fade
        }

        const sAzRad = np_radians(azimuth + 180);
        const earthRadius = 6378137;
        const dLat = (1 / earthRadius) * (180 / Math.PI);
        const dLng = dLat / Math.cos(lat * Math.PI / 180);
        const dx = slen * Math.sin(sAzRad);
        const dy = slen * Math.cos(sAzRad);

        // Update Multi-Layer Shadows (Soft Edges)
        entry.shadows.forEach((s, idx) => {
            const softnessScale = idx === 0 ? 1.15 : 1.0; // Penumbra is larger
            const opacityScale = idx === 0 ? 0.4 : 1.0; // Penumbra is lighter
            s.setOptions({ fillOpacity: baseOpacity * opacityScale });

            if (type === 'tree') {
                const hw = (width / 2) * softnessScale;
                const orthoAz = sAzRad + Math.PI / 2;
                const ox = hw * Math.sin(orthoAz), oy = hw * Math.cos(orthoAz);
                const tipWidthScale = 0.7 * (idx === 0 ? 1.2 : 1.0);

                const path = [
                    { lat: lat - (oy * dLat), lng: lng - (ox * dLng) },
                    { lat: lat + (oy * dLat), lng: lng + (ox * dLng) },
                    { lat: lat + (dy * dLat) + (oy * tipWidthScale * dLat), lng: lng + (dx * dLng) + (ox * tipWidthScale * dLng) },
                    { lat: lat + (dy * 1.1 * dLat), lng: lng + (dx * 1.1 * dLng) }, // Rounded tip
                    { lat: lat + (dy * dLat) - (oy * tipWidthScale * dLat), lng: lng + (dx * dLng) - (ox * tipWidthScale * dLng) }
                ];
                s.setPath(path);
            } else {
                const hw = (width / 2) * softnessScale;
                const b = [{ x: -hw, y: -hw }, { x: hw, y: -hw }, { x: hw, y: hw }, { x: -hw, y: hw }];
                const coords = [];
                b.forEach(p => {
                    coords.push({ lat: lat + (p.y * dLat), lng: lng + (p.x * dLng) });
                    coords.push({ lat: lat + (p.y * dLat) + (dy * dLat), lng: lng + (p.x * dLng) + (dx * dLng) });
                });
                s.setPath(this.computeConvexHull(coords));
            }
        });
    }

    computeConvexHull(points) {
        if (points.length <= 3) return points;
        points.sort((a, b) => a.lat !== b.lat ? a.lat - b.lat : a.lng - b.lng);
        const upper = [], lower = [];
        for (let p of points) {
            while (upper.length >= 2 && this.crossProduct(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
            upper.push(p);
        }
        for (let i = points.length - 1; i >= 0; i--) {
            let p = points[i];
            while (lower.length >= 2 && this.crossProduct(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
            lower.push(p);
        }
        upper.pop(); lower.pop();
        return upper.concat(lower);
    }

    crossProduct(a, b, c) {
        return (b.lng - a.lng) * (c.lat - a.lat) - (b.lat - a.lat) * (c.lng - a.lng);
    }

    /**
     * Fill a polygon with solar panels
     * @param {google.maps.Polygon} polygon - The roof area
     * @param {number} spacing - Gap between panels (meters)
     */
    fillPolygon(polygon, spacing = 0.1) {
        if (!polygon) return;

        const path = polygon.getPath();
        const coords = [];
        path.forEach(p => coords.push({ lat: p.lat(), lng: p.lng() }));

        const bounds = new google.maps.LatLngBounds();
        coords.forEach(c => bounds.extend(c));
        const center = bounds.getCenter();
        const lat0 = center.lat(), lng0 = center.lng();

        const orientation = document.getElementById('orientation')?.value || 'portrait';
        const moduleId = document.getElementById('moduleSelect')?.value;
        const moduleSpec = this.getModuleById(moduleId);
        const currentTilt = parseFloat(document.getElementById('tilt')?.value) || 15;
        const currentAzimuth = parseFloat(document.getElementById('azimuth')?.value) || 180;

        let pWid = 1.0, pLen = 1.7;
        if (moduleSpec) {
            pWid = (orientation === 'portrait' ? moduleSpec.width_m : moduleSpec.length_m);
            pLen = (orientation === 'portrait' ? moduleSpec.length_m : moduleSpec.width_m);
        }

        // Solar Farm Spacing
        // Column Spacing (Side-by-side): Tight (e.g. 0.05m clamps)
        // Row Spacing (Pitch): Wide (Length + Gaps for shadow)
        const colSpacing = 0.05;
        const rowSpacing = 2.5; // Meters gap between rows (maintenance/shadow)

        // Step X is along the Azimuth-90 vector (rows extend East-West)
        // Step Y is along the Azimuth vector (columns extend North-South)
        const stepX = pWid + colSpacing;
        const stepY = pLen + rowSpacing;

        // Grid Alignment Pattern: Align to SOLAR AZIMUTH, not fence.
        // If Azimuth = 180 (South), Panels face South. Rows run East-West.
        // We scan along this rotated grid.

        const gridRotRad = np_radians(currentAzimuth);

        const earthRadius = 6378137;
        const dLat = (1 / earthRadius) * (180 / Math.PI);
        const dLng = dLat / Math.cos(lat0 * Math.PI / 180);

        // Oversized Grid
        const radiusMeters = google.maps.geometry.spherical.computeDistanceBetween(bounds.getNorthEast(), bounds.getSouthWest()) / 2;
        const range = Math.ceil(radiusMeters / Math.min(stepX, stepY)) + 2;

        let count = 0;

        // Scan Grid
        for (let ix = -range; ix <= range; ix++) {
            for (let iy = -range; iy <= range; iy++) {
                // Local Grid Coordinates
                const lx = ix * stepX;
                const ly = iy * stepY;

                // Rotate this point by the Azimuth to place it on the map
                // Note: Standard rotation (x', y') = (x cos - y sin, x sin + y cos)
                // But Azimuth defined 0=N, 90=E. 
                // Grid X (Width) should be perpendicular (90 deg) to Azimuth?
                // Actually: 
                // If Az=180 (S). We want rows to be E-W. 
                // So "Rows" are X axis. "Columns" are Y axis.
                // Lets define X axis as Azimuth + 90. Y axis as Azimuth.

                const xAxisAngle = gridRotRad + (Math.PI / 2); // E-W if Az=180
                const yAxisAngle = gridRotRad;                // N-S if Az=180

                // Project lx along X-Axis, ly along Y-Axis
                const dx = lx * Math.sin(xAxisAngle) + ly * Math.sin(yAxisAngle);
                const dy = lx * Math.cos(xAxisAngle) + ly * Math.cos(yAxisAngle);

                const cLat = lat0 + (dy * dLat);
                const cLng = lng0 + (dx * dLng);

                // Collision Check logic...
                const centerPt = new google.maps.LatLng(cLat, cLng);

                // Check if Center is in Polygon (Fast Pass)
                if (google.maps.geometry.poly.containsLocation(centerPt, polygon)) {

                    // Check all 4 corners (Strict Pass)
                    const panelPath = this.calculateRectCorners(cLat, cLng, pWid, pLen, currentAzimuth);
                    let allInside = true;
                    // Relaxed fit for farms: If center is in, and >50% corners are in?
                    // Strict: All corners.
                    for (let corner of panelPath) {
                        if (!google.maps.geometry.poly.containsLocation(new google.maps.LatLng(corner.lat, corner.lng), polygon)) {
                            allInside = false;
                            break;
                        }
                    }

                    if (allInside) {
                        // Obstacle Check
                        let occluded = false;
                        for (let obs of this.obstacles) {
                            if (google.maps.geometry.poly.containsLocation(centerPt, obs.base)) {
                                occluded = true; break;
                            }
                        }

                        if (!occluded) {
                            this.addPanel(cLng, cLat, 0, currentTilt, currentAzimuth, orientation, moduleSpec);
                            count++;
                        }
                    }
                }
            }
        }

        console.log(`Solar Farm Layout: Added ${count} panels aligned to Azimuth ${currentAzimuth}°`);
        polygon.setMap(null);
        if (count === 0) alert("0 Panels Added. Try changing the Azimuth or drawing a larger area.");
    }

    /**
     * Calculate 4 corners of a rectangle given center, dimensions, and rotation
     */
    calculateRectCorners(centerLat, centerLng, width, length, azimuthDegrees) {
        const center = new google.maps.LatLng(centerLat, centerLng);
        const hw = width / 2;
        const hl = length / 2;

        const dist = Math.sqrt(hw * hw + hl * hl);
        const angleOffset = Math.atan2(hw, hl) * 180 / Math.PI;

        const corners = [
            google.maps.geometry.spherical.computeOffset(center, dist, azimuthDegrees + (180 - angleOffset)), // BL
            google.maps.geometry.spherical.computeOffset(center, dist, azimuthDegrees + (180 + angleOffset)), // BR
            google.maps.geometry.spherical.computeOffset(center, dist, azimuthDegrees - angleOffset),         // TL
            google.maps.geometry.spherical.computeOffset(center, dist, azimuthDegrees + angleOffset)          // TR
        ];

        return corners.map(c => ({ lat: c.lat(), lng: c.lng() }));
    }



    getPanelCount() {
        return this.panels.length;
    }

    getPanels() {
        return this.panels.map(p => p.userData);
    }

    getObstacles() {
        return this.obstacles.map(o => o.data);
    }

    clear() {
        this.panels.forEach(p => p.setMap(null));
        this.obstacles.forEach(o => {
            o.base.setMap(null);
            o.shadow.setMap(null);
        });
        this.panels = [];
        this.obstacles = [];
    }
}

// Utility
function np_radians(deg) {
    return deg * Math.PI / 180;
}

window.MapEngine = MapEngine;
