import React, { useState, useEffect, useRef } from 'react';
import { Search, MapPin, Loader2 } from 'lucide-react';

export default function AddressSearch({ onSelectLocation }) {
    const [query, setQuery] = useState('');
    const [suggestions, setSuggestions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef(null);
    const timeoutRef = useRef(null);

    // Fetch suggestions from Nominatim (OpenStreetMap)
    const fetchSuggestions = async (searchText) => {
        if (searchText.length < 3) {
            setSuggestions([]);
            return;
        }

        setLoading(true);
        try {
            const response = await fetch(
                `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchText)}&addressdetails=1&limit=5`
            );
            const data = await response.json();
            setSuggestions(data);
            setIsOpen(data.length > 0);
        } catch (error) {
            console.error('Autocomplete error:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleInputChange = (e) => {
        const value = e.target.value;
        setQuery(value);

        if (timeoutRef.current) clearTimeout(timeoutRef.current);

        timeoutRef.current = setTimeout(() => {
            fetchSuggestions(value);
        }, 300);
    };

    const handleSelect = (place) => {
        setQuery(place.display_name);
        setSuggestions([]);
        setIsOpen(false);
        onSelectLocation({
            lat: parseFloat(place.lat),
            lng: parseFloat(place.lon),
            name: place.display_name
        });
    };

    // Close dropdown on click outside
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
        <div className="relative w-80" ref={dropdownRef}>
            <div className="flex items-center bg-glass-bg rounded-lg px-4 py-2 w-full border border-border-theme focus-within:border-brand-gold/30 transition-all">
                {loading ? (
                    <Loader2 className="w-4 h-4 text-brand-gold animate-spin mr-2" />
                ) : (
                    <Search className="w-4 h-4 text-text-dim mr-2" />
                )}
                <input
                    type="text"
                    value={query}
                    onChange={handleInputChange}
                    onFocus={() => query.length >= 3 && setIsOpen(true)}
                    placeholder="Search location..."
                    className="bg-transparent border-none outline-none text-sm w-full text-text-primary placeholder:text-text-dim font-medium"
                />
            </div>

            {isOpen && suggestions.length > 0 && (
                <div className="absolute top-full left-0 right-0 mt-2 bg-surface-dropdown rounded-xl border border-border-theme shadow-2xl overflow-hidden z-[100] backdrop-blur-xl">
                    {suggestions.map((place) => (
                        <div
                            key={place.place_id}
                            onClick={() => handleSelect(place)}
                            className="px-4 py-3 hover:bg-glass-bg cursor-pointer flex items-start gap-3 transition-colors group"
                        >
                            <MapPin className="w-4 h-4 text-text-dim mt-0.5 group-hover:text-brand-gold transition-colors" />
                            <div className="flex flex-col gap-0.5">
                                <span className="text-xs text-text-primary font-medium line-clamp-1">
                                    {place.display_name.split(',')[0]}
                                </span>
                                <span className="text-[10px] text-text-dim line-clamp-1">
                                    {place.display_name.split(',').slice(1).join(',').trim()}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
