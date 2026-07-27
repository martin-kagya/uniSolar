import React, { useMemo, useState, useEffect, useRef } from 'react';
import { Sun, Play, Pause } from 'lucide-react';

/**
 * Floating "sun timeline" scrubber. Drives the date + time-of-day that determine
 * the sun position (and therefore the cast shadows) rendered on the map.
 *
 * Props:
 *  - year, month, day, hour : current date/time (hour is fractional local time)
 *  - sun   : { azimuthDeg, zenithDeg, elevationDeg } computed upstream
 *  - onChange(key, value)   : update a single config field
 */
export default function SunTimeline({ year, month, day, hour, sun, onChange }) {
    const HOUR_MIN = 5;
    const HOUR_MAX = 19;
    const ANIMATION_SPEED = 0.1; // hours per frame (6 minutes per frame at 60fps)

    const [isPlaying, setIsPlaying] = useState(false);
    const animationRef = useRef(null);
    const lastTimeRef = useRef(null);

    // Animation loop
    useEffect(() => {
        if (!isPlaying) {
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
                animationRef.current = null;
            }
            lastTimeRef.current = null;
            return;
        }

        const animate = (timestamp) => {
            if (lastTimeRef.current === null) {
                lastTimeRef.current = timestamp;
            }

            const delta = timestamp - lastTimeRef.current;
            const hoursElapsed = (delta / 1000) * ANIMATION_SPEED;

            if (hoursElapsed >= 0.25) { // Update at 15-minute intervals
                const nextHour = hour + 0.25;
                if (nextHour > HOUR_MAX) {
                    setIsPlaying(false);
                    onChange('hour', HOUR_MIN);
                } else {
                    onChange('hour', nextHour);
                }
                lastTimeRef.current = timestamp;
            }

            animationRef.current = requestAnimationFrame(animate);
        };

        animationRef.current = requestAnimationFrame(animate);

        return () => {
            if (animationRef.current) {
                cancelAnimationFrame(animationRef.current);
            }
        };
    }, [isPlaying, hour, onChange]);

    const togglePlayPause = () => {
        if (isPlaying) {
            setIsPlaying(false);
        } else {
            // Reset to start if at end
            if (hour >= HOUR_MAX) {
                onChange('hour', HOUR_MIN);
            }
            setIsPlaying(true);
        }
    };

    const timeLabel = useMemo(() => {
        const h = Math.floor(hour);
        const m = Math.round((hour - h) * 60);
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    }, [hour]);

    const dateValue = useMemo(() => {
        const mm = String(month).padStart(2, '0');
        const dd = String(day).padStart(2, '0');
        return `${year}-${mm}-${dd}`;
    }, [year, month, day]);

    const handleDate = (e) => {
        const [y, m, d] = e.target.value.split('-').map(Number);
        if (!y || !m || !d) return;
        onChange('year', y);
        onChange('month', m);
        onChange('day', d);
    };

    // Sun-arc mini indicator geometry
    const W = 132;
    const H = 44;
    const t = Math.max(0, Math.min(1, (hour - HOUR_MIN) / (HOUR_MAX - HOUR_MIN)));
    const sunX = t * W;
    const elev = Math.max(0, sun?.elevationDeg ?? 0);
    const sunY = H - 6 - (elev / 90) * (H - 12);
    const belowHorizon = (sun?.elevationDeg ?? 0) <= 0;

    return (
        <div className="absolute bottom-6 left-1/2 -translate-x-[calc(50%+192px)] z-50 flex items-center gap-4 bg-surface-overlay/90 backdrop-blur-md border border-border-theme rounded-2xl px-4 py-3 shadow-2xl">
            {/* Date picker */}
            <div className="flex flex-col gap-1">
                <label className="text-[9px] font-bold text-text-dim uppercase tracking-widest">Date</label>
                <input
                    type="date"
                    value={dateValue}
                    onChange={handleDate}
                    className="bg-glass-bg border border-border-subtle rounded-lg px-2 py-1 text-[11px] font-semibold text-text-secondary outline-none focus:border-brand-gold/50 [color-scheme:dark]"
                />
            </div>

            <div className="w-px h-10 bg-border-theme" />

            {/* Play/Pause button + Sun arc + time slider */}
            <div className="flex items-center gap-2">
                <button
                    onClick={togglePlayPause}
                    className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                        isPlaying
                            ? 'bg-brand-gold text-white'
                            : 'bg-glass-bg text-text-dim hover:text-brand-gold hover:bg-brand-gold/10'
                    }`}
                    title={isPlaying ? 'Pause animation' : 'Play animation'}
                >
                    {isPlaying ? (
                        <Pause className="w-4 h-4" />
                    ) : (
                        <Play className="w-4 h-4 fill-current" />
                    )}
                </button>

                <div className="flex flex-col gap-1 w-[260px]">
                    <div className="flex items-center justify-between">
                        <label className="text-[9px] font-bold text-text-dim uppercase tracking-widest">Time of day</label>
                        <span className="text-[11px] font-bold text-brand-gold tabular-nums flex items-center gap-1">
                            <Sun className="w-3 h-3" />
                            {timeLabel}
                        </span>
                    </div>

                    <svg width={W} height={H} className="w-full" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
                        {/* horizon */}
                        <line x1="0" y1={H - 6} x2={W} y2={H - 6} stroke="currentColor" className="text-border-theme" strokeWidth="1" />
                        {/* day arc */}
                        <path
                            d={`M 0 ${H - 6} Q ${W / 2} ${-2} ${W} ${H - 6}`}
                            fill="none"
                            stroke="currentColor"
                            className="text-brand-gold/25"
                            strokeWidth="1.5"
                        />
                        {/* sun */}
                        <circle
                            cx={sunX}
                            cy={belowHorizon ? H - 6 : sunY}
                            r={belowHorizon ? 3 : 5}
                            className={belowHorizon ? 'fill-text-dim' : 'fill-brand-gold'}
                        />
                    </svg>

                    <input
                        type="range"
                        min={HOUR_MIN}
                        max={HOUR_MAX}
                        step={0.25}
                        value={hour}
                        onChange={(e) => onChange('hour', parseFloat(e.target.value))}
                        className="w-full h-1 bg-border-theme rounded-lg appearance-none cursor-pointer accent-amber-500"
                    />
                </div>
            </div>

            <div className="w-px h-10 bg-border-theme" />

            {/* Sun readout */}
            <div className="flex flex-col gap-0.5 min-w-[76px]">
                <span className="text-[9px] font-bold text-text-dim uppercase tracking-widest">Sun</span>
                <span className="text-[11px] font-semibold text-text-secondary tabular-nums">
                    {belowHorizon ? 'below horizon' : `${elev.toFixed(0)}° elev`}
                </span>
                <span className="text-[10px] text-text-dim tabular-nums">
                    az {(sun?.azimuthDeg ?? 0).toFixed(0)}°
                </span>
            </div>
        </div>
    );
}
