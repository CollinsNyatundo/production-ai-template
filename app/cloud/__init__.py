"""Optional AWS cloud-native adapters (verified locally via aws/aws-emulator)."""

from app.cloud.client import AWSClientFactory, aws_client_factory
from app.cloud.queue_store import (
    DynamoDBStateRepository,
    QueuedMessage,
    SQSIngestionQueue,
    dynamodb_state_repo,
    sqs_ingestion_queue,
)
from app.cloud.secrets import AWSSecretsProvider, KMSEnvelopeCipher, aws_secrets_provider, kms_envelope_cipher
from app.cloud.telemetry import AWSObservabilitySink, aws_observability_sink
from app.cloud.vector_store import S3VectorKnowledgeStore, deterministic_embed, sanitize_index_name

__all__ = [
    "AWSClientFactory",
    "AWSObservabilitySink",
    "AWSSecretsProvider",
    "DynamoDBStateRepository",
    "KMSEnvelopeCipher",
    "QueuedMessage",
    "S3VectorKnowledgeStore",
    "SQSIngestionQueue",
    "aws_client_factory",
    "aws_observability_sink",
    "aws_secrets_provider",
    "deterministic_embed",
    "dynamodb_state_repo",
    "kms_envelope_cipher",
    "sanitize_index_name",
    "sqs_ingestion_queue",
]
