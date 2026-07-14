import React, { useState } from 'react';
import { X, Sun, Plus, ChevronRight, Battery, Cpu, Zap, Check, Star } from 'lucide-react';

const CELL_TECHNOLOGIES = ['Mono-PERC', 'Bifacial PERC', 'HJT', 'TOPCon', 'Poly', 'CdTe', 'CIGS', 'Other'];
const BATTERY_CHEMISTRIES = ['LiFePO4', 'NMC', 'Lead-Acid (AGM)', 'Lead-Acid (GEL)', 'NaS', 'Other'];

const FORM_TABS = [
    { label: 'Panel Specs', icon: Sun },
    { label: 'Electrical', icon: Zap },
    { label: 'Battery & Inv.', icon: Battery },
];

function FieldGroup({ label, children }) {
    return (
        <div>
            <p className="text-[9px] font-bold text-text-dim uppercase tracking-widest mb-3">{label}</p>
            {children}
        </div>
    );
}

function Field({ label, required, children }) {
    return (
        <div>
            <label className="block text-[10px] font-semibold text-text-muted uppercase tracking-widest mb-1.5">
                {label}{required && <span className="text-amber-400 ml-0.5">*</span>}
            </label>
            {children}
        </div>
    );
}

const inputCls = "w-full bg-glass-bg border border-border-theme rounded-xl px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:border-amber-500/50 focus:bg-white/[0.06] transition-all";
const selectCls = "w-full bg-surface-dropdown border border-border-theme rounded-xl px-3.5 py-2.5 text-sm text-text-primary focus:outline-none focus:border-amber-500/50 transition-all appearance-none cursor-pointer";

