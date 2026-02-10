'use client';

import type {
  AuthStartResponse,
  AuthVerifyResponse,
  LogoutResponse,
  MeResponse,
} from './types';

async function asJson<T>(res: Response): Promise<T> {
  const txt = await res.text();
  try {
    return JSON.parse(txt) as T;
  } catch {
    throw new Error(`Invalid JSON response (HTTP ${res.status})`);
  }
}

function errFrom(res: Response, body: any) {
  const msg = body?.message || body?.error || `Request failed (HTTP ${res.status})`;
  return new Error(String(msg));
}

export async function getMe(): Promise<MeResponse> {
  const res = await fetch('/api/me', { cache: 'no-store' });
  const body = await asJson<MeResponse>(res);
  if (!res.ok) throw errFrom(res, body);
  return body;
}

export async function startOtp(email: string, role: 'business' | 'influencer'): Promise<AuthStartResponse> {
  const res = await fetch('/api/auth/start', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email, role }),
  });
  const body = await asJson<AuthStartResponse & any>(res);
  if (!res.ok) throw errFrom(res, body);
  return body;
}

export async function verifyOtp(
  email: string,
  code: string,
  role?: 'business' | 'influencer'
): Promise<AuthVerifyResponse> {
  const res = await fetch('/api/auth/verify', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ email, code, role }),
  });
  const body = await asJson<AuthVerifyResponse & any>(res);
  if (!res.ok) throw errFrom(res, body);
  return body;
}

export async function logout(): Promise<LogoutResponse> {
  const res = await fetch('/api/auth/logout', { method: 'POST' });
  const body = await asJson<LogoutResponse & any>(res);
  if (!res.ok) throw errFrom(res, body);
  return body;
}
