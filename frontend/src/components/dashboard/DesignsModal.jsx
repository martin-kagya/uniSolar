import React, { useState, useEffect, useCallback } from 'react';
import { X, Save, FolderOpen, Trash2, MapPin, Calendar, Layers, Loader2, AlertTriangle } from 'lucide-react';

/**
 * Modal for saving, loading, and managing saved designs.
 *
 * Props:
 *  - isOpen: boolean
 *  - onClose: () => void
 *  - onSave: (name: string) => Promise<void>  — called with the user-entered name
 *  - onLoad: (designId: number) => Promise<void>
 *  - currentDesignId: number | null — the currently loaded design (for highlight)
 *  - currentDesignName: string | null
 */
export default function DesignsModal({ isOpen, onClose, onSave, onLoad, onDelete, currentDesignId, currentDesignName }) {
    const [designs, setDesigns] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saveName, setSaveName] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [confirmDelete, setConfirmDelete] = useState(null);

    const fetchDesigns = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch('/designs');
            if (!res.ok) throw new Error('Failed to load designs');
            setDesigns(await res.json());
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (isOpen) {
            fetchDesigns();
            setSaveName(currentDesignName || '');
        }
    }, [isOpen, fetchDesigns, currentDesignName]);

    const handleSave = async () => {
        if (!saveName.trim()) return;
        setSaving(true);
        setError(null);
        try {
            await onSave(saveName.trim());
            await fetchDesigns();
        } catch (e) {
            setError(e.message);
        } finally {
            setSaving(false);
        }
    };

    const handleLoad = async (id) => {
        setLoading(true);
        setError(null);
        try {
            await onLoad(id);
            onClose();
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id) => {
        try {
            await onDelete(id);
            setConfirmDelete(null);
            await fetchDesigns();
        } catch (e) {
            setError(e.message);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center">
            {/* Backdrop */}
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

            {/* Modal */}
            <div className="relative bg-surface-raised border border-border-theme rounded-2xl shadow-2xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col overflow-hidden">

                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle">
                    <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-brand-gold/10 flex items-center justify-center">
                            <FolderOpen className="w-5 h-5 text-brand-gold" />
                        </div>
                        <div>
                            <h2 className="text-base font-bold text-text-primary">My Designs</h2>
                            <p className="text-[10px] text-text-dim font-bold uppercase tracking-widest">{designs.length} saved</p>
                        </div>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-glass-bg rounded-xl text-text-dim hover:text-text-primary transition-all">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Save current */}
                <div className="px-6 py-3 border-b border-border-subtle bg-glass-bg">
                    <div className="flex items-center gap-2">
                        <input
                            type="text"
                            value={saveName}
                            onChange={(e) => setSaveName(e.target.value)}
                            placeholder="Design name..."
                            className="flex-1 px-3 py-2 bg-surface border border-border-subtle rounded-lg text-xs font-semibold text-text-primary placeholder:text-text-dim/50 focus:outline-none focus:border-brand-gold/50 transition-colors"
                            onKeyDown={(e) => e.key === 'Enter' && handleSave()}
                        />
                        <button
                            onClick={handleSave}
                            disabled={!saveName.trim() || saving}
                            className="flex items-center gap-1.5 px-4 py-2 bg-brand-gold/10 hover:bg-brand-gold/20 text-brand-gold rounded-lg text-xs font-bold transition-all disabled:opacity-40 border border-brand-gold/20"
                        >
                            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                            SAVE
                        </button>
                    </div>
                </div>

                {/* Error */}
                {error && (
                    <div className="mx-6 mt-3 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0" />
                        <p className="text-[11px] text-red-400 font-semibold">{error}</p>
                    </div>
                )}

                {/* Design list */}
                <div className="flex-1 overflow-y-auto p-2">
                    {loading && designs.length === 0 ? (
                        <div className="flex items-center justify-center py-12">
                            <Loader2 className="w-6 h-6 text-text-dim animate-spin" />
                        </div>
                    ) : designs.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 text-text-dim">
                            <FolderOpen className="w-10 h-10 mb-3 opacity-30" />
                            <p className="text-xs font-semibold">No saved designs yet</p>
                            <p className="text-[10px] mt-1 opacity-60">Save your current design above</p>
                        </div>
                    ) : (
                        <div className="space-y-1">
                            {designs.map((d) => (
                                <div
                                    key={d.id}
                                    className={`group flex items-center gap-3 px-4 py-3 rounded-xl transition-all cursor-pointer ${
                                        d.id === currentDesignId
                                            ? 'bg-brand-gold/10 border border-brand-gold/20'
                                            : 'hover:bg-glass-bg border border-transparent'
                                    }`}
                                    onClick={() => handleLoad(d.id)}
                                >
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <span className={`text-xs font-bold truncate ${d.id === currentDesignId ? 'text-brand-gold' : 'text-text-primary'}`}>
                                                {d.name}
                                            </span>
                                            {d.id === currentDesignId && (
                                                <span className="px-1.5 py-0.5 rounded text-[8px] font-bold bg-brand-gold/15 text-brand-gold uppercase">Current</span>
                                            )}
                                        </div>
                                        <div className="flex items-center gap-3 mt-1 text-[10px] text-text-dim">
                                            <span className="flex items-center gap-1">
                                                <MapPin className="w-3 h-3" />
                                                {(d.latitude ?? 0).toFixed(3)}, {(d.longitude ?? 0).toFixed(3)}
                                            </span>
                                            <span className="flex items-center gap-1">
                                                <Layers className="w-3 h-3" />
                                                {d.panel_count} panels
                                            </span>
                                            {d.updated_at ? (
                                                <span className="flex items-center gap-1">
                                                    <Calendar className="w-3 h-3" />
                                                    {new Date(d.updated_at).toLocaleDateString()}
                                                </span>
                                            ) : d.created_at ? (
                                                <span className="flex items-center gap-1">
                                                    <Calendar className="w-3 h-3" />
                                                    {new Date(d.created_at).toLocaleDateString()}
                                                </span>
                                            ) : null}
                                        </div>
                                    </div>

                                    {/* Delete button */}
                                    <div className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                                        {confirmDelete === d.id ? (
                                            <div className="flex items-center gap-1">
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); handleDelete(d.id); }}
                                                    className="px-2 py-1 bg-red-500/15 text-red-400 rounded text-[10px] font-bold hover:bg-red-500/25 transition-colors"
                                                >
                                                    Confirm
                                                </button>
                                                <button
                                                    onClick={(e) => { e.stopPropagation(); setConfirmDelete(null); }}
                                                    className="px-2 py-1 bg-glass-bg text-text-dim rounded text-[10px] font-bold hover:text-text-secondary transition-colors"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        ) : (
                                            <button
                                                onClick={(e) => { e.stopPropagation(); setConfirmDelete(d.id); }}
                                                className="p-1.5 rounded-lg hover:bg-red-500/10 text-text-dim hover:text-red-400 transition-colors"
                                                title="Delete design"
                                            >
                                                <Trash2 className="w-3.5 h-3.5" />
                                            </button>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
