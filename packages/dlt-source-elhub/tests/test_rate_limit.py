"""Elhub's rate limit, as measured in specs/README.md: `429` with no `Retry-After` until it lifts."""

import pytest
from dlt.pipeline.exceptions import PipelineStepFailed

from tests.conftest import API_PATH, TOKEN_LIFETIME, FakeElhub, make_pipeline, payload_for, row_count, run, source

POINT = "707057500000000001"
LISTING = {"data": [{"type": "metering-points", "id": POINT}]}
VALUE = {
    "startTime": "2026-02-27T00:00:00+01:00",
    "endTime": "2026-02-27T01:00:00+01:00",
    "quantityKwh": 1.0,
    "resolution": "PT60M",
    "direction": "Out",
    "insertDateTime": "2026-02-28T02:04:25+01:00",
}
REFUSED_FOR = 125
"""Seconds Elhub refused in the measurement."""


def test_a_backfill_waits_out_the_rate_limit_and_loads_everything(api: FakeElhub, caplog: pytest.LogCaptureFixture):
    api.route(API_PATH, LISTING)
    api.route_point(POINT, payload_for(POINT, [VALUE]))
    api.rate_limit(REFUSED_FOR)

    pipeline = make_pipeline("rate_limited")
    elhub = source()
    elhub.metering_points.bind(start_date="2026-02-27", end_date="2026-03-01")
    elhub.metering_values_hour.bind(start_date="2026-02-27", end_date="2026-03-01")
    run(pipeline, elhub)

    assert len(api.calls(API_PATH)) > 2, "the refused day is asked again"
    assert row_count(pipeline, "metering_values_hour") == 1
    assert any(r.levelname == "WARNING" and "429" in r.getMessage() for r in caplog.records), "the wait says why"


def test_a_wait_longer_than_a_token_lives_asks_again_with_a_renewed_one(api: FakeElhub):
    api.route(API_PATH, LISTING)
    api.route_point(POINT, payload_for(POINT, [VALUE]))
    api.rate_limit(TOKEN_LIFETIME + 5)

    pipeline = make_pipeline("outlasted_token")
    run(pipeline, source())

    assert api.token_responses > 1, "the wait outlasted the first token"
    assert row_count(pipeline, "metering_values_hour") == 1


def test_a_request_left_hanging_is_asked_anew_with_a_renewed_token(api: FakeElhub):
    api.route(API_PATH, LISTING)
    api.route_point(POINT, payload_for(POINT, [VALUE]))
    api.leave_unanswered(2)

    pipeline = make_pipeline("left_hanging")
    run(pipeline, source())

    assert api.token_responses > 1, "two timeouts outlast a token"
    assert row_count(pipeline, "metering_values_hour") == 1


def test_a_refusal_that_does_not_end_fails_with_elhubs_status_and_reason(api: FakeElhub):
    api.route(API_PATH, LISTING)
    api.rate_limit()

    with pytest.raises(PipelineStepFailed, match=r"429 Too Many Requests[\s\S]*experimenting with rate limits"):
        run(make_pipeline("refused"), source())


def test_the_patience_is_configurable_for_when_elhub_changes_its_limit(api: FakeElhub, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOURCES__ELHUB__REQUEST_MAX_ATTEMPTS", "3")
    api.route(API_PATH, LISTING)
    api.rate_limit(REFUSED_FOR)

    with pytest.raises(PipelineStepFailed, match="429 Too Many Requests"):
        run(make_pipeline("impatient"), source())
    assert len(api.calls(API_PATH)) == 3
