// Auth gate tests — run: node tests/auth.test.mjs   (Node 20+; no deps)
const root = new URL('..', import.meta.url).pathname.replace(/\/$/, '');
const auth = await import(root + '/functions/api/_auth.js');
const login = await import(root + '/functions/api/login.js');
const setup = await import(root + '/functions/api/setup.js');
const kv = new Map();
const TD = { get: async (k) => (kv.has(k) ? kv.get(k) : null), put: async (k, v) => { kv.set(k, v); }, delete: async (k) => kv.delete(k) };
const env = { TD, COOKIE_SECRET: 'x'.repeat(48) };
const req = (path, method = 'GET', body, headers = {}) => new Request('https://td.example' + path, { method, body: body && JSON.stringify(body), headers: { 'content-type': 'application/json', ...headers } });
const check = (name, ok) => { console.log((ok ? 'PASS ' : 'FAIL ') + name); if (!ok) process.exitCode = 1; };

check('weak secret refused', (await login.onRequest({ request: req('/api/login', 'POST', { password: 'x' }), env: { TD, COOKIE_SECRET: 'short' } })).status === 500);
check('missing secret not authed', !(await auth.isAuthed(req('/'), { TD })));
let r = await setup.onRequest({ request: req('/api/setup', 'POST', { password: 'correct horse battery' }), env: { ...env, SETUP_TOKEN: 'tok' } });
check('setup without token refused', r.status === 403);
r = await setup.onRequest({ request: req('/api/setup', 'POST', { password: 'correct horse battery' }, { 'x-setup-token': 'tok' }), env: { ...env, SETUP_TOKEN: 'tok' } });
check('setup with token ok', r.status === 200);
r = await setup.onRequest({ request: req('/api/setup', 'POST', { password: 'another password' }), env });
check('setup locked after first set', r.status === 403);
r = await login.onRequest({ request: req('/api/login', 'POST', { password: 'wrong wrong wrong' }), env });
check('wrong password 401', r.status === 401);
r = await login.onRequest({ request: req('/api/login', 'POST', { password: 'correct horse battery' }), env });
check('right password 200', r.status === 200);
const cookie = r.headers.get('set-cookie');
check('cookie flags', /HttpOnly/.test(cookie) && /Secure/.test(cookie) && /SameSite=Lax/.test(cookie));
const tok = cookie.match(/td_auth=([^;]+)/)[1];
const withCookie = (t) => req('/', 'GET', undefined, { cookie: 'td_auth=' + t });
check('valid token authed', await auth.isAuthed(withCookie(tok), env));
r = await login.onRequest({ request: req('/api/login', 'POST', { password: 'correct horse battery' }), env });
const tok2 = r.headers.get('set-cookie').match(/td_auth=([^;]+)/)[1];
check('tokens are per-session', tok !== tok2);
const [v, exp, nonce, sig] = tok.split('.');
check('tampered exp rejected', !(await auth.isAuthed(withCookie([v, String(Number(exp) + 999999), nonce, sig].join('.')), env)));
check('wrong secret rejected', !(await auth.isAuthed(withCookie(tok), { ...env, COOKIE_SECRET: 'y'.repeat(48) })));
// legacy v1 constant token
const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(env.COOKIE_SECRET), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
const v1 = Buffer.from(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode('traveldesk-session-v1'))).toString('hex');
check('legacy v1 token rejected', !(await auth.isAuthed(withCookie(v1), env)));
kv.set('auth:hash', 'f'.repeat(64));
check('passphrase change revokes', !(await auth.isAuthed(withCookie(tok), env)));
// expired
kv.delete('auth:hash');
check('cleared passphrase revokes', !(await auth.isAuthed(withCookie(tok2), env)));
check('malformed cookie', !(await auth.isAuthed(withCookie('%E0%A4%A'), env)));
