// Password gate for the whole Travel Desk site.
// Public: /login, /login.html, /api/login, /api/setup, plus the PWA install
// infrastructure (manifest, service worker, icons) — browsers fetch those
// without credentials when deciding installability, and they carry no trip
// data. Editorial images under /img/ are public for the same reason:
// no trip data, and the service worker precaches them without credentials.
// Everything else requires
// the td_auth cookie (HMAC of COOKIE_SECRET, 30-day session). Unauthenticated
// page/asset requests redirect to /login; /api/* gets a 401 JSON so API
// clients never follow a redirect into HTML.
//
// Note: Pages canonicalizes /login.html -> /login with a 308, so /login must
// be public and the redirect target — never /login.html (that loops).

import { isAuthed, json } from "./api/_auth.js";

const PUBLIC_PATHS = new Set(["/login", "/login.html", "/api/login", "/api/setup"]);

// PWA install assets: no trip data, must be fetchable without the auth cookie
// or the browser can't see the app as installable.
const PUBLIC_PWA_PATHS = new Set([
  "/manifest.webmanifest",
  "/sw.js",
  "/icon-192.png",
  "/icon-512.png",
  "/icon-maskable-512.png",
  "/apple-touch-icon.png",
]);

// Editorial images (event logos/photos): no trip data, and the service worker
// precaches them at install time without the auth cookie — gating them would
// poison the cache with the login page under image URLs.
const PUBLIC_PREFIXES = ["/img/"];

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  if (PUBLIC_PATHS.has(url.pathname) || PUBLIC_PWA_PATHS.has(url.pathname) ||
     PUBLIC_PREFIXES.some(p => url.pathname.startsWith(p))) {
    return context.next();
  }

  if (await isAuthed(request, env)) {
    return context.next();
  }

  if (url.pathname.startsWith("/api/")) {
    return json({ error: "unauthorized" }, 401);
  }
  return Response.redirect(new URL("/login", url.origin).toString(), 302);
}
