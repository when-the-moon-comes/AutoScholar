from __future__ import annotations

import os

import pytest

from autoscholar.integrations import SemanticScholarClient


@pytest.mark.live
def test_semantic_scholar_live_smoke() -> None:
    api_key = os.environ.get("S2_API_KEY")
    if not api_key:
        pytest.skip("S2_API_KEY is not set")

    with SemanticScholarClient(api_key=api_key, timeout=30.0) as client:
        payload = client.search_papers(
            query="medical image segmentation",
            limit=1,
            fields="paperId,title,year",
            timeout=30.0,
        )
        papers = payload.get("data", [])
        assert papers, "search returned no papers"
        paper_id = papers[0].get("paperId")
        assert paper_id, "top search result had no paperId"
        recommendations = client.get_recommendations(
            paper_id=paper_id,
            limit=1,
            fields="paperId,title,year",
            timeout=30.0,
        )
        assert isinstance(recommendations, list)
