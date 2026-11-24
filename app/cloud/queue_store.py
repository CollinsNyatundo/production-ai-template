"""AWS SQS (with native DLQ RedrivePolicy) and DynamoDB multi-tenant state adapters."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional

from app.cloud.client import AWSClientFactory, aws_client_factory
from app.config import settings

logger = logging.getLogger("app.cloud.queue_store")


@dataclass(frozen=True)
class QueuedMessage:
    message_id: str
    receipt_handle: str
    body: dict[str, Any]


class SQSIngestionQueue:
    """SQS producer/consumer supporting native visibility timeout and DLQ redrive."""

    def __init__(
        self,
        factory: AWSClientFactory = aws_client_factory,
        queue_url: Optional[str] = None,
    ) -> None:
        self._factory = factory
        self._queue_url = queue_url

    @property
    def queue_url(self) -> str:
        return self._queue_url or settings.aws_sqs_queue_url

    def _send_sync(self, payload: dict[str, Any], target_url: str) -> str:
        sqs = self._factory.get_client("sqs")
        resp = sqs.send_message(QueueUrl=target_url, MessageBody=json.dumps(payload))
        return str(resp["MessageId"])

    def _receive_sync(self, target_url: str, max_messages: int, wait_seconds: int) -> List[QueuedMessage]:
        sqs = self._factory.get_client("sqs")
        resp = sqs.receive_message(
            QueueUrl=target_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
        )
        out: List[QueuedMessage] = []
        for raw in resp.get("Messages", []):
            out.append(
                QueuedMessage(
                    message_id=str(raw["MessageId"]),
                    receipt_handle=str(raw["ReceiptHandle"]),
                    body=json.loads(str(raw["Body"])),
                )
            )
        return out

    def _delete_sync(self, target_url: str, receipt_handle: str) -> None:
        sqs = self._factory.get_client("sqs")
        sqs.delete_message(QueueUrl=target_url, ReceiptHandle=receipt_handle)

    async def enqueue_job(self, job_payload: dict[str, Any], queue_url: Optional[str] = None) -> str:
        url = queue_url or self.queue_url
        if not url:
            raise ValueError("AWS_SQS_QUEUE_URL is required to enqueue ingestion jobs.")
        return await asyncio.to_thread(self._send_sync, job_payload, url)

    async def receive_jobs(
        self,
        max_messages: int = 1,
        wait_seconds: int = 1,
        queue_url: Optional[str] = None,
    ) -> List[QueuedMessage]:
        url = queue_url or self.queue_url
        if not url:
            raise ValueError("AWS_SQS_QUEUE_URL is required to receive ingestion jobs.")
        return await asyncio.to_thread(self._receive_sync, url, max_messages, wait_seconds)

    async def acknowledge(self, receipt_handle: str, queue_url: Optional[str] = None) -> None:
        url = queue_url or self.queue_url
        if not url:
            raise ValueError("AWS_SQS_QUEUE_URL is required to acknowledge messages.")
        await asyncio.to_thread(self._delete_sync, url, receipt_handle)


class DynamoDBStateRepository:
    """Tenant-partitioned DynamoDB repository for feedback ratings and audit records."""

    def __init__(
        self,
        factory: AWSClientFactory = aws_client_factory,
        table_name: Optional[str] = None,
    ) -> None:
        self._factory = factory
        self._table_name = table_name

    @property
    def table_name(self) -> str:
        return self._table_name or settings.aws_dynamodb_table

    def _put_feedback_sync(
        self,
        tenant_id: str,
        session_id: str,
        rating: str,
        comment: str,
    ) -> str:
        ddb = self._factory.get_client("dynamodb")
        feedback_id = f"fb-{uuid.uuid4().hex[:10]}"
        sk = f"FEEDBACK#{session_id}#{feedback_id}"
        ddb.put_item(
            TableName=self.table_name,
            Item={
                "tenant_id": {"S": tenant_id},
                "item_key": {"S": sk},
                "session_id": {"S": session_id},
                "rating": {"S": rating},
                "comment": {"S": comment},
                "created_at": {"S": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            },
        )
        return feedback_id

    def _list_feedback_sync(self, tenant_id: str, session_id: Optional[str] = None) -> List[dict[str, str]]:
        ddb = self._factory.get_client("dynamodb")
        prefix = f"FEEDBACK#{session_id}#" if session_id else "FEEDBACK#"
        resp = ddb.query(
            TableName=self.table_name,
            KeyConditionExpression="tenant_id = :t AND begins_with(item_key, :p)",
            ExpressionAttributeValues={
                ":t": {"S": tenant_id},
                ":p": {"S": prefix},
            },
        )
        rows: List[dict[str, str]] = []
        for item in resp.get("Items", []):
            rows.append(
                {
                    "tenant_id": str(item["tenant_id"]["S"]),
                    "item_key": str(item["item_key"]["S"]),
                    "session_id": str(item["session_id"]["S"]),
                    "rating": str(item["rating"]["S"]),
                    "comment": str(item.get("comment", {}).get("S", "")),
                    "created_at": str(item.get("created_at", {}).get("S", "")),
                }
            )
        return rows

    async def put_feedback(
        self,
        tenant_id: str,
        session_id: str,
        rating: str,
        comment: str = "",
    ) -> str:
        return await asyncio.to_thread(self._put_feedback_sync, tenant_id, session_id, rating, comment)

    async def list_feedback(self, tenant_id: str, session_id: Optional[str] = None) -> List[dict[str, str]]:
        return await asyncio.to_thread(self._list_feedback_sync, tenant_id, session_id)


sqs_ingestion_queue = SQSIngestionQueue()
dynamodb_state_repo = DynamoDBStateRepository()
