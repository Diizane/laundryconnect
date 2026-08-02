# Milestone 10 — First Android internal test build

Status: implemented and smoke-tested on an emulator — pending review.
Flutter/mobile + test-environment configuration only; the Phase 3 backend
API, provider transport, parsers, and token handling are untouched.

## Built artifact (2026-08-02)

- File: `apps/mobile/build/app/outputs/flutter-apk/app-debug.apk`
  (debug/internal-testing build; NOT committed to git)
- Size: 149,102,875 bytes (~149 MB — debug builds bundle all ABIs and the
  debug runtime; the release build of the same code is 50.6 MB)
- SHA-256:
  `45ba84133fd28a558b46c7630434b66deaf64ec325f9d2e4442a6e62fc2c1765`
- Package: `au.com.laundryconnect.laundryconnect` v0.1.0 (versionCode 1)
- Label: LaundryConnect · minSdk 24 (Android 7.0) · targetSdk 36
- Toolchain: Flutter 3.44.7 · OpenJDK 17.0.20 (Homebrew) · Android SDK
  platform 36, build-tools 36.0.0, platform-tools 37.0.1 (command-line
  tools; no IDE), all licences accepted
- Build command:
  `flutter build apk --debug` (from `apps/mobile`; add
  `--dart-define=API_BASE_URL=…` to target a non-default backend)
- Install: `adb install -r app-debug.apk`
- Smoke-tested on: emulator AVD (Pixel 7 profile), Android 16 / API 36,
  arm64 — mock-mode backend at the default `http://10.0.2.2:8000`.

### Cleartext isolation (verified empirically on both APKs)

`android:usesCleartextTraffic="true"` exists ONLY in
`android/app/src/debug/AndroidManifest.xml`, so plain-HTTP backends
(emulator/LAN internal testing) work in debug builds only. `aapt dump
xmltree` confirms the flag is present in `app-debug.apk` and **absent** in
`app-release.apk` — release/staging builds therefore reject cleartext by
Android default and require an HTTPS backend. The release APK was built
solely for this verification and is not distributed.

### Secrets scan (passed)

The unpacked debug APK contains none of: Alliance hostnames, credentials,
account identifiers, session/storage-state JSON, cookies,
`DOCUMENT_TOKEN_SECRET`, `.env` files, or provider PDFs. The only
backend-related string is the documented emulator default
`http://10.0.2.2:8000` (a `--dart-define` default, not a provider URL).

### Known limitation — in-memory PDF viewer

The current viewer loads the complete validated PDF into Dart memory.
This is appropriate for the first internal build and observed document
sizes, but large field manuals may require a temporary-file or
streamed-rendering design in a future milestone.

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
