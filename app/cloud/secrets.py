"""AWS Secrets Manager and KMS AES-256-GCM envelope encryption adapters."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from typing import Optional

from botocore.exceptions import ClientError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.cloud.client import AWSClientFactory, aws_client_factory
from app.config import _INSECURE_DEFAULT_JWT_SECRET, settings

logger = logging.getLogger("app.cloud.secrets")

_ENVELOPE_VERSION = 2
_NONCE_BYTES = 12


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
        if not raw.strip():
            raise ValueError(f"Secret '{secret_id}' has empty SecretString.")
        if json_key:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or json_key not in parsed:
                raise KeyError(f"Key '{json_key}' not present in secret '{secret_id}'.")
            val = str(parsed[json_key])
            if not val.strip():
                raise ValueError(f"Key '{json_key}' in secret '{secret_id}' is empty.")
            return val
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
        """Resolve and validate JWT signing key from Secrets Manager when AWS backend is enabled."""
        if not settings.aws_backend_enabled:
            return settings.jwt_secret
        secret_name = settings.aws_jwt_secret_name.strip()
        if not secret_name:
            raise ValueError("AWS_JWT_SECRET_NAME must be configured when AWS_BACKEND_ENABLED=true.")
        resolved = await self.get_secret(secret_name, json_key="JWT_SECRET")
        normalized = resolved.strip()
        if not normalized or normalized == _INSECURE_DEFAULT_JWT_SECRET:
            raise ValueError("Resolved AWS JWT secret is empty or uses the insecure published default.")
        return resolved

    def clear_cache(self) -> None:
        self._cache.clear()


class KMSEnvelopeCipher:
    """Tenant-bound AES-256-GCM envelope encryption backed by AWS KMS GenerateDataKey.

    Supports arbitrary-size payloads (beyond KMS Encrypt's 4,096-byte direct limit) by
    generating a per-record 256-bit data key via KMS bound to EncryptionContext={"tenant_id": ...},
    authenticating plaintext with AES-256-GCM using tenant_id as AAD, and retaining backward-
    compatible decryption of legacy direct KMS ciphertext blobs.
    """

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
        resp = kms.generate_data_key(
            KeyId=self.key_id,
            KeySpec="AES_256",
            EncryptionContext={"tenant_id": tenant_id},
        )
        data_key = bytes(resp["Plaintext"])
        encrypted_data_key = bytes(resp["CiphertextBlob"])

        nonce = os.urandom(_NONCE_BYTES)
        aes_ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, tenant_id.encode("utf-8"))
        envelope = {
            "v": _ENVELOPE_VERSION,
            "alg": "AES-256-GCM",
            "edk": base64.b64encode(encrypted_data_key).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ct": base64.b64encode(aes_ciphertext).decode("ascii"),
        }
        return json.dumps(envelope, separators=(",", ":")).encode("utf-8")

    def _decrypt_sync(self, tenant_id: str, ciphertext: bytes) -> bytes:
        kms = self._factory.get_client("kms")
        envelope: Optional[dict[str, object]] = None
        if ciphertext.startswith(b"{"):
            try:
                parsed = json.loads(ciphertext.decode("utf-8"))
                if isinstance(parsed, dict) and parsed.get("v") == _ENVELOPE_VERSION:
                    envelope = parsed
            except (UnicodeDecodeError, json.JSONDecodeError):
                envelope = None

        try:
            if envelope is not None:
                edk_raw = envelope.get("edk")
                nonce_raw = envelope.get("nonce")
                ct_raw = envelope.get("ct")
                if not isinstance(edk_raw, str) or not isinstance(nonce_raw, str) or not isinstance(ct_raw, str):
                    raise PermissionError(f"Malformed KMS envelope for tenant '{tenant_id}'.")

                edk = base64.b64decode(edk_raw.encode("ascii"))
                nonce = base64.b64decode(nonce_raw.encode("ascii"))
                aes_ct = base64.b64decode(ct_raw.encode("ascii"))

                dek_resp = kms.decrypt(
                    CiphertextBlob=edk,
                    EncryptionContext={"tenant_id": tenant_id},
                )
                data_key = bytes(dek_resp["Plaintext"])
                return AESGCM(data_key).decrypt(nonce, aes_ct, tenant_id.encode("utf-8"))

            # Backward-compatible path for legacy direct KMS ciphertext blobs
            resp = kms.decrypt(
                CiphertextBlob=ciphertext,
                EncryptionContext={"tenant_id": tenant_id},
            )
            return bytes(resp["Plaintext"])
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", "Unknown"))
            raise PermissionError(f"KMS decryption rejected for tenant '{tenant_id}' ({code}).") from exc
        except InvalidTag as exc:
            raise PermissionError(f"KMS decryption rejected for tenant '{tenant_id}' (InvalidTag).") from exc

    async def encrypt_text(self, tenant_id: str, plaintext: str) -> str:
        blob = await asyncio.to_thread(self._encrypt_sync, tenant_id, plaintext.encode("utf-8"))
        return base64.b64encode(blob).decode("ascii")

    async def decrypt_text(self, tenant_id: str, ciphertext_b64: str) -> str:
        blob = base64.b64decode(ciphertext_b64.encode("ascii"))
        plain = await asyncio.to_thread(self._decrypt_sync, tenant_id, blob)
        return plain.decode("utf-8")


aws_secrets_provider = AWSSecretsProvider()
kms_envelope_cipher = KMSEnvelopeCipher()
