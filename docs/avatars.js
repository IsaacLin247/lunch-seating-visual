// Client-side avatars from anonymous ids (S001…S257). DiceBear is loaded from a
// CDN; if that fails (offline, blocked) we fall back to warm initial badges.
// Nothing here ever touches real student data.

const CORE_URL = 'https://cdn.jsdelivr.net/npm/@dicebear/core@9/+esm';
const COLL_URL = 'https://cdn.jsdelivr.net/npm/@dicebear/collection@9/+esm';

const svgCache = new Map();     // id -> svg string
const uriCache = new Map();     // id -> data uri
const bitmapCache = new Map();  // `${id}@${px}` -> canvas
let dicebear = null;            // { createAvatar, style } or null
let status = 'loading';         // loading | cdn | fallback

const BG = ['#f6d5b8', '#f3c9c4', '#d9e6f2', '#dbeedd', '#f4e3b7', '#e4d6f0', '#cfe8e6', '#f2d9c1'];
const FG = ['#8a4b2a', '#8f3a3a', '#2f5b86', '#2f6b45', '#7a5a13', '#5b3f86', '#256b66', '#8a5a2a'];

function hash(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function withTimeout(p, ms) {
  return Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms))]);
}

export async function initAvatars() {
  try {
    const [core, coll] = await withTimeout(Promise.all([import(CORE_URL), import(COLL_URL)]), 6000);
    dicebear = { createAvatar: core.createAvatar, style: coll.thumbs };
    status = 'cdn';
  } catch (e) {
    dicebear = null;
    status = 'fallback';
    console.info('Avatar CDN unavailable; using initials fallback.', e && e.message);
  }
  return status;
}

export function avatarStatus() { return status; }

function fallbackSvg(id) {
  const h = hash(id);
  const bg = BG[h % BG.length], fg = FG[(h >> 3) % FG.length];
  const digits = id.replace(/^S0*/, '') || id;
  const r = ((h >> 6) % 20) - 10;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">` +
    `<rect width="64" height="64" fill="${bg}"/>` +
    `<circle cx="${32 + r / 2}" cy="${28 + (r % 5)}" r="13" fill="${fg}" opacity=".18"/>` +
    `<text x="32" y="40" text-anchor="middle" font-family="Avenir Next, Segoe UI, Arial, sans-serif" font-weight="700" font-size="24" fill="${fg}">${digits}</text>` +
    `</svg>`;
}

export function avatarSvg(id) {
  let s = svgCache.get(id);
  if (s) return s;
  if (dicebear) {
    try {
      s = dicebear.createAvatar(dicebear.style, {
        seed: id, radius: 50, backgroundColor: ['f6d5b8', 'dbe9f6', 'f8e2c8', 'dbeedd', 'f4e3b7', 'e4d6f0'],
      }).toString();
    } catch (e) { s = null; }
  }
  if (!s) s = fallbackSvg(id);
  svgCache.set(id, s);
  return s;
}

export function avatarUri(id) {
  let u = uriCache.get(id);
  if (u) return u;
  u = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(avatarSvg(id));
  uriCache.set(id, u);
  return u;
}

export function avatarImg(id, cls = '') {
  const img = document.createElement('img');
  img.src = avatarUri(id);
  img.alt = id;
  img.decoding = 'async';
  if (cls) img.className = cls;
  return img;
}

/** Circular bitmap for canvas drawing. Returns a canvas (possibly still blank
 *  until the underlying image decodes; call onReady to repaint). */
export function avatarBitmap(id, px, onReady) {
  const key = `${id}@${px}`;
  let c = bitmapCache.get(key);
  if (c) return c;
  c = document.createElement('canvas');
  c.width = px; c.height = px;
  c.dataset.ready = '0';
  bitmapCache.set(key, c);
  const img = new Image();
  img.onload = () => {
    const ctx = c.getContext('2d');
    ctx.save();
    ctx.beginPath(); ctx.arc(px / 2, px / 2, px / 2, 0, Math.PI * 2); ctx.clip();
    ctx.drawImage(img, 0, 0, px, px);
    ctx.restore();
    c.dataset.ready = '1';
    if (onReady) onReady();
  };
  img.src = avatarUri(id);
  return c;
}

export function preloadBitmaps(ids, px, onProgress) {
  let done = 0;
  ids.forEach(id => avatarBitmap(id, px, () => { done++; if (onProgress) onProgress(done, ids.length); }));
}
