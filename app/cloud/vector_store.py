"""Tenant-isolated S3 document archive and Amazon S3 Vectors semantic index."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from typing import List, Optional, TypedDict

from botocore.exceptions import ClientError

from app.cloud.client import AWSClientFactory, aws_client_factory
from app.cloud.secrets import KMSEnvelopeCipher
from app.config import settings
from app.models import SearchDocument
from app.types import JSONDict

logger = logging.getLogger("app.cloud.vector_store")

_TENANT_SAFE_RE = re.compile(r"[^a-z0-9-]+")
_CHUNK_KEY_RE = re.compile(r"/chunk-(\d+)\.txt$")
_S3_VECTORS_MAX_BATCH = 500
_S3_DELETE_MAX_BATCH = 1000


class VectorFloat32Data(TypedDict):
    float32: List[float]


class VectorRecord(TypedDict):
    key: str
    data: VectorFloat32Data
    metadata: JSONDict


def sanitize_index_name(tenant_id: str) -> str:
    """Convert arbitrary tenant_id into a valid S3 Vectors index name (lowercase alnum + hyphen)."""
    cleaned = _TENANT_SAFE_RE.sub("-", tenant_id.lower()).strip("-")
    if not cleaned:
        cleaned = "default"
    return f"tenant-{cleaned}"[:63]


def deterministic_embed(text: str, dimension: int = 64) -> List[float]:
    """Deterministic unit-normalized feature-hashing embedding for offline/CI vector indexing.

    Maps overlapping word and character 3-grams onto a fixed-dimension unit sphere so
    semantically overlapping documents yield high cosine similarity without external API keys.
    """
    if dimension <= 0:
        raise ValueError("Embedding dimension must be positive.")

    vec = [0.0] * dimension
    tokens = re.findall(r"[a-z0-9]{2,}", text.lower())
    features: List[str] = list(tokens)
    for tok in tokens:
        if len(tok) >= 3:
            for i in range(len(tok) - 2):
                features.append(f"g:{tok[i : i + 3]}")
    if not features:
        features = ["_empty_"]

    for feat in features:
        digest = hashlib.sha256(feat.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        vec[0] = 1.0
        return vec
    return [float(v / norm) for v in vec]


class S3VectorKnowledgeStore:
    """Stores tenant-scoped documents in S3 (optionally KMS-encrypted) and indexes in S3 Vectors."""

    def __init__(
        self,
        factory: AWSClientFactory = aws_client_factory,
        bucket_name: Optional[str] = None,
        vector_bucket_name: Optional[str] = None,
        dimension: int = 64,
        kms_cipher: Optional[KMSEnvelopeCipher] = None,
    ) -> None:
        self._factory = factory
        self._bucket_name = bucket_name
        self._vector_bucket_name = vector_bucket_name
        self._dimension = dimension
        self._kms_cipher = kms_cipher

    @property
    def bucket_name(self) -> str:
        return self._bucket_name or settings.aws_s3_bucket

    @property
    def vector_bucket_name(self) -> str:
        return self._vector_bucket_name or settings.aws_s3_vector_bucket

    def _ensure_tenant_index_sync(self, index_name: str) -> None:
        s3v = self._factory.get_client("s3vectors")
        try:
            s3v.get_index(vectorBucketName=self.vector_bucket_name, indexName=index_name)
            return
        except ClientError:
            pass

        try:
            s3v.create_index(
                vectorBucketName=self.vector_bucket_name,
                indexName=index_name,
                dataType="float32",
                dimension=self._dimension,
                distanceMetric="cosine",
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if "Conflict" not in code and "AlreadyExists" not in code:
                raise

    def _put_s3_object_sync(self, key: str, body: bytes, metadata: dict[str, str]) -> None:
        s3 = self._factory.get_client("s3")
        s3.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=body,
            ContentType="text/plain; charset=utf-8",
            Metadata=metadata,
        )

    def _get_s3_object_sync(self, key: str) -> bytes:
        s3 = self._factory.get_client("s3")
        resp = s3.get_object(Bucket=self.bucket_name, Key=key)
        return bytes(resp["Body"].read())

    def _list_s3_keys_sync(self, prefix: str) -> List[str]:
        s3 = self._factory.get_client("s3")
        keys: List[str] = []
        continuation_token: Optional[str] = None
        while True:
            if continuation_token:
                resp = s3.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix,
                    ContinuationToken=continuation_token,
                )
            else:
                resp = s3.list_objects_v2(Bucket=self.bucket_name, Prefix=prefix)
            contents = resp.get("Contents", [])
            if isinstance(contents, list):
                for entry in contents:
                    if isinstance(entry, dict) and entry.get("Key"):
                        keys.append(str(entry["Key"]))
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
            if not token:
                break
            continuation_token = str(token)
        return keys

    def _delete_s3_keys_sync(self, keys: List[str]) -> None:
        if not keys:
            return
        s3 = self._factory.get_client("s3")
        for start in range(0, len(keys), _S3_DELETE_MAX_BATCH):
            batch = keys[start : start + _S3_DELETE_MAX_BATCH]
            s3.delete_objects(
                Bucket=self.bucket_name,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )

    def _delete_vectors_sync(self, index_name: str, vector_keys: List[str]) -> None:
        if not vector_keys:
            return
        s3v = self._factory.get_client("s3vectors")
        for start in range(0, len(vector_keys), _S3_VECTORS_MAX_BATCH):
            batch = vector_keys[start : start + _S3_VECTORS_MAX_BATCH]
            try:
                s3v.delete_vectors(
                    vectorBucketName=self.vector_bucket_name,
                    indexName=index_name,
                    keys=batch,
                )
            except ClientError as exc:
                code = str(exc.response.get("Error", {}).get("Code", ""))
                if "NotFound" not in code:
                    raise

    def _put_vectors_batch_sync(self, index_name: str, batch: List[VectorRecord]) -> None:
        s3v = self._factory.get_client("s3vectors")
        s3v.put_vectors(
            vectorBucketName=self.vector_bucket_name,
            indexName=index_name,
            vectors=batch,
        )

    def _query_vectors_sync(self, index_name: str, query_vec: List[float], top_k: int) -> List[JSONDict]:
        s3v = self._factory.get_client("s3vectors")
        try:
            resp = s3v.query_vectors(
                vectorBucketName=self.vector_bucket_name,
                indexName=index_name,
                queryVector={"float32": query_vec},
                topK=top_k,
                returnMetadata=True,
                returnDistance=True,
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if "NotFound" in code:
                return []
            raise
        raw_vectors = resp.get("vectors", [])
        return list(raw_vectors) if isinstance(raw_vectors, list) else []

    async def index_chunks(
        self,
        tenant_id: str,
        collection_id: str,
        source_uri: str,
        chunks: List[str],
    ) -> int:
        """Archive tenant chunks in S3 (KMS-wrapped when configured) and batch-index into S3 Vectors."""
        if not chunks:
            return 0

        index_name = sanitize_index_name(tenant_id)
        await asyncio.to_thread(self._ensure_tenant_index_sync, index_name)

        vectors: List[VectorRecord] = []
        written_s3_keys: List[str] = []
        written_vector_keys: List[str] = []
        try:
            for idx, chunk in enumerate(chunks):
                key = f"tenants/{tenant_id}/collections/{collection_id}/chunk-{idx:04d}.txt"
                encrypted = False
                if self._kms_cipher and self._kms_cipher.key_id:
                    payload_text = await self._kms_cipher.encrypt_text(tenant_id, chunk)
                    body = payload_text.encode("utf-8")
                    encrypted = True
                else:
                    body = chunk.encode("utf-8")

                await asyncio.to_thread(
                    self._put_s3_object_sync,
                    key,
                    body,
                    {
                        "tenant_id": tenant_id,
                        "collection_id": collection_id,
                        "kms_encrypted": "true" if encrypted else "false",
                    },
                )
                written_s3_keys.append(key)
                vectors.append(
                    {
                        "key": f"{collection_id}:{idx:04d}",
                        "data": {"float32": deterministic_embed(chunk, self._dimension)},
                        "metadata": {
                            "tenant_id": tenant_id,
                            "collection_id": collection_id,
                            "s3_key": key,
                            "source_uri": source_uri[:200],
                            "kms_encrypted": encrypted,
                            "preview": chunk[:400] if not encrypted else "",
                        },
                    }
                )

            for start in range(0, len(vectors), _S3_VECTORS_MAX_BATCH):
                batch = vectors[start : start + _S3_VECTORS_MAX_BATCH]
                await asyncio.to_thread(self._put_vectors_batch_sync, index_name, batch)
                written_vector_keys.extend(v["key"] for v in batch)
        except Exception:
            # Clean up partial writes so failed jobs leave neither orphaned vectors nor archived objects
            if written_vector_keys:
                try:
                    await asyncio.to_thread(self._delete_vectors_sync, index_name, written_vector_keys)
                except Exception as cleanup_exc:
                    logger.warning("Partial vector cleanup failed for '%s': %s", collection_id, cleanup_exc)
            if written_s3_keys:
                try:
                    await asyncio.to_thread(self._delete_s3_keys_sync, written_s3_keys)
                except Exception as cleanup_exc:
                    logger.warning("Partial S3 cleanup failed for '%s': %s", collection_id, cleanup_exc)
            raise

        logger.info(
            "Indexed %d chunks for tenant '%s' into S3 Vectors index '%s'",
            len(vectors),
            tenant_id,
            index_name,
        )
        return len(vectors)

    async def delete_collection_chunks(
        self,
        tenant_id: str,
        collection_id: str,
        chunk_count: Optional[int] = None,
    ) -> int:
        """Delete a tenant collection's vectors from S3 Vectors and archived chunks from S3."""
        index_name = sanitize_index_name(tenant_id)
        prefix = f"tenants/{tenant_id}/collections/{collection_id}/"
        s3_keys = await asyncio.to_thread(self._list_s3_keys_sync, prefix)

        vector_key_set: set[str] = set()
        for key in s3_keys:
            match = _CHUNK_KEY_RE.search(key)
            if match:
                vector_key_set.add(f"{collection_id}:{match.group(1)}")
        if chunk_count and chunk_count > 0:
            for idx in range(chunk_count):
                vector_key_set.add(f"{collection_id}:{idx:04d}")

        vector_keys = sorted(vector_key_set)
        if vector_keys:
            await asyncio.to_thread(self._delete_vectors_sync, index_name, vector_keys)
        if s3_keys:
            await asyncio.to_thread(self._delete_s3_keys_sync, s3_keys)

        removed = max(len(vector_keys), len(s3_keys))
        logger.info(
            "Deleted %d vectors and %d S3 objects for tenant '%s' collection '%s'",
            len(vector_keys),
            len(s3_keys),
            tenant_id,
            collection_id,
        )
        return removed

    async def query(self, tenant_id: str, query_text: str, top_k: int = 5) -> List[SearchDocument]:
        """Query only the caller's tenant-isolated S3 Vectors index and hydrate from S3."""
        index_name = sanitize_index_name(tenant_id)
        query_vec = deterministic_embed(query_text, self._dimension)
        hits = await asyncio.to_thread(self._query_vectors_sync, index_name, query_vec, top_k)

        docs: List[SearchDocument] = []
        for hit in hits:
            meta = hit.get("metadata")
            meta_dict: JSONDict = dict(meta) if isinstance(meta, dict) else {}
            # Defense-in-depth tenant assertion beyond per-tenant index partitioning
            if meta_dict.get("tenant_id") != tenant_id:
                logger.warning("Skipping cross-tenant vector mismatch for tenant '%s'", tenant_id)
                continue

            s3_key = str(meta_dict.get("s3_key", ""))
            content = str(meta_dict.get("preview", ""))
            if s3_key:
                try:
                    raw_bytes = await asyncio.to_thread(self._get_s3_object_sync, s3_key)
                except ClientError as exc:
                    code = str(exc.response.get("Error", {}).get("Code", ""))
                    if "NoSuchKey" in code or "NotFound" in code:
                        continue
                    raise
                raw_text = raw_bytes.decode("utf-8")
                if meta_dict.get("kms_encrypted") and self._kms_cipher:
                    content = await self._kms_cipher.decrypt_text(tenant_id, raw_text)
                else:
                    content = raw_text

            distance = float(hit.get("distance", 0.0))
            # Convert cosine distance in [0, 2] to similarity score in [0, 1]
            score = max(0.0, min(1.0, 1.0 - distance))
            docs.append(
                SearchDocument(
                    content=content,
                    metadata={
                        "source": "aws-s3-vectors",
                        "tenant_id": tenant_id,
                        "collection_id": str(meta_dict.get("collection_id", "")),
                        "s3_key": s3_key,
                        "source_uri": str(meta_dict.get("source_uri", "")),
                    },
                    score=score,
                )
            )
        return docs
