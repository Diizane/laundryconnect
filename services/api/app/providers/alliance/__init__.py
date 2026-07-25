"""Alliance Laundry Systems provider connector.

Human-in-the-loop authentication architecture (Milestone 8):

- **fixture** mode (default, CI-safe): serves sanitised recorded/synthetic
  fixtures, makes no network requests, passes ConnectorContract.
- **session** mode: loads an operator-bootstrapped browser session from
  `ALLIANCE_SESSION_PATH`; detects missing/invalid/expired sessions and
  raises `ReauthenticationRequired`. Live fetching is hard-gated on the
  access decision record being approved and on not running under CI.
- **credential** mode: intentionally NOT implemented — the provider terms
  do not (yet) permit automated credential login. The mode refuses.

No component here ever requests, stores, logs, or commits real credentials
or session contents. See docs/PROVIDER_CONNECTORS.md and
docs/PROVIDER_ACCESS/alliance-laundry-systems.md.
"""
