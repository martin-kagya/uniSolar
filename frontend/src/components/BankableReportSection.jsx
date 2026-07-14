import React from 'react';
import { motion } from 'framer-motion';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const data = [
    { month: 'Jan', production: 4000, revenue: 2400 },
    { month: 'Feb', production: 3000, revenue: 1398 },
    { month: 'Mar', production: 2000, revenue: 9800 },
    { month: 'Apr', production: 2780, revenue: 3908 },
    { month: 'May', production: 1890, revenue: 4800 },
    { month: 'Jun', production: 2390, revenue: 3800 },
    { month: 'Jul', production: 3490, revenue: 4300 },
];

const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
        return (
            <div className="bg-surface-dropdown border border-border-theme p-4 shadow-xl rounded-lg">
                <p className="text-text-muted text-xs uppercase mb-2">{label}</p>
                <p className="text-blue-400 font-mono text-sm">
                    Production: <span className="text-text-primary">{payload[0].value} kWh</span>
                </p>
                <p className="text-emerald-400 font-mono text-sm">
                    Revenue: <span className="text-text-primary">${payload[1].value}</span>
                </p>
            </div>
        );
    }
    return null;
};

export default function BankableReportSection() {
    return (
        <section className="py-24 relative z-10 w-full bg-surface">
            <div className="max-w-7xl mx-auto px-6 grid grid-cols-1 lg:grid-cols-2 gap-20 items-center">
                <motion.div
                    initial={{ opacity: 0, x: -50 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8 }}
                >
                    <h2 className="font-heading text-4xl md:text-5xl font-bold mb-6 text-text-primary">
                        Bankable Reports, <br /><span className="text-emerald-400">Instantly.</span>
                    </h2>
                    <p className="text-text-muted text-lg mb-8 max-w-lg leading-relaxed">
                        Generate lender-ready PDF reports with P50/P90 yield analysis, cash flow waterfalls, and sensitivity tables. Your investors need certainty—UniSolar delivers it.
                    </p>
                    <ul className="space-y-4 mb-10 text-text-secondary">
                        {['P50 / P90 Probability Analysis', 'Detailed Cash-Flow Waterfalls', 'T.M.Y. Weather Data Integration'].map(item => (
                            <li key={item} className="flex items-center gap-3">
                                <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full shadow-[0_0_8px_rgba(52,211,153,0.8)]"></div>
                                {item}
                            </li>
                        ))}
                    </ul>
                    <button className="text-emerald-400 border-b border-emerald-400/30 pb-1 hover:border-emerald-400 transition-colors">
                        Download Sample Report
                    </button>
                </motion.div>

                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8 }}
                    className="bg-surface-overlay/50 p-8 rounded-2xl backdrop-blur-sm relative card-hover"
                >
                    {/* Decorative glow behind chart */}
                    <div className="absolute inset-0 bg-emerald-500/5 rounded-2xl pointer-events-none"></div>

                    <div className="h-[400px] w-full relative z-10">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorProd" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                    </linearGradient>
                                    <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
                                        <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                <XAxis dataKey="month" stroke="#475569" tickLine={false} axisLine={false} />
                                <YAxis stroke="#475569" tickLine={false} axisLine={false} />
                                <Tooltip content={<CustomTooltip />} />
                                <Area type="monotone" dataKey="production" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#colorProd)" />
                                <Area type="monotone" dataKey="revenue" stroke="#10B981" strokeWidth={2} fillOpacity={1} fill="url(#colorRev)" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                    <div className="mt-6 flex justify-between text-xs text-text-dim font-mono uppercase tracking-wider">
                        <span className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-blue-500"></div> Production (kWh)</span>
                        <span className="flex items-center gap-2"><div className="w-2 h-2 rounded-full bg-emerald-500"></div> Revenue (USD)</span>
                    </div>
                </motion.div>
            </div>
        </section>
    );
}
