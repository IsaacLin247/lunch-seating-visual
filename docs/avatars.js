// Client-side avatars for simulated ids (S001…S257). Optional local portrait
// URLs live only in memory. Names and portrait URL ownership stay with callers.
// Anonymous DiceBear avatars are bundled locally, with initial badges as fallback.

import { studentLabel } from './names.js?v=20260915-directory-names-1';

const LOCAL_AVATARS = './vendor/dicebear.js';

const svgCache = new Map();     // id -> svg string
const uriCache = new Map();     // id -> data uri
const bitmapCache = new Map();  // `${id}@${px}` -> canvas
let directoryPortraits = new Map(); // simulated id -> caller-owned blob URL
let dicebear = null;            // { createAvatar, style } or null
let status = 'loading';         // loading | local | fallback

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
    const local = await withTimeout(import(LOCAL_AVATARS), 6000);
    dicebear = { createAvatar: local.createAvatar, style: local.thumbs };
    status = 'local';
  } catch (e) {
    dicebear = null;
    status = 'fallback';
    console.info('Local avatar bundle unavailable; using initials fallback.', e && e.message);
  }
  return status;
}

export function avatarStatus() { return status; }

/** Replace the in-memory portrait mapping atomically. The caller owns the URLs. */
export function setDirectoryPortraits(map) {
  if (!(map instanceof Map)) throw new TypeError('Portrait mappings must be a Map of simulated IDs to blob URLs.');
  const replacement = new Map();
  for (const [id, uri] of map) {
    // These URLs can also appear in SVG href attributes. Reject quote/control
    // characters as well as all network/data URLs; only local blob URLs belong here.
    if (typeof id !== 'string' || !id || typeof uri !== 'string' || !uri.startsWith('blob:') || /[\s\u0000-\u001f\u007f"'<>`\\]/.test(uri) || uri.length <= 5) {
      throw new TypeError('Portrait mappings accept only nonempty simulated IDs and safe local blob URLs.');
    }
    replacement.set(id, uri);
  }
  directoryPortraits = replacement;
  return directoryPortraits.size;
}

/** Clear references without revoking URLs owned by the directory importer. */
export function clearDirectoryPortraits() { directoryPortraits = new Map(); }

export function directoryPortraitUri(id) { return directoryPortraits.get(id) || null; }

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

export function anonymousAvatarUri(id) {
  let u = uriCache.get(id);
  if (u) return u;
  u = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(avatarSvg(id));
  uriCache.set(id, u);
  return u;
}

export function avatarUri(id) { return directoryPortraitUri(id) || anonymousAvatarUri(id); }

export function avatarImg(id, cls = '') {
  const img = document.createElement('img');
  const portrait = directoryPortraitUri(id);
  img.alt = portrait ? `Illustrative portrait for simulated student ${studentLabel(id)}` : studentLabel(id);
  img.decoding = 'async';
  if (cls) img.className = cls;
  if (portrait) {
    img.classList.add('directory-portrait');
    img.onerror = () => {
      // An error from an earlier source must not overwrite a newer image source.
      if (img.getAttribute('src') !== portrait) return;
      img.onerror = null;
      img.classList.remove('directory-portrait');
      img.alt = studentLabel(id);
      img.src = anonymousAvatarUri(id);
    };
  }
  img.src = portrait || anonymousAvatarUri(id);
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
  img.src = anonymousAvatarUri(id);
  return c;
}

export function preloadBitmaps(ids, px, onProgress) {
  let done = 0;
  ids.forEach(id => avatarBitmap(id, px, () => { done++; if (onProgress) onProgress(done, ids.length); }));
}
