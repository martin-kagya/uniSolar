import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Calculator, Zap, DollarSign, TrendingUp, CheckCircle, Info, Loader2 } from 'lucide-react';

export default function SizingHubModal({ isOpen, onClose, onSizingComplete }) {
    const [monthlyKwh, setMonthlyKwh] = useState(500);
    const [monthlyBill, setMonthlyBill] = useState(1000);
    const [useBill, setUseBill] = useState(false);
    const [utilityRate, setUtilityRate] = useState(1.90);
    const [customerType, setCustomerType] = useState('residential');
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);

    const handleCalculate = async () => {
        setLoading(true);
        try {
            const body = useBill
                ? { monthly_bill_ghs: monthlyBill, electricity_rate: utilityRate }
                : { monthly_consumption_kwh: monthlyKwh, electricity_rate: utilityRate };

            const response = await fetch('/size-system', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    latitude: 5.6037, // Default Accra context if map not ready
                    longitude: -0.1870,
                    customer_type: customerType,
                    ...body
                })
            });

            if (!response.ok) throw new Error('Sizing failed');
            const data = await response.json();
            setResults(data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

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
                    className="relative w-full max-w-2xl bg-surface-raised border border-border-theme rounded-3xl shadow-2xl overflow-hidden flex flex-col"
                >
                    {/* Header */}
                    <div className="px-8 py-6 border-b border-border-subtle flex justify-between items-center bg-gradient-to-r from-glass-bg to-transparent">
                        <div className="flex items-center gap-4">
                            <div className="w-12 h-12 rounded-2xl bg-brand-gold/10 flex items-center justify-center text-brand-gold">
                                <Calculator className="w-6 h-6" />
                            </div>
                            <div>
                                <h2 className="text-xl font-bold text-text-primary tracking-tight">Sizing Hub</h2>
                                <p className="text-xs text-text-dim font-bold uppercase tracking-widest mt-0.5">Scientific Capacity Planning</p>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="p-2 hover:bg-white/5 rounded-xl text-text-dim hover:text-text-primary transition-all"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>

                    {/* Content */}
                    <div className="p-8 space-y-8">

                        {/* Toggles */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="flex bg-glass-bg p-1 rounded-xl border border-border-subtle h-10">
                                <button
                                    onClick={() => setUseBill(false)}
                                    className={`flex-1 text-[10px] font-bold rounded-lg transition-all ${!useBill ? 'bg-brand-gold text-text-primary shadow-lg' : 'text-text-dim hover:text-text-secondary'}`}
                                >
                                    USE kWh
                                </button>
                                <button
                                    onClick={() => setUseBill(true)}
                                    className={`flex-1 text-[10px] font-bold rounded-lg transition-all ${useBill ? 'bg-brand-gold text-text-primary shadow-lg' : 'text-text-dim hover:text-text-secondary'}`}
                                >
                                    USE BILL (₵)
                                </button>
                            </div>

                            <div className="flex bg-glass-bg p-1 rounded-xl border border-border-subtle h-10">
                                <button
                                    onClick={() => setCustomerType('residential')}
                                    className={`flex-1 text-[10px] font-bold rounded-lg transition-all ${customerType === 'residential' ? 'bg-brand-gold text-text-primary shadow-lg' : 'text-text-dim hover:text-text-secondary'}`}
                                >
                                    RESIDENTIAL
                                </button>
                                <button
                                    onClick={() => setCustomerType('non_residential')}
                                    className={`flex-1 text-[10px] font-bold rounded-lg transition-all ${customerType === 'non_residential' ? 'bg-brand-gold text-text-primary shadow-lg' : 'text-text-dim hover:text-text-secondary'}`}
                                >
                                    NON-RES
                                </button>
                            </div>
                        </div>

                        {/* Inputs */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            <div className="space-y-3">
                                <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest flex items-center gap-2">
                                    {useBill ? <TrendingUp className="w-3 h-3" /> : <Zap className="w-3 h-3" />}
                                    {useBill ? 'Avg Monthly Bill (₵)' : 'Avg Monthly Usage (kWh)'}
                                </label>
                                <div className="relative">
                                    <input
                                        type="number"
                                        value={useBill ? monthlyBill : monthlyKwh}
                                        onChange={(e) => useBill ? setMonthlyBill(e.target.value) : setMonthlyKwh(e.target.value)}
                                        className="w-full bg-glass-bg border border-border-theme rounded-xl px-4 py-3 text-text-primary font-bold focus:outline-none focus:border-brand-gold/50 transition-colors"
                                    />
                                    <span className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] font-bold text-text-dim">
                                        {useBill ? '₵/MO' : 'kWh/MO'}
                                    </span>
                                </div>
                            </div>

                            <div className="space-y-3">
                                <label className="text-[10px] font-bold text-text-dim uppercase tracking-widest flex items-center gap-2">
                                    <DollarSign className="w-3 h-3" />
                                    Effective Tariff (₵/kWh)
                                </label>
                                <div className="relative">
                                    <input
                                        type="number"
                                        value={utilityRate}
                                        onChange={(e) => setUtilityRate(e.target.value)}
                                        className="w-full bg-glass-bg border border-border-theme rounded-xl px-4 py-3 text-text-primary font-bold focus:outline-none focus:border-brand-gold/50 transition-colors"
                                    />
                                    <span className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] font-bold text-text-dim">
                                        ₵/kWh
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* Recommendations */}
                        {results && (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="bg-brand-gold/5 rounded-2xl p-6 overflow-hidden relative card-hover"
                            >
                                <div className="absolute top-0 right-0 p-4 opacity-10">
                                    <Calculator className="w-24 h-24" />
                                </div>

                                <h3 className="text-xs font-bold text-brand-gold uppercase tracking-widest mb-4 flex items-center gap-2">
                                    <CheckCircle className="w-4 h-4" />
                                    System Recommendation
                                </h3>

                                <div className="grid grid-cols-2 gap-8 relative z-10">
                                    <div>
                                        <p className="text-[10px] font-bold text-text-dim uppercase tracking-tighter mb-1">Required Capacity</p>
                                        <p className="text-2xl font-black text-text-primary">{results.required_kwp} <span className="text-sm font-medium text-text-dim">kWp</span></p>
                                    </div>
                                    <div>
                                        <p className="text-[10px] font-bold text-text-dim uppercase tracking-tighter mb-1">Avg Daily Yield</p>
                                        <p className="text-2xl font-black text-text-primary">{results.daily_kwh.toFixed(1)} <span className="text-sm font-medium text-text-dim">kWh</span></p>
                                    </div>
                                    {results.tariff_info && (
                                        <div className="col-span-2 mt-2 p-2 bg-black/20 rounded-lg flex items-center justify-between">
                                            <span className="text-[9px] font-bold text-brand-gold uppercase tracking-widest">Effective Rate used:</span>
                                            <span className="text-xs font-bold text-text-primary">₵{results.tariff_info.effective_rate_ghs_per_kwh.toFixed(3)}/kWh</span>
                                        </div>
                                    )}
                                </div>

                                <div className="mt-6 pt-6 border-t border-brand-gold/10 grid grid-cols-1 md:grid-cols-3 gap-4">
                                    {results.recommendations.map((rec, i) => (
                                        <div key={i} className="p-3 bg-glass-bg rounded-xl card-hover">
                                            <p className="text-[10px] font-bold text-text-dim truncate mb-1">{rec.panel}</p>
                                            <p className="text-sm font-bold text-text-primary">{rec.count} <span className="text-[10px] font-medium text-text-dim">Panels</span></p>
                                        </div>
                                    ))}
                                </div>
                            </motion.div>
                        )}

                        {/* Actions */}
                        <div className="flex gap-4">
                            <button
                                onClick={handleCalculate}
                                disabled={loading}
                                className="flex-1 py-4 bg-gradient-to-r from-brand-gold to-orange-500 text-text-primary font-bold text-sm rounded-2xl hover:shadow-[0_0_30px_rgba(245,158,11,0.2)] transition-all flex items-center justify-center gap-2 disabled:opacity-50"
                            >
                                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
                                {loading ? 'CALCULATING...' : 'GENERATE RECOMMENDATION'}
                            </button>
                        </div>

                        {/* Note */}
                        <div className="flex items-start gap-3 p-4 bg-glass-bg rounded-xl card-hover">
                            <Info className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
                            <p className="text-[10px] text-text-dim leading-relaxed uppercase font-semibold">
                                Sizing assumes PSH of {results?.psh_used || 4.8}h/day and PR of {(results?.pr_used * 100 || 78)}% typical for Ghana. This is a scientific estimate for design guidance.
                            </p>
                        </div>
                    </div>
                </motion.div>
            </div>
        </AnimatePresence>
    );
}
