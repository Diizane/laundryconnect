# Provider Access Decision Record — Alliance Laundry Systems

- Status: **CONDITIONALLY APPROVED — Authorised service partner**
  (reclassified 2026-07-24 on verified business-owner information; see the
  Classification section for the basis and mandatory safeguards)
- Date: 2026-07-23 (created); 2026-07-24 (reclassified)
- Decision owner: business account owner
- Prepared by: engineering (Milestone 8)

> **2026-07-24 update — reclassified to CONDITIONALLY APPROVED.** The
> business owner supplied verified information about the account and
> partnership (recorded below). Classification and safeguards are in the
> Classification section. Live access is enabled only after the pre-first-
> request review is approved; no live request has been made.

> Method note: this record was prepared WITHOUT logging in and WITHOUT
> automation code. Only unauthenticated, public pages were viewed
> (login page, robots.txt, sitemap index) — no credentials were entered
> and no authenticated request was made. Every item below is marked
> **[verified]** (established in this project's context or by that public
> reconnaissance) or **[unverified]** (requires account-owner or provider
> confirmation). Nothing unverified may be treated as permission.

## 0. Public reconnaissance findings (no login, 2026-07-23)

Established by viewing only unauthenticated pages of
`portal.alliancels.net`:

- The portal is a **Salesforce Experience Cloud (Communities) site**
  — confirmed by the `/s/` path, the Salesforce "Sorry to interrupt / CSS
  Error" dialog, and a stock `sfdc communities` `robots.txt`.
  **[verified]** Implication worth pursuing: Salesforce-backed sites often
  expose an official API (Salesforce Experience Cloud / Connect REST /
  CMS Delivery API) — an official channel may exist and should be asked
  about (section 3) before any portal automation is considered.
- **The content is login-gated.** The landing page is a bare
  username/password gate (plus an "ALS EMPLOYEE LOGIN" button); the
  manuals/parts content requires authentication. **[verified]**
- **No public terms-of-use, privacy, or acceptable-use link is present on
  the login page.** The governing terms sit behind the login (likely
  presented at account provisioning or inside the authenticated area) and
  therefore have NOT been reviewed. **[verified — absence on public page]**
- `robots.txt` is the permissive Salesforce default (`Allow: /`). This
  governs **public-page crawling by search engines only** and is **not**
  permission for authenticated, programmatic access — which is what a
  connector would perform. **[verified]**
- The public sitemap index exposes managed content (views, news, CMS
  documents, CMS images). Whether any *needed technical documentation* is
  public versus behind the login is **[unverified]**; the service content
  appears authentication-gated.

None of this changes the classification: the terms that actually govern
automated access are behind the login and remain unreviewed.

## 1. Provider and portal name

- Provider: Alliance Laundry Systems (manufacturer; brands include Speed
  Queen, UniMac, Huebsch, IPSO). **[verified — project context]**
- Portal: `portal.alliancels.net` — a Salesforce Experience Cloud service
  portal (login-gated). **[verified — public reconnaissance]**
- Which portal area(s)/objects hold the manuals/parts/wiring content the
  app needs, behind the login: **[unverified — account owner must
  enumerate]**

## 2. Account ownership

- The business operates one shared Alliance account intended for internal
  technician use (per project brief). **[verified — project brief]**
- Account holder entity, account tier/role (distributor, service partner,
  end customer), who administers it, and whether its agreement permits use
  by an internal tool acting on technicians' behalf:
  **[unverified]**

## 3. Official API availability

- Whether Alliance offers any official/partner API for documentation,
  parts, or model data, and whether this account qualifies for it:
  **[unverified]**. If an official API exists, it is strongly preferred
  over any portal automation. The portal being Salesforce-based makes an
  official API surface plausible (Salesforce Connect REST / CMS Delivery
  API) — worth asking Alliance directly.

## 4. Terms governing automated access

- The portal's terms of use / acceptable-use provisions on automated
  access, systematic downloading, or programmatic queries:
  **[unverified — terms text must be obtained and reviewed]**
- Project rule regardless of outcome: no unauthorised scraping and no
  access-control bypasses (docs/SECURITY.md, PRODUCT_VISION guardrails).
  **[verified — internal policy]**

## 5. Scraping / browser automation permission

- Whether authenticated scraping or browser automation is permitted,
  tolerated, or prohibited: **[unverified]**. Not assumed permitted.

## 6. Internal indexing and caching permissions

- Whether page-level text extraction, internal full-text indexing, and
  serving excerpts/snippets to the business's own technicians is
  permitted: **[unverified]**
- LaundryConnect design if permitted: documents remain attributed to the
  provider with source references; origin labelled `live`; official
  documents remain the source of truth. **[verified — architecture]**

## 7. Document retention restrictions

- Whether local/object-storage copies of PDFs may be retained, for how
  long, and whether retention must end with the account relationship:
  **[unverified]**

## 8. Expected rate limits

- Published or contractual rate limits, and acceptable request cadence:
  **[unverified]**. Connector design will enforce conservative client-side
  rate limiting regardless (roadmap checklist). **[verified — design]**

## 9. Credential and session handling

