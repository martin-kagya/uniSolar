import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { TrendingUp, BarChart2, DollarSign, Clock, Zap, ChevronDown, ChevronUp } from 'lucide-react';

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const LOSS_COLORS = {
    soiling: '#f59e0b',
    shading: '#8b5cf6',
    degradation: '#ef4444',
    inverter: '#06b6d4',
    physics_derate: '#64748b',
};

const LOSS_LABELS = {
    soiling: 'Soiling',
    shading: 'Shading',
    degradation: 'Degradation',
    inverter: 'Inverter Efficiency',
    physics_derate: 'Wiring / LID / Mismatch',
};

function LossDonut({ losses }) {
    if (!losses) return null;
    const data = [
        { name: 'Soiling', value: losses.soiling_percent || 0, color: LOSS_COLORS.soiling },
        { name: 'Shading', value: losses.shading_percent || 0, color: LOSS_COLORS.shading },
        { name: 'Degradation', value: losses.degradation_percent || 0, color: LOSS_COLORS.degradation },
        { name: 'Inverter Efficiency', value: losses.inverter_percent || 0, color: LOSS_COLORS.inverter },
        { name: 'Wiring / LID / Mismatch', value: losses.physics_derate_percent || 0, color: LOSS_COLORS.physics_derate },
    ].filter(d => d.value > 0.01);

    if (data.length === 0) return null;
    const totalLoss = data.reduce((s, d) => s + d.value, 0);

    return (
        <div className="flex items-center gap-3">
            <div className="w-16 h-16 flex-shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie
                            data={data}
                            cx="50%"
                            cy="50%"
                            innerRadius={16}
                            outerRadius={30}
                            dataKey="value"
                            strokeWidth={0}
                        >
                            {data.map((entry, i) => (
                                <Cell key={i} fill={entry.color} />
                            ))}
                        </Pie>
                    </PieChart>
                </ResponsiveContainer>
            </div>
            <div className="space-y-0.5 min-w-0">
                {data.map((d) => (
                    <div key={d.name} className="flex items-center gap-1.5 text-[9px]">
                        <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: d.color }} />
                        <span className="text-text-dim truncate">{d.name}</span>
                        <span className="text-text-secondary font-bold ml-auto">{d.value.toFixed(1)}%</span>
                    </div>
                ))}
                <div className="flex items-center gap-1.5 text-[9px] pt-0.5 border-t border-border-subtle mt-0.5">
                    <span className="text-text-dim">Total Loss</span>
                    <span className="text-amber-400 font-bold ml-auto">{totalLoss.toFixed(1)}%</span>
                </div>
            </div>
        </div>
    );
}

