# ADR 0012: Alliance connector — human-in-the-loop authentication

- Status: accepted
- Date: 2026-07-23

## Context

The first real provider connector (Alliance Laundry Systems) must exist as
a proof of architecture WITHOUT any automated agent ever handling real
credentials, and WITHOUT making a live request while the access decision
record is UNKNOWN.

## Decisions

1. **Three modes, fixture is the default.**
   - `fixture` (default, CI, dev): serves sanitised recorded/synthetic
     fixtures via `FixtureTransport`; no network; passes `ConnectorContract`.
     Results are labelled `DataOrigin.FIXTURE` — never `live` — so fixture
     data can never be presented as real provider data.
   - `session`: loads a human-bootstrapped browser storage-state file from
     `ALLIANCE_SESSION_PATH`, validates it, and raises typed
     `ReauthenticationRequired` (missing/invalid/expired). The registry maps
     that to a `reauthentication_required` per-provider outcome.
   - `credential`: NOT implemented — the mode refuses because permission for
     automated credential login has not been established (the provider terms
     are UNKNOWN and unreviewed). No credentials are ever read.
2. **Live access is double-gated.** Even in session mode with a valid
   session, a live fetch requires BOTH `alliance_access_approved=true`
   (mirrors the access decision record) AND not running under CI. Both are
   checked before any network I/O. The record is UNKNOWN → the flag is
   false → no live request is possible. The reviewed live transport is also
   deliberately unimplemented, so an approved flag alone still cannot
   improvise a request.
3. **Manual session bootstrap is operator-only.** `python -m
   app.providers.alliance.bootstrap` opens a VISIBLE browser; the human logs
   in and completes MFA/CAPTCHA; storage state is saved outside the repo
   with `0600` perms. It never prints cookies/tokens/credentials/HTML/state
   and never bypasses bot protection. Playwright is an optional `bootstrap`
   dependency, absent from the runtime and CI.
4. **Sessions never live in the repo.** The loader and the bootstrap refuse
   any path inside the working tree; `.gitignore` also excludes
   `*-session.json` and `.laundryconnect/`. Session contents are never held
   as connector attributes, returned, or logged — only a cookie count.
5. **Fixtures are sanitised and human-reviewed.** `sanitise_capture` strips
   Cookie/Set-Cookie/Authorization/tokens/usernames/account data/signed-URL
   params/session ids. Committed fixtures must carry `_meta.reviewed_by`
   (enforced by a test), and the only committed fixture today is explicitly
   synthetic.

## Consequences

- When the access record is re-classified to approved/conditionally
  approved, work resumes at exactly one place: implement and review the live
  `SessionTransport`, set the approval flag per environment, and record
  real sanitised fixtures — no other wiring changes.
- CI and every automated agent stay in fixture mode permanently; live access
  is a deliberate, human, out-of-CI action.

## Addendum (2026-07-24) — CONDITIONALLY APPROVED; live SessionTransport

The access record is now **CONDITIONALLY APPROVED — authorised service
partner** (owner-asserted authorisation, not written provider permission).
The live transport is implemented WITHOUT any live request having been made:

1. **`SessionTransport`** performs authenticated GETs using the bootstrapped
   session, enforcing the safeguards per request: host allowlist (only
   `portal.alliancels.net`), conservative rate limiting (default 12/min =
   one request per 5s), a 20s timeout with ≤2 retries on transient
   failures/5xx only, and session-expiry detection (401/403 or a login
   redirect → `ReauthenticationRequired`, never a bypass). Fetches only the
   requested query — no crawling. Mechanics are unit-tested against a mocked
   client; the search endpoint path and response→record mapping are pinned
   during the operator smoke test against a captured, sanitised fixture.
2. **Kill switch** (`alliance_live_kill_switch`) refuses live access
   immediately regardless of approval; the gate order is kill-switch → CI →
   approved.
3. **The master gate stays off by default.** `alliance_access_approved` is
   false; a live request needs a deliberate per-environment opt-in AND a
   valid bootstrapped session AND not-CI AND the pre-first-request review
   approved by the business owner. No live request has occurred.
4. Live results are labelled `DataOrigin.LIVE` and retain provider
   attribution (source reference + portal URL). httpx moved to a runtime
   dependency for the client (constructed lazily only on the gated path).

Still deferred to post-approval-of-the-review: the first live request, the
operator smoke test that pins the endpoint/parsing, and a removable-cache
purge for Alliance-origin data.

## Addendum (2026-07-24) — pre-first-request hardening

Closing the gaps surfaced by the reviewer's six-item checklist, all tested
against a mocked client (no live request):

- **Host allowlist:** only `portal.alliancels.net`; redirects are never
  followed (`follow_redirects=False`); off-host URLs raise `HostNotAllowed`
  before any call, on both search and document download.
- **Request limits:** single-flight concurrency (`max_concurrency=1` via a
  semaphore); ~12 req/min (1 per 5s). **401**/login-redirect →
  `ReauthenticationRequired`; **403** → `AccessForbidden`, a hard stop, not
  retried and not looped as reauth (possible block → human review); **429**
  → honours `Retry-After` (capped at 60s) and retries ≤2, else
  `LiveFetchError`; **5xx** → backoff retry ≤2; other 4xx → `LiveFetchError`.
- **Session validation:** missing/invalid/expired detected pre-request; a
  login redirect is treated as auth failure, never followed.
- **Download limits:** search response cap (5 MB) and document cap (100 MB),
  enforced by Content-Length pre-check and actual-bytes check; duration
  bounded by the client's 60s download timeout (search additionally bounded
  by the registry's per-provider timeout). `fetch_document` downloads a
  single document only.
- **Operator smoke test** (`python -m app.providers.alliance.smoke_test`):
  one model search + one optional document retrieval; refuses under CI /
  unless approved / without a valid session; prints only non-sensitive
  summaries. No indexing, crawling, or discovery.
- **Fixture capture:** `sanitise_capture` strips cookies/tokens/usernames/
  account data/signed-URL params/session ids; committed fixtures require
  `_meta.reviewed_by` (test-enforced).

Unchanged: `alliance_access_approved` stays false by default; no live
request has been made.

## Addendum (2026-07-24, #2) — URL policy and redirect hardening

- **Full URL policy before opening a stream** (`_check_url`): scheme must be
  exactly `https`; hostname must exactly match the allowlist; no userinfo
  (username/password); an explicit port, if present, must be 443. Violations
  raise a terminal `InvalidProviderURL` / `HostNotAllowed` (never retried),
  with no full URL in the message. Verified rejected — without opening a
  stream — for `http://`, `user:password@…`, `…:444`, and off-allowlist
  hosts; plain HTTPS and explicit `:443` accepted.
- **Every non-login 3xx is terminal** (`UnexpectedRedirect`): the body is
  not read, the redirect is not followed, and it is not retried. Login
  redirects still map to `ReauthenticationRequired`. Off-host redirects are
  called out as refused. Diagnostics include only a sanitised destination
  host/path — never query parameters, fragments, or userinfo. Verified:
  redirect bodies are never consumed and exactly one request is attempted.

Streaming size caps are genuine (incremental read, early abort, fresh stream
per retry); Retry-After parsing is clamped and supports the HTTP-date form.
Still: no live request; `alliance_access_approved` false by default.
