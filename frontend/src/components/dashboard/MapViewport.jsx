import React, { useEffect, useRef, useCallback, useMemo } from 'react';
import { APIProvider, Map, useMap, useMapsLibrary } from '@vis.gl/react-google-maps';

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

// ─── Geodesic Helpers ────────────────────────────────────────────

const EARTH_RADIUS = 6378137; // WGS-84 semi-major axis in meters

/**
 * Offset a lat/lng point by meters (north, east) using Vincenty direct formula.
 * Accounts for earth curvature at any latitude.
 */
function offsetLatLng(lat, lng, northM, eastM) {
    const dLat = northM / EARTH_RADIUS;
    const dLng = eastM / (EARTH_RADIUS * Math.cos(Math.PI * lat / 180));
    return {
        lat: lat + (dLat * 180 / Math.PI),
        lng: lng + (dLng * 180 / Math.PI),
    };
}

/**
 * Compute the geodesic distance between two lat/lng points (Haversine).
 */
function haversineDistance(p1, p2) {
    const toRad = (deg) => deg * Math.PI / 180;
    const dLat = toRad(p2.lat - p1.lat);
    const dLng = toRad(p2.lng - p1.lng);
    const a = Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(p1.lat)) * Math.cos(toRad(p2.lat)) * Math.sin(dLng / 2) ** 2;
    return 2 * EARTH_RADIUS * Math.asin(Math.sqrt(a));
}

/**
 * Ray-casting point-in-polygon with lat/lng coordinates.
 */
function pointInPolygon(point, polygon) {
    let inside = false;
    const eps = 1e-10; // Precision buffer
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
        const xi = polygon[i].lng, yi = polygon[i].lat;
        const xj = polygon[j].lng, yj = polygon[j].lat;
        const intersect = ((yi > point.lat) !== (yj > point.lat)) &&
            (point.lng < (xj - xi) * (point.lat - yi) / (yj - yi) + xi + eps);
        if (intersect) inside = !inside;
    }
    return inside;
}

/**
 * Check if all 4 corners of a panel rectangle are inside a polygon.
 */
function panelFitsInPolygon(corners, polygon) {
    return corners.every(c => pointInPolygon(c, polygon));
}

/**
 * Generate solar panel rectangles to fill a polygon with geodesic accuracy.
 *
 * @param {Array} polygon - [{lat, lng}, ...] vertices
 * @param {number} panelWidthM - Panel width in meters
 * @param {number} panelHeightM - Panel height in meters
 * @param {number} rowGapM - Gap between rows in meters
 * @param {number} colGapM - Gap between columns in meters
 * @param {'portrait'|'landscape'} orientation - Panel orientation
 * @returns {Array} Array of panel objects with corners and center
 */
/**
 * Computes the angle (in radians) of the longest edge of the polygon.
 * We use this to align the panel grid with the building's orientation.
 */
function getBaselineAngle(polygon) {
    let bestAngle = 0;
    let maxScore = -1;
    for (let i = 0; i < polygon.length; i++) {
        const p1 = polygon[i];
        const p2 = polygon[(i + 1) % polygon.length];
        const distSq = (p2.lng - p1.lng) ** 2 + (p2.lat - p1.lat) ** 2;
        const angle = Math.atan2(p2.lat - p1.lat, p2.lng - p1.lng);

        // Architectural heuristic: prefer edges that are closer to "horizontal"
        // This helps align with most building roof orientations.
        const horizBias = Math.abs(Math.cos(angle));
        const score = distSq * (1 + horizBias * 0.5);

        if (score > maxScore) {
            maxScore = score;
            bestAngle = angle;
        }
    }
    return bestAngle;
}

/**
 * Rotate a point {lat, lng} around an origin, with geodesic correction.
 * We scale longitude by cos(lat) to maintain square proportions in meters.
 */