export default function ResultsPanel({ results, isVisible, onViewReport }) {
    const [showLosses, setShowLosses] = useState(false);

    if (!isVisible || !results) return null;

    const monthlyData = results.monthlyEnergy
        ? results.monthlyEnergy.map((val, idx) => ({ name: MONTH_NAMES[idx], yield: Math.round(val) }))
        : null;

    return (
        <div className="fixed bottom-6 right-6 w-[360px] bg-surface-overlay rounded-2xl flex flex-col z-40 backdrop-blur-xl overflow-hidden card-hover">

            {/* Header — Annual Yield + P50/P90 */}
            <div className="p-5 border-b border-border-subtle">
                <div className="flex justify-between items-start">
                    <div>
                        <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest mb-1">Annual Yield</p>
                        <div className="flex items-baseline gap-1">
                            <span className="text-3xl font-bold text-text-primary">
                                {Number.isFinite(results.annualEnergy)
                                    ? results.annualEnergy.toLocaleString(undefined, { maximumFractionDigits: 0 })
                                    : '0'
                                }
                            </span>
                            <span className="text-sm text-text-dim font-medium">kWh</span>
                        </div>
                    </div>
                    <div className="p-2 bg-brand-gold/10 text-brand-gold rounded-lg">
                        <Zap className="w-5 h-5" />
                    </div>
                </div>

                {/* P50 / P90 / P99 badges */}
                {results.probabilisticResults && (
                    <div className="flex gap-2 mt-3">
                        <div className="px-2 py-1 bg-glass-bg border border-border-theme rounded-lg flex-1">
                            <p className="text-[8px] font-bold text-text-dim uppercase">P50 Expected</p>
                            <p className="text-xs font-bold text-text-primary">
                                {(results.probabilisticResults.p50_yield / 1000).toFixed(1)} <span className="text-[8px] text-text-dim">MWh</span>
                            </p>
                        </div>
                        <div className="px-2 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-lg flex-1">
                            <p className="text-[8px] font-bold text-emerald-500 uppercase">P90 Bankable</p>
                            <p className="text-xs font-bold text-text-primary">
                                {(results.probabilisticResults.p90_yield / 1000).toFixed(1)} <span className="text-[8px] text-emerald-500/60">MWh</span>
                            </p>
                        </div>
                        {results.probabilisticResults.p99_yield != null && (
                            <div className="px-2 py-1 bg-amber-500/10 border border-amber-500/20 rounded-lg flex-1">
                                <p className="text-[8px] font-bold text-amber-500 uppercase">P99 Worst</p>
                                <p className="text-xs font-bold text-text-primary">
                                    {(results.probabilisticResults.p99_yield / 1000).toFixed(1)} <span className="text-[8px] text-amber-500/60">MWh</span>
                                </p>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Metrics Grid — 2x3 */}
            <div className="grid grid-cols-3 border-b border-border-subtle">
                <div className="p-3 border-r border-border-subtle">
                    <p className="text-[9px] font-bold text-text-dim uppercase mb-0.5">NPV</p>
                    <p className="text-sm font-bold text-text-primary">
                        ₵{Number.isFinite(results.npv) ? results.npv.toLocaleString(undefined, { maximumFractionDigits: 0 }) : '0'}
                    </p>
                </div>
                <div className="p-3 border-r border-border-subtle">
                    <p className="text-[9px] font-bold text-text-dim uppercase mb-0.5">Payback</p>
                    <p className="text-sm font-bold text-text-primary">
                        {typeof results.payback === 'number' && Number.isFinite(results.payback) ? results.payback.toFixed(1) : 'N/A'} yr
                    </p>
                </div>
                <div className="p-3">
                    <p className="text-[9px] font-bold text-text-dim uppercase mb-0.5">IRR</p>
                    <p className="text-sm font-bold text-text-primary">
                        {results.irr != null && Number.isFinite(results.irr) ? `${(results.irr * 100).toFixed(1)}%` : 'N/A'}
                    </p>
                </div>
            </div>

            {/* LCOE + Capex row */}
            <div className="grid grid-cols-2 border-b border-border-subtle">
                <div className="p-3 border-r border-border-subtle">
                    <p className="text-[9px] font-bold text-text-dim uppercase mb-0.5">LCOE</p>
                    <p className="text-sm font-bold text-text-primary">
                        {results.lcoe != null && Number.isFinite(results.lcoe) ? `₵${results.lcoe.toFixed(3)}/kWh` : 'N/A'}
                    </p>
                </div>
                <div className="p-3">
                    <p className="text-[9px] font-bold text-text-dim uppercase mb-0.5">Capex</p>
                    <p className="text-sm font-bold text-text-primary">
                        {results.capex != null && Number.isFinite(results.capex) ? `₵${results.capex.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : 'N/A'}
                    </p>
                </div>
            </div>

            {/* Monthly Production Chart */}
            {monthlyData && (
                <div className="h-36 w-full px-4 pt-3">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={monthlyData}>
                            <XAxis dataKey="name" stroke="#475569" fontSize={9} tickLine={false} axisLine={false} />
                            <YAxis hide stroke="#475569" fontSize={9} tickLine={false} axisLine={false} />
                            <Tooltip
                                cursor={{ fill: 'var(--glass-bg)' }}
                                contentStyle={{
                                    borderRadius: '8px',
                                    border: '1px solid var(--chart-tooltip-border)',
                                    backgroundColor: 'var(--chart-tooltip-bg)',
                                    color: '#fff',
                                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                                    fontSize: '11px'
                                }}
                                formatter={(val) => [`${val.toLocaleString()} kWh`, 'Yield']}
                            />
                            <Bar dataKey="yield" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            )}

            {/* Loss Breakdown (collapsible) */}
            {results.losses && (
                <div className="border-t border-border-subtle">
                    <button
                        onClick={() => setShowLosses(!showLosses)}
                        className="w-full px-4 py-2.5 flex items-center justify-between text-[10px] font-bold text-text-dim uppercase tracking-widest hover:bg-glass-bg transition-colors"
                    >
                        <span>Loss Breakdown</span>
                        {showLosses ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>
                    {showLosses && (
                        <div className="px-4 pb-3">
                            <LossDonut losses={results.losses} />
                        </div>
                    )}
                </div>
            )}

            {/* Action Button */}
            <button
                onClick={onViewReport}
                className="w-full py-3.5 bg-gradient-to-r from-brand-gold to-orange-500 text-white font-bold text-sm hover:shadow-[0_0_30px_rgba(245,158,11,0.2)] transition-all flex items-center justify-center gap-2"
            >
                <BarChart2 className="w-4 h-4" />
                VIEW FULL REPORT
            </button>
        </div>
    );
}
