# Provider Access Decision Record — Alliance Laundry Systems

- Status: **UNKNOWN — blocked pending account-owner input** (see
  classification and required information below)
- Date: 2026-07-23
- Decision owner: business account owner (pending)
- Prepared by: engineering (Milestone 8 Task 3)

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

## Classification

**UNKNOWN** (unchanged after public reconnaissance).

Public reconnaissance identified the portal (Salesforce Experience Cloud,
login-gated) and the login mechanism, and confirmed that no terms are
published on the public pages. But the items that determine legality and
compliance of automated access — the authenticated portal's terms of use,
the account agreement/tier, official API availability, and
indexing/caching/retention permissions — sit behind the login and cannot
be verified without the account owner's information or a reviewed copy of
the terms. `robots.txt` permissiveness applies to public-page crawling
only and is not permission for authenticated automation. Classifying
anything other than UNKNOWN would be fabrication.

### What is permitted while UNKNOWN, and what is blocked

A **fixture-only connector architecture is permitted** while the position is
UNKNOWN, because it performs no live access: it serves synthetic/sanitised
fixtures, makes no network request, and labels its data `fixture` (never
`live`). The connector skeleton, configuration model, fixture data,
session-lifecycle handling, and their tests exist on this basis (see
ADR 0012 and `app/providers/alliance/`).

**Blocked until the record is approved or conditionally approved:**

- implementing the live `SessionTransport` (any authenticated fetch);
- capturing authenticated fixtures from the live portal;
- any live request to any Alliance system;
- enabling credential-based automated login.

The connector enforces this: live paths are gated on
`alliance_access_approved` (false while UNKNOWN) AND not-CI, and the live
transport is intentionally unimplemented.

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
