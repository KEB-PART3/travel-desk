// POST /api/login — Travel Desk password gate.
// Env: TD (KV namespace), COOKIE_SECRET.
// Verifies PBKDF2-SHA256(password) against the auth:salt / auth:hash values
// in KV, created once via POST /api/setup. Nobody handling deployment ever
// sees the password.
// On match: sets HttpOnly, Secure, SameSite=Lax cookie td_auth=<hmac> with
// Max-Age 30 days and returns 200 {"ok":true}. Otherwise 401 after a short
// artificial delay. Passwords are never logged.

const ITERATIONS = 100000;

async function deriveHash(password, saltHex) {
  const salt = Uint8Array.from(
    saltHex.match(/../g).map((b) => parseInt(b, 16))
  );
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"]
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt, iterations: ITERATIONS },
    key,
    256
  );
  return Array.from(new Uint8Array(bits), (b) =>
    b.toString(16).padStart(2, "0")
  ).join("");
}

async function sessionToken(secret) {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(String(secret || "")),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode("traveldesk-session-v1")
  );
  return Array.from(new Uint8Array(sig), (b) =>
    b.toString(16).padStart(2, "0")
  ).join("");
}

function timingSafeEqual(a, b) {
  a = String(a);
  b = String(b);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function onRequest(context) {
  const { request, env } = context;

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  if (!env.TD) return json({ error: "not_configured" }, 500);

  const salt = await env.TD.get("auth:salt");
  const expected = await env.TD.get("auth:hash");
  if (salt == null || expected == null) {
    // No password has been chosen yet via POST /api/setup.
    return json({ error: "setup_required" }, 403);
  }

  let password = "";
  try {
    const body = await request.json();
    if (body && typeof body.password === "string") password = body.password;
  } catch (e) {
    // fall through -> 401
  }

  const candidate = await deriveHash(password, salt);
  if (!timingSafeEqual(candidate, expected)) {
    await sleep(700); // slow down password guessing
    return json({ error: "unauthorized" }, 401);
  }

  const token = await sessionToken(env.COOKIE_SECRET);
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
      "set-cookie":
        "td_auth=" +
        token +
        "; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=2592000",
    },
  });
}
