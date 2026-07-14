import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// Avatar nodes positioned to create an organic constellation pattern
// Positions are percentages of the container width/height
const avatarNodes = [
    { id: 1, x: 18, y: 12, size: 56, img: 'https://i.pravatar.cc/150?u=solar1', name: 'James K.', role: 'VP Engineering, Helios Energy', quote: 'UniSolar reduced our feasibility study timeline from months to days.' },
    { id: 2, x: 42, y: 8, size: 44, img: 'https://i.pravatar.cc/150?u=solar2', name: 'Maria T.', role: 'Solar Analyst, BrightWatt', quote: 'The irradiance modeling is the most accurate I have ever used.' },
    { id: 3, x: 68, y: 14, size: 52, img: 'https://i.pravatar.cc/150?u=solar3', name: 'Raj P.', role: 'CTO, SunGrid Solutions', quote: 'Our bankable reports now close deals 3x faster.' },
    { id: 4, x: 88, y: 10, size: 40, img: 'https://i.pravatar.cc/150?u=solar4', name: 'Sofia L.', role: 'Project Manager, Aurora Solar', quote: 'The shading analysis alone saved us $200k on our last project.' },
    { id: 5, x: 8, y: 38, size: 48, img: 'https://i.pravatar.cc/150?u=solar5', name: 'Chen W.', role: 'Director, GreenPeak', quote: 'Physics-grade precision that actually lives up to its promise.' },
    { id: 6, x: 30, y: 32, size: 64, img: 'https://i.pravatar.cc/150?u=solar6', name: 'Sarah J.', role: 'Lead Engineer, SolarFlow', quote: 'The yield model matched our actual production within 1.5%.' },
    { id: 7, x: 55, y: 28, size: 48, img: 'https://i.pravatar.cc/150?u=solar7', name: 'David C.', role: 'CTO, GreenGrid', quote: 'Cut our design phase from 2 weeks to 4 hours.' },
    { id: 8, x: 78, y: 35, size: 56, img: 'https://i.pravatar.cc/150?u=solar8', name: 'Elena R.', role: 'Research Director, Photon Labs', quote: 'Finally respects the physics of diffuse irradiance properly.' },
    { id: 9, x: 95, y: 42, size: 36, img: 'https://i.pravatar.cc/150?u=solar9', name: 'Tom B.', role: 'Analyst, SunVest Capital', quote: 'The financial modeling gives our investors real confidence.' },
    { id: 10, x: 15, y: 60, size: 44, img: 'https://i.pravatar.cc/150?u=solar10', name: 'Aisha M.', role: 'CEO, NovaSun', quote: 'We scaled from 10MW to 500MW projects using UniSolar.' },
    { id: 11, x: 38, y: 55, size: 52, img: 'https://i.pravatar.cc/150?u=solar11', name: 'Lucas F.', role: 'Engineering Lead, Voltaic', quote: 'The multi-layered physics engine is a game-changer.' },
    { id: 12, x: 62, y: 52, size: 40, img: 'https://i.pravatar.cc/150?u=solar12', name: 'Priya S.', role: 'VP Operations, SolarBridge', quote: 'Instant bankable reports that our clients actually trust.' },
    { id: 13, x: 82, y: 58, size: 48, img: 'https://i.pravatar.cc/150?u=solar13', name: 'Mark H.', role: 'Fund Manager, CleanEnergy VC', quote: 'Due diligence that used to take weeks now takes hours.' },
    { id: 14, x: 25, y: 78, size: 40, img: 'https://i.pravatar.cc/150?u=solar14', name: 'Nina V.', role: 'Sustainability Lead, TerraWatt', quote: 'The accuracy gives us confidence to commit capital.' },
    { id: 15, x: 50, y: 75, size: 56, img: 'https://i.pravatar.cc/150?u=solar15', name: 'Oscar G.', role: 'Chief Scientist, LumenTech', quote: 'Sub-hourly satellite data integration is remarkable.' },
    { id: 16, x: 72, y: 78, size: 44, img: 'https://i.pravatar.cc/150?u=solar16', name: 'Hannah K.', role: 'Director, Pacific Solar', quote: 'We trust UniSolar for every utility-scale proposal.' },
    { id: 17, x: 45, y: 90, size: 36, img: 'https://i.pravatar.cc/150?u=solar17', name: 'Yuki T.', role: 'Analyst, EastWind Solar', quote: 'Clean interface, powerful engine. Exactly what we needed.' },
];

// Lines connecting avatar nodes (pairs of node IDs)
const connections = [
    [1, 2], [2, 3], [3, 4], [1, 5], [2, 6], [3, 7], [4, 8],
    [5, 6], [6, 7], [7, 8], [8, 9], [5, 10], [6, 11], [7, 12],
    [8, 13], [10, 11], [11, 12], [12, 13], [10, 14], [11, 15],
    [12, 16], [14, 15], [15, 16], [15, 17], [1, 6], [3, 8],
    [6, 12], [7, 11],
];

