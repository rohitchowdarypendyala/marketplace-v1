export type Platform = 'instagram' | 'youtube';

export function detectPlatform(inputUrl: string): Platform | null {
  let u: URL;
  try {
    u = new URL(inputUrl);
  } catch {
    return null;
  }
  const host = u.hostname.toLowerCase();

  if (host === 'instagram.com' || host === 'www.instagram.com') return 'instagram';
  if (host === 'youtube.com' || host === 'www.youtube.com' || host === 'm.youtube.com') return 'youtube';

  return null;
}

export function normalizeProfileUrl(platform: Platform, inputUrl: string): string | null {
  let u: URL;
  try {
    u = new URL(inputUrl);
  } catch {
    return null;
  }

  if (platform === 'instagram') {
    // Canonical: https://www.instagram.com/<handle>/
    // Supported inputs:
    // - https://www.instagram.com/<handle>/
    // - https://instagram.com/<handle>
    const parts = u.pathname.split('/').filter(Boolean);
    if (!parts.length) return null;
    const handle = parts[0];
    // Basic exclusions
    if (
      ['p', 'reel', 'tv', 'explore', 'accounts', 'direct', 'stories'].includes(handle.toLowerCase())
    ) {
      return null;
    }
    return `https://www.instagram.com/${handle}/`;
  }

  // YouTube
  // Supported:
  // - https://www.youtube.com/@handle
  // - https://www.youtube.com/channel/<id>
  // - https://www.youtube.com/c/<name>
  const path = u.pathname.replace(/\/+$/, '');
  const parts = path.split('/').filter(Boolean);
  if (!parts.length) return null;

  if (parts[0].startsWith('@')) {
    // Canonicalize @handle
    return `https://www.youtube.com/${parts[0]}`;
  }

  const head = parts[0].toLowerCase();
  if ((head === 'channel' || head === 'c') && parts[1]) {
    return `https://www.youtube.com/${head}/${parts[1]}`;
  }

  return null;
}

export function extractHandle(platform: Platform, normalizedProfileUrl: string): string | null {
  try {
    const u = new URL(normalizedProfileUrl);
    const parts = u.pathname.split('/').filter(Boolean);
    if (platform === 'instagram') {
      return parts[0] || null;
    }
    if (platform === 'youtube') {
      if (!parts.length) return null;
      if (parts[0].startsWith('@')) return parts[0].slice(1);
      // channel/<id>, c/<name>
      if ((parts[0] === 'channel' || parts[0] === 'c') && parts[1]) return parts[1];
    }
  } catch {
    return null;
  }
  return null;
}