function rotatePoint(point, origin, angle, centerLat) {
    const rad = centerLat * Math.PI / 180;
    const cosLat = Math.cos(rad);

    const cos = Math.cos(angle);
    const sin = Math.sin(angle);

    // Scale longitude difference by cosLat for rotation in "flat meter-like" space
    const dx = (point.lng - origin.lng) * cosLat;
    const dy = point.lat - origin.lat;

    const rx = dx * cos - dy * sin;
    const ry = dx * sin + dy * cos;

    return {
        lng: origin.lng + (rx / cosLat),
        lat: origin.lat + ry,
    };
}

/**
 * Generate solar panel rectangles to fill a polygon with geodesic accuracy and ROTATION.
 */
/**
 * Generate solar panel rectangles to fill a polygon with a "Utility-Scale" hierarchy.
 * Levels: Blocks (separated by roads) -> Rows (separated by shading gaps) -> Modules.
 */
function generateGeodesicPanelGrid(polygon, panelWidthM, panelHeightM, rowGapM, colGapM, orientation, panelConfig) {
    if (polygon.length < 3) return [];

    const { rowSpacingM = 4.0, blockSizeM = 50.0, roadWidthM = 6.0 } = panelConfig || {};

    const w = orientation === 'landscape' ? Math.max(panelWidthM, panelHeightM) : Math.min(panelWidthM, panelHeightM);
    const h = orientation === 'landscape' ? Math.min(panelWidthM, panelHeightM) : Math.max(panelWidthM, panelHeightM);

    const angle = getBaselineAngle(polygon);
    const origin = polygon[0];

    const polyLats = polygon.map(p => p.lat);
    const centerLat = (Math.min(...polyLats) + Math.max(...polyLats)) / 2;

    const rotPolygon = polygon.map(p => rotatePoint(p, origin, -angle, centerLat));
    const lats = rotPolygon.map(p => p.lat);
    const lngs = rotPolygon.map(p => p.lng);
    const minLat = Math.min(...lats), maxLat = Math.max(...lats);
    const minLng = Math.min(...lngs), maxLng = Math.max(...lngs);

    const mPerLat = 111320;
    const mPerLng = 111320 * Math.cos(centerLat * Math.PI / 180);

    const panels = [];
    let panelId = 0;
    const buffer = 1e-9;

    // Hierarchy: Blocks -> Rows -> Panels
    const stepBlockLat = blockSizeM + roadWidthM;
    const stepBlockLng = blockSizeM + roadWidthM;
    const stepRowLat = h + rowSpacingM;
    const stepModuleLng = w + colGapM;

    let globalRowIdx = 0;
    let blockIdx = 0;

    // 1. Iterate through Blocks
    for (let bLat = minLat; bLat < maxLat; bLat += stepBlockLat / mPerLat) {
        for (let bLng = minLng; bLng < maxLng; bLng += stepBlockLng / mPerLng) {
            const currentBlockId = `block_${blockIdx++}`;

            const blockMaxLat = bLat + (blockSizeM / mPerLat);
            const blockMaxLng = bLng + (blockSizeM / mPerLng);

            // 2. Iterate through Rows inside Block
            for (let rLat = bLat; rLat + (h / mPerLat) <= blockMaxLat + buffer; rLat += stepRowLat / mPerLat) {
                const currentRowId = `${currentBlockId}_row_${globalRowIdx++}`;
                // 3. Iterate through Modules inside Row
                for (let mLng = bLng; mLng + (w / mPerLng) <= blockMaxLng + buffer; mLng += stepModuleLng / mPerLng) {

                    if (rLat + (h / mPerLat) > maxLat + buffer || mLng + (w / mPerLng) > maxLng + buffer) continue;

                    const sw = { lat: rLat, lng: mLng };
                    const se = { lat: rLat, lng: mLng + (w / mPerLng) };
                    const ne = { lat: rLat + (h / mPerLat), lng: mLng + (w / mPerLng) };
                    const nw = { lat: rLat + (h / mPerLat), lng: mLng };

                    const corners = [sw, se, ne, nw].map(p => rotatePoint(p, origin, angle, centerLat));
                    const center = rotatePoint({ lat: rLat + (h / mPerLat) / 2, lng: mLng + (w / mPerLng) / 2 }, origin, angle, centerLat);

                    if (Number.isFinite(center.lat) && Number.isFinite(center.lng)) {
                        if (panelFitsInPolygon(corners, polygon)) {
                            panels.push({
                                id: `panel_${panelId++}`,
                                rowId: currentRowId,
                                blockId: currentBlockId,
                                corners,
                                center,
                                widthM: w,
                                heightM: h,
                                rotation: angle * (180 / Math.PI), // Store base rotation in degrees
                                baseWidthM: w,
                                baseHeightM: h,
                                orientation: orientation
                            });
                        }
                    }
                }
            }
        }
    }

    return panels;
}

