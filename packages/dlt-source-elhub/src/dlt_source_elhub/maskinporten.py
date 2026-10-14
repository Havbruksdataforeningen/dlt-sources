"""Maskinporten authentication: a JWT bearer grant exchanged for an access token.

The flow of https://docs.digdir.no/docs/Maskinporten/maskinporten_protocol_token. Nothing here is
Elhub-specific; another Maskinporten-protected API is a different `scope`.
"""

import logging
import time
import uuid
from typing import Any

import jwt
from dlt.common.configuration.specs import CredentialsConfiguration, configspec
from dlt.common.typing import TSecretStrValue
from dlt.sources.helpers import requests
from requests import HTTPError, PreparedRequest, Response
from requests.auth import AuthBase

logger = logging.getLogger(__name__)

GRANT_LIFETIME_SECONDS = 120
"""The longest `exp - iat` Maskinporten accepts."""

EXPIRY_MARGIN_SECONDS = 30
"""Renew this long before `expires_in`, so no request carries a token that expires in flight."""

REFUSAL_BODY_LIMIT = 1000
"""How much of a refusal that is not Maskinporten's JSON (a proxy's HTML page, say) the message keeps."""


class MaskinportenError(Exception):
    """Maskinporten refused the grant.

    The message carries Maskinporten's own `error` and `error_description`, where the reason lives
    (`MP-250`: the scope is not granted to the organisation, `MP-251`: the delegation is missing). A
    bare `400 Client Error` says none of that, and dlt's `http_show_error_body` never reaches the token
    endpoint. The grant itself stays out of the message.
    """

    def __init__(self, status: int, reason: str, scope: str, consumer_org: str | None):
        self.status = status
        self.reason = reason
        self.scope = scope
        self.consumer_org = consumer_org
        super().__init__(
            f"Maskinporten refused the grant for scope={scope} consumer_org={consumer_org}: {status} {reason}"
        )


def _refusal(response: Response) -> str:
    """`error: error_description` when Maskinporten answered, the raw body when something else did."""
    try:
        body = response.json()
        return f"{body['error']}: {body['error_description']}"
    except (ValueError, KeyError, TypeError):
        return response.text.strip()[:REFUSAL_BODY_LIMIT] or response.reason or ""


@configspec
class MaskinportenCredentials(CredentialsConfiguration):
    """The Maskinporten client as registered in Digdir's self-service portal; dlt resolves it from
    `[sources.<source>.credentials]`."""

    # dlt: a field without Optional is required, hence the None defaults.
    client_id: str = None  # type: ignore[assignment]
    kid: str = None  # type: ignore[assignment]
    private_key: TSecretStrValue = None  # type: ignore[assignment]
    maskinporten_url: str = "https://maskinporten.no"

    def pem(self) -> str:
        """A single-line environment variable carries the PEM with `\\n` written out."""
        return self.private_key.replace("\\n", "\n")


class MaskinportenAuth(AuthBase):
    """A bearer token for one scope, renewed before it expires.

    `consumer_org` is a company that delegated the scope to the client's organisation; the token is
    then issued on its behalf.
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
        """`aud` needs the trailing slash; `jti` because Maskinporten refuses a grant it has seen."""
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
        try:
            response = requests.post(
                f"{self.credentials.maskinporten_url}/token",
                data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self.grant()},
            )
        except HTTPError as error:
            if error.response is None:
                raise
            raise MaskinportenError(
                error.response.status_code, _refusal(error.response), self.scope, self.consumer_org
            ) from error
        body = response.json()
        self._token = body["access_token"]
        self._expires_at = time.time() + int(body["expires_in"]) - EXPIRY_MARGIN_SECONDS
        logger.debug("Maskinporten issued a token for %s, consumer_org=%s", self.scope, self.consumer_org)
