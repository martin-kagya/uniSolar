import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, FileText, Download, TrendingUp, DollarSign, Zap, Clock, PieChart, Leaf, Shield, ChevronDown, ChevronUp, AlertTriangle, Droplets, Cpu, Activity, Umbrella, Wrench, Camera } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart as RePie, Pie, Cell, ReferenceLine } from 'recharts';
import { generateReportPDF, exportAndDownload } from '../../lib/export';

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const LOSS_COLORS = ['#f59e0b', '#8b5cf6', '#ef4444', '#64748b', '#06b6d4'];
const LOSS_KEYS = ['soiling', 'shading', 'degradation', 'inverter', 'physics_derate'];
const LOSS_LABELS = ['Soiling', 'Shading', 'Degradation', 'Inverter Efficiency', 'Wiring / LID / Mismatch'];

/**
 * Format energy values with sensible precision.
 * >= 10,000 kWh → show as MWh with 1 decimal (e.g. "207.9 MWh")
 * < 10,000 kWh → show as kWh rounded to nearest whole number (e.g. "4,520 kWh")
 */
function formatEnergy(kwh) {
    if (!Number.isFinite(kwh) || kwh === 0) return '0 kWh';
    if (kwh >= 10000) {
        return `${(kwh / 1000).toFixed(1)} MWh`;
    }
    return `${Math.round(kwh).toLocaleString()} kWh`;
}

