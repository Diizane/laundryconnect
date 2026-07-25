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
   - `credential`: NOT implemented — provider terms do not permit automated
     credential login; the mode refuses. No credentials are ever read.
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
