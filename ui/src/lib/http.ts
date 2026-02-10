import { NextResponse } from 'next/server';

export function json(data: unknown, init?: ResponseInit) {
  return NextResponse.json(data, init);
}

export function badRequest(message: string, details?: unknown) {
  return json({ ok: false, error: 'bad_request', message, details }, { status: 400 });
}
