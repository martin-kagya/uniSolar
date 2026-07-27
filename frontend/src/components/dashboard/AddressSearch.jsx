import React, { useState, useEffect, useRef } from 'react';
import { Search, MapPin, Loader2 } from 'lucide-react';

export default function AddressSearch({ onSelectLocation }) {
    const [query, setQuery] = useState('');
    const [suggestions, setSuggestions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef(null);
    const timeoutRef = useRef(null);
    const abortRef = useRef(null);

    const fetchSuggestions = async (text) => {
        if (text.length < 2) {
            setSuggestions([]);
            setIsOpen(false);
            return;
        }

        if (abortRef.current) abortRef.current.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        setLoading(true);
        try {
            const res = await fetch(
                `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(text)}&addressdetails=1&limit=5&countrycodes=gh`,
                { signal: controller.signal }
            );
            const data = await res.json();
            setSuggestions(data.map(p => ({
                id: p.place_id,
                primary: p.display_name.split(',')[0],
                secondary: p.display_name.split(',').slice(1).join(',').trim(),
                fullText: p.display_name,
                raw: p,
            })));
            setIsOpen(data.length > 0);
        } catch (e) {
            if (e.name !== 'AbortError') console.error('Autocomplete error:', e);
        } finally {
            setLoading(false);
        }
    };

    const handleInputChange = (e) => {
        const value = e.target.value;
        setQuery(value);

        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => fetchSuggestions(value), 180);
    };

    const handleSelect = (suggestion) => {
        setQuery(suggestion.fullText);
        setSuggestions([]);
        setIsOpen(false);
        onSelectLocation({
            lat: parseFloat(suggestion.raw.lat),
            lng: parseFloat(suggestion.raw.lon),
            name: suggestion.fullText,
        });
    };

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    return (
        <div className="relative w-56" ref={dropdownRef}>
            <div className="flex items-center bg-glass-bg rounded-lg px-2.5 py-1.5 w-full border border-border-theme focus-within:border-brand-gold/30 transition-all">
                {loading ? (
                    <Loader2 className="w-3.5 h-3.5 text-brand-gold animate-spin mr-1.5" />
                ) : (
                    <Search className="w-3.5 h-3.5 text-text-dim mr-1.5" />
                )}
                <input
                    type="text"
                    value={query}
                    onChange={handleInputChange}
                    onFocus={() => suggestions.length > 0 && setIsOpen(true)}
                    placeholder="Search location..."
                    className="bg-transparent border-none outline-none text-xs w-full text-text-primary placeholder:text-text-dim font-medium"
                />
            </div>

            {isOpen && suggestions.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-2 bg-surface-dropdown rounded-xl border border-border-theme shadow-2xl overflow-hidden z-[100] backdrop-blur-xl">
                    {suggestions.map((s) => (
                        <div
                            key={s.id}
                            onClick={() => handleSelect(s)}
                            className="px-4 py-3 hover:bg-glass-bg cursor-pointer flex items-start gap-3 transition-colors group"
                        >
                            <MapPin className="w-4 h-4 text-text-dim mt-0.5 group-hover:text-brand-gold transition-colors" />
                            <div className="flex flex-col gap-0.5">
                                <span className="text-xs text-text-primary font-medium line-clamp-1">
                                    {s.primary}
                                </span>
                                <span className="text-[10px] text-text-dim line-clamp-1">
                                    {s.secondary}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
