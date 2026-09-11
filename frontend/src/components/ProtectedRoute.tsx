import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from '../hooks/useAuth';

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const loc = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <>{children}</>;
}
