import React, { useState } from 'react';
import { Sun, Layout, Calculator, FileText, Layers, Sliders, LogOut, PenTool, ChevronDown, ChevronRight, TreePine, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';

function CollapsibleSection({ title, icon: Icon, defaultOpen = true, accent = false, children }) {
    const [open, setOpen] = useState(defaultOpen);
    return (
        <div className="mb-2">
            <button
                onClick={() => setOpen(!open)}
                className={`w-full flex items-center justify-between px-1 py-2 text-[10px] font-bold uppercase tracking-wider transition-colors rounded-md hover:bg-white/5 ${
                    accent ? 'text-brand-gold' : 'text-text-dim'
                }`}
            >
                <span className="flex items-center gap-2">
                    <Icon className="w-3 h-3" />
                    {title}
                </span>
                {open
                    ? <ChevronDown className="w-3 h-3" />
                    : <ChevronRight className="w-3 h-3" />
                }
            </button>
            {open && <div className="pt-2 pb-3 space-y-4">{children}</div>}
        </div>
    );
}

export default function Sidebar({
    config, updateConfig, panelConfig, updatePanelConfig,
    onViewReport, onOpenSizingHub,
    selectedRowIds = [], placedPanels, onToggleRowOrientation, onChangeRowRotation, onToggleGlobalOrientation,
    obstacles = [], selectedObstacleId, setSelectedObstacleId, onUpdateObstacle, onDeleteObstacle,
}) {
    const selectedRowPanels = placedPanels.filter(p => selectedRowIds.includes(p.rowId));
    const isMultiSelect = selectedRowIds.length > 1;
    const referencePanel = selectedRowPanels[0];
    const rowOrientation = referencePanel?.orientation || 'portrait';
    const rowRotation = referencePanel?.gridRotationDeg || 0;

    return (
        <div className="fixed left-0 top-0 bottom-0 w-[280px] bg-surface-raised border-r border-border-subtle z-50 flex flex-col">
            {/* Brand Header */}
            <div className="px-6 py-6 flex items-center gap-3 border-b border-border-subtle">
                <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-gold to-orange-500 flex items-center justify-center shadow-[0_0_20px_rgba(245,158,11,0.3)]">
                    <Sun className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h1 className="text-lg font-bold tracking-tight text-text-primary">UNISOLAR</h1>
                    <p className="text-[10px] text-text-dim font-bold uppercase tracking-widest">Enterprise Edition</p>
                </div>
            </div>

            {/* Navigation */}
            <nav className="flex-none py-4">
                <div className="px-3 space-y-1">
                    <div className="flex items-center gap-3 px-4 py-2.5 bg-brand-gold/10 text-brand-gold rounded-lg cursor-pointer">
                        <Layout className="w-4 h-4" />
                        <span className="font-medium text-sm">Asset Design</span>
                    </div>
                    <div className="flex items-center gap-3 px-4 py-2.5 text-text-dim hover:bg-glass-bg rounded-lg cursor-pointer transition-colors">
                        <PenTool className="w-4 h-4" />
                        <span className="font-medium text-sm">Draw Panels</span>
                    </div>
                    <div
                        onClick={onOpenSizingHub}
                        className="flex items-center gap-3 px-4 py-2.5 text-text-dim hover:bg-glass-bg rounded-lg cursor-pointer transition-colors"
                    >
                        <Calculator className="w-4 h-4" />
                        <span className="font-medium text-sm">Sizing Hub</span>
                    </div>
                    <div
                        onClick={onViewReport}
                        className="flex items-center gap-3 px-4 py-2.5 text-text-dim hover:bg-glass-bg rounded-lg cursor-pointer transition-colors"
                    >
                        <FileText className="w-4 h-4" />
                        <span className="font-medium text-sm">Reports</span>
                    </div>
                </div>
            </nav>

            {/* Scrollable Controls */}
            <div className="flex-1 overflow-y-auto px-5 py-4 bg-glass-bg border-t border-border-subtle">

                {/* ── Physical Geometry ── */}
                <CollapsibleSection title="Physical Geometry" icon={Layers} defaultOpen>
                    {/* Tilt */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">System Tilt</label>
                            <span className="text-xs font-bold text-brand-gold">{config.tilt}°</span>
                        </div>
                        <input
                            type="range" min="0" max="90" step="1"
                            value={config.tilt}
                            onChange={(e) => updateConfig('tilt', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                    </div>

                    {/* Azimuth */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Azimuth</label>
                            <span className="text-xs font-bold text-brand-gold">{config.azimuth}°</span>
                        </div>
                        <input
                            type="range" min="0" max="359" step="1"
                            value={config.azimuth}
                            onChange={(e) => updateConfig('azimuth', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                        <div className="flex justify-between text-[10px] text-text-dim font-mono">
                            <span>N</span><span>E</span><span>S</span><span>W</span><span>N</span>
                        </div>
                    </div>

                    {/* ECG Tariff Selection */}
                    <div className="space-y-3">
                        <div className="flex items-center justify-between">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">ECG Official Tariff</label>
                            <button
                                onClick={() => updateConfig('use_ecg_tariff', !config.use_ecg_tariff)}
                                className={`w-10 h-5 rounded-full transition-colors relative ${config.use_ecg_tariff ? 'bg-brand-gold' : 'bg-border-theme'}`}
                            >
                                <div className={`absolute top-1 w-3 h-3 rounded-full bg-white transition-all ${config.use_ecg_tariff ? 'right-1' : 'left-1'}`} />
                            </button>
                        </div>

                        {config.use_ecg_tariff ? (
                            <div className="space-y-3">
                                <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest block">Customer Type</label>
                                <div className="grid grid-cols-2 gap-2">
                                    <button
                                        onClick={() => updateConfig('customer_type', 'residential')}
                                        className={`px-3 py-2 text-[10px] font-bold rounded-lg border transition-all ${config.customer_type === 'residential'
                                            ? 'bg-brand-gold/10 border-brand-gold text-brand-gold'
                                            : 'bg-glass-bg border-border-theme text-text-dim hover:text-text-primary'
                                            }`}
                                    >
                                        RESIDENTIAL
                                    </button>
                                    <button
                                        onClick={() => updateConfig('customer_type', 'non_residential')}
                                        className={`px-3 py-2 text-[10px] font-bold rounded-lg border transition-all ${config.customer_type === 'non_residential'
                                            ? 'bg-brand-gold/10 border-brand-gold text-brand-gold'
                                            : 'bg-glass-bg border-border-theme text-text-dim hover:text-text-primary'
                                            }`}
                                    >
                                        NON-RES
                                    </button>
                                </div>
                                <p className="text-[9px] text-text-dim font-medium leading-relaxed italic">
                                    * Rates scaled to May 2025 ECG Reckoner. Includes levies and VAT (for Non-Res).
                                </p>
                            </div>
                        ) : (
                            <div className="space-y-2">
                                <div className="flex justify-between items-center">
                                    <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Manual Rate (₵/kWh)</label>
                                    <span className="text-xs font-bold text-brand-gold">₵{config.rate}</span>
                                </div>
                                <input
                                    type="range" min="0.05" max="5.0" step="0.05"
                                    value={config.rate}
                                    onChange={(e) => updateConfig('rate', parseFloat(e.target.value))}
                                    className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                                />
                            </div>
                        )}
                    </div>
                </CollapsibleSection>

                {/* ── Industrial Farm Layout ── */}
                <CollapsibleSection title="Farm Layout" icon={Layout} defaultOpen>
                    {/* GCR */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">GCR (Ground Coverage)</label>
                            <span className="text-xs font-bold text-brand-gold">{panelConfig.gcr?.toFixed(2) ?? '0.40'}</span>
                        </div>
                        <input
                            type="range" min="0.10" max="0.80" step="0.01"
                            value={panelConfig.gcr ?? 0.40}
                            onChange={(e) => updatePanelConfig('gcr', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                        <p className="text-[9px] text-text-dim font-medium">Row pitch: {panelConfig.rowPitchDisplay ?? '—'}m (projected / GCR)</p>
                    </div>

                    {/* Block Size */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Block Size</label>
                            <span className="text-xs font-bold text-brand-gold">{panelConfig.blockSizeM}m</span>
                        </div>
                        <input
                            type="range" min="10" max="150" step="5"
                            value={panelConfig.blockSizeM}
                            onChange={(e) => updatePanelConfig('blockSizeM', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                    </div>

                    {/* Road Width */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Main Road Width</label>
                            <span className="text-xs font-bold text-brand-gold">{panelConfig.roadWidthM}m</span>
                        </div>
                        <input
                            type="range" min="2" max="15" step="1"
                            value={panelConfig.roadWidthM}
                            onChange={(e) => updatePanelConfig('roadWidthM', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                    </div>

                    {/* Global Orientation */}
                    <div className="pt-2 border-t border-border-subtle">
                        <div className="flex items-center justify-between">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Global Orientation</label>
                            <button
                                onClick={onToggleGlobalOrientation}
                                className="px-3 py-1 bg-glass-bg text-text-secondary rounded font-bold text-[10px] hover:bg-glass-bg-strong transition-colors uppercase border border-border-theme"
                            >
                                {panelConfig.orientation}
                            </button>
                        </div>
                    </div>
                </CollapsibleSection>

                {/* ── Financial Settings ── */}
                <CollapsibleSection title="Financial Settings" icon={Calculator} defaultOpen>
                    {/* System Cost */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">System Cost (₵/kWp)</label>
                            <span className="text-xs font-bold text-brand-gold">{config.systemCost.toLocaleString()}</span>
                        </div>
                        <input
                            type="range" min="10000" max="40000" step="500"
                            value={config.systemCost}
                            onChange={(e) => updateConfig('systemCost', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                    </div>

                    {/* O&M Cost */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Annual O&M (₵/kWp)</label>
                            <span className="text-xs font-bold text-brand-gold">{config.omCost.toLocaleString()}</span>
                        </div>
                        <input
                            type="range" min="0" max="1000" step="20"
                            value={config.omCost}
                            onChange={(e) => updateConfig('omCost', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                    </div>
                </CollapsibleSection>

                {/* ── Advanced (collapsed by default) ── */}
                <CollapsibleSection title="Advanced" icon={Sliders} defaultOpen={false}>
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Irradiance Bias</label>
                            <span className="text-xs font-bold text-brand-gold">{config.bias}x</span>
                        </div>
                        <input
                            type="range" min="0.8" max="1.2" step="0.01"
                            value={config.bias}
                            onChange={(e) => updateConfig('bias', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
                        <p className="text-[9px] text-text-dim font-medium">Multiplier applied to NASA POWER irradiance data</p>
                    </div>
                </CollapsibleSection>

                {/* ── Obstacles ── */}
                <CollapsibleSection title="Obstacles" icon={TreePine} defaultOpen={obstacles.length > 0}>
                    {obstacles.length === 0 ? (
                        <p className="text-[9px] text-text-dim font-medium leading-relaxed">
                            No obstacles placed. Select the <strong className="text-emerald-400">Obstacle</strong> tool in the toolbar and click on the map to place trees, buildings, or other shading objects.
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {obstacles.map(o => (
                                <div
                                    key={o.id}
                                    onClick={() => setSelectedObstacleId(o.id)}
                                    className={`p-3 rounded-xl cursor-pointer transition-all border ${
                                        selectedObstacleId === o.id
                                            ? 'bg-emerald-500/10 border-emerald-500/30'
                                            : 'bg-glass-bg border-border-theme hover:border-emerald-500/20'
                                    }`}
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2">
                                            <TreePine className="w-3.5 h-3.5 text-emerald-400" />
                                            <div>
                                                <p className="text-[10px] font-bold text-text-primary capitalize">{o.type}</p>
                                                <p className="text-[8px] text-text-dim">{o.heightM.toFixed(1)}m H × {o.widthM.toFixed(1)}m W</p>
                                            </div>
                                        </div>
                                        <button
                                            onClick={(e) => { e.stopPropagation(); onDeleteObstacle(o.id); }}
                                            className="p-1 rounded-md hover:bg-red-500/10 text-text-dim hover:text-red-400 transition-colors"
                                        >
                                            <Trash2 className="w-3 h-3" />
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </CollapsibleSection>

                {/* Row Selection Overrides (conditional) */}
                {selectedRowIds.length > 0 && (
                    <div className="mt-4 mb-2">
                        <h3 className="text-[10px] font-bold text-brand-gold uppercase mb-3 tracking-wider flex items-center gap-2">
                            <Sliders className="w-3 h-3" />
                            {isMultiSelect ? `${selectedRowIds.length} Rows Selected` : 'Row Overrides'}
                        </h3>
                        <div className="p-4 rounded-xl bg-brand-gold/5 border border-brand-gold/20 space-y-4">
                            <div className="flex items-center justify-between">
                                <div className="flex flex-col">
                                    <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Orientation</label>
                                    {isMultiSelect && <span className="text-[8px] text-text-dim uppercase">Apply to all</span>}
                                </div>
                                <button
                                    onClick={onToggleRowOrientation}
                                    className="px-3 py-1 bg-brand-gold/20 text-brand-gold rounded font-bold text-[10px] hover:bg-brand-gold/30 transition-colors uppercase"
                                >
                                    {rowOrientation}
                                </button>
                            </div>

                            <div className="space-y-2">
                                <div className="flex justify-between items-center">
                                    <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">2D Rotation</label>
                                    <span className="text-xs font-bold text-brand-gold">{rowRotation.toFixed(1)}°</span>
                                </div>
                                <input
                                    type="range" min="-180" max="180" step="1"
                                    value={rowRotation}
                                    onChange={(e) => onChangeRowRotation(parseFloat(e.target.value))}
                                    className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                                />
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Footer */}
            <div className="p-4 border-t border-border-subtle">
                <Link to="/" className="flex items-center gap-2 text-text-dim hover:text-text-secondary transition-colors text-xs">
                    <LogOut className="w-3.5 h-3.5" />
                    Back to Home
                </Link>
            </div>
        </div>
    );
}