export default function AddPanelModal({ isOpen, onClose, existingModules = [], onModuleSelected, onModuleAdded }) {
    const [mode, setMode] = useState('select');
    const [activeTab, setActiveTab] = useState(0);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);

    const [form, setForm] = useState({
        // Tab 0 – Panel Specs
        name: '', power_wp: '', width_m: '', length_m: '',
        efficiency_pct: '', performance_ratio: '',
        cell_technology: '', warranty_years: '',
        // Tab 1 – Electrical (STC)
        voc: '', isc: '', vmp: '', imp: '',
        temp_coeff_pmax: '', temp_coeff_voc: '', noct: '', num_cells: '',
        // Tab 2 – Battery & Inverter
        battery_brand: '', battery_capacity_kwh: '', battery_voltage: '', battery_chemistry: '',
        inverter_brand: '', inverter_kw: '', inverter_efficiency_pct: '',
    });

    if (!isOpen) return null;

    const set = (key, val) => setForm(prev => ({ ...prev, [key]: val }));
    const num = v => v !== '' ? parseFloat(v) : null;
    const int = v => v !== '' ? parseInt(v) : null;

    const handleSelectExisting = (m) => { onModuleSelected(m); onClose(); };

    const handleCustomize = (m) => {
        setMode('custom');
        setActiveTab(0);
        setForm({
            name: `${m.name} (Modified)`,
            power_wp: m.power_wp || '',
            width_m: m.width_m || '',
            length_m: m.length_m || '',
            efficiency_pct: m.efficiency_pct || '',
            performance_ratio: m.performance_ratio || '',
            cell_technology: m.cell_technology || '',
            warranty_years: m.warranty_years || '',
            voc: m.voc || '',
            isc: m.isc || '',
            vmp: m.vmp || '',
            imp: m.imp || '',
            temp_coeff_pmax: m.temp_coeff_pmax || '',
            temp_coeff_voc: m.temp_coeff_voc || '',
            noct: m.noct || '',
            num_cells: m.num_cells || '',
            battery_brand: m.battery_brand || '',
            battery_capacity_kwh: m.battery_capacity_kwh || '',
            battery_voltage: m.battery_voltage || '',
            battery_chemistry: m.battery_chemistry || '',
            inverter_brand: m.inverter_brand || '',
            inverter_kw: m.inverter_kw || '',
            inverter_efficiency_pct: m.inverter_efficiency_pct || '',
        });
    };

    const handleSubmit = async () => {
        setError(null);
        if (!form.name.trim() || !form.power_wp || !form.width_m || !form.length_m) {
            setError('Panel name, power, width and length are required.');
            setActiveTab(0);
            return;
        }
        setSubmitting(true);
        try {
            const payload = {
                name: form.name.trim(),
                power_wp: parseFloat(form.power_wp),
                width_m: parseFloat(form.width_m),
                length_m: parseFloat(form.length_m),
                efficiency_pct: num(form.efficiency_pct),
                performance_ratio: num(form.performance_ratio),
                cell_technology: form.cell_technology || null,
                warranty_years: int(form.warranty_years),
                voc: num(form.voc), isc: num(form.isc),
                vmp: num(form.vmp), imp: num(form.imp),
                temp_coeff_pmax: num(form.temp_coeff_pmax),
                temp_coeff_voc: num(form.temp_coeff_voc),
                noct: num(form.noct),
                num_cells: int(form.num_cells),
                battery_brand: form.battery_brand || null,
                battery_capacity_kwh: num(form.battery_capacity_kwh),
                battery_voltage: num(form.battery_voltage),
                battery_chemistry: form.battery_chemistry || null,
                inverter_brand: form.inverter_brand || null,
                inverter_kw: num(form.inverter_kw),
                inverter_efficiency_pct: num(form.inverter_efficiency_pct),
            };
            const res = await fetch('/modules', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error('Failed to save panel.');
            const newModule = await res.json();
            onModuleAdded(newModule);
            onClose();
        } catch (err) { setError(err.message); }
        finally { setSubmitting(false); }
    };

    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center" style={{ backdropFilter: 'blur(14px)', background: 'rgba(0,0,0,0.78)' }}>
            <div className="relative w-full max-w-2xl mx-4 rounded-2xl border border-border-theme overflow-hidden shadow-2xl flex flex-col"
                style={{ background: 'linear-gradient(135deg, var(--surface-raised) 0%, var(--surface-overlay) 100%)', maxHeight: '90vh' }}>

                {/* top glow */}
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-3/4 h-px bg-gradient-to-r from-transparent via-amber-500/50 to-transparent" />

                {/* ── Header ── */}
                <div className="px-7 pt-7 pb-5 border-b border-border-subtle flex-none">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-[0_0_20px_rgba(245,158,11,0.35)]">
                                <Sun className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <h2 className="text-base font-bold text-text-primary tracking-tight">
                                    {mode === 'custom' && form.name.includes('(Modified)') ? 'Customize Solar Panel' : 'Configure Solar Panel'}
                                </h2>
                                <p className="text-[10px] text-text-dim mt-0.5">
                                    {mode === 'custom' && form.name.includes('(Modified)') 
                                        ? `Modifying ${form.name.replace(' (Modified)', '')}` 
                                        : 'Select an existing module or define your own'}
                                </p>
                            </div>
                        </div>
                        <button onClick={onClose} className="w-8 h-8 flex items-center justify-center rounded-lg text-text-dim hover:text-text-primary hover:bg-glass-bg-strong transition-all">
                            <X className="w-4 h-4" />
                        </button>
                    </div>

                    {/* Mode toggle */}
                    <div className="flex gap-2 mt-5">
                        {[['select', 'Use Existing Panel'], ['custom', '+ Add Custom Panel']].map(([key, label]) => (
                            <button key={key} onClick={() => setMode(key)}
                                className={`flex-1 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all border ${mode === key
                                    ? 'bg-amber-500/15 border-amber-500/40 text-amber-400'
                                    : 'bg-glass-bg border-border-subtle text-text-dim hover:text-text-secondary hover:bg-glass-bg'}`}>
                                {label}
                            </button>
                        ))}
                    </div>
                </div>

                {/* ── Body (scrollable) ── */}
                <div className="overflow-y-auto flex-1 px-7 py-6">

                    {/* ─── SELECT EXISTING ─── */}
                    {mode === 'select' && (
                        <div className="space-y-2.5">
                            <p className="text-[9px] font-bold text-text-dim uppercase tracking-widest mb-4">Available Modules</p>
                            {existingModules.map(m => (
                                <button key={m.id} onClick={() => handleSelectExisting(m)}
                                    className="w-full flex items-center justify-between p-4 rounded-xl bg-glass-bg hover:bg-amber-500/10 transition-all group text-left card-hover">
                                    <div className="flex items-center gap-3.5 flex-1 min-w-0">
                                        <div className="w-9 h-9 rounded-lg bg-glass-bg border border-border-theme flex items-center justify-center shrink-0 group-hover:bg-amber-500/15 group-hover:border-amber-500/20 transition-all">
                                            <Sun className="w-4 h-4 text-text-dim group-hover:text-amber-400 transition-colors" />
                                        </div>
                                        <div className="truncate">
                                            <p className="text-sm font-semibold text-text-primary flex items-center gap-2 truncate">
                                                <span className="truncate">{m.name}</span>
                                                {m.custom && <span className="shrink-0 px-1.5 py-0.5 rounded text-[8px] font-bold bg-amber-500/15 text-amber-400 uppercase">Custom</span>}
                                            </p>
                                            <div className="text-[10px] text-text-dim mt-0.5 flex items-center gap-2 truncate">
                                                <span className="font-mono">{m.width_m}×{m.length_m}m</span>
                                                {m.cell_technology && <span>• {m.cell_technology}</span>}
                                                {m.battery_brand && (
                                                    <span className="flex items-center gap-1 text-text-muted">
                                                        • <Battery className="w-3 h-3 text-amber-500/70" /> {m.battery_capacity_kwh}kWh
                                                    </span>
                                                )}
                                                {m.inverter_brand && (
                                                    <span className="flex items-center gap-1 text-text-muted">
                                                        • <Cpu className="w-3 h-3 text-amber-500/70" /> {m.inverter_kw}kW
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-4 shrink-0 pl-4 border-l border-border-subtle ml-4">
                                        <div className="text-right">
                                            <p className="text-sm font-bold text-amber-400">{m.power_wp} W</p>
                                            {m.efficiency_pct && <p className="text-[10px] text-text-dim">{m.efficiency_pct}% eff.</p>}
                                        </div>
                                        <div className="flex flex-col gap-1.5">
                                            <button 
                                                onClick={(e) => { e.stopPropagation(); handleCustomize(m); }}
                                                className="p-1.5 rounded-lg bg-glass-bg text-text-muted hover:text-amber-400 hover:bg-amber-500/10 transition-all group/btn flex items-center gap-1.5 px-2"
                                                title="Customize this panel"
                                            >
                                                <Cpu className="w-3.5 h-3.5" />
                                                <span className="text-[9px] font-bold uppercase tracking-wider">Customize</span>
                                            </button>
                                            <button 
                                                onClick={() => handleSelectExisting(m)}
                                                className="p-1.5 rounded-lg bg-amber-500/10 text-amber-500 hover:bg-amber-500/20 transition-all flex items-center gap-1.5 px-2"
                                            >
                                                <Check className="w-3.5 h-3.5" />
                                                <span className="text-[9px] font-bold uppercase tracking-wider">Select</span>
                                            </button>
                                        </div>
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}

                    {/* ─── CUSTOM PANEL ─── */}
                    {mode === 'custom' && (
                        <div>
                            {/* Tab bar */}
                            <div className="flex gap-1 mb-6 bg-glass-bg rounded-xl p-1 border border-border-subtle">
                                {FORM_TABS.map(({ label, icon: Icon }, i) => (
                                    <button key={label} onClick={() => setActiveTab(i)}
                                        className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-bold transition-all ${activeTab === i ? 'bg-amber-500/15 text-amber-400' : 'text-text-dim hover:text-text-secondary'}`}>
                                        <Icon className="w-3.5 h-3.5" />{label}
                                    </button>
                                ))}
                            </div>

                            {/* ── Tab 0: Panel Specs ── */}
                            {activeTab === 0 && (
                                <div className="space-y-5">
                                    <Field label="Panel Name" required>
                                        <input type="text" className={inputCls} placeholder="e.g. Longi Hi-MO6 550W"
                                            value={form.name} onChange={e => set('name', e.target.value)} />
                                    </Field>

                                    <FieldGroup label="Power & Dimensions">
                                        <div className="grid grid-cols-3 gap-3">
                                            <Field label="Power (Wp)" required>
                                                <input type="number" className={inputCls} placeholder="550"
                                                    value={form.power_wp} onChange={e => set('power_wp', e.target.value)} />
                                            </Field>
                                            <Field label="Width (m)" required>
                                                <input type="number" step="0.001" className={inputCls} placeholder="1.134"
                                                    value={form.width_m} onChange={e => set('width_m', e.target.value)} />
                                            </Field>
                                            <Field label="Length (m)" required>
                                                <input type="number" step="0.001" className={inputCls} placeholder="2.278"
                                                    value={form.length_m} onChange={e => set('length_m', e.target.value)} />
                                            </Field>
                                        </div>
                                    </FieldGroup>

                                    <FieldGroup label="Performance">
                                        <div className="grid grid-cols-2 gap-3">
                                            <Field label="Module Efficiency (%)">
                                                <input type="number" step="0.1" className={inputCls} placeholder="e.g. 21.3"
                                                    value={form.efficiency_pct} onChange={e => set('efficiency_pct', e.target.value)} />
                                            </Field>
                                            <Field label="Performance Ratio (%)">
                                                <input type="number" step="0.1" min="0" max="100" className={inputCls} placeholder="e.g. 80"
                                                    value={form.performance_ratio} onChange={e => set('performance_ratio', e.target.value)} />
                                            </Field>
                                        </div>
                                    </FieldGroup>

                                    <FieldGroup label="Build">
                                        <div className="grid grid-cols-2 gap-3">
                                            <Field label="Cell Technology">
                                                <select className={selectCls} value={form.cell_technology} onChange={e => set('cell_technology', e.target.value)}>
                                                    <option value="">Select...</option>
                                                    {CELL_TECHNOLOGIES.map(t => <option key={t} value={t}>{t}</option>)}
                                                </select>
                                            </Field>
                                            <Field label="Warranty (years)">
                                                <input type="number" className={inputCls} placeholder="e.g. 25"
                                                    value={form.warranty_years} onChange={e => set('warranty_years', e.target.value)} />
                                            </Field>
                                        </div>
                                    </FieldGroup>

                                    <button onClick={() => setActiveTab(1)}
                                        className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-dashed border-border-theme text-text-dim hover:text-text-secondary hover:border-white/20 transition-all text-xs font-semibold">
                                        <span>Next: Electrical Parameters →</span>
                                        <ChevronRight className="w-4 h-4" />
                                    </button>
                                </div>
                            )}

                            {/* ── Tab 1: Electrical (STC) ── */}
                            {activeTab === 1 && (
                                <div className="space-y-5">
                                    <FieldGroup label="STC Ratings (Standard Test Conditions)">
                                        <div className="grid grid-cols-2 gap-3">
                                            <Field label="Voc — Open Circuit (V)">
                                                <input type="number" step="0.1" className={inputCls} placeholder="e.g. 49.5"
                                                    value={form.voc} onChange={e => set('voc', e.target.value)} />
                                            </Field>
                                            <Field label="Isc — Short Circuit (A)">
                                                <input type="number" step="0.01" className={inputCls} placeholder="e.g. 14.0"
                                                    value={form.isc} onChange={e => set('isc', e.target.value)} />
                                            </Field>
                                            <Field label="Vmp — Max Power (V)">
                                                <input type="number" step="0.1" className={inputCls} placeholder="e.g. 41.8"
                                                    value={form.vmp} onChange={e => set('vmp', e.target.value)} />
                                            </Field>
                                            <Field label="Imp — Max Power (A)">
                                                <input type="number" step="0.01" className={inputCls} placeholder="e.g. 13.16"
                                                    value={form.imp} onChange={e => set('imp', e.target.value)} />
                                            </Field>
                                        </div>
                                    </FieldGroup>

                                    <FieldGroup label="Thermal & Operating">
                                        <div className="grid grid-cols-3 gap-3">
                                            <Field label="Temp. Coeff. Pmax (%/°C)">
                                                <input type="number" step="0.001" className={inputCls} placeholder="e.g. -0.35"
                                                    value={form.temp_coeff_pmax} onChange={e => set('temp_coeff_pmax', e.target.value)} />
                                            </Field>
                                            <Field label="Temp. Coeff. Voc (%/°C)">
                                                <input type="number" step="0.001" className={inputCls} placeholder="e.g. -0.28"
                                                    value={form.temp_coeff_voc} onChange={e => set('temp_coeff_voc', e.target.value)} />
                                            </Field>
                                            <Field label="NOCT (°C)">
                                                <input type="number" step="0.5" className={inputCls} placeholder="e.g. 43"
                                                    value={form.noct} onChange={e => set('noct', e.target.value)} />
                                            </Field>
                                        </div>
                                    </FieldGroup>

                                    <FieldGroup label="Configuration">
                                        <div className="grid grid-cols-2 gap-3">
                                            <Field label="Number of Cells">
                                                <input type="number" className={inputCls} placeholder="e.g. 144"
                                                    value={form.num_cells} onChange={e => set('num_cells', e.target.value)} />
                                            </Field>
                                        </div>
                                    </FieldGroup>

                                    <button onClick={() => setActiveTab(2)}
                                        className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-dashed border-border-theme text-text-dim hover:text-text-secondary hover:border-white/20 transition-all text-xs font-semibold">
                                        <span>Next: Battery & Inverter →</span>
                                        <ChevronRight className="w-4 h-4" />
                                    </button>
                                </div>
                            )}

                            {/* ── Tab 2: Battery & Inverter ── */}
                            {activeTab === 2 && (
                                <div className="space-y-5">
                                    <FieldGroup label="Battery Storage (optional)">
                                        <div className="grid grid-cols-2 gap-3">
                                            <Field label="Brand">
                                                <input type="text" className={inputCls} placeholder="e.g. Pylontech"
                                                    value={form.battery_brand} onChange={e => set('battery_brand', e.target.value)} />
                                            </Field>
                                            <Field label="Capacity (kWh)">
                                                <input type="number" step="0.1" className={inputCls} placeholder="e.g. 10"
                                                    value={form.battery_capacity_kwh} onChange={e => set('battery_capacity_kwh', e.target.value)} />
                                            </Field>
                                            <Field label="Nominal Voltage (V)">
                                                <input type="number" step="1" className={inputCls} placeholder="e.g. 48"
                                                    value={form.battery_voltage} onChange={e => set('battery_voltage', e.target.value)} />
                                            </Field>
                                            <Field label="Chemistry">
                                                <select className={selectCls} value={form.battery_chemistry} onChange={e => set('battery_chemistry', e.target.value)}>
                                                    <option value="">Select...</option>
                                                    {BATTERY_CHEMISTRIES.map(c => <option key={c} value={c}>{c}</option>)}
                                                </select>
                                            </Field>
                                        </div>
                                    </FieldGroup>

                                    <div className="border-t border-border-subtle" />

                                    <FieldGroup label="Inverter (optional)">
                                        <div className="grid grid-cols-3 gap-3">
                                            <Field label="Brand">
                                                <input type="text" className={inputCls} placeholder="e.g. Fronius"
                                                    value={form.inverter_brand} onChange={e => set('inverter_brand', e.target.value)} />
                                            </Field>
                                            <Field label="Rated Power (kW)">
                                                <input type="number" step="0.1" className={inputCls} placeholder="e.g. 5"
                                                    value={form.inverter_kw} onChange={e => set('inverter_kw', e.target.value)} />
                                            </Field>
                                            <Field label="Peak Efficiency (%)">
                                                <input type="number" step="0.1" max="100" className={inputCls} placeholder="e.g. 98.1"
                                                    value={form.inverter_efficiency_pct} onChange={e => set('inverter_efficiency_pct', e.target.value)} />
                                            </Field>
                                        </div>
                                    </FieldGroup>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Error */}
                    {error && (
                        <div className="mt-4 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-semibold">
                            {error}
                        </div>
                    )}
                </div>

                {/* ── Footer ── */}
                <div className="px-7 pb-7 pt-4 border-t border-border-subtle flex items-center justify-between gap-3 flex-none">
                    <button onClick={onClose}
                        className="px-5 py-2.5 rounded-xl text-xs font-bold text-text-dim hover:text-text-secondary hover:bg-glass-bg transition-all border border-transparent hover:border-white/8">
                        Skip for now
                    </button>

                    {mode === 'custom' && (
                        <div className="flex items-center gap-2">
                            {activeTab > 0 && (
                                <button onClick={() => setActiveTab(t => t - 1)}
                                    className="px-4 py-2.5 rounded-xl text-xs font-bold text-text-muted hover:text-text-primary hover:bg-glass-bg transition-all border border-border-theme">
                                    ← Back
                                </button>
                            )}
                            {activeTab < FORM_TABS.length - 1 ? (
                                <button onClick={() => setActiveTab(t => t + 1)}
                                    className="px-5 py-2.5 bg-white/8 hover:bg-glass-bg-strong text-text-primary rounded-xl text-xs font-bold transition-all border border-border-theme">
                                    Next →
                                </button>
                            ) : (
                                <button onClick={handleSubmit} disabled={submitting}
                                    className="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-amber-500 to-orange-500 hover:shadow-[0_0_20px_rgba(245,158,11,0.35)] disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all active:scale-95">
                                    {submitting
                                        ? <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                                        : <Check className="w-3.5 h-3.5" />}
                                    {submitting ? 'Saving...' : 'Add Panel'}
                                </button>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
