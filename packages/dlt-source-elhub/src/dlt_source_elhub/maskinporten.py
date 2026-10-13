"""Maskinporten authentication: a JWT bearer grant exchanged for an access token.

Maskinporten is Digdir's machine-to-machine token service, used by Elhub and other
Norwegian public APIs. The flow is one documented at
https://docs.digdir.no/docs/Maskinporten/maskinporten_protocol_token: sign a short-lived
JWT with the client's private key, post it to `/token`, and send the access token it
returns as a bearer token. Nothing here is Elhub-specific, so another Maskinporten-protected
API is a matter of a different `scope`.
"""

import logging
import time
import uuid
from typing import Any

import jwt
from dlt.common.configuration.specs import CredentialsConfiguration, configspec
from dlt.common.typing import TSecretStrValue
from dlt.sources.helpers import requests
from requests import PreparedRequest
from requests.auth import AuthBase

logger = logging.getLogger(__name__)

GRANT_LIFETIME_SECONDS = 120
"""The longest `exp - iat` Maskinporten accepts on a grant. A grant is used once, so nothing is lost."""

EXPIRY_MARGIN_SECONDS = 30
"""A token is renewed this long before Maskinporten's `expires_in`, so a request never carries one that
expires in flight."""


@configspec
class MaskinportenCredentials(CredentialsConfiguration):
    """The Maskinporten client, as registered in Digdir's self-service portal.

    Resolved by dlt from `[sources.<source>.credentials]` in `secrets.toml`, or from the
    environment as `SOURCES__<SOURCE>__CREDENTIALS__CLIENT_ID` and so on.
    """

    client_id: str = None  # type: ignore[assignment]  # dlt: a field without Optional is required
    kid: str = None  # type: ignore[assignment]
    """The key id of the client's registered public key, carried in the grant's header."""
    private_key: TSecretStrValue = None  # type: ignore[assignment]
    """The matching private key as PEM. A `\\n` written out as two characters, the way a
    single-line environment variable carries a PEM, is read as a line break."""
    maskinporten_url: str = "https://maskinporten.no"
    """`https://test.maskinporten.no` needs a client registered in the test environment."""

    def pem(self) -> str:
        return self.private_key.replace("\\n", "\n")


class MaskinportenAuth(AuthBase):
    """Fetches a token for one scope and sends it as a bearer token, renewing it before it expires.

    `consumer_org` is the organisation number of a company that has delegated the scope to the
    client's organisation in Altinn; the token is then issued on that company's behalf. Leave it
    out to act as the client's own organisation.
    """

    def __init__(self, credentials: MaskinportenCredentials, scope: str, consumer_org: str | None = None):
        self.credentials = credentials
        self.scope = scope
        self.consumer_org = consumer_org
        self._token: str | None = None
        self._expires_at = 0.0

    def __call__(self, request: PreparedRequest) -> PreparedRequest:
        if self._token is None or time.time() >= self._expires_at:
            self.obtain_token()
        request.headers["Authorization"] = f"Bearer {self._token}"
        return request

    def grant(self) -> str:
        """The signed JWT bearer grant: `aud` is the issuer's URL with its trailing slash, `jti` makes
        every grant unique because Maskinporten refuses one it has seen before."""
        now = int(time.time())
        claims: dict[str, Any] = {
            "aud": f"{self.credentials.maskinporten_url}/",
            "iss": self.credentials.client_id,
            "scope": self.scope,
            "iat": now,
            "exp": now + GRANT_LIFETIME_SECONDS,
            "jti": str(uuid.uuid4()),
        }
        if self.consumer_org:
            claims["consumer_org"] = self.consumer_org
        return jwt.encode(claims, self.credentials.pem(), algorithm="RS256", headers={"kid": self.credentials.kid})

    def obtain_token(self) -> None:
        response = requests.post(
            f"{self.credentials.maskinporten_url}/token",
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self.grant()},
        )
        body = response.json()
        self._token = body["access_token"]
        self._expires_at = time.time() + int(body["expires_in"]) - EXPIRY_MARGIN_SECONDS
        logger.debug("Maskinporten issued a token for %s, consumer_org=%s", self.scope, self.consumer_org)
