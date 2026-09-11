import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, session, setSession } from './helpers';
import LoginPage from '../pages/LoginPage';
import RegisterPage from '../pages/RegisterPage';
import VerifyEmailPage from '../pages/VerifyEmailPage';
import { Api } from '../services/api';

vi.mock('../services/api', async () => {
  const actual = await vi.importActual<typeof import('../services/api')>('../services/api');
  return { ...actual, Api: { ...actual.Api, login: vi.fn(), register: vi.fn(), verifyEmail: vi.fn(), resendVerification: vi.fn(), status: vi.fn() } };
});

beforeEach(() => { localStorage.clear(); vi.clearAllMocks(); });

describe('login', () => {
  it('signs in and stores the session', async () => {
    (Api.login as any).mockResolvedValue(session);
    renderWithProviders(<LoginPage />, { route: '/login', path: '/login' });
    await userEvent.type(screen.getByLabelText('E-mail'), 'analyst@example.org');
    await userEvent.type(screen.getByLabelText('Password'), 'StrongPassw0rd!');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
    await waitFor(() => expect(Api.login).toHaveBeenCalledWith('analyst@example.org', 'StrongPassw0rd!'));
    await waitFor(() => expect(JSON.parse(localStorage.getItem('tsi-session') || '{}').user?.email).toBe('analyst@example.org'));
  });

  it('shows the verification hint when the account is not verified', async () => {
    (Api.login as any).mockRejectedValue({ isAxiosError: true, response: { status: 403, data: { detail: 'Email verification required - enter the code' } }, message: 'x' });
    renderWithProviders(<LoginPage />, { route: '/login', path: '/login' });
    await userEvent.type(screen.getByLabelText('E-mail'), 'new@example.org');
    await userEvent.type(screen.getByLabelText('Password'), 'StrongPassw0rd!');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/verification required/i);
    expect(screen.getByRole('link', { name: /enter your verification code/i })).toBeInTheDocument();
  });
});

describe('registration + verification', () => {
  it('registers and navigates to the verification step', async () => {
    (Api.register as any).mockResolvedValue({ message: 'Account created. Verify your e-mail address to activate it.', detail: 'Verification code sent' });
    renderWithProviders(<RegisterPage />, { route: '/register', path: '/register' });
    await userEvent.type(screen.getByLabelText('E-mail'), 'new@example.org');
    await userEvent.type(screen.getByLabelText(/^Password/), 'StrongPassw0rd!');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'StrongPassw0rd!');
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));
    await waitFor(() => expect(Api.register).toHaveBeenCalled());
    expect(await screen.findByText('VERIFY PAGE')).toBeInTheDocument();
  });

  it('rejects mismatched passwords before calling the API', async () => {
    renderWithProviders(<RegisterPage />, { route: '/register', path: '/register' });
    await userEvent.type(screen.getByLabelText('E-mail'), 'new@example.org');
    await userEvent.type(screen.getByLabelText(/^Password/), 'StrongPassw0rd!');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'DifferentPass1!');
    await userEvent.click(screen.getByRole('button', { name: /create account/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/do not match/i);
    expect(Api.register).not.toHaveBeenCalled();
  });

  it('submits the 6-digit code and can resend', async () => {
    (Api.verifyEmail as any).mockResolvedValue({ message: 'E-mail verified - your account is active.' });
    (Api.resendVerification as any).mockResolvedValue({ message: 'A new verification code has been issued.' });
    renderWithProviders(<VerifyEmailPage />, { route: '/verify-email?email=new%40example.org', path: '/verify-email' });
    expect(screen.getByLabelText('E-mail')).toHaveValue('new@example.org');
    await userEvent.type(screen.getByLabelText('Verification code'), '123456');
    await userEvent.click(screen.getByRole('button', { name: /verify e-mail/i }));
    await waitFor(() => expect(Api.verifyEmail).toHaveBeenCalledWith('new@example.org', '123456'));
    expect(await screen.findByText(/your account is active/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /resend verification code/i }));
    await waitFor(() => expect(Api.resendVerification).toHaveBeenCalledWith('new@example.org'));
  });
});

describe('protected routes', () => {
  it('redirects anonymous users to the login page', async () => {
    setSession(null);
    const { ProtectedRoute } = await import('../components/ProtectedRoute');
    renderWithProviders(<ProtectedRoute><div>SECRET</div></ProtectedRoute>, { route: '/dashboard', path: '/dashboard' });
    expect(await screen.findByText('LOGIN PAGE')).toBeInTheDocument();
  });
});
