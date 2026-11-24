"""AWS Secrets Manager and KMS envelope encryption adapters."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Optional

from botocore.exceptions import ClientError

from app.cloud.client import AWSClientFactory, aws_client_factory
from app.config import settings

logger = logging.getLogger("app.cloud.secrets")


class AWSSecretsProvider:
    """Retrieves runtime secrets from AWS Secrets Manager with bounded TTL caching."""

    def __init__(
        self,
        factory: AWSClientFactory = aws_client_factory,
        ttl_seconds: float = 300.0,
    ) -> None:
        self._factory = factory
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[str, float]] = {}

    def _fetch_secret_sync(self, secret_id: str, json_key: Optional[str] = None) -> str:
        sm = self._factory.get_client("secretsmanager")
        resp = sm.get_secret_value(SecretId=secret_id)
        raw = str(resp.get("SecretString", ""))
        if not raw:
            raise ValueError(f"Secret '{secret_id}' has empty SecretString.")
        if json_key:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or json_key not in parsed:
                raise KeyError(f"Key '{json_key}' not present in secret '{secret_id}'.")
            return str(parsed[json_key])
        return raw

    async def get_secret(self, secret_id: str, json_key: Optional[str] = None) -> str:
        cache_key = f"{secret_id}:{json_key or ''}"
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and (now - cached[1]) < self._ttl_seconds:
            return cached[0]

        value = await asyncio.to_thread(self._fetch_secret_sync, secret_id, json_key)
        self._cache[cache_key] = (value, now)
        return value

    async def get_jwt_secret(self) -> str:
        """Resolve JWT signing key from Secrets Manager when AWS backend is enabled."""
        if not settings.aws_backend_enabled:
            return settings.jwt_secret
        return await self.get_secret(settings.aws_jwt_secret_name, json_key="JWT_SECRET")

    def clear_cache(self) -> None:
        self._cache.clear()


class KMSEnvelopeCipher:
    """Tenant-bound cryptographic encryption using AWS KMS EncryptionContext."""

    def __init__(
        self,
        factory: AWSClientFactory = aws_client_factory,
        key_id: Optional[str] = None,
    ) -> None:
        self._factory = factory
        self._key_id = key_id

    @property
    def key_id(self) -> str:
        return self._key_id or settings.aws_kms_key_id

    def _encrypt_sync(self, tenant_id: str, plaintext: bytes) -> bytes:
        if not self.key_id:
            raise ValueError("AWS_KMS_KEY_ID must be configured for KMS encryption.")
        kms = self._factory.get_client("kms")
        resp = kms.encrypt(
            KeyId=self.key_id,
            Plaintext=plaintext,
            EncryptionContext={"tenant_id": tenant_id},
        )
        return bytes(resp["CiphertextBlob"])

    def _decrypt_sync(self, tenant_id: str, ciphertext: bytes) -> bytes:
        kms = self._factory.get_client("kms")
        try:
            resp = kms.decrypt(
                CiphertextBlob=ciphertext,
                EncryptionContext={"tenant_id": tenant_id},
            )
            return bytes(resp["Plaintext"])
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "Unknown"))
            raise PermissionError(f"KMS decryption rejected for tenant '{tenant_id}' ({code}).") from exc

    async def encrypt_text(self, tenant_id: str, plaintext: str) -> str:
        blob = await asyncio.to_thread(self._encrypt_sync, tenant_id, plaintext.encode("utf-8"))
        return base64.b64encode(blob).decode("ascii")

    async def decrypt_text(self, tenant_id: str, ciphertext_b64: str) -> str:
        blob = base64.b64decode(ciphertext_b64.encode("ascii"))
        plain = await asyncio.to_thread(self._decrypt_sync, tenant_id, blob)
        return plain.decode("utf-8")


aws_secrets_provider = AWSSecretsProvider()
kms_envelope_cipher = KMSEnvelopeCipher()
