# ADR 0006: Flutter foundation choices

- Status: accepted
- Date: 2026-07-23

## Context

Milestone 5 establishes the technician-facing Flutter app. Early structural
choices here set the pattern for all future mobile work.

## Decisions

1. **Minimal dependencies: `http` only.** No state-management package
   (riverpod/bloc), no code-gen (freezed/json_serializable) yet. State is a
   sealed class + `StatefulWidget`; JSON parsing is hand-written mirrors of
   the backend schemas with unit tests. Revisit when screens multiply (M6+).
2. **Search-first single screen.** Search bar and results live on one screen
   — launch → type → answer, no navigation in between. The machine workspace
   (M6) adds the first navigation step.
3. **`SearchApi` interface injected at the root.** `LaundryConnectApp`
   defaults to the real HTTP client; widget tests inject a fake. No DI
   framework.
4. **Backend URL via `--dart-define=API_BASE_URL`** (default
   `http://10.0.2.2:8000`, the Android-emulator host loopback). No secrets
   in the app, ever — it only talks to the LaundryConnect backend.
5. **Data origin is always visible.** Every result card renders a
   MOCK/MANUAL/LIVE/CACHED badge; a warning banner appears whenever any
   provider failed or timed out. Honesty about data quality is a UI
   requirement, tested in widget tests.
6. **Stale-response guard.** Search responses carry a request sequence
   number; a slow earlier response can never overwrite a newer one.
7. **Platforms: android + ios generated, Android-first.** No web/desktop
   targets to maintain.

## Consequences

- Adding the machine workspace means a second screen + navigation; the
  sealed-state pattern carries over.
- If model classes multiply in M6/M7, adopt json_serializable then (one
  mechanical migration) rather than carrying codegen overhead now.