/**
 * Re-calculate panel corners based on a new rotation angle (degrees).
 */
function updatePanelGeometry(panel, newRotationDeg, newWidthM, newHeightM) {
    const angleRad = newRotationDeg * Math.PI / 180;
    const centerLat = panel.center.lat;
    const mPerLat = 111320;
    const mPerLng = 111320 * Math.cos(centerLat * Math.PI / 180);

    const hw = newWidthM / 2;
    const hh = newHeightM / 2;

    // Relative offsets in meters
    const cornersM = [
        { x: -hw, y: -hh }, // SW
        { x: hw, y: -hh },  // SE
        { x: hw, y: hh },   // NE
        { x: -hw, y: hh },  // NW
    ];

    const cos = Math.cos(angleRad);
    const sin = Math.sin(angleRad);

    const newCorners = cornersM.map(c => {
        // Rotate in meter space
        const rx = c.x * cos - c.y * sin;
        const ry = c.x * sin + c.y * cos;

        // Convert back to lat/lng relative to center
        return {
            lng: panel.center.lng + (rx / mPerLng),
            lat: panel.center.lat + (ry / mPerLat)
        };
    });

    return {
        ...panel,
        corners: newCorners,
        rotation: newRotationDeg,
        widthM: newWidthM,
        heightM: newHeightM
    };
}

/**
 * Redistributes panels in a row to maintain a specific gap, preventing overlaps.
 */
function redistributeRowPanels(rowPanels, gapM) {
    if (rowPanels.length < 2) return rowPanels;

    // Sort panels by position (usually left-to-right)
    const sorted = [...rowPanels].sort((a, b) => (a.center.lng - b.center.lng) || (a.center.lat - b.center.lat));
    const first = sorted[0];
    const last = sorted[sorted.length - 1];

    // Determine row direction vector in lat/lng
    const dlng = last.center.lng - first.center.lng;
    const dlat = last.center.lat - first.center.lat;
    const distLatLng = Math.sqrt(dlng * dlng + dlat * dlat);
    if (distLatLng === 0) return rowPanels;

    // Meter-space scaling
    const centerLat = first.center.lat;
    const mPerLat = 111320;
    const mPerLng = 111320 * Math.cos(centerLat * Math.PI / 180);

    // Get bearing in radians
    const bearingRad = Math.atan2(dlng * mPerLng, dlat * mPerLat);

    return sorted.map((p, i) => {
        if (i === 0) return p;
        const stepM = p.widthM + gapM;
        const totalDistM = i * stepM;

        // Calculate new center using offsetLatLng logic
        const dLat = (Math.cos(bearingRad) * totalDistM) / EARTH_RADIUS;
        const dLng = (Math.sin(bearingRad) * totalDistM) / (EARTH_RADIUS * Math.cos(Math.PI * first.center.lat / 180));

        const nextCenter = {
            lat: first.center.lat + (dLat * 180 / Math.PI),
            lng: first.center.lng + (dLng * 180 / Math.PI)
        };

        return updatePanelGeometry({ ...p, center: nextCenter }, p.rotation, p.widthM, p.heightM);
    });
}


