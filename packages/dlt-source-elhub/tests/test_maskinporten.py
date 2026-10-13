"""The Maskinporten grant and the token it buys, as Maskinporten would see them."""

import jwt
import pytest
from requests import Request

from dlt_source_elhub import MaskinportenAuth
from dlt_source_elhub.maskinporten import EXPIRY_MARGIN_SECONDS, GRANT_LIFETIME_SECONDS
from tests.conftest import (
    API_PATH,
    CLIENT_ID,
    KID,
    PRIVATE_PEM,
    PUBLIC_PEM,
    TOKEN_LIFETIME,
    TOKEN_PATH,
    FakeElhub,
    credentials,
    make_pipeline,
    run,
    source,
)


def _claims(grant: str) -> dict:
    """Verified with the public key, so a grant Maskinporten would refuse fails here."""
    return jwt.decode(grant, PUBLIC_PEM, algorithms=["RS256"], audience="https://maskinporten.no/")


def _auth(**kwargs) -> MaskinportenAuth:
    return MaskinportenAuth(credentials(), "elhub:enduser", **kwargs)


def test_the_grant_carries_what_maskinporten_requires():
    grant = _auth().grant()

    claims = _claims(grant)
    assert claims["iss"] == CLIENT_ID
    assert claims["scope"] == "elhub:enduser"
    assert claims["exp"] - claims["iat"] == GRANT_LIFETIME_SECONDS
    assert "consumer_org" not in claims
    assert jwt.get_unverified_header(grant) == {"alg": "RS256", "kid": KID, "typ": "JWT"}
    assert _claims(_auth(consumer_org="999999991").grant())["consumer_org"] == "999999991"


def test_every_grant_is_unique():
    auth = _auth()
    assert _claims(auth.grant())["jti"] != _claims(auth.grant())["jti"]


def test_an_escaped_private_key_signs_too():
    escaped = PRIVATE_PEM.replace("\n", "\\n")
    grant = MaskinportenAuth(credentials(private_key=escaped), "elhub:enduser").grant()
    assert _claims(grant)["iss"] == CLIENT_ID


def test_one_token_serves_every_request_until_it_expires(api: FakeElhub, monkeypatch: pytest.MonkeyPatch):
    now = 1_700_000_000.0
    monkeypatch.setattr("dlt_source_elhub.maskinporten.time.time", lambda: now)
    request = Request("GET", "https://api.elhub.no/energy-data/v0/metering-points").prepare()
    auth = _auth()

    for _ in range(3):
        auth(request)
    assert api.token_responses == 1

    now += TOKEN_LIFETIME - EXPIRY_MARGIN_SECONDS
    auth(request)
    assert api.token_responses == 2, "renewed before expires_in, not after"


def test_the_token_is_sent_as_a_bearer_token(api: FakeElhub):
    api.route(API_PATH, None)
    run(make_pipeline("test_bearer"), source(), "metering_points")

    (call,) = api.calls(API_PATH)
    assert call.headers["Authorization"] == "Bearer token-1"
    (exchange,) = api.calls(TOKEN_PATH)
    assert exchange.form["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer"
    assert _claims(exchange.form["assertion"])["iss"] == CLIENT_ID
