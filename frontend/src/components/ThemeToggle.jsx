import React from 'react';
import { motion } from 'framer-motion';
import { Sun, Moon } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

export default function ThemeToggle({ className = '' }) {
    const { theme, toggleTheme } = useTheme();
    const isDark = theme === 'dark';

    return (
        <button
            onClick={toggleTheme}
            className={`relative flex items-center justify-center w-9 h-9 rounded-lg bg-glass-bg border border-glass-border hover:bg-glass-bg-strong transition-all ${className}`}
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
        >
            <motion.div
                key={theme}
                initial={{ scale: 0, rotate: -90, opacity: 0 }}
                animate={{ scale: 1, rotate: 0, opacity: 1 }}
                exit={{ scale: 0, rotate: 90, opacity: 0 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
            >
                {isDark ? (
                    <Sun className="w-4 h-4 text-brand-gold" />
                ) : (
                    <Moon className="w-4 h-4 text-slate-700" />
                )}
            </motion.div>
        </button>
    );
}
