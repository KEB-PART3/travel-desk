// POST /api/login — Travel Desk password gate.
// Env: TD (KV namespace), COOKIE_SECRET (32+ chars).
// Verifies PBKDF2-SHA256(password) against the auth:salt / auth:hash values
// in KV, created once via POST /api/setup (or seeded offline). Nobody
// handling deployment ever sees the password.
// On match: sets an HttpOnly, Secure, SameSite=Lax td_auth cookie carrying a
// v2 session token (expiry checked server-side; see _auth.js) and returns
// 200 {"ok":true}. Otherwise 401 after a short artificial delay. Passwords
// are never logged. The delay is not a rate limit — pair a long passphrase
// with a Cloudflare rate-limiting rule on /api/login (see README).

import {
  json,
  configError,
  deriveHash,
  timingSafeEqual,
  issueSessionToken,
  sessionCookie,
} from "./_auth.js";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function onRequest(context) {
  const { request, env } = context;

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  const bad = configError(env);
  if (bad) return bad;

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
    await sleep(700); // slow down password guessing (per request, not a rate limit)
    return json({ error: "unauthorized" }, 401);
  }

  const token = await issueSessionToken(env, expected);
  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
      "set-cookie": sessionCookie(token),
    },
  });
}
