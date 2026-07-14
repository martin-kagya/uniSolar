import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import HeroSection from './components/HeroSection';
import AboutSection from './components/AboutSection';
import BankableReportSection from './components/BankableReportSection';
import TestimonialsSection from './components/TestimonialsSection';
import ModelStatsSection from './components/ModelStatsSection';
import Footer from './components/Footer';
import ThemeToggle from './components/ThemeToggle';
import Dashboard from './pages/Dashboard';
import LoginPage from './pages/LoginPage';

function LandingPage() {
  return (
    <>
      <nav className="fixed top-0 w-full z-40 flex justify-between items-center px-8 py-4 bg-transparent backdrop-blur-sm border-b border-border-subtle">
        <div className="font-heading font-bold text-xl tracking-tight text-text-primary shadow-black drop-shadow-lg">UNISOLAR</div>
        <div className="hidden md:flex gap-8 text-sm font-medium text-text-muted drop-shadow-md">
          <a href="#" className="hover:text-text-primary transition-colors">Features</a>
          <a href="#" className="hover:text-text-primary transition-colors">Pricing</a>
          <a href="#" className="hover:text-text-primary transition-colors">API</a>
        </div>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <Link to="/login" className="bg-glass-bg-strong backdrop-blur-md text-text-primary px-4 py-2 text-sm font-medium hover:bg-glass-bg transition-colors border border-glass-border rounded-md">
            Login
          </Link>
        </div>
      </nav>

      {/* Main content */}
      <main className="min-h-screen relative z-10">
        <HeroSection />
        <AboutSection />
        <ModelStatsSection />
        <BankableReportSection />
        <TestimonialsSection />
      </main>

      <Footer />
    </>
  );
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<Dashboard />} />
      </Routes>
    </Router>
  );
}

export default App;
