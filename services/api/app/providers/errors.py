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


class ProviderForbidden(ProviderError):
    """The provider refused access (e.g. HTTP 403) — a hard stop that may
    indicate blocking. Surfaced as a distinct `forbidden` outcome; never
    retried or treated as a reauthentication loop."""


class ProviderDocumentsUnsupported(ProviderError):
    """This provider does not implement the document workflow. A stable
    domain outcome (mapped to a 4xx by the API), never a crash."""


class InvalidDocumentReference(ProviderError):
    """A document/manual reference failed the provider's strict format
    validation. Raised before any request is attempted — client-supplied
    references can never reach the transport unvalidated."""


class DocumentNotFound(ProviderError):
    """The provider has no document at the requested location (HTTP 404 in
    the document workflow). A domain outcome, not a transport failure —
    callers can surface "document not found" to the technician instead of a
    generic provider error."""


class InvalidDocumentContent(ProviderError):
    """The provider served something other than the expected document format
    (wrong Content-Type, or a body that fails the format's magic-byte check
    — e.g. an HTML page where a PDF was expected). Terminal; never retried.
    The message carries only structural detail (declared content type),
    never response content."""


class LiveModeRefused(ProviderError):
    """A live provider mode was requested but is not permitted here.

    Raised when running under CI, when the provider access decision record
    is not approved, or when a mode (e.g. credential login) is disallowed by
    provider terms. Guarantees no live request is attempted.
    """
