import React from 'react';
import { Sun, Layout, Calculator, FileText, Layers, Sliders, LogOut, PenTool } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Sidebar({
    config, updateConfig, panelConfig, updatePanelConfig,
    onViewReport, onOpenSizingHub,
    selectedRowIds = [], placedPanels, onToggleRowOrientation, onChangeRowRotation, onToggleGlobalOrientation
}) {
    // Current selected row properties
    const selectedRowPanels = placedPanels.filter(p => selectedRowIds.includes(p.rowId));
    const isMultiSelect = selectedRowIds.length > 1;

    // Use the first selected row as reference for UI labels
    const referencePanel = selectedRowPanels[0];
    const rowOrientation = referencePanel?.orientation || 'portrait';
    const rowRotation = referencePanel?.rotation || 0;

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

            {/* Geometry Controls */}
            <div className="flex-1 overflow-y-auto px-5 py-5 bg-glass-bg border-t border-border-subtle">
                <h3 className="text-[10px] font-bold text-text-dim uppercase mb-5 tracking-wider flex items-center gap-2">
                    <Layers className="w-3 h-3 text-brand-gold" />
                    Physical Geometry
                </h3>

                <div className="space-y-5">
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
                    <div className="space-y-4">
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
                </div>

                <h3 className="text-[10px] font-bold text-text-dim uppercase mt-8 mb-5 tracking-wider flex items-center gap-2">
                    <Sliders className="w-3 h-3 text-brand-gold" />
                    Advanced Tuning
                </h3>

                <div className="space-y-5">
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
                    </div>
                </div>

                {/* Industrial Layout Section */}
                <h3 className="text-[10px] font-bold text-text-dim uppercase mt-8 mb-5 tracking-wider flex items-center gap-2">
                    <Layout className="w-3 h-3 text-brand-gold" />
                    Industrial Farm Layout
                </h3>

                <div className="space-y-5">
                    {/* Row Spacing */}
                    <div className="space-y-2">
                        <div className="flex justify-between items-center">
                            <label className="text-[10px] font-semibold text-text-muted uppercase tracking-widest">Inter-Row Spacing</label>
                            <span className="text-xs font-bold text-brand-gold">{panelConfig.rowSpacingM}m</span>
                        </div>
                        <input
                            type="range" min="0.5" max="15" step="0.5"
                            value={panelConfig.rowSpacingM}
                            onChange={(e) => updatePanelConfig('rowSpacingM', parseFloat(e.target.value))}
                            className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                        />
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
                </div>

                {/* NEW: Global Layout Section */}
                <div className="px-5 py-4 border-t border-border-subtle">
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

                {/* Row Selection Overrides */}
                {selectedRowIds.length > 0 && (
                    <>
                        <h3 className="text-[10px] font-bold text-brand-gold uppercase mt-4 mb-5 px-5 tracking-wider flex items-center gap-2">
                            <Sliders className="w-3 h-3" />
                            {isMultiSelect ? `${selectedRowIds.length} Rows Selected` : 'Row Property Overrides'}
                        </h3>
                        <div className="mx-5 p-4 rounded-xl bg-brand-gold/5 border border-brand-gold/20 space-y-5">
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
                    </>
                )}

                <h3 className="text-[10px] font-bold text-text-dim uppercase mt-8 mb-5 tracking-wider flex items-center gap-2">
                    <Calculator className="w-3 h-3 text-brand-gold" />
                    Financial Settings
                </h3>

                <div className="space-y-5 pb-10">
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
                </div>
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
