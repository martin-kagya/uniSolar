import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useMap } from '@vis.gl/react-google-maps';
import { TreePine, Building2, Factory, HelpCircle, Trash2, X } from 'lucide-react';

const TYPE_OPTIONS = [
    { value: 'tree',     label: 'Tree',     Icon: TreePine,    defaultW: 3,   defaultH: 6 },
    { value: 'building', label: 'Building', Icon: Building2,   defaultW: 8,   defaultH: 5 },
    { value: 'chimney',  label: 'Chimney',  Icon: Factory,     defaultW: 1.5, defaultH: 3 },
    { value: 'other',    label: 'Other',    Icon: HelpCircle,  defaultW: 2,   defaultH: 4 },
];

/**
 * React-rendered obstacle editing popover that tracks an obstacle's lat/lng
 * on the map. Uses the Google Maps projection to convert geo → pixel coords
 * and positions itself with CSS transform.
 */
export default function ObstaclePopover({ obstacle, onUpdate, onDelete, onClose }) {
    const map = useMap();
    const [pos, setPos] = useState({ x: 0, y: 0 });
    const [visible, setVisible] = useState(false);

    // Recompute pixel position whenever the map moves or the obstacle moves
    const recompute = useCallback(() => {
        if (!map || !obstacle) return;
        const projection = map.getProjection();
        if (!projection || typeof projection.fromLatLngToDivPixel !== 'function') return;
        const bounds = map.getBounds();
        if (!bounds) return;

        const LatLng = window.google?.maps?.LatLng;
        if (!LatLng) return;

        const point = projection.fromLatLngToDivPixel(new LatLng(obstacle.lat, obstacle.lng));
        if (!point) return;
        setPos({ x: point.x, y: point.y });
        setVisible(true);
    }, [map, obstacle?.lat, obstacle?.lng]);

    useEffect(() => {
        recompute();
        if (!map) return;
        const listeners = [
            map.addListener('idle', recompute),
            map.addListener('zoom_changed', recompute),
            map.addListener('center_changed', recompute),
        ];
        return () => listeners.forEach(l => l.remove?.());
    }, [map, recompute]);

    // Also recompute when the map container resizes
    useEffect(() => {
        recompute();
    }, [obstacle?.heightM, obstacle?.widthM, obstacle?.type, recompute]);

    if (!obstacle || !visible) return null;

    const typeInfo = TYPE_OPTIONS.find(t => t.value === obstacle.type) || TYPE_OPTIONS[3];

    return (
        <div
            style={{
                position: 'absolute',
                left: pos.x,
                top: pos.y,
                transform: 'translate(-50%, calc(-100% - 16px))',
                zIndex: 9999,
                pointerEvents: 'auto',
            }}
            className="bg-surface-raised border border-border-theme rounded-xl shadow-2xl p-3 w-56 backdrop-blur-xl"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => e.stopPropagation()}
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <typeInfo.Icon className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs font-bold text-text-primary">Obstacle</span>
                </div>
                <div className="flex items-center gap-1">
                    <button
                        onClick={(e) => { e.stopPropagation(); onDelete(obstacle.id); }}
                        className="p-1 rounded-md hover:bg-red-500/10 text-text-dim hover:text-red-400 transition-colors"
                        title="Delete obstacle"
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                        onClick={(e) => { e.stopPropagation(); onClose(); }}
                        className="p-1 rounded-md hover:bg-glass-bg text-text-dim hover:text-text-primary transition-colors"
                    >
                        <X className="w-3.5 h-3.5" />
                    </button>
                </div>
            </div>

            {/* Type selector */}
            <div className="flex gap-1 mb-3">
                {TYPE_OPTIONS.map(opt => (
                    <button
                        key={opt.value}
                        onClick={(e) => { e.stopPropagation(); onUpdate(obstacle.id, { type: opt.value }); }}
                        className={`flex-1 flex flex-col items-center gap-0.5 py-1.5 rounded-lg text-[9px] font-bold transition-all ${
                            obstacle.type === opt.value
                                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                                : 'bg-glass-bg text-text-dim hover:text-text-secondary border border-transparent'
                        }`}
                    >
                        <opt.Icon className="w-3.5 h-3.5" />
                        {opt.label}
                    </button>
                ))}
            </div>

            {/* Height slider — controlled React input, no DOM manipulation */}
            <div className="mb-2">
                <div className="flex justify-between items-center mb-1">
                    <span className="text-[9px] font-bold text-text-dim uppercase">Height</span>
                    <span className="text-[10px] font-bold text-text-primary font-mono">{obstacle.heightM.toFixed(1)}m</span>
                </div>
                <input
                    type="range"
                    min="0.5"
                    max="25"
                    step="0.5"
                    value={obstacle.heightM}
                    onMouseDown={(e) => e.stopPropagation()}
                    onChange={(e) => { e.stopPropagation(); onUpdate(obstacle.id, { heightM: parseFloat(e.target.value) }); }}
                    className="w-full h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer accent-emerald-400"
                />
            </div>

            {/* Width slider */}
            <div>
                <div className="flex justify-between items-center mb-1">
                    <span className="text-[9px] font-bold text-text-dim uppercase">Width</span>
                    <span className="text-[10px] font-bold text-text-primary font-mono">{obstacle.widthM.toFixed(1)}m</span>
                </div>
                <input
                    type="range"
                    min="0.5"
                    max="20"
                    step="0.5"
                    value={obstacle.widthM}
                    onMouseDown={(e) => e.stopPropagation()}
                    onChange={(e) => { e.stopPropagation(); onUpdate(obstacle.id, { widthM: parseFloat(e.target.value) }); }}
                    className="w-full h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer accent-emerald-400"
                />
            </div>

            {/* Shadow info */}
            <div className="mt-2 pt-2 border-t border-border-subtle">
                <p className="text-[8px] text-text-dim leading-relaxed">
                    Shadow moves with sun position. Shading is computed per-timestep during simulation.
                </p>
            </div>
        </div>
    );
}
