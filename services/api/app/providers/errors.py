"""Typed provider errors.

Connectors raise these; the registry maps them to structured per-provider
outcomes. Error *messages* here must never contain credentials, cookies,
tokens, session-state contents, or provider HTML — only safe, structural
detail. The registry additionally exposes only the exception class name.
"""


class ProviderError(Exception):
    """Base class for provider connector errors."""


class ReauthenticationRequired(ProviderError):
    """A live provider session is missing, invalid, or expired.

    Maps to the `reauthentication_required` outcome. Resolution is always a
    human re-running the manual session bootstrap — never an automatic
    bypass of MFA, CAPTCHA, or bot protection.
    """


class SessionMissing(ReauthenticationRequired):
    """No session file was found at the configured path."""


class SessionInvalid(ReauthenticationRequired):
    """The session file is unreadable or not a valid storage-state document."""


class SessionExpired(ReauthenticationRequired):
    """The session's cookies have all expired."""


class LiveModeRefused(ProviderError):
    """A live provider mode was requested but is not permitted here.

    Raised when running under CI, when the provider access decision record
    is not approved, or when a mode (e.g. credential login) is disallowed by
    provider terms. Guarantees no live request is attempted.
    """
