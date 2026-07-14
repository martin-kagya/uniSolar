import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, ArrowRight, Sun } from 'lucide-react';

export default function LoginPage() {
    const [showPassword, setShowPassword] = useState(false);
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const navigate = useNavigate();

    const handleSubmit = (e) => {
        e.preventDefault();
        setIsLoading(true);
        // Simulate login
        setTimeout(() => {
            setIsLoading(false);
            navigate('/dashboard');
        }, 1200);
    };

    return (
        <div className="min-h-screen flex bg-surface">
            {/* Left Side — Login Form */}
            <div className="w-full lg:w-1/2 flex flex-col justify-center px-8 md:px-16 lg:px-24 py-12">
                {/* Logo */}
                <Link to="/" className="flex items-center gap-2 mb-16 group">
                    <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-gold to-orange-500 flex items-center justify-center shadow-[0_0_20px_rgba(245,158,11,0.3)] group-hover:shadow-[0_0_30px_rgba(245,158,11,0.5)] transition-shadow">
                        <Sun className="w-5 h-5 text-white" />
                    </div>
                    <span className="font-heading font-bold text-xl tracking-tight text-text-primary">UNISOLAR</span>
                </Link>

                {/* Welcome Text */}
                <div className="mb-10">
                    <h1 className="font-heading text-4xl font-bold text-text-primary mb-3">Welcome back</h1>
                    <p className="text-text-dim text-sm">Enter your credentials to access your simulation dashboard.</p>
                </div>

                {/* Login Form */}
                <form onSubmit={handleSubmit} className="space-y-5">
                    {/* Email */}
                    <div>
                        <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
                            Email Address
                        </label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="you@company.com"
                            className="w-full px-4 py-3.5 bg-glass-bg border border-border-theme rounded-xl text-text-primary text-sm placeholder:text-text-dim focus:outline-none focus:border-brand-gold/50 focus:ring-1 focus:ring-brand-gold/20 transition-all"
                            required
                        />
                    </div>

                    {/* Password */}
                    <div>
                        <div className="flex justify-between items-center mb-2">
                            <label className="block text-xs font-semibold text-text-muted uppercase tracking-wider">
                                Password
                            </label>
                            <a href="#" className="text-xs text-brand-gold hover:text-brand-gold-glow transition-colors">
                                Forgot password?
                            </a>
                        </div>
                        <div className="relative">
                            <input
                                type={showPassword ? 'text' : 'password'}
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                placeholder="••••••••"
                                className="w-full px-4 py-3.5 bg-glass-bg border border-border-theme rounded-xl text-text-primary text-sm placeholder:text-text-dim focus:outline-none focus:border-brand-gold/50 focus:ring-1 focus:ring-brand-gold/20 transition-all pr-12"
                                required
                            />
                            <button
                                type="button"
                                onClick={() => setShowPassword(!showPassword)}
                                className="absolute right-4 top-1/2 -translate-y-1/2 text-text-dim hover:text-text-secondary transition-colors"
                            >
                                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>

                    {/* Remember Me */}
                    <div className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            id="remember"
                            className="w-4 h-4 rounded bg-glass-bg border border-border-theme text-brand-gold focus:ring-brand-gold/20 accent-amber-500"
                        />
                        <label htmlFor="remember" className="text-sm text-text-dim">Remember me for 30 days</label>
                    </div>

                    {/* Submit Button */}
                    <button
                        type="submit"
                        disabled={isLoading}
                        className="w-full py-3.5 bg-gradient-to-r from-brand-gold to-orange-500 text-white rounded-xl font-semibold text-sm tracking-wide hover:shadow-[0_0_30px_rgba(245,158,11,0.3)] transition-all duration-300 flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                        {isLoading ? (
                            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                        ) : (
                            <>
                                Sign In <ArrowRight className="w-4 h-4" />
                            </>
                        )}
                    </button>
                </form>

                {/* Divider */}
                <div className="flex items-center gap-4 my-8">
                    <div className="flex-1 h-px bg-border-subtle"></div>
                    <span className="text-xs text-text-dim uppercase tracking-wider">or continue with</span>
                    <div className="flex-1 h-px bg-border-subtle"></div>
                </div>

                {/* Social Logins */}
                <div className="grid grid-cols-2 gap-3">
                    <button className="flex items-center justify-center gap-2 py-3 bg-glass-bg border border-border-theme rounded-xl text-sm text-text-muted hover:bg-glass-bg-strong hover:border-border-theme transition-all">
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                            <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                            <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                            <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                        </svg>
                        Google
                    </button>
                    <button className="flex items-center justify-center gap-2 py-3 bg-glass-bg border border-border-theme rounded-xl text-sm text-text-muted hover:bg-glass-bg-strong hover:border-border-theme transition-all">
                        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
                        </svg>
                        GitHub
                    </button>
                </div>

                {/* Sign Up Link */}
                <p className="text-sm text-text-dim text-center mt-10">
                    Don't have an account?{' '}
                    <a href="#" className="text-brand-gold hover:text-brand-gold-glow font-medium transition-colors">
                        Request access
                    </a>
                </p>
            </div>

            {/* Right Side — Image */}
            <div className="hidden lg:block lg:w-1/2 relative">
                <img
                    src="/american-public-power-association-XGAZzyLzn18-unsplash.jpg"
                    alt="Solar farm at sunset"
                    className="absolute inset-0 w-full h-full object-cover"
                />
                {/* Top gradient for text readability */}
                <div className="absolute inset-x-0 top-0 h-1/2 bg-gradient-to-b from-black/70 to-transparent" />

                {/* Overlay Content */}
                <div className="absolute top-10 left-10 right-10 z-10">
                    <div className="p-5 rounded-2xl bg-glass-bg-strong backdrop-blur-xl card-hover">
                        <p className="text-text-primary text-sm font-medium leading-relaxed mb-3">
                            "UniSolar cut our preliminary design phase from 2 weeks to 4 hours. The financial modeling is spot on."
                        </p>
                        <div className="flex items-center gap-3">
                            <img src="https://i.pravatar.cc/150?u=a042581f4e29026704d" alt="David Chen" className="w-8 h-8 rounded-full object-cover" />
                            <div>
                                <div className="text-text-primary text-xs font-semibold">David Chen</div>
                                <div className="text-text-muted text-[10px]">CTO, GreenGrid</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
