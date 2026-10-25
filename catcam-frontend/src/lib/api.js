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

async function signAdminRequest(token, path) {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const message = `POST:${path}:${timestamp}`;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(token),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sigBuf = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  const signature = Array.from(new Uint8Array(sigBuf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
  return { timestamp, signature };
}

export async function adminFeed(token) {
  const { timestamp, signature } = await signAdminRequest(token, '/admin/feed');
  const r = await fetch(`${API_BASE}/admin/feed`, {
    method: 'POST',
    headers: {
      'X-Admin-Timestamp': timestamp,
      'X-Admin-Signature': signature
    }
  });
  let data = {};
  try {
    data = await r.json();
  } catch (e) {

  }
  return { httpOk: r.ok, status: r.status, data };
}
