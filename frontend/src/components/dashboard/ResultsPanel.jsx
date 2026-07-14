import React from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, BarChart2 } from 'lucide-react';

export default function ResultsPanel({ results, isVisible, onViewReport }) {
    if (!isVisible || !results) return null;

    const data = results.dailyCurve || [
        { hour: '6am', val: 0 }, { hour: '8am', val: 20 }, { hour: '10am', val: 60 },
        { hour: '12pm', val: 95 }, { hour: '2pm', val: 70 }, { hour: '4pm', val: 30 }, { hour: '6pm', val: 5 }
    ];

    return (
        <div className="absolute bottom-6 right-6 w-[360px] bg-surface-overlay rounded-2xl flex flex-col z-40 backdrop-blur-xl overflow-hidden card-hover">

            {/* Header */}
            <div className="p-5 border-b border-border-subtle flex justify-between items-start">
                <div>
                    <h2 className="text-[10px] font-bold text-text-dim uppercase tracking-widest mb-1">Annual Yield</h2>
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
                    <TrendingUp className="w-5 h-5" />
                </div>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 border-b border-border-subtle">
                <div className="p-4 border-r border-border-subtle">
                    <p className="text-lg font-bold text-text-primary">
                        ₵{Number.isFinite(results.npv)
                            ? results.npv.toLocaleString(undefined, { maximumFractionDigits: 0 })
                            : '0'
                        }
                    </p>
                </div>
                <div className="p-4">
                    <p className="text-[10px] font-bold text-text-dim uppercase mb-1">Payback</p>
                    <p className="text-lg font-bold text-text-primary">
                        {typeof results.payback === 'number' && Number.isFinite(results.payback)
                            ? results.payback.toFixed(1)
                            : 'N/A'
                        } years
                    </p>
                </div>
            </div>

            {/* Mini Chart */}
            <div className="h-32 w-full p-4">
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={data}>
                        <defs>
                            <linearGradient id="colorValDark" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                            </linearGradient>
                        </defs>
                        <Tooltip
                            cursor={false}
                            contentStyle={{
                                borderRadius: '8px',
                                border: 'var(--chart-tooltip-border)',
                                backgroundColor: 'var(--chart-tooltip-bg)',
                                color: '#fff',
                                boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
                            }}
                        />
                        <Area type="monotone" dataKey="val" stroke="#f59e0b" strokeWidth={2} fillOpacity={1} fill="url(#colorValDark)" />
                    </AreaChart>
                </ResponsiveContainer>
            </div>

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
