// GET /api/setup -> { needs_setup: true|false }
// POST /api/setup { password } -> one-time first-run password creation.
//
// The Travel Desk password is chosen on the site itself, so nobody handling
// deployment ever sees it. Stores a PBKDF2-SHA256 (100k iterations) hash in
// KV under auth:salt / auth:hash; login.js verifies against these.
// Env: TD (KV namespace). Passwords are never logged.

const ITERATIONS = 100000;

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

function randomSaltHex() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

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

export async function onRequest(context) {
  const { request, env } = context;
  if (!env.TD) return json({ error: "not_configured" }, 500);

  if (request.method === "GET") {
    const existing = await env.TD.get("auth:hash");
    return json({ needs_setup: existing == null });
  }

  if (request.method !== "POST") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  if ((await env.TD.get("auth:hash")) != null) {
    return json({ error: "already_set" }, 403);
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
  await env.TD.put("auth:salt", salt);
  await env.TD.put("auth:hash", hash);
  return json({ ok: true });
}
