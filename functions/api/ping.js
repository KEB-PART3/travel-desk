// Client version telemetry for the Travel Desk PWA.
// The app POSTs its build tag on load so deploys can be verified from the
// server side (which build is each device actually running?). Authenticated
// only — the middleware rejects unauthenticated /api/* with 401.

import { isAuthed, json } from "./_auth.js";

export async function onRequestPost({ request, env }) {
  if (!(await isAuthed(request, env))) {
    return json({ error: "unauthorized" }, 401);
  }
  let body = {};
  try {
    body = await request.json();
  } catch (e) {
    body = {};
  }
  const client = String(body.client || "unknown").slice(0, 48);
  const build = String(body.build || "unknown").slice(0, 64);
  const key =
    "ping:" + Date.now() + ":" + Math.random().toString(36).slice(2, 10);
  try {
    await env.TD.put(
      key,
      JSON.stringify({
        client,
        build,
        ua: request.headers.get("user-agent") || "",
        ts: Date.now(),
      }),
      { expirationTtl: 604800 }
    );
  } catch (e) {
    return json({ error: "kv_unavailable" }, 500);
  }
  return json({ ok: true });
}
