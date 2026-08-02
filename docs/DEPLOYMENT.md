# Deployment — staging/production backend

Purpose: run the LaundryConnect backend somewhere a technician's phone can
reach over HTTPS from anywhere (cellular included), without requiring any
developer machine to be online.

Security posture this document assumes:

- The backend holds an authenticated Alliance session. It must therefore
  **never** be exposed without API-key authentication — the app refuses to
  start in production without `API_KEYS` (min 24 chars each).
- Nothing provider-related ever reaches the phone: the app talks only to
  this backend, with opaque encrypted document tokens.
- The Alliance session file stays operator-bootstrapped and human-supplied;
  no automated login, ever.

## 1. Server

Any small VM works (1 vCPU / 1–2 GB is ample): Hetzner (~€4/mo),
DigitalOcean, Vultr, Lightsail. Requirements: Docker + Docker Compose, a
hostname resolving to it, and ports 80/443 open.

Recommended image: Ubuntu 24.04 LTS. After first login:

```
apt update && apt install -y docker.io docker-compose-v2 git
```

### Hostname without buying a domain

A VPS has no hostname of its own, and Let's Encrypt will not issue a
certificate for a bare IP address — but two free services give a real DNS
name that works with automatic HTTPS:

- **DuckDNS** (recommended — a memorable name): register free at
  duckdns.org, create e.g. `laundryconnect`, point it at the server's IP.
  Your domain becomes `laundryconnect.duckdns.org`.
- **sslip.io** (zero signup): the hostname `<server-ip>.sslip.io` resolves
  to that IP automatically — e.g. `203.0.113.10.sslip.io`. Nothing to
  register; slightly uglier.

Either works as `API_DOMAIN` below and Caddy will obtain a valid
certificate for it. Swap in a real domain later by changing `API_DOMAIN`
and rebuilding the app with the new URL.

## 2. Secrets (never in the repository)

Clone the repository to the server (`git clone <repo> /opt/laundryconnect/app`),
then create `/opt/laundryconnect/.env`, `chmod 600`:

```
API_DOMAIN=laundryconnect.duckdns.org        # or <ip>.sslip.io
API_KEYS=<paste a generated key>            # add more, comma-separated
DOCUMENT_TOKEN_SECRET=<paste a generated secret>
ENABLED_PROVIDERS=mock,alliance
ALLIANCE_MODE=session
ALLIANCE_ACCESS_APPROVED=true
ALLIANCE_SESSION_HOST_PATH=/opt/laundryconnect/alliance-session.json
```

Generate each value from a cryptographically secure source, e.g.:

```
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use a different value for `API_KEYS` and `DOCUMENT_TOKEN_SECRET`. Rotating
`DOCUMENT_TOKEN_SECRET` invalidates outstanding document tokens (clients
just rediscover); rotating an API key requires rebuilding the app with the
new key.

## 3. Alliance session

The session is still bootstrapped by a human on a workstation with a
browser — the server never logs in:

```
# on the operator workstation
cd services/api
ALLIANCE_SESSION_PATH=~/.laundryconnect/alliance-session.json \
  uv run python -m app.providers.alliance.bootstrap

# copy it to the server (never into the repo or the image)
scp ~/.laundryconnect/alliance-session.json \
    server:/opt/laundryconnect/alliance-session.json
ssh server 'chmod 600 /opt/laundryconnect/alliance-session.json'
```

Portal sessions expire in the order of hours-to-days. When they do, the API
returns its normal `reauthentication_required` state and the app shows the
"needs operator sign-in" message; repeat the two commands above to restore
service. (Automating this refresh is deliberately out of scope: it would
mean automated login.)

## 4. Run

```
cd /opt/laundryconnect/app
docker compose --env-file /opt/laundryconnect/.env \
  -f infrastructure/docker/docker-compose.prod.yml up -d --build
```

Caddy obtains and renews the TLS certificate automatically. Verify:

```
curl https://laundryconnect.duckdns.org/api/v1/health/live          # 200, no key needed
curl -X POST https://laundryconnect.duckdns.org/api/v1/search \
     -H "Content-Type: application/json" \
     -H "X-API-Key: $API_KEY" -d '{"query":"SC60"}'      # 200
curl -X POST https://laundryconnect.duckdns.org/api/v1/search \
     -H "Content-Type: application/json" -d '{"query":"SC60"}'   # 401
```

The last check is the important one: **an unauthenticated request must be
rejected.**

## 5. Mobile build against staging

```
cd apps/mobile
flutter build apk --release \
  --dart-define=API_BASE_URL=https://laundryconnect.duckdns.org \
  --dart-define=API_KEY=<the api key>
```

Release builds do not permit cleartext HTTP (verified on the built APK), so
the backend must be HTTPS — which the Caddy setup above provides.

Note on the API key in the app: a key embedded in an APK is extractable by
anyone holding the file, so treat it as an internal-distribution control,
not a user credential. It stops opportunistic access to the public
endpoint; real per-technician accounts are the follow-up milestone. Keep
the APK internal, and rotate the key if a device is lost.

## 6. Operating notes

- Logs: `docker compose -f … logs -f api` (JSON, request-id correlated;
  never contains session material, keys, or provider payloads).
- Health: `/api/v1/health/live` (process), `/api/v1/health/ready`
  (dependencies) — both open for uptime checks.
- Kill switch: set `ALLIANCE_LIVE_KILL_SWITCH=true` and restart to stop all
  live provider access immediately while keeping the service up.
- Backups: nothing provider-related is persisted; only the database (when
  configured) holds catalog/sample data.
