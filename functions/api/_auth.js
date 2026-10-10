// Shared auth helpers for the Travel Desk password gate.
// Files prefixed with _ are not routed by Pages Functions.
//
// Session token (v2): "v2.<exp>.<nonce>.<sig>"
//   exp   — unix seconds; checked server-side (Max-Age alone is only advisory)
//   nonce — 16 random bytes, hex; makes every session token distinct
//   sig   — HMAC-SHA256(COOKIE_SECRET, "v2|exp|nonce|<auth:hash>")
// Binding the signature to the stored passphrase hash means changing the
// passphrase (or deleting it) revokes every outstanding session; rotating
// COOKIE_SECRET still revokes everything too. v1 tokens are no longer
// accepted — every device signs in once after this change.

export const SESSION_TTL_SECONDS = 30 * 24 * 60 * 60;
const MIN_SECRET_LENGTH = 32;
const HASH_CACHE_TTL = 60; // seconds; passphrase-change revocation lag at the edge

export function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

// Refuse to run with a missing or weak secret instead of minting tokens
// from it. Returns null when fine, or a 500 Response to send back.
export function configError(env) {
  if (!env.TD) return json({ error: "not_configured", detail: "TD KV binding missing" }, 500);
  const s = env.COOKIE_SECRET;
  if (typeof s !== "string" || s.length < MIN_SECRET_LENGTH) {
    return json({ error: "not_configured", detail: "COOKIE_SECRET missing or shorter than " + MIN_SECRET_LENGTH + " chars" }, 500);
  }
  return null;
}

function hex(buf) {
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacHex(secret, message) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  return hex(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message)));
}

export function timingSafeEqual(a, b) {
  a = String(a);
  b = String(b);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

export async function storedHash(env, cacheTtl) {
  const opts = cacheTtl ? { cacheTtl } : undefined;
  return env.TD.get("auth:hash", opts);
}

// Mint a fresh session token. Call only after the passphrase verified.
export async function issueSessionToken(env, authHash) {
  const exp = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const nonce = hex(crypto.getRandomValues(new Uint8Array(16)));
  const sig = await hmacHex(env.COOKIE_SECRET, `v2|${exp}|${nonce}|${authHash}`);
  return `v2.${exp}.${nonce}.${sig}`;
}

export function sessionCookie(token) {
  return "td_auth=" + token + "; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=" + SESSION_TTL_SECONDS;
}

function getCookie(request, name) {
  const header = request.headers.get("cookie") || "";
  const match = header.match(new RegExp("(?:^|;\\s*)" + name + "=([^;]*)"));
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch (e) {
    return null;
  }
}

export async function isAuthed(request, env) {
  if (configError(env)) return false;
  const presented = getCookie(request, "td_auth");
  if (!presented) return false;
  const parts = presented.split(".");
  if (parts.length !== 4 || parts[0] !== "v2") return false;
  const [, expStr, nonce, sig] = parts;
  if (!/^\d{1,12}$/.test(expStr) || !/^[0-9a-f]{32}$/.test(nonce) || !/^[0-9a-f]{64}$/.test(sig)) return false;
  if (Number(expStr) <= Math.floor(Date.now() / 1000)) return false;
  const authHash = await storedHash(env, HASH_CACHE_TTL);
  if (authHash == null) return false; // passphrase cleared → every session revoked
  const expected = await hmacHex(env.COOKIE_SECRET, `v2|${expStr}|${nonce}|${authHash}`);
  return timingSafeEqual(sig, expected);
}

// PBKDF2-SHA256, 100k iterations (the Workers runtime maximum). Shared by
// login.js and setup.js so the two can never drift apart. scripts that seed
// the hash offline must use identical parameters.
export const PBKDF2_ITERATIONS = 100000;

export async function deriveHash(password, saltHex) {
  const salt = Uint8Array.from(saltHex.match(/../g).map((b) => parseInt(b, 16)));
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations: PBKDF2_ITERATIONS },
    key,
    256
  );
  return hex(bits);
}

export function randomSaltHex() {
  return hex(crypto.getRandomValues(new Uint8Array(16)));
}
