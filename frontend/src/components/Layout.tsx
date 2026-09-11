import { useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { Activity, AlertTriangle, BarChart3, Bot, Crosshair, FileText, Flame, Globe2, Home, LogOut, Map as MapIcon, Menu, Moon, Satellite, Settings, Sun, UserCheck, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useTheme } from '../themes/ThemeContext';
import { useAuth } from '../hooks/useAuth';
import { Api } from '../services/api';
import { SearchBox } from './SearchBox';
import { NotificationBell } from './NotificationBell';
import { LiveIndicator } from './LiveIndicator';

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: Home },
  { to: '/map', label: 'India Map', icon: MapIcon },
  { to: '/incidents', label: 'Thermal Events', icon: Flame },
  { to: '/high-risk', label: 'High Risk', icon: AlertTriangle },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/affected-areas', label: 'Affected Areas', icon: Globe2 },
  { to: '/satellite', label: 'Satellite Data', icon: Satellite },
  { to: '/reports', label: 'Reports', icon: FileText },
  { to: '/explainability', label: 'AI Explainability', icon: Bot },
  { to: '/verification', label: 'Human Verification', icon: UserCheck },
  { to: '/location-analysis', label: 'Coordinate Analysis', icon: Crosshair },
  { to: '/settings', label: 'Settings', icon: Settings },
];

export default function Layout() {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const { data: status } = useQuery({ queryKey: ['status'], queryFn: Api.status, staleTime: 300_000 });
  return (
    <div className="min-h-screen flex bg-ink-100 dark:bg-ink-950 text-ink-900 dark:text-ink-100">
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 transform bg-white dark:bg-ink-900 border-r border-ink-200 dark:border-ink-800 transition-transform lg:static lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
        <div className="h-16 flex items-center gap-2 px-4 border-b border-ink-200 dark:border-ink-800">
          <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-brand-500 to-ember-500 grid place-items-center text-white shadow"><Flame size={20} /></div>
          <div className="leading-tight"><div className="font-extrabold tracking-tight">THERMO-SHIELD</div><div className="text-[10px] font-semibold text-ink-500 dark:text-ink-400 tracking-[0.2em]">INDIA · v2.0</div></div>
          <button className="ml-auto lg:hidden btn-ghost p-1" onClick={() => setOpen(false)} aria-label="Close menu"><X size={18} /></button>
        </div>
        <nav className="p-3 space-y-0.5 overflow-y-auto h-[calc(100vh-4rem)]">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} onClick={() => setOpen(false)} className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${isActive ? 'bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300' : 'text-ink-700 dark:text-ink-300 hover:bg-ink-100 dark:hover:bg-ink-800'}`}>
              <Icon size={17} /> {label}
            </NavLink>
          ))}
          <div className="pt-4 px-3 text-[11px] text-ink-500 dark:text-ink-400 leading-relaxed">
            <div className="font-semibold uppercase tracking-wider mb-1">Data policy</div>
            <div>{status?.data_policy ?? 'Real data only'}</div>
            <div className="mt-1">{status?.database}</div>
            {status && <div className="mt-1">History: {new Date(status.history_window.from).toLocaleDateString('en-IN')} → {new Date(status.history_window.to).toLocaleDateString('en-IN')}</div>}
          </div>
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex-1 min-w-0 flex flex-col">
        <header className="h-16 sticky top-0 z-20 flex items-center gap-3 px-4 bg-white/90 dark:bg-ink-900/90 backdrop-blur border-b border-ink-200 dark:border-ink-800">
          <button className="lg:hidden btn-ghost p-1.5" onClick={() => setOpen(true)} aria-label="Open menu"><Menu size={20} /></button>
          <div className="hidden md:flex items-center gap-2 text-sm font-semibold text-ink-700 dark:text-ink-200 whitespace-nowrap"><Activity size={16} className="text-brand-600" /> National Thermal Incident Intelligence</div>
          <div className="flex-1 max-w-xl"><SearchBox /></div>
          <NotificationBell />
          <button className="btn-secondary" onClick={toggle} title="Toggle theme" aria-label="Toggle theme" data-testid="theme-toggle">
            {theme === 'dark' ? <><Sun size={16} /> <span className="hidden sm:inline">Light</span></> : <><Moon size={16} /> <span className="hidden sm:inline">Dark</span></>}
          </button>
          {user && (
            <div className="flex items-center gap-2">
              <div className="hidden sm:block text-right leading-tight"><div className="text-sm font-semibold">{user.full_name || user.email}</div><div className="text-[10px] uppercase tracking-wider text-ink-500">{user.role}</div></div>
              <button className="btn-ghost p-2" onClick={() => logout().then(() => nav('/login'))} title="Sign out" aria-label="Sign out"><LogOut size={18} /></button>
            </div>
          )}
        </header>
        <div className="px-4 md:px-6 pt-3"><LiveIndicator /></div>
        <main className="flex-1 min-w-0 p-4 md:p-6 space-y-6"><Outlet /></main>
        <footer className="px-6 py-3 text-[11px] text-ink-500 dark:text-ink-400 border-t border-ink-200 dark:border-ink-800">
          Automated AI/GIS assessment — decision-support information to be verified by authorized personnel. Data sources: NASA FIRMS (VIIRS/MODIS), OpenStreetMap (ODbL), Open-Meteo, Census 2011 reference population, Sentinel-2 L2A (Earth Search STAC), NASA GIBS.
        </footer>
      </div>
    </div>
  );
}
