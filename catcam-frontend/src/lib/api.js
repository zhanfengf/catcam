const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export async function getStatus() {
  const r = await fetch(`${API_BASE}/status`, { cache: 'no-store' });
  if (!r.ok) throw new Error(`status ${r.status}`);
  return r.json();
}

export async function feed() {
  const r = await fetch(`${API_BASE}/feed`, { method: 'POST' });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}

export const STREAM_URL = import.meta.env.VITE_STREAM_URL ?? '';