// ─── Drawing Engine ──────────────────────────────────────────────

function DrawingEngine({
    activeTool, polygonAreas, setPolygonAreas, activeVertices, setActiveVertices,
    placedPanels, setPlacedPanels, panelConfig, selectedModule,
    selectedRowIds, setSelectedRowIds
}) {
    const map = useMap();
    const mapsLib = useMapsLibrary('maps');

    // Refs for map objects
    const outlinePolygonsRef = useRef([]);
    const panelOverlaysRef = useRef([]);
    const polylineRef = useRef(null);
    const closingLineRef = useRef(null);
    const vertexMarkersRef = useRef([]);
    const clipboardRef = useRef(null);

    /* ---------- cursor ---------- */
    useEffect(() => {
        if (!map) return;
        map.setOptions({
            draggableCursor: activeTool === 'draw' ? 'crosshair' : null,
        });
    }, [map, activeTool]);

    /* ---------- keyboard interactions (delete, copy, paste) ---------- */
    useEffect(() => {
        const handleKeyDown = (e) => {
            const isMod = e.metaKey || e.ctrlKey;

            // Delete selected rows
            if ((e.key === 'Backspace' || e.key === 'Delete') && selectedRowIds.length > 0) {
                setPlacedPanels(prev => prev.filter(p => !selectedRowIds.includes(p.rowId)));
                setSelectedRowIds([]);
            }

            // Copy selected rows (only handles first selected row for now to simplify, or could combine)
            if (isMod && e.key === 'c' && selectedRowIds.length > 0) {
                const combinedPanels = placedPanels.filter(p => selectedRowIds.includes(p.rowId));
                if (combinedPanels.length > 0) {
                    clipboardRef.current = JSON.parse(JSON.stringify(combinedPanels));
                }
            }

            // Paste row
            if (isMod && e.key === 'v' && clipboardRef.current) {
                const newRowId = `row_pasted_${Date.now()}`;

                // Offset slightly for visibility (approx 2m south-east)
                const offsetLat = -0.00002;
                const offsetLng = 0.00002;

                const pastedPanels = clipboardRef.current.map((p, idx) => {
                    const movedCorners = p.corners.map(c => ({
                        lat: c.lat + offsetLat,
                        lng: c.lng + offsetLng
                    }));
                    const movedCenter = {
                        lat: p.center.lat + offsetLat,
                        lng: p.center.lng + offsetLng
                    };
                    return {
                        ...p,
                        id: `pasted_${Date.now()}_${idx}`,
                        rowId: newRowId,
                        corners: movedCorners,
                        center: movedCenter
                    };
                });

                setPlacedPanels(prev => [...prev, ...pastedPanels]);
                clipboardRef.current = JSON.parse(JSON.stringify(pastedPanels));
                setSelectedRowIds([newRowId]);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedRowIds, placedPanels, setPlacedPanels, setSelectedRowIds]);

    /* ---------- completed polygons (outlines) ---------- */
    useEffect(() => {
        if (!map || !mapsLib) return;

        outlinePolygonsRef.current.forEach(p => p.setMap(null));
        outlinePolygonsRef.current = [];

        polygonAreas.forEach(vertices => {
            const outline = new mapsLib.Polygon({
                paths: vertices,
                strokeColor: '#f59e0b',
                strokeOpacity: 0.7,
                strokeWeight: 2,
                fillColor: '#f59e0b',
                fillOpacity: 0.05,
                map,
                clickable: false,
                zIndex: 10,
            });
            outlinePolygonsRef.current.push(outline);
        });
    }, [map, mapsLib, polygonAreas]);

    /* ---------- panel rectangles ---------- */
    useEffect(() => {
        if (!map || !mapsLib) return;

        // Clear old panels
        panelOverlaysRef.current.forEach(p => p.setMap(null));
        panelOverlaysRef.current = [];

        placedPanels.forEach((panel, idx) => {
            const isRowSelected = selectedRowIds.includes(panel.rowId);
            const rect = new mapsLib.Polygon({
                paths: panel.corners,
                strokeColor: isRowSelected ? '#f59e0b' : '#ffffff',
                strokeOpacity: isRowSelected ? 0.9 : 0.6,
                strokeWeight: isRowSelected ? 1.5 : 0.4,
                fillColor: '#1e293b',
                fillOpacity: 0.95,
                map,
                clickable: true,
                draggable: true,
                zIndex: isRowSelected ? 20 : 15,
            });

            // Metadata for real-time drag logic
            rect._rowId = panel.rowId;
            rect._corners = panel.corners;
            panelOverlaysRef.current.push(rect);

            // Selection handling
            rect.addListener('click', (e) => {
                if (activeTool === 'select_row' || activeTool === 'select') {
                    // Be more robust with event detection
                    const domEvent = e.domEvent;
                    const isMulti = domEvent ? (domEvent.shiftKey || domEvent.metaKey || domEvent.ctrlKey) : false;

                    setSelectedRowIds(prev => {
                        if (isMulti) {
                            if (prev.includes(panel.rowId)) {
                                return prev.filter(id => id !== panel.rowId);
                            } else {
                                return [...prev, panel.rowId];
                            }
                        } else {
                            return [panel.rowId];
                        }
                    });
                }
            });

            // Removed the `dragstart` listener that was auto-selecting rows and causing sticky selections.

            // Drag handling
            rect.addListener('drag', () => {
                const isSelectionTool = activeTool === 'select_row' || activeTool === 'select';
                if (isSelectionTool && panel.rowId) {
                    const currentPath = rect.getPath().getArray();
                    const deltaLat = currentPath[0].lat() - panel.corners[0].lat;
                    const deltaLng = currentPath[0].lng() - panel.corners[0].lng;

                    // Visually move all other panels in current selection (or just this row if not selected)
                    const affectedRowIds = selectedRowIds.includes(panel.rowId) ? selectedRowIds : [panel.rowId];

                    panelOverlaysRef.current.forEach(otherRect => {
                        if (affectedRowIds.includes(otherRect._rowId) && otherRect !== rect) {
                            const movedPath = otherRect._corners.map(c => ({
                                lat: c.lat + deltaLat,
                                lng: c.lng + deltaLng
                            }));
                            otherRect.setPath(movedPath);
                        }
                    });
                }
            });

            rect.addListener('dragend', () => {
                const isSelectionTool = activeTool === 'select_row' || activeTool === 'select';
                const currentPath = rect.getPath().getArray().map(p => ({
                    lat: p.lat(),
                    lng: p.lng(),
                }));

                const deltaLat = currentPath[0].lat - panel.corners[0].lat;
                const deltaLng = currentPath[0].lng - panel.corners[0].lng;

                if (isSelectionTool && panel.rowId) {
                    const affectedRowIds = selectedRowIds.includes(panel.rowId) ? selectedRowIds : [panel.rowId];

                    // Final state update for all selected rows
                    setPlacedPanels(prev => prev.map(p => {
                        if (affectedRowIds.includes(p.rowId)) {
                            const movedCorners = p.corners.map(c => ({
                                lat: c.lat + deltaLat,
                                lng: c.lng + deltaLng,
                            }));
                            const movedCenter = {
                                lat: p.center.lat + deltaLat,
                                lng: p.center.lng + deltaLng,
                            };
                            return { ...p, corners: movedCorners, center: movedCenter };
                        }
                        return p;
                    }));
                } else {
                    // Standard single panel move logic (outside of row selection mode)
                    const newCenter = {
                        lat: (currentPath[0].lat + currentPath[2].lat) / 2,
                        lng: (currentPath[0].lng + currentPath[2].lng) / 2,
                    };
                    const parentPolygon = polygonAreas.find(poly => panelFitsInPolygon(currentPath, poly));
                    if (parentPolygon) {
                        setPlacedPanels(prev => prev.map(p => {
                            if (p.id === panel.id) return { ...p, corners: currentPath, center: newCenter };
                            return p;
                        }));
                    } else {
                        rect.setPath(panel.corners.map(c => new mapsLib.LatLng(c.lat, c.lng)));
                    }
                }
            });

            panelOverlaysRef.current.push(rect);
        });
    }, [map, mapsLib, placedPanels, polygonAreas, setPlacedPanels, activeTool, selectedRowIds, setSelectedRowIds]);

    /* ---------- active polyline + vertex markers ---------- */
    useEffect(() => {
        if (!map || !mapsLib) return;

        // cleanup
        if (polylineRef.current) { polylineRef.current.setMap(null); polylineRef.current = null; }
        if (closingLineRef.current) { closingLineRef.current.setMap(null); closingLineRef.current = null; }
        vertexMarkersRef.current.forEach(el => {
            if (el.setMap) el.setMap(null);
        });
        vertexMarkersRef.current = [];

        if (activeVertices.length === 0) return;

        // Main polyline
        const line = new mapsLib.Polyline({
            path: activeVertices,
            strokeColor: '#fbbf24',
            strokeOpacity: 1,
            strokeWeight: 2.5,
            map,
            clickable: false,
            zIndex: 20,
        });
        polylineRef.current = line;

        // Dashed closing preview
        if (activeVertices.length >= 3) {
            const closeLine = new mapsLib.Polyline({
                path: [activeVertices[activeVertices.length - 1], activeVertices[0]],
                strokeColor: '#fbbf24',
                strokeOpacity: 0.4,
                strokeWeight: 1.5,
                icons: [{
                    icon: { path: 'M 0,-1 0,1', strokeOpacity: 0.6, scale: 3 },
                    offset: '0',
                    repeat: '12px',
                }],
                map,
                clickable: false,
                zIndex: 19,
            });
            closingLineRef.current = closeLine;
        }

        // Vertex dots via OverlayView
        activeVertices.forEach((vertex, i) => {
            const isFirst = i === 0;
            const canClose = isFirst && activeVertices.length >= 3;

            const overlay = new mapsLib.OverlayView();
            overlay.onAdd = function () {
                const div = document.createElement('div');
                const size = canClose ? 16 : 10;
                Object.assign(div.style, {
                    width: size + 'px',
                    height: size + 'px',
                    borderRadius: '50%',
                    background: isFirst ? '#f59e0b' : '#fbbf24',
                    border: `2px solid ${canClose ? '#fff' : 'rgba(255,255,255,0.7)'}`,
                    cursor: canClose ? 'pointer' : 'default',
                    boxShadow: canClose
                        ? '0 0 12px rgba(245,158,11,0.6), 0 0 24px rgba(245,158,11,0.3)'
                        : '0 0 6px rgba(0,0,0,0.4)',
                    transition: 'transform 0.15s ease',
                    position: 'absolute',
                });

                if (canClose) {
                    div.addEventListener('mouseenter', () => { div.style.transform = 'scale(1.5)'; });
                    div.addEventListener('mouseleave', () => { div.style.transform = 'scale(1)'; });
                    div.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const newPolygon = [...activeVertices];

                        // Auto-fill with panels
                        const moduleW = selectedModule?.width_m || 1.134;
                        const moduleH = selectedModule?.length_m || 1.722;
                        const newPanels = generateGeodesicPanelGrid(
                            newPolygon,
                            moduleW,
                            moduleH,
                            panelConfig.rowGap,
                            panelConfig.colGap,
                            panelConfig.orientation,
                            panelConfig
                        );

                        setPolygonAreas(prev => [...prev, newPolygon]);
                        setPlacedPanels(prev => [...prev, ...newPanels]);
                        setActiveVertices([]);
                    });
                }

                this._div = div;
                this.getPanes().floatPane.appendChild(div);
            };
            overlay.draw = function () {
                const proj = this.getProjection();
                if (!proj) return;
                // Ensure NaN safety for vertex coordinates
                if (!Number.isFinite(vertex.lat) || !Number.isFinite(vertex.lng)) return;
                const pos = proj.fromLatLngToDivPixel(new mapsLib.LatLng(vertex.lat, vertex.lng));
                if (!pos) return;
                const size = canClose ? 16 : 10;
                this._div.style.left = (pos.x - size / 2) + 'px';
                this._div.style.top = (pos.y - size / 2) + 'px';
            };
            overlay.onRemove = function () {
                if (this._div) this._div.remove();
            };

            overlay.setMap(map);
            vertexMarkersRef.current.push(overlay);
        });

        return () => {
            if (polylineRef.current) { polylineRef.current.setMap(null); polylineRef.current = null; }
            if (closingLineRef.current) { closingLineRef.current.setMap(null); closingLineRef.current = null; }
            vertexMarkersRef.current.forEach(el => { if (el.setMap) el.setMap(null); });
            vertexMarkersRef.current = [];
        };
    }, [map, mapsLib, activeVertices, panelConfig, selectedModule, setPolygonAreas, setPlacedPanels, setActiveVertices]);

    return null;
}


