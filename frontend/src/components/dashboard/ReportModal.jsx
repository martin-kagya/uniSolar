import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, FileText, Download, TrendingUp, DollarSign, Zap, Clock, PieChart } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

export default function ReportModal({ isOpen, onClose, results }) {
    if (!isOpen || !results) return null;

    const [activeTab, setActiveTab] = useState('yield');

    const monthlyData = [
        { name: 'Jan', yield: 450, revenue: 850 },
        { name: 'Feb', yield: 420, revenue: 790 },
        { name: 'Mar', yield: 510, revenue: 960 },
        { name: 'Apr', yield: 580, revenue: 1100 },
        { name: 'May', yield: 640, revenue: 1210 },
        { name: 'Jun', yield: 610, revenue: 1150 },
        { name: 'Jul', yield: 590, revenue: 1110 },
        { name: 'Aug', yield: 630, revenue: 1190 },
        { name: 'Sep', yield: 540, revenue: 1020 },
        { name: 'Oct', yield: 490, revenue: 930 },
        { name: 'Nov', yield: 440, revenue: 830 },
        { name: 'Dec', yield: 410, revenue: 770 },
    ];

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
                    <div className="px-8 py-6 border-b border-border-subtle flex justify-between items-center bg-gradient-to-r from-glass-bg to-transparent">
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 rounded-2xl bg-brand-gold/10 flex items-center justify-center text-brand-gold">
                                <FileText className="w-6 h-6" />
                            </div>
                            <div>
                                <h2 className="text-xl font-bold text-text-primary tracking-tight">Financial & Yield Audit</h2>
                                <p className="text-xs text-text-dim font-bold uppercase tracking-widest mt-0.5">Lender-Ready Project Report</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3">
                            <button className="flex items-center gap-2 px-4 py-2 bg-glass-bg hover:bg-white/10 text-text-primary rounded-xl text-xs font-bold transition-all border border-border-theme group">
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
                            <button
                                onClick={() => setActiveTab('yield')}
                                className={`py-4 text-xs font-bold uppercase tracking-widest relative transition-colors ${activeTab === 'yield' ? 'text-amber-400' : 'text-text-dim hover:text-text-secondary'}`}
                            >
                                <span className="flex items-center gap-2"><Zap className="w-4 h-4" /> Yield Report</span>
                                {activeTab === 'yield' && (
                                    <motion.div layoutId="activeTab" className="absolute bottom-[-1px] left-0 right-0 h-0.5 bg-amber-400" />
                                )}
                            </button>
                            <button
                                onClick={() => setActiveTab('financial')}
                                className={`py-4 text-xs font-bold uppercase tracking-widest relative transition-colors ${activeTab === 'financial' ? 'text-amber-400' : 'text-text-dim hover:text-text-secondary'}`}
                            >
                                <span className="flex items-center gap-2"><DollarSign className="w-4 h-4" /> Financial Report</span>
                                {activeTab === 'financial' && (
                                    <motion.div layoutId="activeTab" className="absolute bottom-[-1px] left-0 right-0 h-0.5 bg-amber-400" />
                                )}
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-8 space-y-10 custom-scrollbar">

                            {activeTab === 'yield' ? (
                                <>
                                    {/* Yield Summary Cards */}
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Annual Energy</p>
                                                <Zap className="w-4 h-4 text-brand-gold" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">{results.annualEnergy.toLocaleString()} kWh</p>
                                        </div>
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Installed DC</p>
                                                <TrendingUp className="w-4 h-4 text-blue-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">{results.capacityKw.toFixed(2)} kWp</p>
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
                                                    <p className="text-xs text-text-dim">Normal distribution of 1,000 Monte Carlo simulation runs</p>
                                                </div>
                                                <div className="flex gap-2">
                                                    <div className="px-2 py-1 bg-glass-bg border border-border-theme rounded-lg">
                                                        <p className="text-[8px] font-bold text-text-dim uppercase">P50 (Expected)</p>
                                                        <p className="text-xs font-bold text-text-primary">{(results.probabilisticResults.p50_yield / 1000).toFixed(1)} <span className="text-[8px] text-text-dim">MWh</span></p>
                                                    </div>
                                                    <div className="px-2 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-lg">
                                                        <p className="text-[8px] font-bold text-emerald-500 uppercase">P90 (Bankable)</p>
                                                        <p className="text-xs font-bold text-text-primary">{(results.probabilisticResults.p90_yield / 1000).toFixed(1)} <span className="text-[8px] text-emerald-500/60">MWh</span></p>
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

                                    {/* Yield Distribution */}
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
                                                    />
                                                    <Bar dataKey="yield" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                                                </BarChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </div>

                                    {/* Audit Details */}
                                    <div className="bg-glass-bg rounded-3xl overflow-hidden card-hover">
                                        <div className="px-8 py-5 border-b border-border-subtle bg-glass-bg">
                                            <h3 className="text-xs font-bold text-text-muted uppercase tracking-widest">Simulation Parameters</h3>
                                        </div>
                                        <div className="p-8 grid grid-cols-2 md:grid-cols-4 gap-8">
                                            {[
                                                { k: 'Panel Count', v: results.panelCount },
                                                { k: 'Installed DC', v: `${results.capacityKw.toFixed(2)} kWp` },
                                                { k: 'PR Rating', v: '82.4%' },
                                                { k: 'Soiling Loss', v: '3.5%' },
                                                { k: 'System Tilt', v: '15°' },
                                                { k: 'Grid Connection', v: 'LV / Single' },
                                            ].map((row, i) => (
                                                <div key={i}>
                                                    <p className="text-[10px] font-bold text-text-dim uppercase tracking-tighter mb-1">{row.k}</p>
                                                    <p className="text-sm font-bold text-text-primary tracking-tight">{row.v}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </>
                            ) : (
                                <>
                                    {/* Financial Summary Cards */}
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <div className="p-5 bg-glass-bg rounded-2xl card-hover">
                                            <div className="flex justify-between items-start mb-3">
                                                <p className="text-[10px] font-bold text-text-dim uppercase tracking-widest">Net Present Value</p>
                                                <DollarSign className="w-4 h-4 text-emerald-400" />
                                            </div>
                                            <p className="text-2xl font-black text-text-primary">₵{results.npv.toLocaleString()}</p>
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

                                    {/* Revenue Stream */}
                                    <div className="p-8 bg-glass-bg rounded-3xl space-y-6 card-hover">
                                        <div>
                                            <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                                                <DollarSign className="w-4 h-4 text-emerald-400" />
                                                Projected Savings
                                            </h3>
                                            <p className="text-xs text-text-dim mt-1">Avoided utility costs based on ₵{results.rate || 1.90}/kWh tariff</p>
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
                                                    />
                                                    <Area type="monotone" dataKey="revenue" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorReportRev)" />
                                                </AreaChart>
                                            </ResponsiveContainer>
                                        </div>
                                    </div>

                                    {/* Financial Details */}
                                    <div className="bg-glass-bg rounded-3xl overflow-hidden card-hover">
                                        <div className="px-8 py-5 border-b border-border-subtle bg-glass-bg">
                                            <h3 className="text-xs font-bold text-text-muted uppercase tracking-widest">Financial Parameters</h3>
                                        </div>
                                        <div className="p-8 grid grid-cols-2 md:grid-cols-4 gap-8">
                                            {[
                                                { k: 'Installed DC', v: `${results.capacityKw.toFixed(2)} kWp` },
                                                { k: 'LCOE (Est.)', v: results.lcoe != null ? `₵${results.lcoe.toFixed(3)}/kWh` : 'N/A' },
                                            ].map((row, i) => (
                                                <div key={i}>
                                                    <p className="text-[10px] font-bold text-text-dim uppercase tracking-tighter mb-1">{row.k}</p>
                                                    <p className="text-sm font-bold text-text-primary tracking-tight">{row.v}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="px-8 py-5 bg-surface border-t border-border-subtle flex justify-between items-center text-[10px] text-text-dim font-mono">
                        <span>UNISOLAR FINANCIAL REPORT V2.4</span>
                        <span>CONFIDENTIAL - GENERATED FOR ASSET DESIGN</span>
                    </div>
                </motion.div>
            </div>
        </AnimatePresence>
    );
}
