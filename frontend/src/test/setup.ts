import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// jsdom lacks matchMedia / ResizeObserver used by the theme provider, Leaflet and Recharts
Object.defineProperty(window, 'matchMedia', { writable: true, value: vi.fn().mockImplementation((query: string) => ({ matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn() })) });
class RO { observe() {} unobserve() {} disconnect() {} }
(globalThis as any).ResizeObserver = RO;
(globalThis as any).URL.createObjectURL = vi.fn(() => 'blob:test');
(globalThis as any).URL.revokeObjectURL = vi.fn();