function AvatarNode({ node, isActive, onHover, onLeave }) {
    const isHighlighted = node.id === 6 || node.id === 8 || node.id === 15; // "featured" nodes

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ delay: node.id * 0.04, type: 'spring', stiffness: 200, damping: 15 }}
            className="absolute group cursor-pointer"
            style={{
                left: `${node.x}%`,
                top: `${node.y}%`,
                width: node.size,
                height: node.size,
                transform: 'translate(-50%, -50%)',
                zIndex: isActive ? 30 : isHighlighted ? 20 : 10,
            }}
            onMouseEnter={() => onHover(node.id)}
            onMouseLeave={onLeave}
        >
            {/* Glow ring for highlighted/active nodes */}
            <div className={`
                absolute inset-[-4px] rounded-full transition-all duration-500
                ${isActive
                    ? 'bg-gradient-to-br from-brand-gold/60 to-orange-500/40 blur-[2px]'
                    : isHighlighted
                        ? 'bg-gradient-to-br from-brand-gold/30 to-transparent blur-[1px]'
                        : 'bg-transparent'
                }
            `} />

            {/* Avatar circle */}
            <div className={`
                relative w-full h-full rounded-full overflow-hidden border-2 transition-all duration-300
                ${isActive
                    ? 'border-brand-gold shadow-[0_0_30px_rgba(245,158,11,0.4)] scale-110'
                    : isHighlighted
                        ? 'border-brand-gold/50 shadow-[0_0_15px_rgba(245,158,11,0.15)]'
                        : 'border-border-theme grayscale-[50%] hover:grayscale-0 hover:border-white/30'
                }
            `}>
                <img
                    src={node.img}
                    alt={node.name}
                    className="w-full h-full object-cover"
                    loading="lazy"
                />
            </div>

            {/* Tooltip on hover */}
            <AnimatePresence>
                {isActive && (
                    <motion.div
                        initial={{ opacity: 0, y: 10, scale: 0.9 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 5, scale: 0.95 }}
                        transition={{ duration: 0.2 }}
                        className="absolute left-1/2 -translate-x-1/2 mt-3 w-64 p-4 rounded-2xl bg-surface-dropdown/95 backdrop-blur-xl border border-brand-gold/30 shadow-[0_0_40px_rgba(245,158,11,0.1)] pointer-events-none"
                        style={{ top: '100%', zIndex: 50 }}
                    >
                        <p className="text-text-secondary text-xs leading-relaxed font-light mb-3 italic">
                            &ldquo;{node.quote}&rdquo;
                        </p>
                        <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded-full overflow-hidden border border-brand-gold/50">
                                <img src={node.img} alt={node.name} className="w-full h-full object-cover" />
                            </div>
                            <div>
                                <div className="text-text-primary text-xs font-semibold">{node.name}</div>
                                <div className="text-text-dim text-[10px]">{node.role}</div>
                            </div>
                        </div>
                        {/* Tooltip arrow */}
                        <div className="absolute -top-1.5 left-1/2 -translate-x-1/2 w-3 h-3 rotate-45 bg-surface-dropdown/95 border-l border-t border-brand-gold/30" />
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
}

export default function TestimonialsSection() {
    const [activeNode, setActiveNode] = useState(null);

    // Get node position by ID
    const getNode = (id) => avatarNodes.find(n => n.id === id);

    return (
        <section className="py-32 relative z-10 bg-surface overflow-hidden">
            <div className="max-w-7xl mx-auto px-6">
                {/* Header */}
                <div className="mb-16 text-center">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        className="inline-block px-4 py-1.5 mb-6 rounded-full bg-glass-bg border border-border-theme text-brand-gold text-xs font-bold uppercase tracking-wider backdrop-blur-md"
                    >
                        Trusted Worldwide
                    </motion.div>
                    <motion.h2
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        transition={{ delay: 0.1 }}
                        className="font-heading text-5xl md:text-6xl font-bold text-text-primary mb-6"
                    >
                        Share your stories
                    </motion.h2>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        transition={{ delay: 0.2 }}
                        className="text-text-muted max-w-2xl mx-auto text-lg font-light"
                    >
                        Join the community of industry leaders who trust UniSolar for their solar engineering and feasibility reports.
                    </motion.p>
                </div>

                {/* Constellation Network */}
                <motion.div
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.8, delay: 0.3 }}
                    className="relative w-full mx-auto"
                    style={{ aspectRatio: '16 / 9' }}
                >
                    {/* SVG Connection Lines */}
                    <svg
                        className="absolute inset-0 w-full h-full pointer-events-none"
                        style={{ zIndex: 1 }}
                    >
                        {connections.map(([fromId, toId], i) => {
                            const from = getNode(fromId);
                            const to = getNode(toId);
                            if (!from || !to) return null;
                            const isConnectedToActive = activeNode === fromId || activeNode === toId;

                            return (
                                <motion.line
                                    key={`${fromId}-${toId}`}
                                    x1={`${from.x}%`}
                                    y1={`${from.y}%`}
                                    x2={`${to.x}%`}
                                    y2={`${to.y}%`}
                                    stroke={isConnectedToActive ? 'rgba(245,158,11,0.4)' : 'rgba(255,255,255,0.06)'}
                                    strokeWidth={isConnectedToActive ? 1.5 : 0.5}
                                    initial={{ pathLength: 0, opacity: 0 }}
                                    whileInView={{ pathLength: 1, opacity: 1 }}
                                    viewport={{ once: true }}
                                    transition={{ delay: 0.4 + i * 0.02, duration: 0.5 }}
                                    style={{ transition: 'stroke 0.3s ease, stroke-width 0.3s ease' }}
                                />
                            );
                        })}
                    </svg>

                    {/* Avatar Nodes */}
                    {avatarNodes.map(node => (
                        <AvatarNode
                            key={node.id}
                            node={node}
                            isActive={activeNode === node.id}
                            onHover={setActiveNode}
                            onLeave={() => setActiveNode(null)}
                        />
                    ))}
                </motion.div>

                {/* CTA */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.5 }}
                    className="text-center mt-16"
                >
                    <a
                        href="#"
                        className="inline-block px-8 py-3 rounded-full border border-border-theme text-text-primary text-sm font-medium hover:bg-glass-bg hover:border-brand-gold/30 transition-all duration-300"
                    >
                        Read more success stories
                    </a>
                </motion.div>
            </div>
        </section>
    );
}