// ─── Main Component ──────────────────────────────────────────────

export default function MapViewport({
    activeTool, polygonAreas, setPolygonAreas, activeVertices, setActiveVertices,
    placedPanels, setPlacedPanels, panelConfig, selectedModule,
    center, zoom, onCenterChange, onZoomChange,
    selectedRowIds, setSelectedRowIds
}) {
    if (!API_KEY) return (
        <div className="flex items-center justify-center h-full bg-surface text-red-400 text-sm">
            Missing Google Maps API Key
        </div>
    );

    const handleMapClick = useCallback((e) => {
        if (activeTool === 'draw') {
            if (!e.detail?.latLng) return;
            const { lat, lng } = e.detail.latLng;
            setActiveVertices(prev => [...prev, { lat, lng }]);
        } else if (activeTool === 'select' || activeTool === 'select_row') {
            // Clear selection when clicking on empty map space
            setSelectedRowIds([]);
        }
    }, [activeTool, setActiveVertices, setSelectedRowIds]);

    const handleCameraChange = useCallback((ev) => {
        if (onCenterChange) onCenterChange(ev.detail.center);
        if (onZoomChange) onZoomChange(ev.detail.zoom);
    }, [onCenterChange, onZoomChange]);

    return (
        <div className="absolute inset-0 bg-surface">
            <APIProvider apiKey={API_KEY}>
                <Map
                    center={center}
                    zoom={zoom}
                    onCameraChanged={handleCameraChange}
                    mapId={'DEMO_MAP_ID'}
                    gestureHandling={'greedy'}
                    disableDefaultUI={true}
                    mapTypeId={'satellite'}
                    tilt={0}
                    heading={0}
                    onClick={handleMapClick}
                    className="w-full h-full outline-none"
                >
                    <DrawingEngine
                        activeTool={activeTool}
                        polygonAreas={polygonAreas}
                        setPolygonAreas={setPolygonAreas}
                        activeVertices={activeVertices}
                        setActiveVertices={setActiveVertices}
                        placedPanels={placedPanels}
                        setPlacedPanels={setPlacedPanels}
                        panelConfig={panelConfig}
                        selectedModule={selectedModule}
                        selectedRowIds={selectedRowIds}
                        setSelectedRowIds={setSelectedRowIds}
                    />
                </Map>
            </APIProvider>
        </div>
    );
}

// Export for use in simulation payload and row transformations
export { generateGeodesicPanelGrid, updatePanelGeometry, redistributeRowPanels };
