from __future__ import annotations

from typing import Any

import httpx

from autoscholar.integrations.openalex import OpenAlexClient


def test_openalex_client_adds_api_key_query_param(monkeypatch) -> None:
    client = OpenAlexClient(api_key="demo-key")
    seen: dict[str, Any] = {}

    def fake_request(method: str, url: str, **kwargs: Any) -> httpx.Response:
        seen["method"] = method
        seen["url"] = url
        seen["params"] = kwargs["params"]
        request = httpx.Request(method, url)
        return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(client.client, "request", fake_request)

    assert client._request("GET", "https://api.openalex.org/works", params={"select": "id"}) == {"ok": True}
    assert seen["params"] == {"select": "id", "api_key": "demo-key"}
    client.close()


def test_openalex_normalizes_work_to_semantic_like_shape() -> None:
    client = OpenAlexClient()
    paper = client.normalize_work(
        {
            "id": "https://openalex.org/W1",
            "display_name": "Demo Work",
            "publication_year": 2024,
            "abstract_inverted_index": {"Hello": [0], "world": [1]},
            "cited_by_count": 12,
            "ids": {"doi": "https://doi.org/10.1/demo"},
            "authorships": [
                {
                    "author": {"id": "https://openalex.org/A1", "display_name": "Ada Lovelace"},
                    "raw_author_name": "Ada Lovelace",
                }
            ],
            "primary_location": {"source": {"display_name": "Demo Venue"}},
            "open_access": {"is_oa": True},
        }
    )

    assert paper["paperId"] == "W1"
    assert paper["title"] == "Demo Work"
    assert paper["year"] == 2024
    assert paper["abstract"] == "Hello world"
    assert paper["citationCount"] == 12
    assert paper["venue"] == "Demo Venue"
    assert paper["externalIds"]["DOI"] == "https://doi.org/10.1/demo"
    assert paper["authors"][0]["authorId"] == "A1"
    client.close()


def test_openalex_filtered_works_uses_cursor_pagination(monkeypatch) -> None:
    client = OpenAlexClient()
    calls: list[dict[str, Any]] = []

    def fake_request(_method: str, _url: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs["params"])
        if len(calls) == 1:
            return {
                "meta": {"next_cursor": "next-page"},
                "results": [{"id": "https://openalex.org/W1", "display_name": "First"}],
            }
        return {
            "meta": {"next_cursor": None},
            "results": [{"id": "https://openalex.org/W2", "display_name": "Second"}],
        }

    monkeypatch.setattr(client, "_request", fake_request)

    papers = client._get_filtered_works("cites:W0", limit=2, fields="id,display_name")

    assert [paper["paperId"] for paper in papers] == ["W1", "W2"]
    assert calls[0]["cursor"] == "*"
    assert calls[1]["cursor"] == "next-page"
    client.close()
