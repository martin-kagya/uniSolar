import React, { useEffect, useRef, useCallback } from 'react';
import { APIProvider, Map, useMap, useMapsLibrary } from '@vis.gl/react-google-maps';
import DeckGLOverlay from './DeckGLOverlay';
import ObstaclePopover from './ObstaclePopover';
import { rebuildPanelFootprint } from '../../lib/panelGeometry';

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

// ─── Snap helpers ────────────────────────────────────────────
const M_PER_LAT = 111320.0;
function metersPerLon(lat) { return 111320.0 * Math.cos((lat * Math.PI) / 180); }

/** Snap to the nearest 45° angle from a reference point (used when Shift held). */
function snapToAngle(from, to, snapDeg = 45) {
    const mLon = metersPerLon(from.lat);
    const dx = (to.lng - from.lng) * mLon;
    const dy = (to.lat - from.lat) * M_PER_LAT;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 0.01) return { ...to };
    const rawAngle = Math.atan2(dy, dx);
    const snapRad = (snapDeg * Math.PI) / 180;
    const snapped = Math.round(rawAngle / snapRad) * snapRad;
    return {
        lat: from.lat + (dist * Math.sin(snapped)) / M_PER_LAT,
        lng: from.lng + (dist * Math.cos(snapped)) / mLon,
    };
}

/**
 * Snap to align with an existing vertex (same lat or same lng) when close.
 * Skips the most recent vertex to avoid placing on top of it.
 */
function snapToVertexAlignment(candidates, to, thresholdM = 3) {
    if (candidates.length === 0) return { ...to };

    const mLon = metersPerLon(to.lat);
    const last = candidates[candidates.length - 1];
    let bestLat = null, bestLng = null, bestDistLat = Infinity, bestDistLng = Infinity;

    for (const v of candidates) {
        // Skip the most recent vertex — don't snap back to it
        if (v === last) continue;

        const dlatM = Math.abs(to.lat - v.lat) * M_PER_LAT;
        const dlngM = Math.abs(to.lng - v.lng) * mLon;
        if (dlatM < thresholdM && dlatM < bestDistLat) { bestDistLat = dlatM; bestLat = v.lat; }
        if (dlngM < thresholdM && dlngM < bestDistLng) { bestDistLng = dlngM; bestLng = v.lng; }
    }

    return {
        lat: bestLat !== null ? bestLat : to.lat,
        lng: bestLng !== null ? bestLng : to.lng,
    };
}

// ─── Drawing Engine ──────────────────────────────────────────────
// Handles polygon drawing, outlines, selection and keyboard editing.
// Panel *generation* lives in Dashboard (from the unified geometry model);
// this component only draws boundaries and renders the deck.gl overlay.