export default function ReportModal({ isOpen, onClose, results }) {
    if (!isOpen || !results) return null;

    const [activeTab, setActiveTab] = useState('yield');
    const [showAssumptions, setShowAssumptions] = useState(false);

    const handleExportPdf = async () => {
        try {
            await generateReportPDF(results);
        } catch (err) {
            console.error('PDF export failed:', err);
        }
    };

    const handleExportScreenshot = () => {
        const mapContainer = document.querySelector('.flex-1.relative');
        if (mapContainer) {
            exportAndDownload(mapContainer, {
                format: 'png',
                filename: `unisolar-map`,
            });
        }
    };

    const monthlyData = results.monthlyEnergy
        ? results.monthlyEnergy.map((val, idx) => ({
            name: MONTH_NAMES[idx],
            yield: Math.round(val),
            revenue: Math.round(val * (results.effectiveTariffY1 || results.rate || 1.90)),
        }))
        : null;

    const lossData = results.losses
        ? LOSS_KEYS.map((key, i) => ({
            name: LOSS_LABELS[i],
            value: results.losses[`${key}_percent`] || 0,
            color: LOSS_COLORS[i],
        })).filter(d => d.value > 0.01)
        : [];

    const totalLoss = lossData.reduce((s, d) => s + d.value, 0);

    const envMetrics = results.environmentalMetrics;

    return (
        <AnimatePresence>
            <div className="fixed inset-0 z-[60] flex items-center justify-center p-6 sm:p-10">
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    onClick={onClose}
                    className="absolute inset-0 bg-black/80 backdrop-blur-md"
                />

                <motion.div
                    initial={{ opacity: 0, scale: 0.95, y: 20 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: 20 }}
                    className="relative w-full max-w-5xl max-h-[90vh] bg-surface-raised border border-border-theme rounded-3xl shadow-2xl overflow-hidden flex flex-col"
                >
                    {/* Header */}
                    <div className="px-8 py-6 border-b border-border-theme flex justify-between items-center bg-gradient-to-r from-glass-bg to-transparent">
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 rounded-2xl bg-brand-gold/10 flex items-center justify-center text-brand-gold">
                                <FileText className="w-6 h-6" />
                            </div>
                            <div>
                                <h2 className="text-xl font-bold text-text-primary tracking-tight">Financial & Yield Audit</h2>
                                <p className="text-xs text-text-dim font-bold uppercase tracking-widest mt-0.5">Lender-Ready Project Report</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={handleExportScreenshot}
                                className="flex items-center gap-2 px-3 py-2 bg-glass-bg hover:bg-white/10 text-text-primary rounded-xl text-xs font-bold transition-all border border-border-theme group"
                                title="Export map as PNG screenshot"
                            >
                                <Camera className="w-4 h-4 text-text-dim group-hover:text-text-primary transition-colors" />
                                SCREENSHOT
                            </button>
                            <button
                                id="report-export-btn"
                                onClick={handleExportPdf}
                                className="flex items-center gap-2 px-4 py-2 bg-glass-bg hover:bg-white/10 text-text-primary rounded-xl text-xs font-bold transition-all border border-border-theme group"
                            >
                                <Download className="w-4 h-4 text-text-dim group-hover:text-text-primary transition-colors" />
                                EXPORT PDF
                            </button>
                            <button
                                onClick={onClose}
                                className="p-2 hover:bg-glass-bg rounded-xl text-text-dim hover:text-text-primary transition-all border border-transparent hover:border-border-subtle"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>
                    </div>

                    {/* Content */}
                    <div className="flex-1 flex flex-col min-h-0">
                        {/* Tabs */}
                        <div className="px-8 flex items-center gap-6 border-b border-border-subtle bg-glass-bg">
                            {[
                                { id: 'yield', icon: Zap, label: 'Yield Report' },
                                { id: 'financial', icon: DollarSign, label: 'Financial Report' },
                                { id: 'environmental', icon: Leaf, label: 'Environmental' },
                            ].map(({ id, icon: Icon, label }) => (
                                <button
                                    key={id}
                                    onClick={() => setActiveTab(id)}
                                    className={`py-4 text-xs font-bold uppercase tracking-widest relative transition-colors ${activeTab === id ? 'text-amber-400' : 'text-text-dim hover:text-text-secondary'}`}
                                >
                                    <span className="flex items-center gap-2"><Icon className="w-4 h-4" /> {label}</span>
                                    {activeTab === id && (
                                        <motion.div layoutId="activeTab" className="absolute bottom-[-1px] left-0 right-0 h-0.5 bg-amber-400" />
                                    )}
                                </button>
                            ))}
                        </div>

                        <div className="flex-1 overflow-y-auto p-8 space-y-10 custom-scrollbar">

                            {activeTab === 'yield' && (
                                <>
                                    {/* Yield Summary Cards */}
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Annual Energy</p>
                                                <Zap className="w-4 h-4 text-brand-gold" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">{formatEnergy(results.annualEnergy)}</p>
                                        </div>
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Installed DC</p>
                                                <TrendingUp className="w-4 h-4 text-blue-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">{results.capacityKw.toFixed(1)} kWp</p>
                                        </div>
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Panel Count</p>
                                                <TrendingUp className="w-4 h-4 text-emerald-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">{results.panelCount}</p>
                                        </div>
                                    </div>

                                    {/* Probabilistic Yield Section */}
                                    {results.probabilisticResults && (
                                        <div className="p-8 bg-glass-bg rounded-3xl space-y-6 card-hover">
                                            <div className="flex justify-between items-end">
                                                <div className="space-y-1">
                                                    <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                                                        <TrendingUp className="w-4 h-4 text-emerald-400" />
                                                        Yield Probability Distribution
                                                    </h3>
                                                    <p className="text-xs text-text-dim">1,000 Monte Carlo runs — combined uncertainty: irradiance ±5%, soiling ±12%, hardware ±3%</p>
                                                </div>
                                                <div className="flex gap-2">
                                                    <div className="px-2 py-1 bg-glass-bg border border-border-theme rounded-lg">
                                                        <p className="text-[8px] font-bold text-text-dim uppercase">P50 (Expected)</p>
                                                        <p className="text-xs font-bold text-text-primary">{formatEnergy(results.probabilisticResults.p50_yield)}</p>
                                                        {results.probabilisticResults.p50_npv != null && (
                                                            <p className="text-[8px] text-text-dim">NPV: ₵{Math.round(results.probabilisticResults.p50_npv).toLocaleString()}</p>
                                                        )}
                                                    </div>
                                                    <div className="px-2 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                                                        <p className="text-[8px] font-bold text-emerald-500 uppercase">P90 (Bankable)</p>
                                                        <p className="text-xs font-bold text-text-primary">{formatEnergy(results.probabilisticResults.p90_yield)}</p>
                                                        {results.probabilisticResults.p90_npv != null && (
                                                            <p className="text-[8px] text-text-dim">NPV: ₵{Math.round(results.probabilisticResults.p90_npv).toLocaleString()}</p>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="h-64 w-full">
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <AreaChart data={results.probabilisticResults.distribution}>
                                                        <defs>
                                                            <linearGradient id="colorProb" x1="0" y1="0" x2="0" y2="1">
                                                                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                                                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                                            </linearGradient>
                                                        </defs>
                                                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                                                        <XAxis
                                                            dataKey="bin"
                                                            stroke="#475569"
                                                            fontSize={10}
                                                            tickLine={false}
                                                            axisLine={false}
                                                            tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
                                                        />
                                                        <YAxis hide stroke="#475569" fontSize={10} tickLine={false} axisLine={false} />
                                                        <Tooltip
                                                            contentStyle={{ backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--chart-tooltip-border)', borderRadius: '12px' }}
                                                            labelFormatter={(val) => `Yield: ${val.toLocaleString()} kWh`}
                                                        />
                                                        <Area type="monotone" dataKey="count" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorProb)" />
                                                    </AreaChart>
                                                </ResponsiveContainer>
                                            </div>
                                        </div>
                                    )}

                                    {/* Monthly Yield Forecast */}
                                    {monthlyData && (
                                        <div className="p-8 bg-glass-bg rounded-3xl space-y-6 card-hover">
                                            <div>
                                                <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                                                    <PieChart className="w-4 h-4 text-brand-gold" />
                                                    Monthly Yield Forecast
                                                </h3>
                                                <p className="text-xs text-text-dim mt-1">Simulated performance across a typical meteorological year (TMY)</p>
                                            </div>
                                            <div className="h-64 w-full">
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <BarChart data={monthlyData}>
                                                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                                                        <XAxis dataKey="name" stroke="#475569" fontSize={10} tickLine={false} axisLine={false} />
                                                        <YAxis stroke="#475569" fontSize={10} tickLine={false} axisLine={false} />
                                                        <Tooltip
                                                            cursor={{ fill: 'var(--glass-bg)' }}
                                                            contentStyle={{ backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--chart-tooltip-border)', borderRadius: '12px' }}
                                                            formatter={(val) => [`${val.toLocaleString()} kWh`, 'Yield']}
                                                        />
                                                        <Bar dataKey="yield" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                                                    </BarChart>
                                                </ResponsiveContainer>
                                            </div>
                                        </div>
                                    )}

                                    {/* Loss Breakdown */}
                                    {lossData.length > 0 && (
                                        <div className="p-8 bg-glass-bg rounded-3xl space-y-6 card-hover">
                                            <div>
                                                <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                                                    <Shield className="w-4 h-4 text-purple-400" />
                                                    Loss Waterfall
                                                </h3>
                                                <p className="text-xs text-text-dim mt-1">Energy losses by category relative to total potential yield</p>
                                            </div>
                                            <div className="flex items-center gap-8">
                                                <div className="w-48 h-48 flex-shrink-0">
                                                    <ResponsiveContainer width="100%" height="100%">
                                                        <RePie>
                                                            <Pie
                                                                data={lossData}
                                                                cx="50%"
                                                                cy="50%"
                                                                innerRadius={40}
                                                                outerRadius={80}
                                                                dataKey="value"
                                                                strokeWidth={0}
                                                            >
                                                                {lossData.map((entry, i) => (
                                                                    <Cell key={i} fill={entry.color} />
                                                                ))}
                                                            </Pie>
                                                            <Tooltip
                                                                contentStyle={{ backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--chart-tooltip-border)', borderRadius: '12px', fontSize: '11px' }}
                                                                formatter={(val) => [`${val.toFixed(1)}%`, 'Loss']}
                                                            />
                                                        </RePie>
                                                    </ResponsiveContainer>
                                                </div>
                                                <div className="flex-1 space-y-3">
                                                    {lossData.map((d) => (
                                                        <div key={d.name} className="space-y-1">
                                                            <div className="flex items-center justify-between text-xs">
                                                                <div className="flex items-center gap-2">
                                                                    <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                                                                    <span className="text-text-secondary">{d.name}</span>
                                                                </div>
                                                                <span className="font-bold text-text-primary">{d.value.toFixed(1)}%</span>
                                                            </div>
                                                            <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                                                                <div
                                                                    className="h-full rounded-full transition-all"
                                                                    style={{ width: `${(d.value / totalLoss) * 100}%`, backgroundColor: d.color }}
                                                                />
                                                            </div>
                                                        </div>
                                                    ))}
                                                    <div className="pt-2 border-t border-border-subtle flex justify-between text-xs">
                                                        <span className="text-text-dim font-bold">Total Loss</span>
                                                        <span className="text-amber-400 font-bold">{totalLoss.toFixed(1)}%</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {/* Assumptions Footnote — always visible */}
                                    <div className="p-6 bg-glass-bg rounded-3xl border border-border-subtle">
                                        <h3 className="text-xs font-bold text-text-muted uppercase tracking-widest mb-4 flex items-center gap-2">
                                            <Shield className="w-3.5 h-3.5" />
                                            Key Assumptions
                                        </h3>
                                        <div className="grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-3 text-[11px]">
                                            {(() => {
                                                const lp = results.lossParams || {};
                                                const invEff = lp.actual_inverter_efficiency_pct ?? lp.inverter_efficiency_pct ?? 96;
                                                return [
                                                    { k: 'Degradation Rate', v: `${(lp.degradation_rate_pct ?? 0.5).toFixed(1)}%/yr` },
                                                    { k: 'Soiling Loss', v: `${(lp.soiling_rate_pct ?? 5.0).toFixed(1)}% (annual avg)` },
                                                    { k: 'Discount Rate (WACC)', v: '8.0%' },
                                                    { k: 'Tariff Escalation', v: '3.0%/yr' },
                                                    { k: 'O&M Escalation', v: '2.0%/yr' },
                                                    { k: 'System Lifetime', v: '25 years' },
                                                    { k: 'Inverter Efficiency', v: `${invEff.toFixed(1)}%` },
                                                    { k: 'Wiring Loss', v: `${(lp.wiring_loss_pct ?? 2).toFixed(1)}%` },
                                                    { k: 'LID Loss', v: `${(lp.lid_loss_pct ?? 2).toFixed(1)}%` },
                                                    { k: 'Mismatch Loss', v: `${(lp.mismatch_loss_pct ?? 2).toFixed(1)}%` },
                                                    { k: 'DC/AC Ratio', v: '~1.2 (module-dependent)' },
                                                ];
                                            })().map((row, i) => (
                                                <div key={i} className="flex justify-between">
                                                    <span className="text-text-dim">{row.k}</span>
                                                    <span className="text-text-secondary font-semibold">{row.v}</span>
                                                </div>
                                            ))}
                                        </div>

                                        {/* Internal consistency check — visible only when mismatch detected */}
                                        {(() => {
                                            const lp = results.lossParams || {};
                                            const totalInputLoss = (lp.wiring_loss_pct ?? 2) + (lp.lid_loss_pct ?? 2) + (lp.mismatch_loss_pct ?? 2) + (lp.soiling_rate_pct ?? 5);
                                            const actualInvEff = lp.actual_inverter_efficiency_pct ?? lp.inverter_efficiency_pct ?? 96;
                                            const inverterLoss = 100 - actualInvEff;
                                            const expectedTotal = totalInputLoss + inverterLoss + (lp.degradation_rate_pct ?? 0.5);
                                            const waterfallTotal = lossData.reduce((s, d) => s + d.value, 0);
                                            const discrepancy = Math.abs(expectedTotal - waterfallTotal);
                                            if (discrepancy > 5) {
                                                return (
                                                    <div className="mt-3 p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl">
                                                        <p className="text-[10px] text-amber-400 font-bold">
                                                            ⚠ Consistency note: design derates sum to ~{expectedTotal.toFixed(1)}% while the waterfall shows {waterfallTotal.toFixed(1)}% total.
                                                            The gap is expected: soiling is computed dynamically from actual climate data (rainfall cleans panels, reducing effective soiling below the design assumption),
                                                            and degradation reflects year-1 loss rather than the lifetime average.
                                                            Fixed derates (wiring, LID, mismatch, inverter) use the actual values applied in simulation.
                                                        </p>
                                                    </div>
                                                );
                                            }
                                            return null;
                                        })()}

                                        <p className="text-[9px] text-text-dim mt-4 leading-relaxed">
                                            Monte Carlo P50/P90 spread reflects combined uncertainty from inter-annual irradiance variability (±5%),
                                            Harmattan soiling deposition (±12%), hardware tolerance (±3%), tariff regulation risk (±15%),
                                            degradation variance (±0.2%/yr), and grid availability (±5%). P90 represents the yield exceeded
                                            90% of simulated years — suitable for bankable yield estimates per IEC 61724 methodology.
                                        </p>
                                    </div>
                                </>
                            )}

                            {activeTab === 'financial' && (
                                <>
                                    {/* Financial Summary Cards */}
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Net Present Value</p>
                                                <DollarSign className="w-4 h-4 text-emerald-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">₵{Math.round(results.npv).toLocaleString()}</p>
                                        </div>
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Payback Period</p>
                                                <Clock className="w-4 h-4 text-blue-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">{results.payback.toFixed(1)} Years</p>
                                        </div>
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Internal Rate</p>
                                                <TrendingUp className="w-4 h-4 text-orange-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">{results.irr != null ? `${(results.irr * 100).toFixed(1)}%` : 'N/A'}</p>
                                        </div>
                                    </div>

                                    {/* LCOE + Capex + Savings row */}
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">LCOE</p>
                                                <DollarSign className="w-4 h-4 text-brand-gold" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">
                                                {results.lcoe != null ? `₵${results.lcoe.toFixed(2)}` : 'N/A'}
                                            </p>
                                            <p className="text-[10px] text-text-dim mt-1">per kWh</p>
                                        </div>
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Total Capex</p>
                                                <DollarSign className="w-4 h-4 text-red-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">
                                                {results.capex != null ? `₵${Math.round(results.capex).toLocaleString()}` : 'N/A'}
                                            </p>
                                        </div>
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Lifetime Savings</p>
                                                <TrendingUp className="w-4 h-4 text-emerald-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">
                                                {results.lifetimeSavings != null ? `₵${Math.round(results.lifetimeSavings).toLocaleString()}` : 'N/A'}
                                            </p>
                                        </div>
                                    </div>

                                    {/* Projected Savings Chart */}
                                    {monthlyData && (
                                        <div className="p-8 bg-glass-bg rounded-3xl space-y-6 card-hover">
                                            <div>
                                                <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                                                    <DollarSign className="w-4 h-4 text-emerald-400" />
                                                    Projected Monthly Savings
                                                </h3>
                                                <p className="text-xs text-text-dim mt-1">
                                                    Avoided utility costs based on ₵{(results.effectiveTariffY1 || results.rate || 1.90).toFixed(2)}/kWh effective tariff
                                                    {results.tariffMode === 'ecg_official' ? ' (ECG Official Tiered)' : ''}
                                                </p>
                                            </div>
                                            <div className="h-64 w-full">
                                                <ResponsiveContainer width="100%" height="100%">
                                                    <AreaChart data={monthlyData}>
                                                        <defs>
                                                            <linearGradient id="colorReportRev" x1="0" y1="0" x2="0" y2="1">
                                                                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                                                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                                                            </linearGradient>
                                                        </defs>
                                                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                                                        <XAxis dataKey="name" stroke="#475569" fontSize={10} tickLine={false} axisLine={false} />
                                                        <YAxis stroke="#475569" fontSize={10} tickLine={false} axisLine={false} />
                                                        <Tooltip
                                                            contentStyle={{ backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--chart-tooltip-border)', borderRadius: '12px' }}
                                                            formatter={(val) => [`₵${val.toLocaleString()}`, 'Savings']}
                                                        />
                                                        <Area type="monotone" dataKey="revenue" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorReportRev)" />
                                                    </AreaChart>
                                                </ResponsiveContainer>
                                            </div>
                                        </div>
                                    )}

                                    {/* Financial Parameters */}
                                    <div className="bg-glass-bg rounded-3xl overflow-hidden card-hover">
                                        <div className="px-8 py-5 border-b border-border-subtle bg-glass-bg">
                                            <h3 className="text-xs font-bold text-text-muted uppercase tracking-widest">Financial Parameters</h3>
                                        </div>
                                        <div className="p-8 grid grid-cols-2 md:grid-cols-4 gap-8">
                                            {[
                                                { k: 'Installed DC', v: `${results.capacityKw.toFixed(1)} kWp` },
                                                { k: 'LCOE', v: results.lcoe != null ? `₵${results.lcoe.toFixed(2)}/kWh` : 'N/A' },
                                                { k: 'Year-1 Savings', v: results.annualSavingsY1 != null ? `₵${Math.round(results.annualSavingsY1).toLocaleString()}` : 'N/A' },
                                                { k: 'Tariff Mode', v: results.tariffMode === 'ecg_official' ? 'ECG Official' : 'Flat Rate' },
                                            ].map((row, i) => (
                                                <div key={i}>
                                                    <p className="text-[10px] font-bold text-text-dim uppercase tracking-tighter mb-1">{row.k}</p>
                                                    <p className="text-sm font-bold text-text-primary tracking-tight">{row.v}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Debt Service & DSCR */}
                                    {results.financials?.debt && (
                                        <div className="p-8 bg-glass-bg rounded-3xl space-y-6 card-hover">
                                            <div>
                                                <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                                                    <Shield className="w-4 h-4 text-blue-400" />
                                                    Debt Service Coverage Ratio (DSCR)
                                                </h3>
                                                <p className="text-xs text-text-dim mt-1">
                                                    {(results.financials.debt.debt_ratio_pct).toFixed(0)}% debt at {(results.financials.debt.interest_rate_pct).toFixed(0)}% interest over {results.financials.debt.loan_term_years} years
                                                </p>
                                            </div>
                                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                                <div className="p-4 bg-white/5 rounded-xl">
                                                    <p className="text-[9px] font-bold text-text-dim uppercase">Debt Amount</p>
                                                    <p className="text-lg font-black text-text-primary">₵{results.financials.debt.debt_amount.toLocaleString()}</p>
                                                </div>
                                                <div className="p-4 bg-white/5 rounded-xl">
                                                    <p className="text-[9px] font-bold text-text-dim uppercase">Equity</p>
                                                    <p className="text-lg font-black text-text-primary">₵{results.financials.debt.equity_amount.toLocaleString()}</p>
                                                </div>
                                                <div className="p-4 bg-white/5 rounded-xl">
                                                    <p className="text-[9px] font-bold text-text-dim uppercase">Annual Debt Service</p>
                                                    <p className="text-lg font-black text-text-primary">₵{results.financials.debt.annual_debt_service.toLocaleString()}</p>
                                                </div>
                                                <div className={`p-4 rounded-xl ${results.financials.debt.min_dscr >= 1.3 ? 'bg-emerald-500/10 border border-emerald-500/20' : results.financials.debt.min_dscr >= 1.0 ? 'bg-amber-500/10 border border-amber-500/20' : 'bg-red-500/10 border border-red-500/20'}`}>
                                                    <p className="text-[9px] font-bold text-text-dim uppercase">Min DSCR</p>
                                                    <p className={`text-lg font-black ${results.financials.debt.min_dscr >= 1.3 ? 'text-emerald-400' : results.financials.debt.min_dscr >= 1.0 ? 'text-amber-400' : 'text-red-400'}`}>
                                                        {results.financials.debt.min_dscr.toFixed(2)}x
                                                    </p>
                                                    <p className="text-[8px] text-text-dim mt-0.5">
                                                        {results.financials.debt.min_dscr >= 1.3 ? 'Lender threshold met' : results.financials.debt.min_dscr >= 1.0 ? 'Marginal — below 1.3x' : 'Below 1.0x — debt cannot be serviced'}
                                                    </p>
                                                </div>
                                            </div>
                                            {results.financials.debt.dscr_by_year && results.financials.debt.dscr_by_year.length > 0 && (
                                                <div className="h-48 w-full">
                                                    <ResponsiveContainer width="100%" height="100%">
                                                        <BarChart data={results.financials.debt.dscr_by_year.map((v, i) => ({ year: `Y${i + 1}`, dscr: v }))}>
                                                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
                                                            <XAxis dataKey="year" stroke="#475569" fontSize={9} tickLine={false} axisLine={false} />
                                                            <YAxis stroke="#475569" fontSize={9} tickLine={false} axisLine={false} domain={[0, 'auto']} />
                                                            <Tooltip
                                                                contentStyle={{ backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--chart-tooltip-border)', borderRadius: '12px' }}
                                                                formatter={(val) => [`${val.toFixed(2)}x`, 'DSCR']}
                                                            />
                                                            <ReferenceLine y={1.3} stroke="#10b981" strokeDasharray="4 4" label={{ value: '1.3x', position: 'right', fontSize: 9, fill: '#10b981' }} />
                                                            <Bar dataKey="dscr" radius={[3, 3, 0, 0]}>
                                                                {results.financials.debt.dscr_by_year.map((v, i) => (
                                                                    <Cell key={i} fill={v >= 1.3 ? '#10b981' : v >= 1.0 ? '#f59e0b' : '#ef4444'} />
                                                                ))}
                                                            </Bar>
                                                        </BarChart>
                                                    </ResponsiveContainer>
                                                </div>
                                            )}
                                        </div>
                                    )}

                                    {/* O&M Breakdown */}
                                    {results.financials?.om_breakdown && (
                                        <div className="bg-glass-bg rounded-3xl overflow-hidden card-hover">
                                            <div className="px-8 py-5 border-b border-border-subtle bg-glass-bg">
                                                <h3 className="text-xs font-bold text-text-muted uppercase tracking-widest">O&M Cost Breakdown</h3>
                                                <p className="text-[10px] text-text-dim mt-1">GH₵{results.financials.om_per_kw}/kWp/year — transparent assumptions per IRENA West Africa benchmarks</p>
                                            </div>
                                            <div className="p-8 grid grid-cols-2 md:grid-cols-5 gap-4">
                                                {[
                                                    { k: 'Cleaning', v: results.financials.om_breakdown.cleaning, Icon: Droplets },
                                                    { k: 'Inverter Reserve', v: results.financials.om_breakdown.inverter_reserve, Icon: Cpu },
                                                    { k: 'Monitoring', v: results.financials.om_breakdown.monitoring, Icon: Activity },
                                                    { k: 'Insurance', v: results.financials.om_breakdown.insurance, Icon: Umbrella },
                                                    { k: 'Spare Parts', v: results.financials.om_breakdown.spare_parts, Icon: Wrench },
                                                ].map((item, i) => (
                                                    <div key={i} className="p-3 bg-white/5 rounded-xl text-center">
                                                        <div className="flex justify-center mb-2">
                                                            <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center">
                                                                <item.Icon className="w-4 h-4 text-text-dim" />
                                                            </div>
                                                        </div>
                                                        <p className="text-[9px] font-bold text-text-dim uppercase">{item.k}</p>
                                                        <p className="text-sm font-black text-text-primary">GH₵{item.v}/kWp</p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Sensitivity Tornado */}
                                    {results.lossParams && (
                                        <SensitivityTornado results={results} />
                                    )}
                                </>
                            )}

                            {activeTab === 'environmental' && (
                                <div className="space-y-8">
                                    <div className="p-8 bg-glass-bg rounded-3xl space-y-6 card-hover">
                                        <div>
                                            <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                                                <Leaf className="w-4 h-4 text-emerald-400" />
                                                Environmental Impact
                                            </h3>
                                            <p className="text-xs text-text-dim mt-1">Estimated emission avoidance from displaced grid electricity</p>
                                        </div>

                                        {envMetrics ? (
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                                <div className="p-5 bg-white/5 rounded-2xl">
                                                    <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest mb-2">Air Quality</p>
                                                    <div className="space-y-3">
                                                        <div className="flex justify-between items-center">
                                                            <span className="text-xs text-text-secondary">PM2.5 (Ambient)</span>
                                                            <span className="text-sm font-bold text-text-primary">
                                                                {envMetrics.pm_data_available && envMetrics.mean_pm25 != null
                                                                    ? `${envMetrics.mean_pm25.toFixed(2)} µg/m³`
                                                                    : <span className="text-text-dim text-xs italic">Not yet available</span>}
                                                            </span>
                                                        </div>
                                                        <div className="flex justify-between items-center">
                                                            <span className="text-xs text-text-secondary">PM10 (Ambient)</span>
                                                            <span className="text-sm font-bold text-text-primary">
                                                                {envMetrics.pm_data_available && envMetrics.mean_pm10 != null
                                                                    ? `${envMetrics.mean_pm10.toFixed(2)} µg/m³`
                                                                    : <span className="text-text-dim text-xs italic">Not yet available</span>}
                                                            </span>
                                                        </div>
                                                    </div>
                                                    {!envMetrics.pm_data_available && (
                                                        <p className="text-[9px] text-text-dim mt-3 italic">PM data requires ground-level sensors; satellite sources (NASA POWER) do not provide particulate measurements.</p>
                                                    )}
                                                </div>
                                                <div className="p-5 bg-white/5 rounded-2xl">
                                                    <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest mb-2">System Maintenance</p>
                                                    <div className="space-y-3">
                                                        <div className="flex justify-between items-center">
                                                            <span className="text-xs text-text-secondary">Cleaning Events / Month</span>
                                                            <span className="text-sm font-bold text-text-primary">{envMetrics.mean_cleaning_events_monthly?.toFixed(1) || '0'}</span>
                                                        </div>
                                                    </div>
                                                    <p className="text-[9px] text-text-dim mt-3 italic">Estimated from rainfall events (&gt;0.5mm); heavy rain self-cleans panels.</p>
                                                </div>
                                            </div>
                                        ) : (
                                            <p className="text-sm text-text-dim">Environmental metrics not available for this simulation.</p>
                                        )}
                                    </div>

                                    {/* Carbon equivalence */}
                                    {envMetrics && (
                                        <div className="p-8 bg-glass-bg rounded-3xl card-hover">
                                            <h3 className="text-sm font-bold text-text-primary flex items-center gap-2 mb-4">
                                                <Leaf className="w-4 h-4 text-emerald-400" />
                                                Carbon Equivalence
                                            </h3>
                                            <p className="text-xs text-text-dim">
                                                Based on {formatEnergy(results.annualEnergy)} annual yield, this system avoids an estimated{' '}
                                                <span className="text-emerald-400 font-bold">
                                                    {(results.annualEnergy * 0.0005).toFixed(1)} tonnes CO₂
                                                </span>{' '}
                                                per year (using Ghana grid emission factor of ~0.5 kg CO₂/kWh).
                                            </p>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="px-8 py-5 bg-surface border-t border-border-subtle flex justify-between items-center text-[10px] text-text-dim font-mono">
                        <span>UNISOLAR FINANCIAL REPORT V2.5</span>
                        <span>CONFIDENTIAL — GENERATED FOR ASSET DESIGN</span>
                    </div>
                </motion.div>
            </div>
        </AnimatePresence>
    );
}

/**
 * Sensitivity Tornado — shows NPV sensitivity to ±20% variation in key parameters.
 * Computed client-side by perturbing each variable independently.
 */
function SensitivityTornado({ results }) {
    const baseNpv = results.npv || 0;
    const capex = results.capex || 0;
    const annualSavings = results.annualSavingsY1 || 0;
    const lcoe = results.lcoe || 0;
    const lp = results.lossParams || {};
    const degradationPct = (lp.degradation_rate_pct ?? 0.5) / 100;
    const tariffEscPct = (lp.tariff_escalation_pct ?? 3.0) / 100;

    const perturbations = useMemo(() => {
        const factor = 0.20; // ±20%
        const wacc = 0.08;
        const lifetime = 25;

        // Simple NPV recalculation for each perturbation
        function calcNpv(degradationRate, tariffEsc, capexVal, savingsVal) {
            let npv = -capexVal;
            for (let y = 1; y <= lifetime; y++) {
                const deg = y === 1 ? 0.98 : 0.98 * Math.pow(1 - degradationRate, y - 1);
                const esc = Math.pow(1 + tariffEsc, y - 1);
                const netCash = (savingsVal * deg * esc) - (320 * results.capacityKw * Math.pow(1.02, y - 1));
                npv += netCash / Math.pow(1 + wacc, y);
            }
            return npv;
        }

        const rows = [
            {
                name: 'Tariff Escalation',
                low: calcNpv(degradationPct, tariffEscPct * (1 - factor), capex, annualSavings),
                high: calcNpv(degradationPct, tariffEscPct * (1 + factor), capex, annualSavings),
            },
            {
                name: 'Degradation Rate',
                low: calcNpv(degradationPct * (1 + factor), tariffEscPct, capex, annualSavings),
                high: calcNpv(degradationPct * (1 - factor), tariffEscPct, capex, annualSavings),
            },
            {
                name: 'CAPEX',
                low: calcNpv(degradationPct, tariffEscPct, capex * (1 - factor), annualSavings),
                high: calcNpv(degradationPct, tariffEscPct, capex * (1 + factor), annualSavings),
            },
            {
                name: 'Irradiance (Yield)',
                low: calcNpv(degradationPct, tariffEscPct, capex, annualSavings * (1 - factor)),
                high: calcNpv(degradationPct, tariffEscPct, capex, annualSavings * (1 + factor)),
            },
            {
                name: 'WACC (Discount Rate)',
                low: (() => {
                    let npv = -capex;
                    for (let y = 1; y <= lifetime; y++) {
                        const deg = y === 1 ? 0.98 : 0.98 * Math.pow(1 - degradationPct, y - 1);
                        const esc = Math.pow(1 + tariffEscPct, y - 1);
                        const netCash = (annualSavings * deg * esc) - (320 * results.capacityKw * Math.pow(1.02, y - 1));
                        npv += netCash / Math.pow(1 + wacc * (1 - factor), y);
                    }
                    return npv;
                })(),
                high: (() => {
                    let npv = -capex;
                    for (let y = 1; y <= lifetime; y++) {
                        const deg = y === 1 ? 0.98 : 0.98 * Math.pow(1 - degradationPct, y - 1);
                        const esc = Math.pow(1 + tariffEscPct, y - 1);
                        const netCash = (annualSavings * deg * esc) - (320 * results.capacityKw * Math.pow(1.02, y - 1));
                        npv += netCash / Math.pow(1 + wacc * (1 + factor), y);
                    }
                    return npv;
                })(),
            },
        ];

        // Compute deltas from base NPV
        return rows.map(r => ({
            name: r.name,
            lowDelta: r.low - baseNpv,
            highDelta: r.high - baseNpv,
            range: Math.abs(r.high - r.low),
        })).sort((a, b) => b.range - a.range);
    }, [baseNpv, capex, annualSavings, degradationPct, tariffEscPct, results.capacityKw]);

    const maxDelta = Math.max(...perturbations.map(p => Math.max(Math.abs(p.lowDelta), Math.abs(p.highDelta))), 1);

    return (
        <div className="p-8 bg-glass-bg rounded-3xl space-y-6 card-hover">
            <div>
                <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                    Sensitivity Analysis — NPV Tornado
                </h3>
                <p className="text-xs text-text-dim mt-1">Impact on NPV from ±20% variation in each parameter (all else held constant)</p>
            </div>
            <div className="space-y-3">
                {perturbations.map((p, i) => {
                    const barScale = 200 / maxDelta;
                    const lowPx = Math.abs(p.lowDelta) * barScale;
                    const highPx = Math.abs(p.highDelta) * barScale;
                    return (
                        <div key={i} className="flex items-center gap-3">
                            <div className="w-32 text-right">
                                <p className="text-[10px] font-bold text-text-secondary">{p.name}</p>
                                <p className="text-[8px] text-text-dim">±20%</p>
                            </div>
                            <div className="flex-1 flex items-center h-6 relative">
                                {/* Center line */}
                                <div className="absolute left-1/2 top-0 bottom-0 w-px bg-border-subtle" />
                                {/* Low bar (left) */}
                                <div
                                    className="absolute h-4 rounded-l-md bg-red-400/70"
                                    style={{
                                        right: '50%',
                                        width: `${lowPx / 2}px`,
                                    }}
                                />
                                {/* High bar (right) */}
                                <div
                                    className="absolute h-4 rounded-r-md bg-emerald-400/70"
                                    style={{
                                        left: '50%',
                                        width: `${highPx / 2}px`,
                                    }}
                                />
                            </div>
                            <div className="w-28 text-right">
                                <p className="text-[9px] text-red-400 font-mono">-₵{Math.abs(Math.round(p.lowDelta)).toLocaleString()}</p>
                                <p className="text-[9px] text-emerald-400 font-mono">+₵{Math.abs(Math.round(p.highDelta)).toLocaleString()}</p>
                            </div>
                        </div>
                    );
                })}
            </div>
            <div className="flex items-center gap-4 text-[9px] text-text-dim pt-2 border-t border-border-subtle">
                <span className="flex items-center gap-1"><span className="w-3 h-2 bg-red-400/70 rounded" /> NPV decreases</span>
                <span className="flex items-center gap-1"><span className="w-3 h-2 bg-emerald-400/70 rounded" /> NPV increases</span>
                <span>Base NPV: ₵{Math.round(baseNpv).toLocaleString()}</span>
            </div>
        </div>
    );
}
