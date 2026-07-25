# Alliance connector fixtures

Sanitised responses that drive the connector in **fixture mode** (default,
CI). See the recording/sanitisation policy in
`app/tests/fixtures/providers/README.md` and ADR 0011.

## Rules

- **No live data may be committed until the access decision record is
  approved.** The current `search.json` is **synthetic, hand-authored**
  representative data — not captured from the live portal — and is labelled
  `"synthetic": true` in `_meta`.
- Every fixture carries a `_meta` block with `reviewed_by` (a human),
  `date`, and either `synthetic: true` or capture provenance. A test
  (`test_alliance_fixtures_reviewed`) rejects unreviewed fixtures.
- When real responses are recorded (post-approval, via manual login), run
  the sanitiser (`python -m app.providers.alliance.capture`) which strips
  Cookie/Set-Cookie/Authorization/tokens/usernames/account data/signed
  URLs/session ids, then a human must review the diff before committing.
