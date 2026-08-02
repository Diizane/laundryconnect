# Milestone 10 — First Android internal test build

Status: implemented — pending review. Flutter/mobile + test-environment
configuration only; the Phase 3 backend API, provider transport, parsers,
and token handling are untouched.

## What the build does

The complete validated technician workflow, end to end on a phone:

```
Search (model or serial)
  → select Alliance result            (results carry catalog metadata)
  → Documents button (PDF icon)       (only on results with a document ref)
  → document list                     (title, type, part number, comment,
                                       languages, category, origin badge;
                                       non-downloadable items disabled and
                                       labelled)
  → tap a document                    (backend proxy download, opaque token)
  → read the PDF                      (in-app viewer, rendered from memory)
```

Security properties preserved on the client:

- The app only ever calls the LaundryConnect backend (`API_BASE_URL`); it
  never sees, stores, or constructs an Alliance URL, path, or identifier
  beyond the catalog metadata the search API already returns.
- Documents are referenced solely by the backend's opaque encrypted token.
- PDF bytes are held in memory and rendered in-app (`pdfx`); nothing is
  written to disk — no cache, no temporary files, no persistence.
- No credentials, session material, or token secrets exist in the app or
  the APK (verified — see build checks).

## Failure handling (technician-facing)

- Loading, empty ("No documents listed for this machine."), and error
  states with Retry.
- `reauthentication_required` → "The Alliance session needs to be signed
  in again by an operator. Try again once that is done." (lock icon; no
  token/session mechanics exposed).
- Expired document token (backend 404): the app silently rediscovers once
  (minting fresh tokens) and retries the download; only if the document is
  genuinely gone does the technician see "That document is no longer
  available."
- Provider failures (502) and invalid content: safe backend-provided
  message in a snackbar; list stays usable.
- Wrong content type at download: rejected client-side too ("Unexpected
  server response.") — a non-PDF body is never handed to the viewer.

## Configuration

- App label: **LaundryConnect** (`android:label`).
- Application id: `au.com.laundryconnect.laundryconnect` (unchanged).
- Launcher icon: default Flutter placeholder (deliberate; branding is a
  later milestone).
- Backend base URL per environment via `--dart-define`:
  - emulator default: `http://10.0.2.2:8000`
  - physical device on LAN: `--dart-define=API_BASE_URL=http://<host-ip>:8000`

## Build

```
cd apps/mobile
flutter build apk --debug \
  --dart-define=API_BASE_URL=http://<backend-host>:8000
```

Output: `apps/mobile/build/app/outputs/flutter-apk/app-debug.apk`

Pre-build verification (all required to pass): `flutter analyze`,
`flutter test` (46 tests), backend `pytest` (368) + `ruff`, and an APK
content scan confirming no token secret, session material, provider
document, or Alliance session URL is bundled (only the configured backend
base URL and public portal hostnames appearing in sample/search data).

## Install (internal testers)

1. Ensure the backend is reachable from the phone (same network) and
   running with the desired provider configuration. Live Alliance requires
   the operator session bootstrap + `ALLIANCE_ACCESS_APPROVED=true` on the
   backend; the app needs no configuration beyond the base URL baked in at
   build time.
2. Copy `app-debug.apk` to the device (USB, drive link, or
   `adb install app-debug.apk`).
3. Android will warn about installing outside the Play Store — allow
   "install unknown apps" for the chosen transfer app. (Debug build,
   internal testing only; not Play-signed.)

## Field-test checklist

- [ ] Search a model (e.g. BA120N) — results appear with origin badges.
- [ ] Search a serial number — the exact machine's manual generation is
      resolved (different serials of the same family may map to different
      manuals; verify the documents differ accordingly).
- [ ] Documents button appears on Alliance model results; opens the list.
- [ ] Document metadata is sufficient to choose (type, part no, language).
- [ ] Non-downloadable documents are visibly disabled, not tappable.
- [ ] Tapping a manual downloads and opens it in-app; pinch-zoom works;
      diagrams are legible at zoom.
- [ ] Airplane mode: search and document actions show the connectivity
      message with Retry, no crash.
- [ ] With the backend session expired: the operator-sign-in message
      appears (no token/session jargon).
- [ ] Leave the document list open >15 minutes, then tap a document: it
      still opens (silent rediscovery) — no visible token error.
- [ ] Kill/relaunch the app: nothing document-related was persisted.

## Out of scope (unchanged)

Play Store publishing, offline caching, favourites, pricing, interactive
drawings, part ordering, additional providers, launcher-icon branding.
