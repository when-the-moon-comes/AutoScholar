from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import requests

from SemanticScholarApi import SemanticScholarClient as CompatSemanticScholarClient
from autoscholar.integrations import SemanticScholarClient


def test_legacy_semantic_scholar_api_reexports_v2_client() -> None:
    assert issubclass(CompatSemanticScholarClient, SemanticScholarClient)


def test_legacy_semantic_scholar_api_download_returns_path(tmp_path: Path, monkeypatch) -> None:
    class _FakeStream:
        headers = {"content-type": "application/pdf"}

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"%PDF-1.4\n"

    client = CompatSemanticScholarClient()
    monkeypatch.setattr(
        client,
        "get_paper",
        lambda *_args, **_kwargs: {
            "paperId": "demo",
            "isOpenAccess": True,
            "openAccessPdf": {"url": "https://example.test/demo.pdf"},
        },
    )
    monkeypatch.setattr(client.client, "stream", lambda *_args, **_kwargs: _FakeStream())

    output = client.download_open_access_pdf("demo", tmp_path)

    assert output == tmp_path.resolve() / "demo.pdf"
    assert output.read_bytes().startswith(b"%PDF")
    client.close()


def test_legacy_semantic_scholar_api_exceptions_match_old_and_new_handlers(monkeypatch) -> None:
    client = CompatSemanticScholarClient()

    def _raise_status(*_args, **_kwargs):
        request = httpx.Request("GET", "https://example.test")
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)

    monkeypatch.setattr(client.client, "request", _raise_status)

    with pytest.raises(httpx.HTTPStatusError) as new_exc:
        client.search_papers("demo")
    assert new_exc.value.response.status_code == 429

    with pytest.raises(requests.exceptions.HTTPError) as old_exc:
        client.search_papers("demo")
    assert old_exc.value.response.status_code == 429
    client.close()
