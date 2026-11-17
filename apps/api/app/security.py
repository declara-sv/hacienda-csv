"""Clerk session-token verification.

Clerk handles identity only: a verified token yields the Clerk user id (`sub`) plus the optional
`email` / `name` custom claims. Users, accounts and memberships are provisioned from those claims
in `app.services.users`.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, Protocol

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import ApiError
from app.config import VERCEL_ORIGIN_PATTERN, Settings

logger = logging.getLogger(__name__)

CLOCK_SKEW_SECONDS = 30
ALGORITHMS = ["RS256"]
JWKS_CACHE_SECONDS = 300
JWKS_TIMEOUT_SECONDS = 5

_bearer = HTTPBearer(auto_error=False)
_VERCEL_ORIGIN = re.compile(VERCEL_ORIGIN_PATTERN, re.IGNORECASE)


class SigningKeySource(Protocol):
    """What the verifier needs from a JWKS client (`jwt.PyJWKClient` or a test double)."""

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK: ...


class InvalidToken(Exception):
    """The token is missing, malformed, unsigned by Clerk, expired, or not meant for this app."""


@dataclass(frozen=True)
class ClerkIdentity:
    clerk_user_id: str
    email: str | None
    name: str | None


@lru_cache
def shared_jwks_client(url: str) -> jwt.PyJWKClient:
    """One client per JWKS URL for the whole process, so its key cache survives app re-creation."""
    return jwt.PyJWKClient(
        url, cache_keys=True, lifespan=JWKS_CACHE_SECONDS, timeout=JWKS_TIMEOUT_SECONDS
    )


def _clean(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


class ClerkTokenVerifier:
    def __init__(self, settings: Settings, jwks_client: SigningKeySource | None = None) -> None:
        self.issuer = settings.clerk_issuer
        self.authorized_parties = {_normalize_origin(p) for p in settings.clerk_authorized_parties}
        self.allow_vercel = settings.cors_allow_vercel_subdomains
        self._jwks_url = settings.clerk_jwks_url
        self._jwks_client = jwks_client

    @property
    def jwks_client(self) -> SigningKeySource:
        # Resolved lazily so creating the app never touches the network.
        if self._jwks_client is None:
            self._jwks_client = shared_jwks_client(self._jwks_url)
        return self._jwks_client

    def is_authorized_party(self, azp: str) -> bool:
        origin = _normalize_origin(azp)
        if origin in self.authorized_parties:
            return True
        return self.allow_vercel and _VERCEL_ORIGIN.fullmatch(origin) is not None

    def verify(self, token: str) -> ClerkIdentity:
        try:
            if jwt.get_unverified_header(token).get("alg") not in ALGORITHMS:
                raise InvalidToken("alg")
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=ALGORITHMS,
                issuer=self.issuer,
                leeway=CLOCK_SKEW_SECONDS,
                # Clerk session tokens carry no `aud`; `azp` is checked below instead.
                options={"require": ["exp", "iss", "sub"], "verify_aud": False},
            )
        except jwt.PyJWKClientConnectionError as exc:
            logger.warning("No se pudo obtener el JWKS de Clerk: %s", exc)
            raise InvalidToken("jwks") from exc
        except jwt.PyJWTError as exc:
            raise InvalidToken(str(exc)) from exc

        sub = _clean(claims.get("sub"))
        if sub is None:
            raise InvalidToken("sub")
        azp = claims.get("azp")
        if azp is not None and not (isinstance(azp, str) and self.is_authorized_party(azp)):
            raise InvalidToken("azp")
        return ClerkIdentity(
            clerk_user_id=sub, email=_clean(claims.get("email")), name=_clean(claims.get("name"))
        )


def _normalize_origin(value: str) -> str:
    return value.strip().rstrip("/").lower()


def _unauthorized() -> ApiError:
    return ApiError(401, "No autorizado.", headers={"WWW-Authenticate": "Bearer"})


def get_token_verifier(request: Request) -> ClerkTokenVerifier:
    return request.app.state.token_verifier


def get_clerk_identity(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[ClerkTokenVerifier, Depends(get_token_verifier)],
) -> ClerkIdentity:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        return verifier.verify(credentials.credentials)
    except InvalidToken as exc:
        raise _unauthorized() from exc


CurrentIdentity = Annotated[ClerkIdentity, Depends(get_clerk_identity)]
