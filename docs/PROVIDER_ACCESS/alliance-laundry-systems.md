# Provider Access Decision Record — Alliance Laundry Systems

- Status: **UNKNOWN — blocked pending account-owner input** (see
  classification and required information below)
- Date: 2026-07-23
- Decision owner: business account owner (pending)
- Prepared by: engineering (Milestone 8 Task 3)

> Method note: this record was prepared WITHOUT any live request to any
> Alliance system and without automation code, per the Task 3 instruction.
> Every item below is marked **[verified]** (established in this project's
> context) or **[unverified]** (requires account-owner or provider
> confirmation). Nothing unverified may be treated as permission.

## 1. Provider and portal name

- Provider: Alliance Laundry Systems (manufacturer; brands include Speed
  Queen, UniMac, Huebsch, IPSO). **[verified — project context]**
- Exact portal(s) the business account can access (e.g. a partner/service
  portal, technical-documentation site, parts system), their URLs, and
  which of them hold the manuals/parts/wiring content LaundryConnect
  needs: **[unverified — account owner must enumerate]**

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
  over any portal automation.

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

- Portal authentication mechanism (form login, SSO, MFA, session
  lifetime): **[unverified]**
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

**UNKNOWN.**

The items that determine legality and compliance of automated access
(sections 1 sub-item, 2–8, 10–11) cannot be verified from the repository,
the project brief, or any source available to engineering without either
the account owner's information or a reviewed copy of the portal terms.
Classifying anything other than UNKNOWN would be fabrication.

Per Task 3 instructions: **work stops here.** No connector skeleton,
configuration model, fixtures, or tests are created while the position is
UNKNOWN.

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
