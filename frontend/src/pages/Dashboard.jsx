import React, { useState, useEffect, useCallback, useMemo, useRef, lazy, Suspense } from 'react';
import Sidebar from '../components/dashboard/Sidebar';
import MapViewport from '../components/dashboard/MapViewport';
import ResultsPanel from '../components/dashboard/ResultsPanel';
const ReportModal = lazy(() => import('../components/dashboard/ReportModal'));
const SizingHubModal = lazy(() => import('../components/dashboard/SizingHubModal'));
const DesignsModal = lazy(() => import('../components/dashboard/DesignsModal'));
import AddressSearch from '../components/dashboard/AddressSearch';
const AddPanelModal = lazy(() => import('../components/dashboard/AddPanelModal'));
import SunTimeline from '../components/dashboard/SunTimeline';
import { Play, Search, Box, Zap, Calendar, Loader2, PenTool, MousePointer, Undo2, Trash2, RotateCw, GripVertical, Rows, Plus, Layers, TreePine, Save, Building2, Factory, HelpCircle } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';
import {
    rowPitch as computeRowPitch,
    fillPolygonWithPanels,
    rebuildPanelFootprint,
    redistributeRow,
    computeSiteAnchor,
    panelCenterLatLng,
} from '../lib/panelGeometry';
import { solarPosition } from '../lib/solarPosition';
import { assignStrings, placeInverters, generateWiringPaths } from '../lib/electrical';
import { generateSetbackLines } from '../lib/setbacks';

