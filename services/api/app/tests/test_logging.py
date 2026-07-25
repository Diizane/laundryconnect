import json
import logging

from app.core.logging import JsonFormatter, request_id_var


def _format_record(**extra: object) -> dict:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonFormatter().format(record))


def test_json_formatter_basic_fields() -> None:
    payload = _format_record()
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test"
    assert "timestamp" in payload


def test_json_formatter_includes_request_id() -> None:
    token = request_id_var.set("req-123")
    try:
        payload = _format_record()
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "req-123"


def test_httpx_request_logging_is_quieted() -> None:
    from app.core.logging import configure_logging

    configure_logging("INFO")
    assert logging.getLogger("httpx").level == logging.WARNING


def test_sensitive_extras_are_redacted() -> None:
    payload = _format_record(
        provider_password="hunter2",
        session_cookie="abc",
        auth_token="xyz",
        provider="alliance",
    )
    assert payload["provider_password"] == "[REDACTED]"
    assert payload["session_cookie"] == "[REDACTED]"
    assert payload["auth_token"] == "[REDACTED]"
    assert payload["provider"] == "alliance"
    assert "hunter2" not in json.dumps(payload)
