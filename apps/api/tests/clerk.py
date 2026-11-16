"""Clerk test doubles: an RSA key pair, an in-memory JWKS and a minter of Clerk-like session tokens."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "https://test-clerk.clerk.accounts.dev"
AUTHORIZED_PARTY = "http://localhost:5173"
_UNSET: Any = object()


def generate_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    return {**jwk, "kid": kid, "use": "sig", "alg": "RS256"}


class FakeJwksClient(jwt.PyJWKClient):
    """A real `PyJWKClient` (kid lookup, caching) whose JWKS comes from memory, not the network."""

    def __init__(self, keys: list[dict[str, Any]]) -> None:
        super().__init__("https://jwks.invalid/.well-known/jwks.json", cache_keys=True)
        self.keys = keys
        self.fetches = 0

    def fetch_data(self) -> Any:
        self.fetches += 1
        data = {"keys": self.keys}
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(data)
        return data


class TokenMinter:
    def __init__(self, key: rsa.RSAPrivateKey, kid: str, issuer: str = ISSUER) -> None:
        self.key = key
        self.kid = kid
        self.issuer = issuer

    def mint(
        self,
        sub: str | None = None,
        *,
        email: str | None = _UNSET,
        name: str | None = _UNSET,
        azp: str | None = AUTHORIZED_PARTY,
        issuer: str | None = None,
        expires_in: int = 3600,
        key: rsa.RSAPrivateKey | None = None,
        kid: str | None = None,
        algorithm: str = "RS256",
        **extra: Any,
    ) -> str:
        """A session token like Clerk's; `None` drops a claim, unset email/name get test defaults."""
        now = int(time.time())
        sub = sub or new_sub()
        claims: dict[str, Any] = {
            "iss": issuer or self.issuer,
            "sub": sub,
            "sid": f"sess_{uuid.uuid4().hex}",
            "iat": now,
            "nbf": now - 5,
            "exp": now + expires_in,
            "azp": azp,
            "email": f"{sub}@test.local" if email is _UNSET else email,
            "name": "Test User" if name is _UNSET else name,
            **extra,
        }
        claims = {k: v for k, v in claims.items() if v is not None}
        signing_key: Any = key or self.key
        if algorithm.startswith("HS"):
            signing_key = "x" * 64
        return jwt.encode(claims, signing_key, algorithm=algorithm, headers={"kid": kid or self.kid})


def new_sub() -> str:
    return f"user_{uuid.uuid4().hex}"