- Portal authentication mechanism: a **Salesforce Experience Cloud form
  login** (username/password on the public page; a separate "ALS EMPLOYEE
  LOGIN" path exists for staff). Whether MFA is enforced for this account
  and the typical session lifetime are **[unverified]**. A credential was
  pasted into chat during this task and must be treated as compromised and
  rotated (SECURITY.md); it was not stored or used.
- LaundryConnect handling regardless: credentials backend-only via
  environment/secret manager; never in the mobile app, repository, logs,
  or CI; sessions refreshed server-side; any credential ever exposed is
  treated as compromised. **[verified — SECURITY.md]**

## 10. Allowed technician audience

- Business intent: internal technicians of the account-holder company
  only; no public access, no resale of content. **[verified — brief]**
- Whether the account's agreement matches that intent (named users vs
  company-wide use): **[unverified]**

## 11. Unresolved legal or commercial questions

1. Does the account agreement or portal ToS permit programmatic access by
   an internal tool? Under what conditions?
2. Is there an official API or bulk-documentation channel we should use
   instead — and can the business request access to it?
3. Are indexing, excerpt display, and PDF retention permitted for internal
   use?
4. Does automated access risk the commercial relationship (account
   suspension), and does the business accept that risk profile?
5. Is written permission from an Alliance representative obtainable? (The
   strongest position; recommended.)

## Verified business-owner information (2026-07-24)

Supplied by the business account owner; the basis for the reclassification:

- The business is an **authorised Alliance Laundry Systems service
  partner**; its technicians repair Alliance equipment under that
  partnership.
- The business holds a **legitimate Alliance service portal account**
  provided for that work, with **authorised access** to the manuals, parts
  information, wiring diagrams, and machine documentation required for
  repairs.
- **No official API, SDK, or documented integration** exists for this
  account — the service portal is the only available interface.
- **LaundryConnect is an internal tool only**: not customer-facing, used
  solely by the business's own authorised technicians, only to improve
  search and retrieval of information they are already authorised to access.
- The business does **not** redistribute Alliance documentation publicly or
  sell access to it.
- The business is **not aware of any published restriction** prohibiting
  this internal use, but has **no written confirmation from Alliance**
  specifically permitting browser automation or programmatic access.

## Classification

**CONDITIONALLY APPROVED — Authorised service partner.**

Basis: the business owner's knowledge of their own account and Alliance
service partnership (above), **not** explicit written provider permission.
The business accesses only material it is already authorised to access, for
internal use by its own technicians, via the only interface available to
the account (the portal). This is a conditional approval resting on
owner-asserted authorisation; it is not a legal opinion and not provider
sign-off.

### Mandatory safeguards (retained; conditions of this approval)

1. Internal authorised technicians only.
2. Backend-only authentication; no credentials in the mobile app, repo,
   API, logs, or CI.
3. **Manual browser login only** (operator bootstrap); **no automated
   username/password login**.
4. No MFA/CAPTCHA/bot-protection bypass.
5. Session files stored **outside the repository**, restrictive permissions.
6. **CI permanently fixture-only** — CI can never enter live mode.
7. Conservative client-side request rate limiting.
8. Fetch only the specifically requested models/documents (no crawling or
   bulk harvesting).
9. Preserve provider attribution on every record (source reference + URL).
10. Cache is removable (Alliance-origin cached data can be purged).
11. Configuration kill switch to disable Alliance live mode immediately.
12. **Immediately disable live mode** if Alliance objects or publishes
    contrary terms — and re-open this record.

### What proceeds now, and what still gates the first live request

Permitted now: implementing the live `SessionTransport` (auth, session
handling, rate limiting, host allowlist, timeout/retry) with tests that use
mocked HTTP — no live request.

Still gated: the **first live request** requires (a) the operator to enable
`alliance_access_approved` per environment, (b) a valid manually-
bootstrapped session, (c) not running under CI, and (d) an engineering
pre-first-request review (proposed rate, host allowlist, timeout/retry,
session-expiry handling, sanitisation, operator-only smoke test) approved by
the business owner. `alliance_access_approved` remains **false by default**.

## Information required from the account owner (exact list)

1. Portal name(s) and URL(s) the account can access, and which contain the
   needed documentation.
2. Account holder entity, tier/role, and administrator.
3. A copy (or screenshots/export) of the portal's terms of use and any
   signed account agreement — for the automated-access review.
4. Whether Alliance offers an official API/partner data channel to this
   account, or a contact who can answer that.
5. Any known statements from Alliance about automation, indexing, caching,
   or document retention.
6. Session/authentication details needed for design only (login mechanism,
   MFA yes/no, typical session lifetime) — NOT the credentials themselves.
7. The business's risk decision if terms are silent on automation, and
   whether to seek written permission from an Alliance representative
   (recommended).

## Re-classification criteria

- **approved** — written provider permission or terms that clearly permit
  the intended access, indexing, and retention.
- **conditionally approved** — terms silent or partially permissive AND the
  account owner documents an explicit business decision to proceed within
  stated conditions (e.g. metadata-only indexing, no PDF retention,
  conservative rate limits). Conditions must be listed in this record.
- **blocked** — terms prohibit the intended access and no permission is
  obtainable; connector work for this provider stops and an alternative
  provider or a manual/company-upload ingestion path is chosen instead.

This record must be updated and re-classified before any connector code,
fixture recording, or live access is attempted.
