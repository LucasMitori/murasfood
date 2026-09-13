"""
A private download has to be reachable from a browser.

Public assets already used `S3_PUBLIC_ENDPOINT`; private ones did not. Their
presigned URLs were signed against the endpoint the *API* talks to, which in
Docker is `minio:9000` — a name that resolves on the compose network and
nowhere else. Reports were generated correctly and then handed to the merchant
as a link their browser could not open.

The host cannot simply be rewritten afterwards: SigV4 signs the Host header, so
a URL signed for one host and requested on another fails the signature check.
It has to be signed for the host it will be requested on, which means a second
client bound to the public address.
"""

from __future__ import annotations

from typing import Any

import pytest

from apps.media.storage import S3CompatibleStorage


@pytest.fixture
def s3_settings(settings: Any) -> Any:
    settings.S3_ENDPOINT = "http://minio:9000"
    settings.S3_BUCKET = "murasfood-media"
    settings.S3_ACCESS_KEY = "key"
    settings.S3_SECRET_KEY = "secret"
    settings.S3_REGION = "us-east-1"
    settings.S3_SIGNED_URL_TTL_SECONDS = 900
    return settings


class TestSigningEndpoint:
    def test_a_public_endpoint_gets_its_own_signing_client(self, s3_settings: Any) -> None:
        """Signed for the address the browser will use, not the internal one."""
        s3_settings.S3_PUBLIC_ENDPOINT = "http://localhost:9000"

        storage = S3CompatibleStorage()

        assert storage._signing_client is not storage._client
        assert "localhost:9000" in storage._signing_client.meta.endpoint_url

    def test_a_signed_url_points_at_the_public_host(self, s3_settings: Any) -> None:
        """The property that was broken: the link a merchant clicks."""
        s3_settings.S3_PUBLIC_ENDPOINT = "http://localhost:9000"

        url = S3CompatibleStorage().url("reports/vendas.csv", public=False)

        assert url.startswith("http://localhost:9000/")
        assert "minio:9000" not in url
        # Still signed — this is a private document, not a public link.
        assert "X-Amz-Signature" in url

    def test_one_client_is_reused_when_the_addresses_match(self, s3_settings: Any) -> None:
        """A deployment where the API and the browser share an endpoint — most
        real ones — should not pay for a second client."""
        s3_settings.S3_PUBLIC_ENDPOINT = s3_settings.S3_ENDPOINT

        storage = S3CompatibleStorage()

        assert storage._signing_client is storage._client
