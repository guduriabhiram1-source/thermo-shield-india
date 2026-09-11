import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import { ThemeProvider } from './themes/ThemeContext';
import { AuthProvider } from './hooks/useAuth';
import { DateRangeProvider } from './hooks/useDateRange';
import 'leaflet/dist/leaflet.css';
import './index.css';

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <AuthProvider>
            <DateRangeProvider>
              <App />
            </DateRangeProvider>
          </AuthProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
