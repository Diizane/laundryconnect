"""Smoke-test output sanitisation — no live path exercised."""

from app.providers.alliance.smoke_test import result_summary, sanitise_reference
from app.providers.models import DataOrigin, ProviderResult, ResultType

SIGNED_URL = (
    "https://portal.alliancels.net/s/document/ALS-SC60-SVC"
    "?sig=SECRETSIGNATUREVALUE&sid=SESSIONIDVALUE&token=BEARERTOKEN#frag"
)


def test_sanitise_reference_strips_query_and_fragment() -> None:
    cleaned = sanitise_reference(SIGNED_URL)
    assert cleaned == "portal.alliancels.net/s/document/ALS-SC60-SVC"
    for secret in (
        "SECRETSIGNATUREVALUE",
        "SESSIONIDVALUE",
        "BEARERTOKEN",
        "sig=",
        "sid=",
        "token=",
    ):
        assert secret not in cleaned


def test_sanitise_reference_handles_non_url() -> None:
    assert sanitise_reference("ALS-SC60-SVC") == "ALS-SC60-SVC"
    assert sanitise_reference("ALS-SC60?sig=SECRET") == "ALS-SC60"  # defensive strip
    assert sanitise_reference(None) == ""
    assert sanitise_reference("") == ""


def test_result_summary_contains_no_sensitive_params() -> None:
    result = ProviderResult(
        provider_id="alliance",
        source_reference=SIGNED_URL,
        result_type=ResultType.DOCUMENT,
        data_origin=DataOrigin.LIVE,
        title="SC60 Service Manual",
    )
    summary = result_summary(result)
    for secret in (
        "SECRETSIGNATUREVALUE",
        "SESSIONIDVALUE",
        "BEARERTOKEN",
        "sig=",
        "sid=",
        "token=",
    ):
        assert secret not in summary
    assert "portal.alliancels.net/s/document/ALS-SC60-SVC" in summary
