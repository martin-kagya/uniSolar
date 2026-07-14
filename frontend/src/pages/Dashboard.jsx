import React, { useState, useEffect, useCallback, useMemo } from 'react';
import Sidebar from '../components/dashboard/Sidebar';
import MapViewport, { generateGeodesicPanelGrid, updatePanelGeometry, redistributeRowPanels } from '../components/dashboard/MapViewport';
import ResultsPanel from '../components/dashboard/ResultsPanel';
import ReportModal from '../components/dashboard/ReportModal';
import SizingHubModal from '../components/dashboard/SizingHubModal';
import AddressSearch from '../components/dashboard/AddressSearch';
import AddPanelModal from '../components/dashboard/AddPanelModal';
import { Play, Search, Box, Zap, Calendar, Loader2, PenTool, MousePointer, Undo2, Trash2, RotateCw, GripVertical, Rows, Plus } from 'lucide-react';
import ThemeToggle from '../components/ThemeToggle';

export default function Dashboard() {
    const [config, setConfig] = useState({
        tilt: 15,
        azimuth: 180,
        rate: 1.90, // GHS 1.90 per kWh typical
        bias: 1.0,
        module: 'jinko_420',
        year: 2024,
        systemCost: 20000,
        omCost: 320,
        use_ecg_tariff: true,
        customer_type: 'residential'
    });

    const [modules, setModules] = useState([]);
    const [results, setResults] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [activeTool, setActiveTool] = useState('select');
    const [moduleMenuOpen, setModuleMenuOpen] = useState(false);
    const [selectedRowIds, setSelectedRowIds] = useState([]);
    const [isReportOpen, setIsReportOpen] = useState(false);
    const [isSizingHubOpen, setIsSizingHubOpen] = useState(false);
    const [isAddPanelOpen, setIsAddPanelOpen] = useState(false);

    // Map View State
    const [mapCenter, setMapCenter] = useState({ lat: 8.26148, lng: -2.24555 });
    const [mapZoom, setMapZoom] = useState(18);

    // Drawing state
    const [polygonAreas, setPolygonAreas] = useState([]);   // completed polygon outlines
    const [activeVertices, setActiveVertices] = useState([]); // in-progress polygon
    const [placedPanels, setPlacedPanels] = useState([]);     // individual panel rectangles

    // Panel arrangement config
    const [panelConfig, setPanelConfig] = useState({
        orientation: 'portrait',   // 'portrait' or 'landscape'
        rowGap: 0.2,               // meters between modules (fine gap)
        colGap: 0.15,              // meters between strings
        rowSpacingM: 4.5,          // Row-to-row spacing (shading gap)
        blockSizeM: 40.0,          // Size of sub-array blocks
        roadWidthM: 6.0,           // Width of main access roads
    });

    // Currently selected module object
    const selectedModule = useMemo(
        () => modules.find(m => m.id === config.module) || null,
        [modules, config.module]
    );

    // Keyboard shortcuts
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.key === 'Escape') {
                setActiveVertices([]);
                setActiveTool('select');
            }
            if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
                e.preventDefault();
                setActiveVertices(prev => prev.slice(0, -1));
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, []);

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

    // Recompute panels when config changes (orientation, gaps, module)
    const handleRecalculatePanels = useCallback(() => {
        if (polygonAreas.length === 0 || !selectedModule) return;

        const allPanels = [];
        polygonAreas.forEach(polygon => {
            const panels = generateGeodesicPanelGrid(
                polygon,
                selectedModule.width_m,
                selectedModule.length_m,
                panelConfig.rowGap,
                panelConfig.colGap,
                panelConfig.orientation,
                panelConfig
            );
            allPanels.push(...panels);
        });
        setPlacedPanels(allPanels);
    }, [polygonAreas, selectedModule, panelConfig]);

    // Auto-recalculate when panel config changes
    useEffect(() => {
        handleRecalculatePanels();
    }, [panelConfig, config.module, handleRecalculatePanels]);

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

        try {
            // Build panels payload with lat/lng
            const panelsPayload = placedPanels.map(p => ({
                id: p.id,
                x: p.center.lng,   // longitude
                y: p.center.lat,   // latitude
                rotation: p.rotation || 0,
            }));

            const payload = {
                latitude: mapCenter.lat,
                longitude: mapCenter.lng,
                capacity_kw: totalCapacityKw > 0 ? totalCapacityKw : 100.0,
                tilt: config.tilt,
                azimuth: config.azimuth,
                electricity_rate: config.rate,
                module_name: config.module,
                year: config.year,
                irradiance_bias: config.bias,
                system_cost_kw: config.systemCost,
                om_cost_kw: config.omCost,
                use_ecg_tariff: config.use_ecg_tariff,
                customer_type: config.customer_type,
                panels: panelsPayload,
                features: []
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
                probabilisticResults: data.probabilistic_results
            });
        } catch (err) {
            console.error(err);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleRowOrientationToggle = useCallback(() => {
        if (selectedRowIds.length === 0) return;
        setPlacedPanels(prev => {
            let nextPanels = [...prev];
            selectedRowIds.forEach(rowId => {
                const rowPanels = nextPanels.filter(p => p.rowId === rowId);
                const currentOrientation = rowPanels[0]?.orientation || 'portrait';
                const newOrientation = currentOrientation === 'portrait' ? 'landscape' : 'portrait';

                // 1. Flip orientation and dimensions for all panels in row
                const flipped = rowPanels.map(p => {
                    const updated = updatePanelGeometry(p, p.rotation || 0, p.heightM, p.widthM);
                    return { ...updated, orientation: newOrientation };
                });

                // 2. Redistribute centers to fix landscape overlap
                // Only redistribute if we just flipped to landscape
                const redistributed = newOrientation === 'landscape'
                    ? redistributeRowPanels(flipped, panelConfig.colGap)
                    : flipped;

                // 3. Update main array
                nextPanels = nextPanels.map(p => {
                    const match = redistributed.find(r => r.id === p.id);
                    return match || p;
                });
            });
            return nextPanels;
        });
    }, [selectedRowIds, panelConfig.colGap]);

    const handleRowRotationChange = useCallback((newRotation) => {
        if (selectedRowIds.length === 0) return;
        setPlacedPanels(prev => prev.map(p => {
            if (selectedRowIds.includes(p.rowId)) {
                return updatePanelGeometry(p, newRotation, p.widthM, p.heightM);
            }
            return p;
        }));
    }, [selectedRowIds]);

    const handleGlobalOrientationToggle = useCallback(() => {
        setPlacedPanels(prev => {
            const currentGlobalOrientation = panelConfig.orientation;
            const newOrientation = currentGlobalOrientation === 'portrait' ? 'landscape' : 'portrait';

            // Group panels by rowId to redistribute correctly
            const rows = {};
            prev.forEach(p => {
                if (!rows[p.rowId]) rows[p.rowId] = [];
                rows[p.rowId].push(p);
            });

            const processed = Object.values(rows).flatMap(rowPanels => {
                const flipped = rowPanels.map(p => {
                    // Check if already in target orientation
                    if (p.orientation === newOrientation) return p;
                    const updated = updatePanelGeometry(p, p.rotation || 0, p.heightM, p.widthM);
                    return { ...updated, orientation: newOrientation };
                });

                return newOrientation === 'landscape'
                    ? redistributeRowPanels(flipped, panelConfig.colGap)
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
            />

            {/* Main Content Area */}
            <div className="flex-1 ml-[280px] relative flex flex-col">

                {/* Toolbar Header */}
                <header className="h-[60px] bg-surface-raised border-b border-border-subtle px-5 flex items-center justify-between z-40">
                    {/* Search */}
                    <AddressSearch
                        onSelectLocation={({ lat, lng }) => {
                            setMapCenter({ lat, lng });
                            setMapZoom(19); // Zoom in on selection
                        }}
                    />

                    {/* Tools */}
                    <div className="flex items-center gap-3">
                        {/* Drawing Tools */}
                        <div className="flex items-center bg-glass-bg rounded-lg p-1 gap-1 border border-border-subtle">
                            <button
                                onClick={() => setActiveTool('select')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${activeTool === 'select'
                                    ? 'bg-brand-gold/10 text-brand-gold'
                                    : 'text-text-dim hover:text-text-secondary'
                                    }`}
                            >
                                <MousePointer className="w-3.5 h-3.5" />
                                Select
                            </button>
                            <button
                                onClick={() => setActiveTool('draw')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${activeTool === 'draw'
                                    ? 'bg-brand-gold/10 text-brand-gold'
                                    : 'text-text-dim hover:text-text-secondary'
                                    }`}
                            >
                                <PenTool className="w-3.5 h-3.5" />
                                Draw
                            </button>
                            <button
                                onClick={() => setActiveTool('select_row')}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${activeTool === 'select_row'
                                    ? 'bg-brand-gold/10 text-brand-gold'
                                    : 'text-text-dim hover:text-text-secondary'
                                    }`}
                            >
                                <GripVertical className="w-3.5 h-3.5" />
                                Select Row
                            </button>
                        </div>

                        {/* Config pills */}
                        <div className="flex items-center bg-glass-bg rounded-lg p-1 gap-1 border border-border-subtle">
                            <button className="flex items-center gap-1.5 px-3 py-1.5 text-text-muted hover:text-text-primary rounded-md text-xs font-semibold transition-colors">
                                <Calendar className="w-3.5 h-3.5 text-text-dim" />
                                {config.year}
                            </button>

                            {/* Module Select */}
                            <div className="relative">
                                <button
                                    onClick={() => setModuleMenuOpen(!moduleMenuOpen)}
                                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${moduleMenuOpen ? 'bg-glass-bg-strong text-text-primary' : 'text-text-muted hover:text-text-primary hover:bg-glass-bg-strong'}`}
                                >
                                    <Box className="w-3.5 h-3.5 text-text-dim" />
                                    {currentModule ? currentModule.name : 'Select Module'}
                                </button>

                                {moduleMenuOpen && (
                                    <>
                                        <div className="fixed inset-0 z-40" onClick={() => setModuleMenuOpen(false)} />
                                        <div className="absolute top-full right-0 mt-2 w-64 bg-surface-dropdown rounded-xl shadow-2xl border border-border-theme py-1 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
                                            <div className="px-3 py-2 border-b border-border-subtle flex items-center justify-between">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Select Module Type</p>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); setModuleMenuOpen(false); setIsAddPanelOpen(true); }}
                                                    className="flex items-center gap-1 text-[10px] font-bold text-amber-400 hover:text-amber-300 transition-colors px-2 py-1 rounded-lg hover:bg-amber-500/10"
                                                    title="Add custom panel"
                                                >
                                                    <Plus className="w-3 h-3" />
                                                    Add
                                                </button>
                                            </div>
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
                                                            {m.battery_brand && <span className="text-amber-500/70 truncate">• {m.battery_capacity_kwh}kWh Battery</span>}
                                                            {m.inverter_brand && <span className="text-amber-500/70 truncate">• {m.inverter_kw}kW Inv.</span>}
                                                        </div>
                                                    </div>
                                                    <span className={`text-xs font-bold shrink-0 ${m.id === config.module ? 'text-brand-gold' : 'text-text-primary'}`}>{m.power_wp}W</span>
                                                </div>
                                            ))}
                                        </div>
                                    </>
                                )}
                            </div>

                            {/* Capacity display */}
                            <button className="flex items-center gap-1.5 px-3 py-1.5 text-text-muted rounded-md text-xs font-semibold">
                                <Zap className="w-3.5 h-3.5 text-text-dim" />
                                {totalCapacityKw > 0 ? `${totalCapacityKw.toFixed(1)} kWp` : 'No panels'}
                            </button>
                        </div>

                        {/* Run Button */}
                        <button
                            onClick={handleRunSimulation}
                            disabled={loading}
                            className="flex items-center gap-2 px-5 py-2 bg-gradient-to-r from-brand-gold to-orange-500 hover:shadow-[0_0_25px_rgba(245,158,11,0.3)] disabled:opacity-50 text-white rounded-lg text-xs font-bold transition-all transform active:scale-95"
                        >
                            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
                            {loading ? 'SIMULATING...' : 'RUN SIMULATION'}
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
                        panelConfig={panelConfig}
                        selectedModule={selectedModule}
                        selectedRowIds={selectedRowIds}
                        setSelectedRowIds={setSelectedRowIds}
                        center={mapCenter}
                        zoom={mapZoom}
                        onCenterChange={setMapCenter}
                        onZoomChange={setMapZoom}
                    />

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
                    <ReportModal
                        isOpen={isReportOpen}
                        onClose={() => setIsReportOpen(false)}
                        results={results}
                    />

                    {/* Sizing Hub Modal */}
                    <SizingHubModal
                        isOpen={isSizingHubOpen}
                        onClose={() => setIsSizingHubOpen(false)}
                    />

                    {/* Add Panel Modal */}
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
                </div>

            </div>
        </div>
    );
}