export default function Dashboard() {
    const [config, setConfig] = useState({
        tilt: 15,
        azimuth: 180,
        rate: 1.90, // GHS 1.90 per kWh typical
        bias: 1.0,
        module: 'jinko_420',
        year: 2024,
        month: 6,          // June — near solar-noon default
        day: 21,
        hour: 12,          // fractional local hour for the sun scrubber
        systemCost: 20000,
        omCost: 320,
        use_ecg_tariff: true,
        customer_type: 'residential'
    });

    // Map render mode: '2d' photorealistic top-down / '3d' tilted inspect
    const [viewMode, setViewMode] = useState('2d');

    const [modules, setModules] = useState([]);
    const [results, setResults] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [activeTool, setActiveTool] = useState('select');
    const [obstacleType, setObstacleType] = useState('tree');
    const [moduleMenuOpen, setModuleMenuOpen] = useState(false);
    const [selectedRowIds, setSelectedRowIds] = useState([]);
    const [isReportOpen, setIsReportOpen] = useState(false);
    const [isSizingHubOpen, setIsSizingHubOpen] = useState(false);
    const [isAddPanelOpen, setIsAddPanelOpen] = useState(false);
    const [isDesignsOpen, setIsDesignsOpen] = useState(false);
    const [currentDesignId, setCurrentDesignId] = useState(null);
    const [currentDesignName, setCurrentDesignName] = useState('');
    const [showLabels, setShowLabels] = useState(true);
    const [showMeasurements, setShowMeasurements] = useState(false);
    const [showStrings, setShowStrings] = useState(false);
    const [showInverters, setShowInverters] = useState(false);
    const [showSetbacks, setShowSetbacks] = useState(false);
    const [panelsPerString, setPanelsPerString] = useState(18);
    const [inverterKw, setInverterKw] = useState(50);

    // Map View State
    const [mapCenter, setMapCenter] = useState({ lat: 8.26148, lng: -2.24555 });
    const [mapZoom, setMapZoom] = useState(18);

    // Drawing state
    const [polygonAreas, setPolygonAreas] = useState([]);   // completed polygon outlines
    const [activeVertices, setActiveVertices] = useState([]); // in-progress polygon
    const [placedPanels, setPlacedPanels] = useState([]);     // individual panel rectangles

    // Obstacle state
    const OBSTACLE_DEFAULTS = {
        tree:      { widthM: 3,   heightM: 6,   color: [34, 139, 34] },
        building:  { widthM: 8,   heightM: 5,   color: [120, 120, 120] },
        chimney:   { widthM: 1.5, heightM: 3,   color: [160, 82, 45] },
        other:     { widthM: 2,   heightM: 4,   color: [70, 130, 180] },
    };
    const [obstacles, setObstacles] = useState([]);
    const [selectedObstacleId, setSelectedObstacleId] = useState(null);

    const addObstacle = useCallback((type, lat, lng) => {
        const defaults = OBSTACLE_DEFAULTS[type] || OBSTACLE_DEFAULTS.other;
        const id = `obs_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
        const obstacle = { id, type, lat, lng, widthM: defaults.widthM, heightM: defaults.heightM };
        setObstacles(prev => [...prev, obstacle]);
        setSelectedObstacleId(id);
        return obstacle;
    }, []);

    const updateObstacle = useCallback((id, updates) => {
        setObstacles(prev => prev.map(o => o.id === id ? { ...o, ...updates } : o));
    }, []);

    const deleteObstacle = useCallback((id) => {
        setObstacles(prev => prev.filter(o => o.id !== id));
        if (selectedObstacleId === id) setSelectedObstacleId(null);
    }, [selectedObstacleId]);

    // Panel arrangement config
    const [panelConfig, setPanelConfig] = useState({
        orientation: 'portrait',   // 'portrait' or 'landscape'
        rowGap: 0.2,               // meters between modules (fine gap)
        colGap: 0.15,              // meters between strings
        gcr: 0.40,                 // Ground Coverage Ratio (replaces rowSpacingM)
        blockSizeM: 40.0,          // Size of sub-array blocks
        roadWidthM: 6.0,           // Width of main access roads
        rowPitchDisplay: '—',      // computed row pitch for display
    });

    // Currently selected module object
    const selectedModule = useMemo(
        () => modules.find(m => m.id === config.module) || null,
        [modules, config.module]
    );

    // Shared site anchor (centroid) — one meter frame for all polygons/panels.
    const siteAnchor = useMemo(() => computeSiteAnchor(polygonAreas), [polygonAreas]);

    // Live sun position for the selected date/time at the site, driving shadows.
    const sun = useMemo(
        () => solarPosition(
            mapCenter.lat, mapCenter.lng,
            config.year, config.month, config.day, config.hour
        ),
        [mapCenter.lat, mapCenter.lng, config.year, config.month, config.day, config.hour]
    );

    // Compute electrical layout (strings, inverters, wiring)
    const electricalLayout = useMemo(() => {
        if (placedPanels.length === 0) {
            return { strings: [], inverters: [], wiringPaths: [] };
        }

        const numInverters = Math.max(1, Math.ceil(placedPanels.length / panelsPerString / 6));
        const strings = assignStrings(placedPanels, panelsPerString, numInverters);
        const inverters = placeInverters(placedPanels, strings, siteAnchor, inverterKw);
        const wiringPaths = generateWiringPaths(placedPanels, strings, inverters, siteAnchor);

        return { strings, inverters, wiringPaths };
    }, [placedPanels, siteAnchor, panelsPerString, inverterKw]);

    // Compute setback lines for code compliance visualization
    const setbackLines = useMemo(() => {
        if (polygonAreas.length === 0) return [];
        
        // Use the first polygon for setback computation
        const firstPolygon = polygonAreas[0];
        return generateSetbackLines(firstPolygon, siteAnchor, {
            fireSetbackM: true,
            necClearanceM: true,
        });
    }, [polygonAreas, siteAnchor]);

    // Compute row pitch display whenever GCR, tilt, or module changes
    useEffect(() => {
        if (!selectedModule) return;
        const moduleLength = config.tilt > 45 ? (selectedModule.width_m || 1.134) : (selectedModule.length_m || 2.278);
        try {
            const pitch = computeRowPitch(moduleLength, config.tilt, panelConfig.gcr ?? 0.40);
            setPanelConfig(prev => ({ ...prev, rowPitchDisplay: pitch.toFixed(2) }));
        } catch {
            setPanelConfig(prev => ({ ...prev, rowPitchDisplay: '—' }));
        }
    }, [selectedModule, config.tilt, panelConfig.gcr]);

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                setActiveVertices([]);
                setSelectedObstacleId(null);
                setActiveTool('select');
            }
            if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
                e.preventDefault();
                setActiveVertices(prev => prev.slice(0, -1));
            }
            if ((e.key === 'Backspace' || e.key === 'Delete') && selectedObstacleId) {
                e.preventDefault();
                deleteObstacle(selectedObstacleId);
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [selectedObstacleId, deleteObstacle]);

    // Fetch modules on mount
    useEffect(() => {
        fetch('/modules')
            .then(res => res.json())
            .then(data => {
                setModules(data);
                if (data.length > 0) setConfig(prev => ({ ...prev, module: data[0].id }));
                // Show panel config modal once per session
                if (!sessionStorage.getItem('panelModalShown')) {
                    setIsAddPanelOpen(true);
                    sessionStorage.setItem('panelModalShown', '1');
                }
            })
            .catch(err => console.error("Failed to fetch modules:", err));
    }, []);

    // Recompute the unified panel set whenever the layout inputs change.
    // These panels ARE the rendered, selectable, and simulated dataset.
    const handleRecalculatePanels = useCallback(() => {
        if (polygonAreas.length === 0 || !selectedModule) return;

        const moduleSpec = {
            length: selectedModule.length_m || 2.278,
            width: selectedModule.width_m || 1.134,
            wattage: selectedModule.power_wp || 420,
        };

        const anchor = computeSiteAnchor(polygonAreas);
        const allPanels = [];
        polygonAreas.forEach((polygon, i) => {
            const panels = fillPolygonWithPanels(
                polygon,
                anchor,
                moduleSpec,
                config.tilt,
                config.azimuth,
                panelConfig.gcr ?? 0.40,
                panelConfig.orientation,
                panelConfig.colGap,
                panelConfig.blockSizeM,
                panelConfig.roadWidthM,
                `area${i}`,
            );
            allPanels.push(...panels);
        });
        setPlacedPanels(allPanels);
    }, [polygonAreas, selectedModule, panelConfig, config.tilt, config.azimuth]);

    // Auto-recalculate when panel config changes (debounced for slider drag)
    const recalcTimeoutRef = useRef(null);
    useEffect(() => {
        if (recalcTimeoutRef.current) clearTimeout(recalcTimeoutRef.current);
        recalcTimeoutRef.current = setTimeout(() => {
            handleRecalculatePanels();
        }, 50);
        return () => { if (recalcTimeoutRef.current) clearTimeout(recalcTimeoutRef.current); };
    }, [panelConfig, config.module, config.tilt, config.azimuth, handleRecalculatePanels]);

    const handleConfigUpdate = (key, value) => {
        setConfig(prev => ({ ...prev, [key]: value }));
    };

    const handlePanelConfigUpdate = (key, value) => {
        setPanelConfig(prev => ({ ...prev, [key]: value }));
    };

    // Computed capacity from placed panels
    const totalCapacityKw = useMemo(() => {
        if (!selectedModule || placedPanels.length === 0) return 0;
        return (placedPanels.length * selectedModule.power_wp) / 1000;
    }, [placedPanels, selectedModule]);

    const handleRunSimulation = async () => {
        setLoading(true);
        setError(null);
        setResults(null);

        if (!config.module) {
            setError("Please select a module.");
            setLoading(false);
            return;
        }

        if (placedPanels.length === 0) {
            setError("Draw an array area first — no panels to simulate.");
            setLoading(false);
            return;
        }

        try {
            // Build panels payload with lat/lng from the unified model
            const panelsPayload = placedPanels.map(p => {
                const ll = panelCenterLatLng(p, siteAnchor);
                return {
                    id: p.id,
                    x: ll.lng,   // longitude
                    y: ll.lat,   // latitude
                    rotation: p.gridRotationDeg || 0,
                };
            });

            const payload = {
                latitude: mapCenter.lat,
                longitude: mapCenter.lng,
                capacity_kw: totalCapacityKw,
                tilt: config.tilt,
                azimuth: config.azimuth,
                gcr: panelConfig.gcr ?? 0.40,
                electricity_rate: config.rate,
                module_name: config.module,
                year: config.year,
                irradiance_bias: config.bias,
                system_cost_kw: config.systemCost,
                om_cost_kw: config.omCost,
                use_ecg_tariff: config.use_ecg_tariff,
                customer_type: config.customer_type,
                panels: panelsPayload,
                features: obstacles.map(o => ({
                    type: o.type,
                    x: o.lng,
                    y: o.lat,
                    width: o.widthM,
                    height: o.heightM,
                }))
            };

            const response = await fetch('/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || `Simulation failed: ${response.statusText}`);
            }

            const data = await response.json();
            setResults({
                annualEnergy: data.results.annual_energy_kwh,
                npv: data.financials.npv,
                irr: data.financials.irr,
                lcoe: data.financials.lcoe,
                payback: data.financials.payback_years,
                panelCount: placedPanels.length,
                capacityKw: totalCapacityKw,
                rate: config.rate,
                dailyCurve: data.hourly_curve.map((val, idx) => ({
                    hour: `${idx}:00`,
                    val: val
                })),
                probabilisticResults: data.probabilistic_results,
                losses: data.results.losses,
                lossParams: data.loss_params,
                monthlyEnergy: data.results.monthly_energy,
                capex: data.financials.capex,
                annualSavingsY1: data.financials.annual_savings_y1,
                effectiveTariffY1: data.financials.effective_tariff_y1,
                lifetimeSavings: data.financials.lifetime_savings,
                tariffMode: data.financials.tariff_mode,
                financials: data.financials,
                environmentalMetrics: data.environmental_metrics,
                tilt: config.tilt,
                azimuth: config.azimuth,
                gcr: panelConfig.gcr
            });
        } catch (err) {
            console.error(err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    // Flip a single panel's orientation: swap footprint + module dimensions.
    const flipPanel = (p, newOrientation) => {
        const rebuilt = rebuildPanelFootprint(p, p.gridRotationDeg, p.heightM, p.widthM);
        return {
            ...rebuilt,
            orientation: newOrientation,
            moduleLengthM: p.moduleWidthM,
            moduleWidthM: p.moduleLengthM,
        };
    };

    const handleRowOrientationToggle = useCallback(() => {
        if (selectedRowIds.length === 0) return;
        setPlacedPanels(prev => {
            let nextPanels = [...prev];
            selectedRowIds.forEach(rowId => {
                const rowPanels = nextPanels.filter(p => p.rowId === rowId);
                if (rowPanels.length === 0) return;
                const newOrientation = (rowPanels[0].orientation || 'portrait') === 'portrait' ? 'landscape' : 'portrait';

                const flipped = rowPanels.map(p => flipPanel(p, newOrientation));
                const redistributed = newOrientation === 'landscape'
                    ? redistributeRow(flipped, panelConfig.colGap)
                    : flipped;

                const byId = new Map(redistributed.map(r => [r.id, r]));
                nextPanels = nextPanels.map(p => byId.get(p.id) || p);
            });
            return nextPanels;
        });
    }, [selectedRowIds, panelConfig.colGap]);

    const handleRowRotationChange = useCallback((newRotation) => {
        if (selectedRowIds.length === 0) return;
        setPlacedPanels(prev => prev.map(p =>
            selectedRowIds.includes(p.rowId)
                ? rebuildPanelFootprint(p, newRotation, p.widthM, p.heightM)
                : p
        ));
    }, [selectedRowIds]);

    const handleGlobalOrientationToggle = useCallback(() => {
        setPlacedPanels(prev => {
            const newOrientation = panelConfig.orientation === 'portrait' ? 'landscape' : 'portrait';

            const rows = {};
            prev.forEach(p => {
                (rows[p.rowId] ||= []).push(p);
            });

            const processed = Object.values(rows).flatMap(rowPanels => {
                const flipped = rowPanels.map(p =>
                    p.orientation === newOrientation ? p : flipPanel(p, newOrientation)
                );
                return newOrientation === 'landscape'
                    ? redistributeRow(flipped, panelConfig.colGap)
                    : flipped;
            });

            handlePanelConfigUpdate('orientation', newOrientation);
            return processed;
        });
    }, [panelConfig.orientation, panelConfig.colGap]);

    const handleClearAll = () => {
        setPolygonAreas([]);
        setPlacedPanels([]);
        setActiveVertices([]);
    };

    // ---- Design Save / Load / Delete ----------------------------------------
    const serializeDesign = (name) => ({
        name,
        latitude: mapCenter.lat,
        longitude: mapCenter.lng,
        map_zoom: mapZoom,
        config_json: config,
        polygon_areas_json: polygonAreas,
        obstacles_json: obstacles,
        panel_config_json: {
            orientation: panelConfig.orientation,
            rowGap: panelConfig.rowGap,
            colGap: panelConfig.colGap,
            gcr: panelConfig.gcr,
            blockSizeM: panelConfig.blockSizeM,
            roadWidthM: panelConfig.roadWidthM,
        },
        electrical_json: { panelsPerString, inverterKw },
        placed_panels_json: placedPanels.length > 0 ? placedPanels : null,
    });

    const handleSaveDesign = async (name) => {
        const body = serializeDesign(name);
        let url, method;
        if (currentDesignId) {
            url = `/designs/${currentDesignId}`;
            method = 'PUT';
        } else {
            url = '/designs';
            method = 'POST';
        }
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || 'Failed to save design');
        }
        const data = await res.json();
        setCurrentDesignId(data.id);
        setCurrentDesignName(name);
    };

    const handleLoadDesign = async (designId) => {
        const res = await fetch(`/designs/${designId}`);
        if (!res.ok) throw new Error('Failed to load design');
        const d = await res.json();

        // Restore all state
        setConfig(d.config_json);
        setMapCenter({ lat: d.latitude, lng: d.longitude });
        setMapZoom(d.map_zoom || 18);
        setPolygonAreas(d.polygon_areas_json || []);
        setObstacles(d.obstacles_json || []);
        setPlacedPanels(d.placed_panels_json || []);
        if (d.panel_config_json) {
            setPanelConfig(prev => ({
                ...prev,
                ...d.panel_config_json,
            }));
        }
        if (d.electrical_json) {
            setPanelsPerString(d.electrical_json.panelsPerString || 18);
            setInverterKw(d.electrical_json.inverterKw || 50);
        }
        setCurrentDesignId(d.id);
        setCurrentDesignName(d.name);
        setResults(null); // clear previous results
    };

    const handleDeleteDesign = async (designId) => {
        const res = await fetch(`/designs/${designId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete design');
        if (currentDesignId === designId) {
            setCurrentDesignId(null);
            setCurrentDesignName('');
        }
    };

    const currentModule = selectedModule;

    return (
        <div className="flex h-screen w-screen bg-surface overflow-hidden">

            {/* Sidebar */}
            <Sidebar
                config={config}
                updateConfig={handleConfigUpdate}
                panelConfig={panelConfig}
                updatePanelConfig={handlePanelConfigUpdate}
                panelCount={placedPanels.length}
                totalCapacityKw={totalCapacityKw}
                selectedModule={selectedModule}
                onViewReport={() => results && setIsReportOpen(true)}
                onOpenSizingHub={() => setIsSizingHubOpen(true)}
                selectedRowIds={selectedRowIds}
                placedPanels={placedPanels}
                onToggleRowOrientation={handleRowOrientationToggle}
                onChangeRowRotation={handleRowRotationChange}
                onToggleGlobalOrientation={handleGlobalOrientationToggle}
                obstacles={obstacles}
                selectedObstacleId={selectedObstacleId}
                setSelectedObstacleId={setSelectedObstacleId}
                onUpdateObstacle={updateObstacle}
                onDeleteObstacle={deleteObstacle}
            />

            {/* Main Content Area */}
            <div className="flex-1 ml-[280px] relative flex flex-col">

                {/* Toolbar Header */}
                <header className="h-[52px] bg-surface-raised border-b border-border-subtle px-3 flex items-center gap-2 z-[100] relative">
                    {/* Search */}
                    <div className="shrink-0">
                    <AddressSearch
                        onSelectLocation={({ lat, lng }) => {
                            setMapCenter({ lat, lng });
                            setMapZoom(19); // Zoom in on selection
                        }}
                    />
                    </div>

                    {/* Tools */}
                    <div className="flex items-center gap-1.5 min-w-0 flex-1 justify-end">
                        {/* Drawing Tools — compact icon-only */}
                        <div className="flex items-center bg-glass-bg rounded-lg p-0.5 gap-0.5 border border-border-subtle">
                            <button
                                onClick={() => setActiveTool('select')}
                                className={`flex items-center justify-center w-7 h-7 rounded-md transition-all ${activeTool === 'select'
                                    ? 'bg-brand-gold/10 text-brand-gold'
                                    : 'text-text-dim hover:text-text-secondary'
                                    }`}
                                title="Select"
                            >
                                <MousePointer className="w-3.5 h-3.5" />
                            </button>
                            <button
                                onClick={() => setActiveTool('draw')}
                                className={`flex items-center justify-center w-7 h-7 rounded-md transition-all ${activeTool === 'draw'
                                    ? 'bg-brand-gold/10 text-brand-gold'
                                    : 'text-text-dim hover:text-text-secondary'
                                    }`}
                                title="Draw area"
                            >
                                <PenTool className="w-3.5 h-3.5" />
                            </button>
                            <button
                                onClick={() => setActiveTool('select_row')}
                                className={`flex items-center justify-center w-7 h-7 rounded-md transition-all ${activeTool === 'select_row'
                                    ? 'bg-brand-gold/10 text-brand-gold'
                                    : 'text-text-dim hover:text-text-secondary'
                                    }`}
                                title="Select row"
                            >
                                <GripVertical className="w-3.5 h-3.5" />
                            </button>
                            <button
                                onClick={() => setActiveTool('place_obstacle')}
                                className={`flex items-center justify-center w-7 h-7 rounded-md transition-all ${activeTool === 'place_obstacle'
                                    ? 'bg-brand-gold/10 text-brand-gold'
                                    : 'text-text-dim hover:text-text-secondary'
                                    }`}
                                title="Place obstacle"
                            >
                                <TreePine className="w-3.5 h-3.5" />
                            </button>
                        </div>

                        {/* Config dropdown — Year + Module + Capacity in one compact toggle */}
                        <div className="relative">
                            <button
                                onClick={() => setModuleMenuOpen(!moduleMenuOpen)}
                                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-semibold transition-colors border border-border-subtle ${moduleMenuOpen ? 'bg-glass-bg-strong text-text-primary' : 'text-text-muted hover:text-text-primary hover:bg-glass-bg-strong'}`}
                            >
                                <Calendar className="w-3.5 h-3.5 text-text-dim" />
                                <span>{config.year}</span>
                                <span className="text-text-dim">·</span>
                                <Box className="w-3.5 h-3.5 text-text-dim" />
                                <span className="truncate max-w-[70px]">{currentModule ? currentModule.name : 'Select'}</span>
                                {totalCapacityKw > 0 && (
                                    <>
                                        <span className="text-text-dim">·</span>
                                        <Zap className="w-3.5 h-3.5 text-text-dim" />
                                        <span>{totalCapacityKw.toFixed(1)} kWp</span>
                                    </>
                                )}
                            </button>

                            {moduleMenuOpen && (
                                <>
                                    <div className="fixed inset-0 z-[99]" onClick={() => setModuleMenuOpen(false)} />
                                    <div className="absolute top-full right-0 mt-2 w-72 bg-surface-dropdown rounded-xl shadow-2xl border border-border-theme py-1 z-[101] animate-in fade-in slide-in-from-top-2 duration-200">
                                        <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
                                            <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Configuration</p>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); setModuleMenuOpen(false); setIsAddPanelOpen(true); }}
                                                className="flex items-center gap-1 text-[10px] font-bold text-amber-400 hover:text-amber-300 transition-colors px-2 py-1 rounded-lg hover:bg-amber-500/10"
                                                title="Add custom panel"
                                            >
                                                <Plus className="w-3 h-3" />
                                                Add Panel
                                            </button>
                                        </div>

                                        {/* Year row */}
                                        <div className="px-3 py-2 border-b border-border-subtle">
                                            <p className="text-[9px] font-bold text-text-dim uppercase mb-1">Simulation Year</p>
                                            <div className="flex gap-1">
                                                {[2022, 2023, 2024, 2025].map(y => (
                                                    <button
                                                        key={y}
                                                        onClick={(e) => { e.stopPropagation(); handleConfigUpdate('year', y); }}
                                                        className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${config.year === y
                                                            ? 'bg-brand-gold/15 text-brand-gold border border-brand-gold/30'
                                                            : 'bg-glass-bg text-text-dim hover:text-text-secondary border border-transparent'
                                                        }`}
                                                    >
                                                        {y}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        {/* Module list */}
                                        <div className="max-h-64 overflow-y-auto">
                                            {modules.map(m => (
                                                <div
                                                    key={m.id}
                                                    onClick={() => {
                                                        handleConfigUpdate('module', m.id);
                                                        setModuleMenuOpen(false);
                                                    }}
                                                    className={`px-4 py-3 cursor-pointer transition-colors flex justify-between items-center border-b border-border-subtle last:border-0 ${m.id === config.module
                                                        ? 'bg-brand-gold/10 hover:bg-brand-gold/15'
                                                        : 'hover:bg-glass-bg'
                                                    }`}
                                                >
                                                    <div className="flex flex-col min-w-0 flex-1 pr-4">
                                                        <span className={`text-xs font-bold truncate flex items-center gap-1.5 ${m.id === config.module ? 'text-brand-gold' : 'text-text-secondary'}`}>
                                                            <span className="truncate">{m.name}</span>
                                                            {m.custom && <span className="shrink-0 px-1 py-0.5 rounded text-[8px] font-bold bg-amber-500/15 text-amber-400 uppercase">Custom</span>}
                                                        </span>
                                                        <div className="text-[9px] text-text-dim mt-0.5 flex items-center gap-1.5 truncate">
                                                            <span className="font-mono">{m.width_m}×{m.length_m}m</span>
                                                            {m.cell_technology && <span>• {m.cell_technology}</span>}
                                                        </div>
                                                    </div>
                                                    <span className={`text-xs font-bold shrink-0 ${m.id === config.module ? 'text-brand-gold' : 'text-text-primary'}`}>{m.power_wp}W</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>

                        {/* Run Button */}
                        <button
                            onClick={handleRunSimulation}
                            disabled={loading}
                            className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 bg-gradient-to-r from-brand-gold to-orange-500 hover:shadow-[0_0_25px_rgba(245,158,11,0.3)] disabled:opacity-50 text-white rounded-lg text-[11px] font-bold transition-all transform active:scale-95"
                        >
                            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
                            {loading ? 'SIMULATING...' : 'RUN SIMULATION'}
                        </button>

                        {/* 2D / 3D view toggle */}
                        <div className="flex items-center bg-glass-bg p-0.5 rounded-lg border border-border-subtle h-7">
                            <button
                                onClick={() => setViewMode('2d')}
                                className={`flex items-center gap-1 px-2 h-full text-[10px] font-bold rounded-md transition-all ${viewMode === '2d' ? 'bg-brand-gold text-white shadow' : 'text-text-dim hover:text-text-secondary'}`}
                                title="Top-down photorealistic view"
                            >
                                <Layers className="w-3 h-3" />
                                2D
                            </button>
                            <button
                                onClick={() => setViewMode('3d')}
                                className={`flex items-center gap-1 px-2 h-full text-[10px] font-bold rounded-md transition-all ${viewMode === '3d' ? 'bg-brand-gold text-white shadow' : 'text-text-dim hover:text-text-secondary'}`}
                                title="Tilted 3D inspect view"
                            >
                                <Box className="w-3 h-3" />
                                3D
                            </button>
                        </div>

                        {/* Overlay toggles */}
                        <div className="flex items-center bg-glass-bg p-0.5 rounded-lg border border-border-subtle h-7 gap-0.5">
                            <button
                                onClick={() => setShowLabels(!showLabels)}
                                className={`flex items-center justify-center w-6 h-full rounded-md transition-all ${showLabels ? 'bg-brand-gold/20 text-brand-gold' : 'text-text-dim hover:text-text-secondary'}`}
                                title="Show row/block labels"
                            >
                                <span className="text-[9px] font-bold">LBL</span>
                            </button>
                            <button
                                onClick={() => setShowMeasurements(!showMeasurements)}
                                className={`flex items-center justify-center w-6 h-full rounded-md transition-all ${showMeasurements ? 'bg-brand-gold/20 text-brand-gold' : 'text-text-dim hover:text-text-secondary'}`}
                                title="Show inter-row measurements"
                            >
                                <span className="text-[9px] font-bold">DIM</span>
                            </button>
                            <button
                                onClick={() => setShowStrings(!showStrings)}
                                className={`flex items-center justify-center w-6 h-full rounded-md transition-all ${showStrings ? 'bg-brand-gold/20 text-brand-gold' : 'text-text-dim hover:text-text-secondary'}`}
                                title="Show electrical strings"
                            >
                                <span className="text-[9px] font-bold">STR</span>
                            </button>
                            <button
                                onClick={() => setShowInverters(!showInverters)}
                                className={`flex items-center justify-center w-6 h-full rounded-md transition-all ${showInverters ? 'bg-brand-gold/20 text-brand-gold' : 'text-text-dim hover:text-text-secondary'}`}
                                title="Show inverters and wiring"
                            >
                                <span className="text-[9px] font-bold">INV</span>
                            </button>
                            <button
                                onClick={() => setShowSetbacks(!showSetbacks)}
                                className={`flex items-center justify-center w-6 h-full rounded-md transition-all ${showSetbacks ? 'bg-brand-gold/20 text-brand-gold' : 'text-text-dim hover:text-text-secondary'}`}
                                title="Show fire/NEC setbacks"
                            >
                                <span className="text-[9px] font-bold">SET</span>
                            </button>
                        </div>

                        {/* Save / Load designs */}
                        <button
                            onClick={() => setIsDesignsOpen(true)}
                            className="flex items-center gap-1.5 px-3 h-9 text-[10px] font-bold rounded-lg bg-glass-bg border border-border-subtle text-text-dim hover:text-brand-gold hover:bg-brand-gold/10 transition-all"
                            title="Save or load designs"
                        >
                            <Save className="w-3.5 h-3.5" />
                            {currentDesignName ? currentDesignName : 'DESIGNS'}
                        </button>

                        <ThemeToggle />
                    </div>
                </header>

                {/* Map Viewport */}
                <div className="flex-1 relative">
                    <MapViewport
                        activeTool={activeTool}
                        polygonAreas={polygonAreas}
                        setPolygonAreas={setPolygonAreas}
                        activeVertices={activeVertices}
                        setActiveVertices={setActiveVertices}
                        placedPanels={placedPanels}
                        setPlacedPanels={setPlacedPanels}
                        selectedRowIds={selectedRowIds}
                        setSelectedRowIds={setSelectedRowIds}
                        center={mapCenter}
                        zoom={mapZoom}
                        onCenterChange={setMapCenter}
                        onZoomChange={setMapZoom}
                        anchor={siteAnchor}
                        sun={sun}
                        viewMode={viewMode}
                        showLabels={showLabels}
                        showMeasurements={showMeasurements}
                        showStrings={showStrings}
                        showInverters={showInverters}
                        showSetbacks={showSetbacks}
                        strings={electricalLayout.strings}
                        inverters={electricalLayout.inverters}
                        wiringPaths={electricalLayout.wiringPaths}
                        setbackLines={setbackLines}
                        obstacles={obstacles}
                        selectedObstacleId={selectedObstacleId}
                        setSelectedObstacleId={setSelectedObstacleId}
                        onAddObstacle={addObstacle}
                        obstacleType={obstacleType}
                        onUpdateObstacle={updateObstacle}
                        onDeleteObstacle={deleteObstacle}
                    />

                    {/* Sun timeline scrubber (only meaningful once panels exist) */}
                    {placedPanels.length > 0 && (
                        <SunTimeline
                            year={config.year}
                            month={config.month}
                            day={config.day}
                            hour={config.hour}
                            sun={sun}
                            onChange={(key, value) => handleConfigUpdate(key, value)}
                        />
                    )}

                    {/* Active Tool Indicator */}
                    {activeTool === 'draw' && (
                        <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-surface-overlay/90 text-brand-gold px-4 py-2.5 rounded-xl border border-brand-gold/20 text-xs font-semibold z-50 backdrop-blur-md flex items-center gap-3">
                            <PenTool className="w-3.5 h-3.5" />
                            <span>
                                {activeVertices.length === 0
                                    ? 'Click on the map to start drawing a panel area'
                                    : activeVertices.length < 3
                                        ? `${activeVertices.length} vertices placed — need at least 3`
                                        : `${activeVertices.length} vertices — click first point to close`
                                }
                            </span>
                            {activeVertices.length > 0 && (
                                <>
                                    <div className="w-px h-4 bg-border-theme" />
                                    <button
                                        onClick={() => setActiveVertices(prev => prev.slice(0, -1))}
                                        className="text-text-muted hover:text-text-primary transition-colors"
                                        title="Undo last vertex (⌘Z)"
                                    >
                                        <Undo2 className="w-3.5 h-3.5" />
                                    </button>
                                    <button
                                        onClick={() => setActiveVertices([])}
                                        className="text-text-muted hover:text-red-400 transition-colors"
                                        title="Cancel (Esc)"
                                    >
                                        <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                </>
                            )}
                        </div>
                    )}

                    {activeTool === 'place_obstacle' && (
                        <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-surface-overlay/90 text-emerald-400 px-4 py-2.5 rounded-xl border border-emerald-500/20 text-xs font-semibold z-50 backdrop-blur-md flex items-center gap-3">
                            <TreePine className="w-3.5 h-3.5" />
                            <span>Click map to place</span>
                            <div className="w-px h-4 bg-border-theme" />
                            <div className="flex gap-1">
                                {[
                                    { key: 'tree', Icon: TreePine, label: 'Tree' },
                                    { key: 'building', Icon: Building2, label: 'Building' },
                                    { key: 'chimney', Icon: Factory, label: 'Chimney' },
                                    { key: 'other', Icon: HelpCircle, label: 'Other' },
                                ].map(({ key, Icon, label }) => (
                                    <button
                                        key={key}
                                        onClick={() => setObstacleType(key)}
                                        className={`flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-bold transition-all ${
                                            obstacleType === key
                                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                                : 'text-text-dim hover:text-text-secondary border border-transparent'
                                        }`}
                                        title={label}
                                    >
                                        <Icon className="w-3 h-3" />
                                        {label}
                                    </button>
                                ))}
                            </div>
                            <div className="w-px h-4 bg-border-theme" />
                            <button
                                onClick={() => { setActiveTool('select'); setSelectedObstacleId(null); }}
                                className="text-text-muted hover:text-red-400 transition-colors"
                                title="Cancel (Esc)"
                            >
                                <Trash2 className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    )}

                    {/* Panel count + capacity badge */}
                    {placedPanels.length > 0 && (
                        <div className="absolute bottom-6 left-6 bg-surface-overlay/90 text-text-primary px-4 py-2.5 rounded-xl border border-border-theme text-xs font-semibold z-50 backdrop-blur-md flex items-center gap-3">
                            <div className="flex items-center gap-2">
                                <span className="text-brand-gold font-bold">{placedPanels.length}</span>
                                <span className="text-text-muted">panels</span>
                                <span className="text-text-dim">·</span>
                                <span className="text-brand-gold font-bold">{totalCapacityKw.toFixed(1)}</span>
                                <span className="text-text-muted">kWp</span>
                            </div>
                            <div className="w-px h-4 bg-border-theme" />
                            <button
                                onClick={handleRecalculatePanels}
                                className="text-text-dim hover:text-brand-gold transition-colors"
                                title="Recalculate panel layout"
                            >
                                <RotateCw className="w-3.5 h-3.5" />
                            </button>
                            <button
                                onClick={handleClearAll}
                                className="text-text-dim hover:text-red-400 transition-colors"
                                title="Clear all"
                            >
                                <Trash2 className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    )}

                    {/* Error Toast */}
                    {error && (
                        <div
                            className="absolute top-4 left-1/2 -translate-x-1/2 bg-red-500/10 text-red-400 px-4 py-2 rounded-lg border border-red-500/20 text-sm font-semibold shadow-lg z-50 backdrop-blur-md cursor-pointer"
                            onClick={() => setError(null)}
                        >
                            {error}
                        </div>
                    )}

                    {/* Simulation Results Card */}
                    <ResultsPanel
                        results={results}
                        isVisible={!!results}
                        onViewReport={() => setIsReportOpen(true)}
                    />

                    {/* Full Audit Report Modal */}
                    <Suspense fallback={null}>
                        <ReportModal
                            isOpen={isReportOpen}
                            onClose={() => setIsReportOpen(false)}
                            results={results}
                        />
                    </Suspense>

                    {/* Sizing Hub Modal */}
                    <Suspense fallback={null}>
                        <SizingHubModal
                            isOpen={isSizingHubOpen}
                            onClose={() => setIsSizingHubOpen(false)}
                        />
                    </Suspense>

                    {/* Add Panel Modal */}
                    <Suspense fallback={null}>
                        <AddPanelModal
                            isOpen={isAddPanelOpen}
                            onClose={() => setIsAddPanelOpen(false)}
                            existingModules={modules}
                            onModuleSelected={(m) => {
                                handleConfigUpdate('module', m.id);
                            }}
                            onModuleAdded={(newModule) => {
                                setModules(prev => [...prev, newModule]);
                                handleConfigUpdate('module', newModule.id);
                            }}
                        />
                    </Suspense>

                    {/* Designs Modal */}
                    <Suspense fallback={null}>
                        <DesignsModal
                            isOpen={isDesignsOpen}
                            onClose={() => setIsDesignsOpen(false)}
                            onSave={handleSaveDesign}
                            onLoad={handleLoadDesign}
                            onDelete={handleDeleteDesign}
                            currentDesignId={currentDesignId}
                            currentDesignName={currentDesignName}
                        />
                    </Suspense>
                </div>

            </div>
        </div>
    );
}
