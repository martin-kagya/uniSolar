import React from 'react';
import { motion } from 'framer-motion';
import { Layers, Zap, Globe, Cpu } from 'lucide-react';

const Feature = ({ icon: Icon, title, desc }) => (
    <div className="group flex flex-col items-start p-8 rounded-2xl bg-glass-bg card-hover transition-colors backdrop-blur-sm">
        <div className="p-3 bg-brand-blue/20 rounded-lg mb-6 group-hover:bg-brand-blue/30 transition-colors">
            <Icon className="w-6 h-6 text-blue-400" />
        </div>
        <h3 className="text-xl font-bold text-text-primary mb-3">{title}</h3>
        <p className="text-text-muted leading-relaxed text-sm">{desc}</p>
    </div>
);

export default function AboutSection() {
    return (
        <section className="py-32 w-full relative z-10 bg-surface">
            <div className="max-w-7xl mx-auto px-6">
                <motion.div
                    initial={{ opacity: 0, y: 50 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-100px" }}
                    transition={{ duration: 0.8 }}
                    className="grid grid-cols-1 lg:grid-cols-2 gap-20 mb-32 items-center"
                >
                    <div>
                        <h2 className="font-heading text-4xl md:text-5xl font-bold mb-8 text-text-primary leading-tight">
                            Beyond Basic Estimation. <br /> This is <span className="text-brand-gold">Simulation.</span>
                        </h2>
                        <p className="text-lg text-text-muted mb-8 leading-relaxed">
                            Most solar calculators use simple geometric approximations. UniSolar uses a multi-layered physics engine that accounts for atmospheric scattering, panel temperature coefficients, and inverter efficiency curves in real-time.
                        </p>
                        <div className="flex gap-4 text-sm font-mono text-blue-300">
                            <span>// 99.8% Accuracy</span>
                            <span>// Sub-second Latency</span>
                        </div>
                    </div>

                    {/* Visual Stack */}
                    <div className="relative h-[500px] w-full flex flex-col justify-center items-center perspective-1000">
                        <div className="absolute inset-0 bg-blue-500/5 blur-3xl rounded-full"></div>
                        <div className="space-y-2 relative z-10 w-80 transform rotate-x-12">
                            {['Financial Model', 'Energy Yield', 'Electrical Config', 'Irradiance Map', 'Topography'].map((layer, i) => (
                                <motion.div
                                    key={layer}
                                    initial={{ x: -50, opacity: 0, scale: 0.9 }}
                                    whileInView={{ x: 0, opacity: 1, scale: 1 }}
                                    transition={{ delay: i * 0.1, duration: 0.5 }}
                                    className={`
                        h-16 flex items-center px-6 font-mono text-sm border backdrop-blur-md rounded-lg shadow-2xl
                        ${i === 0 ? 'bg-brand-accent/10 border-brand-accent/30 text-brand-gold z-50' :
                                            i === 1 ? 'bg-blue-500/10 border-blue-500/30 text-blue-300 z-40' :
                                                'bg-surface-raised/40 border-border-theme text-text-muted'}
                    `}
                                    style={{
                                        transform: `translateY(${i * -10}px) scale(${1 - i * 0.05})`,
                                        zIndex: 50 - i
                                    }}
                                >
                                    <span className="w-8 opacity-50">0{5 - i}</span>
                                    {layer}
                                </motion.div>
                            ))}
                        </div>
                    </div>
                </motion.div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    <Feature icon={Globe} title="Gis-Based" desc="High-resolution terrain data integration from NASA & Google Earth." />
                    <Feature icon={Zap} title="Electrical" desc="Detailed inverter and string sizing logic with automated clipping analysis." />
                    <Feature icon={Cpu} title="AI-Driven" desc="Optimizes panel layout for maximum ROI automatically using genetic algorithms." />
                    <Feature icon={Layers} title="Multi-Layered" desc="From irradiance to financial modeling in a single pass." />
                </div>
            </div>
        </section>
    );
}
