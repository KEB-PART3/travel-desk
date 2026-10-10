// GET /api/setup -> { needs_setup: true|false }
// POST /api/setup { password } -> one-time first-run password creation.
//
// The Travel Desk password is chosen on the site itself, so nobody handling
// deployment ever sees it. Stores a PBKDF2-SHA256 (100k iterations) hash in
// KV under auth:salt / auth:hash; login.js verifies against these. Once
// auth:hash exists this endpoint refuses (already_set) — deleting that KV key
// is the reset path.
//
// First-run claim window: between the first deploy and the first visit,
// anyone who finds the URL can claim the passphrase. Two ways to close it:
//   1. Set SETUP_TOKEN (a Pages secret). Setup then requires it — open
//      /login?setup=<token> to choose the passphrase.
//   2. Seed auth:salt / auth:hash with wrangler before the first deploy, so
//      setup is never open at all.
// Env: TD (KV namespace), optional SETUP_TOKEN. Passwords are never logged.

import { json, configError, deriveHash, randomSaltHex, timingSafeEqual } from "./_auth.js";

export async function onRequest(context) {
  const { request, env } = context;
  const bad = configError(env);
  if (bad) return bad;

  if (request.method === "GET") {
    const existing = await env.TD.get("auth:hash");
    return json({ needs_setup: existing == null, token_required: !!env.SETUP_TOKEN });
  }

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  if ((await env.TD.get("auth:hash")) != null) {
    return json({ error: "already_set" }, 403);
  }

  if (env.SETUP_TOKEN) {
    const presented = request.headers.get("x-setup-token") || "";
    if (!timingSafeEqual(presented, env.SETUP_TOKEN)) {
      return json({ error: "setup_token_required" }, 403);
    }
  }

  let password = "";
  try {
    const body = await request.json();
    if (body && typeof body.password === "string") password = body.password;
  } catch (e) {
    // fall through -> 400
  }
  if (password.length < 8) {
    return json({ error: "password_too_short" }, 400);
  }

  const salt = randomSaltHex();
  const hash = await deriveHash(password, salt);
  // Salt first: login treats a missing hash as "setup required", so a crash
  // between the two writes leaves setup open rather than a half-set login.
  await env.TD.put("auth:salt", salt);
  await env.TD.put("auth:hash", hash);
  return json({ ok: true });
}