function DrawingEngine({
    activeTool, polygonAreas, setPolygonAreas, activeVertices, setActiveVertices,
    placedPanels, setPlacedPanels, selectedRowIds, setSelectedRowIds,
    anchor, sun, viewMode, showLabels, showMeasurements, showStrings, showInverters, showSetbacks,
    strings, inverters, wiringPaths, setbackLines,
    obstacles, selectedObstacleId, setSelectedObstacleId, onUpdateObstacle, onDeleteObstacle, onAddObstacle, obstacleType,
}) {
    const map = useMap();
    const mapsLib = useMapsLibrary('maps');

    const outlinePolygonsRef = useRef([]);
    const polylineRef = useRef(null);
    const closingLineRef = useRef(null);
    const vertexMarkersRef = useRef([]);
    const clipboardRef = useRef(null);
    const guideLineRef = useRef(null);
    const guidePolyRef = useRef(null);
    const shiftRef = useRef(false);

    /* ---------- track Shift key for ortho toggle ---------- */
    useEffect(() => {
        const down = (e) => { if (e.key === 'Shift') shiftRef.current = true; };
        const up = (e) => { if (e.key === 'Shift') shiftRef.current = false; };
        window.addEventListener('keydown', down);
        window.addEventListener('keyup', up);
        return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up); };
    }, []);

    /* ---------- mousemove guide line ---------- */
    useEffect(() => {
        if (!map || !mapsLib) return;

        const listener = map.addListener('mousemove', (e) => {
            if (!e.latLng || activeVertices.length === 0) {
                if (guideLineRef.current) { guideLineRef.current.setMap(null); guideLineRef.current = null; }
                if (guidePolyRef.current) { guidePolyRef.current.setMap(null); guidePolyRef.current = null; }
                return;
            }
            const cursor = { lat: e.latLng.lat(), lng: e.latLng.lng() };
            const last = activeVertices[activeVertices.length - 1];

            // Default: snap to vertex alignment (same X/Y as existing points)
            // Shift held: snap to 45° angle from last vertex
            let target;
            if (shiftRef.current) {
                target = snapToAngle(last, cursor, 45);
            } else {
                target = snapToVertexAlignment(activeVertices, cursor, 3);
            }

            // Draw guide from last vertex to snapped cursor position
            if (!guideLineRef.current) {
                guideLineRef.current = new mapsLib.Polyline({
                    strokeColor: '#fbbf24',
                    strokeOpacity: 0.5,
                    strokeWeight: 1.5,
                    geodesic: false,
                    icons: [{
                        icon: { path: 'M 0,-1 0,1', strokeOpacity: 0.5, scale: 2 },
                        offset: '0',
                        repeat: '8px',
                    }],
                    map,
                    clickable: false,
                    zIndex: 18,
                });
            }
            guideLineRef.current.setPath([last, target]);

            // If ≥3 vertices, draw closing guide from target to first vertex
            if (activeVertices.length >= 3) {
                if (!guidePolyRef.current) {
                    guidePolyRef.current = new mapsLib.Polyline({
                        strokeColor: '#fbbf24',
                        strokeOpacity: 0.2,
                        strokeWeight: 1,
                        geodesic: false,
                        map,
                        clickable: false,
                        zIndex: 17,
                    });
                }
                guidePolyRef.current.setPath([target, activeVertices[0]]);
            }
        });

        return () => listener.remove();
    }, [map, mapsLib, activeVertices]);

    /* ---------- cursor ---------- */
    useEffect(() => {
        if (!map) return;
        map.setOptions({
            draggableCursor: activeTool === 'draw' || activeTool === 'place_obstacle' ? 'crosshair' : null,
        });
    }, [map, activeTool]);

    /* ---------- native click listener (bypasses deck.gl overlay canvas) ---------- */
    useEffect(() => {
        if (!map || !mapsLib) return;

        const listener = map.addListener('click', (e) => {
            if (!e.latLng) return;

            if (activeTool === 'draw') {
                let lat = e.latLng.lat();
                let lng = e.latLng.lng();
                if (activeVertices.length > 0) {
                    if (shiftRef.current) {
                        const snapped = snapToAngle(activeVertices[activeVertices.length - 1], { lat, lng }, 45);
                        lat = snapped.lat; lng = snapped.lng;
                    } else {
                        const snapped = snapToVertexAlignment(activeVertices, { lat, lng }, 3);
                        lat = snapped.lat; lng = snapped.lng;
                    }
                }
                setActiveVertices(prev => [...prev, { lat, lng }]);
            } else if (activeTool === 'place_obstacle') {
                if (onAddObstacle) onAddObstacle(obstacleType || 'tree', e.latLng.lat(), e.latLng.lng());
            } else if (activeTool === 'select') {
                setSelectedRowIds([]);
                setSelectedObstacleId(null);
            }
        });

        return () => listener.remove();
    }, [map, mapsLib, activeTool, activeVertices, setActiveVertices, setSelectedRowIds, onAddObstacle, setSelectedObstacleId, obstacleType]);

    /* ---------- keyboard interactions (delete, copy, paste, arrow nudge) ---------- */
    useEffect(() => {
        const handleKeyDown = (e) => {
            const isMod = e.metaKey || e.ctrlKey;

            if ((e.key === 'Backspace' || e.key === 'Delete') && selectedRowIds.length > 0) {
                setPlacedPanels(prev => prev.filter(p => !selectedRowIds.includes(p.rowId)));
                setSelectedRowIds([]);
            }

            if (isMod && e.key === 'c' && selectedRowIds.length > 0) {
                const combined = placedPanels.filter(p => selectedRowIds.includes(p.rowId));
                if (combined.length > 0) clipboardRef.current = JSON.parse(JSON.stringify(combined));
            }

            if (isMod && e.key === 'v' && clipboardRef.current) {
                const stamp = Date.now();
                const newRowId = `row_pasted_${stamp}`;
                const offsetM = 2.5;
                const pasted = clipboardRef.current.map((p, idx) => {
                    const movedCenter = {
                        x: p.centerMeters.x + offsetM,
                        y: p.centerMeters.y + offsetM,
                    };
                    const rebuilt = rebuildPanelFootprint(
                        { ...p, centerMeters: movedCenter },
                        p.gridRotationDeg, p.widthM, p.heightM
                    );
                    return { ...rebuilt, id: `pasted_${stamp}_${idx}`, rowId: newRowId };
                });
                setPlacedPanels(prev => [...prev, ...pasted]);
                clipboardRef.current = JSON.parse(JSON.stringify(pasted));
                setSelectedRowIds([newRowId]);
            }

            // Arrow key nudge: move selected rows
            if (selectedRowIds.length > 0 && ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                e.preventDefault();
                e.stopPropagation();
                const step = e.shiftKey ? 2.0 : 0.5;
                let dx = 0, dy = 0;
                if (e.key === 'ArrowUp') dy = step;
                else if (e.key === 'ArrowDown') dy = -step;
                else if (e.key === 'ArrowRight') dx = step;
                else if (e.key === 'ArrowLeft') dx = -step;

                const selectedSet = new Set(selectedRowIds);
                setPlacedPanels(prev => prev.map(p => {
                    if (!selectedSet.has(p.rowId)) return p;
                    const newCenter = { x: p.centerMeters.x + dx, y: p.centerMeters.y + dy };
                    return rebuildPanelFootprint(
                        { ...p, centerMeters: newCenter },
                        p.gridRotationDeg, p.widthM, p.heightM
                    );
                }));
            }
        };

        // Attach to map container with capture so it fires before Google Maps handlers
        const container = map?.getDiv?.() || window;
        container.addEventListener('keydown', handleKeyDown, true);
        window.addEventListener('keydown', handleKeyDown);
        return () => {
            container.removeEventListener('keydown', handleKeyDown, true);
            window.removeEventListener('keydown', handleKeyDown);
        };
    }, [selectedRowIds, placedPanels, setPlacedPanels, setSelectedRowIds, map]);

    /* ---------- completed polygon outlines ---------- */
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
                geodesic: false,
                map,
                clickable: false,
                zIndex: 10,
            });
            outlinePolygonsRef.current.push(outline);
        });
    }, [map, mapsLib, polygonAreas]);

    /* ---------- active polyline + vertex markers ---------- */
    useEffect(() => {
        if (!map || !mapsLib) return;

        if (polylineRef.current) { polylineRef.current.setMap(null); polylineRef.current = null; }
        if (closingLineRef.current) { closingLineRef.current.setMap(null); closingLineRef.current = null; }
        if (guideLineRef.current) { guideLineRef.current.setMap(null); guideLineRef.current = null; }
        if (guidePolyRef.current) { guidePolyRef.current.setMap(null); guidePolyRef.current = null; }
        vertexMarkersRef.current.forEach(el => { if (el.setMap) el.setMap(null); });
        vertexMarkersRef.current = [];

        if (activeVertices.length === 0) return;

        const line = new mapsLib.Polyline({
            path: activeVertices,
            strokeColor: '#fbbf24',
            strokeOpacity: 1,
            strokeWeight: 2.5,
            geodesic: false,
            map,
            clickable: false,
            zIndex: 20,
        });
        polylineRef.current = line;

        if (activeVertices.length >= 3) {
            const closeLine = new mapsLib.Polyline({
                path: [activeVertices[activeVertices.length - 1], activeVertices[0]],
                strokeColor: '#fbbf24',
                strokeOpacity: 0.4,
                strokeWeight: 1.5,
                geodesic: false,
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
                    pointerEvents: canClose ? 'auto' : 'none',
                    boxShadow: canClose
                        ? '0 0 12px rgba(245,158,11,0.6), 0 0 24px rgba(245,158,11,0.3)'
                        : '0 0 6px rgba(0,0,0,0.4)',
                    transition: 'transform 0.15s ease',
                    position: 'absolute',
                    zIndex: 30,
                });

                if (canClose) {
                    div.addEventListener('mouseenter', () => { div.style.transform = 'scale(1.5)'; });
                    div.addEventListener('mouseleave', () => { div.style.transform = 'scale(1)'; });
                    div.addEventListener('click', (e) => {
                        e.stopPropagation();
                        // Complete the polygon; Dashboard fills it with panels reactively.
                        setPolygonAreas(prev => [...prev, [...activeVertices]]);
                        setActiveVertices([]);
                    });
                }

                this._div = div;
                this.getPanes().floatPane.appendChild(div);
            };
            overlay.draw = function () {
                const proj = this.getProjection();
                if (!proj) return;
                if (!Number.isFinite(vertex.lat) || !Number.isFinite(vertex.lng)) return;
                // Safely access LatLng - use window.google.maps if available, fallback to mapsLib
                try {
                    const LatLngConstructor = mapsLib?.LatLng || window?.google?.maps?.LatLng;
                    if (!LatLngConstructor) return;
                    const pos = proj.fromLatLngToDivPixel(new LatLngConstructor(vertex.lat, vertex.lng));
                    if (!pos) return;
                    const size = canClose ? 16 : 10;
                    this._div.style.left = (pos.x - size / 2) + 'px';
                    this._div.style.top = (pos.y - size / 2) + 'px';
                } catch (err) {
                    // Silently fail if LatLng isn't available yet
                }
            };
            overlay.onRemove = function () { if (this._div) this._div.remove(); };

            overlay.setMap(map);
            vertexMarkersRef.current.push(overlay);
        });

        return () => {
            if (polylineRef.current) { polylineRef.current.setMap(null); polylineRef.current = null; }
            if (closingLineRef.current) { closingLineRef.current.setMap(null); closingLineRef.current = null; }
            if (guideLineRef.current) { guideLineRef.current.setMap(null); guideLineRef.current = null; }
            if (guidePolyRef.current) { guidePolyRef.current.setMap(null); guidePolyRef.current = null; }
            vertexMarkersRef.current.forEach(el => { if (el.setMap) el.setMap(null); });
            vertexMarkersRef.current = [];
        };
    }, [map, mapsLib, activeVertices, setPolygonAreas, setActiveVertices]);

    return (
        <>
        <DeckGLOverlay
            panels={placedPanels}
            anchor={anchor}
            selectedRowIds={selectedRowIds}
            setSelectedRowIds={setSelectedRowIds}
            sun={sun}
            viewMode={viewMode}
            showLabels={showLabels}
            showMeasurements={showMeasurements}
            showStrings={showStrings}
            showInverters={showInverters}
            showSetbacks={showSetbacks}
            strings={strings}
            inverters={inverters}
            wiringPaths={wiringPaths}
            setbackLines={setbackLines}
            obstacles={obstacles}
            selectedObstacleId={selectedObstacleId}
            setSelectedObstacleId={setSelectedObstacleId}
        />
        {selectedObstacleId && (() => {
            const obs = obstacles.find(o => o.id === selectedObstacleId);
            if (!obs) return null;
            return (
                <ObstaclePopover
                    obstacle={obs}
                    onUpdate={onUpdateObstacle}
                    onDelete={(id) => {
                        if (onDeleteObstacle) onDeleteObstacle(id);
                    }}
                    onClose={() => setSelectedObstacleId(null)}
                />
            );
        })()}
        </>
    );
}


