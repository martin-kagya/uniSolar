import React, { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';
import { ArrowRight, Play } from 'lucide-react';

export default function HeroSection() {
    const containerRef = useRef(null);
    const { scrollYProgress } = useScroll({
        target: containerRef,
        offset: ["start start", "end start"]
    });

    const y = useTransform(scrollYProgress, [0, 1], ["0%", "50%"]);
    const opacity = useTransform(scrollYProgress, [0, 0.5], [1, 0]);

    return (
        <div ref={containerRef} className="relative min-h-[100vh] flex items-center justify-center overflow-hidden">

            {/* Background Image */}
            <div className="absolute inset-0 z-0">
                <img
                    src="/soren-h-omfN1pW-n2Y-unsplash.jpg"
                    alt="Solar panel background"
                    className="w-full h-full object-cover opacity-50"
                />
                <div className="absolute inset-0 bg-gradient-to-b from-surface/30 via-surface/60 to-surface"></div>
            </div>

            {/* Content */}
            <motion.div
                style={{ y, opacity }}
                className="relative z-10 text-center px-6 max-w-5xl mx-auto mt-[-20vh]"
            >
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8 }}
                    className="inline-block px-4 py-1.5 mb-6 rounded-full bg-glass-bg border border-border-theme text-brand-gold text-xs font-bold uppercase tracking-wider backdrop-blur-md"
                >
                    Physics-Grade Solar Engineering
                </motion.div>

                <motion.h1
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, delay: 0.2 }}
                    className="font-heading text-6xl md:text-8xl font-bold bg-clip-text text-transparent bg-gradient-to-b from-white to-white/60 mb-8 tracking-tight"
                >
                    Utility-scale precision.<br />
                    <span className="text-text-primary">Instant results.</span>
                </motion.h1>

                <motion.p
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, delay: 0.4 }}
                    className="text-lg md:text-xl text-text-muted max-w-2xl mx-auto mb-12 font-light leading-relaxed"
                >
                    The only bankable feasibility engine that combines <span className="text-text-secondary font-normal">sub-hourly satellite data</span> with
                    <span className="text-text-secondary font-normal"> real-time financial modeling</span>.
                </motion.p>

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, delay: 0.6 }}
                    className="flex flex-col md:flex-row gap-4 justify-center items-center"
                >
                    <a
                        href="/dashboard"
                        className="group relative px-8 py-4 bg-white text-slate-900 rounded-full font-bold text-sm tracking-wide overflow-hidden hover:shadow-[0_0_40px_-10px_rgba(255,255,255,0.3)] transition-all"
                    >
                        <span className="relative z-10 flex items-center gap-2">
                            START SIMULATION <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                        </span>
                    </a>

                    <button className="px-8 py-4 bg-glass-bg text-text-primary border border-border-theme rounded-full font-bold text-sm tracking-wide hover:bg-glass-bg-strong transition-colors flex items-center gap-2 backdrop-blur-sm">
                        <Play className="w-4 h-4 fill-current" /> WATCH DEMO
                    </button>
                </motion.div>

                {/* External benchmark trust strip */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.8, delay: 0.9 }}
                    className="mt-14 flex flex-wrap justify-center gap-x-8 gap-y-3"
                >
                    {[
                        { label: 'vs ERA5', value: '−34%', sub: 'RMSE' },
                        { label: 'vs CAMS', value: '−23%', sub: 'RMSE' },
                        { label: 'vs SARAH-2', value: '−27%', sub: 'RMSE' },
                    ].map((item) => (
                        <div key={item.label} className="flex items-center gap-2.5 text-sm">
                            <span className="font-mono font-bold text-brand-gold">{item.value}</span>
                            <span className="text-text-muted">{item.label}</span>
                            <span className="text-text-dim text-xs">({item.sub})</span>
                        </div>
                    ))}
                    <div className="text-text-dim text-xs self-center">
                        Sawadogo et al. 2023 · 37 stations, West Africa
                    </div>
                </motion.div>
            </motion.div>

            {/* Scroll Indicator */}
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1, duration: 1 }}
                className="absolute bottom-12 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
            >
                <span className="text-[10px] uppercase tracking-widest text-text-dim">Scroll to Explore</span>
                <div className="w-[1px] h-12 bg-gradient-to-b from-slate-500 to-transparent"></div>
            </motion.div>
        </div>
    );
}
