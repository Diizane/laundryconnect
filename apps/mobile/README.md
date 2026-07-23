# LaundryConnect Mobile

Flutter app for commercial laundry service technicians. Android-first;
structured so iOS can follow.

## Run

Requires the [Flutter SDK](https://docs.flutter.dev/get-started/install)
(3.44+). With the backend running locally:

```bash
cd apps/mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000   # Android emulator
# Physical device on the same network: use your machine's LAN IP instead.
```

`API_BASE_URL` defaults to `http://10.0.2.2:8000` (Android emulator loopback).

## Test and lint

```bash
flutter analyze
flutter test
dart format lib test
```

## Structure

```
lib/
  main.dart                 Entry point
  src/
    app.dart                Root widget (theme + injectable SearchApi)
    theme/app_theme.dart    Navy/teal minimalist brand theme
    api/api_client.dart     Backend client (POST /api/v1/search)
    models/search.dart      Models mirroring backend search schemas
    screens/home_search_screen.dart   Search bar + idle/loading/results/error states
    widgets/                Result cards, metadata badges
```

## Principles

- Universal search first: launch → type → answer, minimal taps.
- Every result shows a `data_origin` badge (MOCK/LIVE/CACHED) — sample data
  is never presented as live provider data.
- Partial provider failure shows a warning banner; results are never
  silently incomplete.
- **No provider credentials in this app, ever.** All provider access happens
  on the backend.