// ─── Main Component ──────────────────────────────────────────────

export default function MapViewport({
    activeTool, polygonAreas, setPolygonAreas, activeVertices, setActiveVertices,
    placedPanels, setPlacedPanels, selectedRowIds, setSelectedRowIds,
    center, zoom, onCenterChange, onZoomChange,
    anchor, sun, viewMode, showLabels, showMeasurements, showStrings, showInverters, showSetbacks,
    strings, inverters, wiringPaths, setbackLines,
    obstacles = [], selectedObstacleId, setSelectedObstacleId, onAddObstacle, onUpdateObstacle, onDeleteObstacle, obstacleType,
}) {
    if (!API_KEY) return (
        <div className="flex items-center justify-center h-full bg-surface text-red-400 text-sm">
            Missing Google Maps API Key
        </div>
    );

    const handleCameraChange = useCallback((ev) => {
        if (onCenterChange) onCenterChange(ev.detail.center);
        if (onZoomChange) onZoomChange(ev.detail.zoom);
    }, [onCenterChange, onZoomChange]);

    const is3D = viewMode === '3d';

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
                    tilt={is3D ? 60 : 0}
                    heading={is3D ? 30 : 0}
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
                        selectedRowIds={selectedRowIds}
                        setSelectedRowIds={setSelectedRowIds}
                        anchor={anchor}
                        sun={sun}
                        viewMode={viewMode}
                        showLabels={showLabels}
                        showMeasurements={showMeasurements}
                        showStrings={showStrings}
                        showInverters={showInverters}
                        showSetbacks={showSetbacks}
                        strings={strings}
                        inverters={inverters}
                        wiringPaths={wiringPaths}
                        setbackLines={setbackLines}
                        obstacles={obstacles}
                        selectedObstacleId={selectedObstacleId}
                        setSelectedObstacleId={setSelectedObstacleId}
                        onUpdateObstacle={onUpdateObstacle}
                        onDeleteObstacle={onDeleteObstacle}
                        onAddObstacle={onAddObstacle}
                        obstacleType={obstacleType}
                    />
                </Map>
            </APIProvider>
        </div>
    );
}
