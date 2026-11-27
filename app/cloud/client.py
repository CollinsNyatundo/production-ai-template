"""AWS client factory for local AWS Emulator and production AWS runtimes."""

from __future__ import annotations

import logging
import os
from typing import Optional

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from app.config import settings

logger = logging.getLogger("app.cloud.client")


class AWSClientFactory:
    """Builds boto3 service clients honoring standard AWS env vars and path-style S3."""

    def __init__(
        self,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        ca_bundle: Optional[str] = None,
    ) -> None:
        self._region_name = region_name
        self._endpoint_url = endpoint_url
        self._ca_bundle = ca_bundle
        self._clients: dict[str, BaseClient] = {}

    @property
    def region_name(self) -> str:
        return (
            self._region_name
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or settings.aws_region
        )

    @property
    def endpoint_url(self) -> Optional[str]:
        ep = self._endpoint_url or os.environ.get("AWS_ENDPOINT_URL") or settings.aws_endpoint_url
        return ep or None

    @property
    def verify(self) -> str | bool:
        ca = self._ca_bundle or os.environ.get("AWS_CA_BUNDLE") or settings.aws_ca_bundle
        return ca if ca else True

    def get_client(self, service_name: str) -> BaseClient:
        if service_name in self._clients:
            return self._clients[service_name]

        if service_name == "s3":
            # Path-style addressing works cleanly on both AWS Emulator (avoids virtual-host bug) and S3
            cfg = Config(region_name=self.region_name, s3={"addressing_style": "path"})
        else:
            cfg = Config(region_name=self.region_name)

        if self.endpoint_url:
            client: BaseClient = boto3.client(
                service_name,
                config=cfg,
                verify=self.verify,
                endpoint_url=self.endpoint_url,
            )
        else:
            client = boto3.client(
                service_name,
                config=cfg,
                verify=self.verify,
            )
        self._clients[service_name] = client
        return client

    def reset(self) -> None:
        self._clients.clear()


aws_client_factory = AWSClientFactory()
