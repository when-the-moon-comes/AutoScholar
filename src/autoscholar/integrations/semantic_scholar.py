from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Generator, Sequence

import httpx


class SemanticScholarClient:
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    RECOMMENDATIONS_URL = "https://api.semanticscholar.org/recommendations/v1"

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        self.api_key = api_key or os.environ.get("S2_API_KEY")
        headers = {}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        self.client = httpx.Client(headers=headers, timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "SemanticScholarClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _serialize_multi_value(value: Sequence[str] | str | None) -> str | None:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        items = [str(item).strip() for item in value if str(item).strip()]
        return ",".join(items) if items else None

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        response = self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def get_paper(
        self,
        paper_id: str,
        fields: str = "paperId,title,authors,year,abstract",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.BASE_URL}/paper/{paper_id}",
            params={"fields": fields},
            timeout=timeout,
        )

    def get_papers_batch(
        self,
        paper_ids: list[str],
        fields: str = "paperId,title,authors,year,abstract",
        batch_size: int = 100,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index in range(0, len(paper_ids), batch_size):
            batch = paper_ids[index:index + batch_size]
            results.extend(
                self._request(
                    "POST",
                    f"{self.BASE_URL}/paper/batch",
                    params={"fields": fields},
                    json={"ids": batch},
                    timeout=timeout,
                )
            )
        return results

    def search_papers(
        self,
        query: str,
        limit: int = 10,
        fields: str = "title,url,year,authors",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.BASE_URL}/paper/search",
            params={"query": query, "limit": limit, "fields": fields},
            timeout=timeout,
        )

    def search_papers_bulk_page(
        self,
        query: str,
        fields: str = "title,year,authors",
        token: str | None = None,
        sort: str | None = None,
        publication_types: Sequence[str] | str | None = None,
        open_access_pdf: bool | None = None,
        min_citation_count: int | None = None,
        publication_date_or_year: str | None = None,
        year: str | None = None,
        venue: str | None = None,
        fields_of_study: Sequence[str] | str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"query": query, "fields": fields}
        if token:
            params["token"] = token
        if sort:
            params["sort"] = sort
        publication_types_value = self._serialize_multi_value(publication_types)
        if publication_types_value:
            params["publicationTypes"] = publication_types_value
        if open_access_pdf is not None:
            params["openAccessPdf"] = open_access_pdf
        if min_citation_count is not None:
            params["minCitationCount"] = min_citation_count
        if publication_date_or_year:
            params["publicationDateOrYear"] = publication_date_or_year
        if year:
            params["year"] = year
        if venue:
            params["venue"] = venue
        fields_of_study_value = self._serialize_multi_value(fields_of_study)
        if fields_of_study_value:
            params["fieldsOfStudy"] = fields_of_study_value
        return self._request(
            "GET",
            f"{self.BASE_URL}/paper/search/bulk",
            params=params,
            timeout=timeout,
        )

    def search_papers_bulk(
        self,
        query: str,
        fields: str = "title,year,authors",
        max_results: int | None = None,
        **kwargs: Any,
    ) -> Generator[dict[str, Any], None, None]:
        token: str | None = None
        yielded = 0
        while True:
            payload = self.search_papers_bulk_page(
                query=query,
                fields=fields,
                token=token,
                **kwargs,
            )
            for paper in payload.get("data", []):
                yield paper
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return
            token = payload.get("token")
            if not token:
                return

    def get_recommendations(
        self,
        paper_id: str,
        limit: int = 10,
        fields: str = "title,url,year",
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{self.RECOMMENDATIONS_URL}/papers/forpaper/{paper_id}",
            params={"fields": fields, "limit": limit},
            timeout=timeout,
        )
        return payload.get("recommendedPapers", [])

    def get_recommendations_from_lists(
        self,
        positive_paper_ids: Sequence[str],
        negative_paper_ids: Sequence[str] | None = None,
        limit: int = 10,
        fields: str = "title,url,year",
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "positivePaperIds": [str(item).strip() for item in positive_paper_ids if str(item).strip()],
        }
        negative = [str(item).strip() for item in (negative_paper_ids or []) if str(item).strip()]
        if negative:
            payload["negativePaperIds"] = negative
        data = self._request(
            "POST",
            f"{self.RECOMMENDATIONS_URL}/papers",
            params={"fields": fields, "limit": limit},
            json=payload,
            timeout=timeout,
        )
        return data.get("recommendedPapers", [])

    def search_author(
        self,
        query: str,
        fields: str = "authorId,name,url",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.BASE_URL}/author/search",
            params={"query": query, "fields": fields},
            timeout=timeout,
        )

    def get_author(
        self,
        author_id: str,
        fields: str = "authorId,name,url,paperCount,citationCount",
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.BASE_URL}/author/{author_id}",
            params={"fields": fields},
            timeout=timeout,
        )

    def get_author_papers(
        self,
        author_id: str,
        limit: int = 1000,
        fields: str = "title,url,year",
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            f"{self.BASE_URL}/author/{author_id}/papers",
            params={"fields": fields, "limit": limit},
            timeout=timeout,
        )
        return payload.get("data", [])

    def download_open_access_pdf(
        self,
        paper_id: str,
        directory: str | Path = "papers",
        user_agent: str = "AutoScholar/2.0",
        timeout: float | None = None,
    ) -> Path | None:
        paper = self.get_paper(
            paper_id,
            fields="paperId,isOpenAccess,openAccessPdf",
            timeout=timeout,
        )

        if not paper.get("isOpenAccess") or not paper.get("openAccessPdf"):
            return None

        pdf_url = (paper.get("openAccessPdf") or {}).get("url")
        if not pdf_url:
            return None

        target_dir = Path(directory).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{paper_id}.pdf"
        if target_path.exists():
            return target_path

        headers = {"user-agent": user_agent}
        with self.client.stream("GET", pdf_url, headers=headers, timeout=timeout) as response:
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "pdf" not in content_type:
                return None
            with target_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return target_path

    def _get_citation_edges(
        self,
        base_url: str,
        fields: str = "title,authors",
        timeout: float | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        page_size = 1000
        offset = 0
        while True:
            payload = self._request(
                "GET",
                base_url,
                params={"fields": fields, "limit": page_size, "offset": offset},
                timeout=timeout,
            )
            data = payload.get("data", [])
            for item in data:
                yield item
            if len(data) < page_size:
                return
            offset += page_size

    def get_paper_citations(
        self,
        paper_id: str,
        fields: str = "title,authors",
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        edges = self._get_citation_edges(
            f"{self.BASE_URL}/paper/{paper_id}/citations",
            fields=fields,
            timeout=timeout,
        )
        return [edge["citingPaper"] for edge in edges if "citingPaper" in edge]

    def get_paper_references(
        self,
        paper_id: str,
        fields: str = "title,authors",
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        edges = self._get_citation_edges(
            f"{self.BASE_URL}/paper/{paper_id}/references",
            fields=fields,
            timeout=timeout,
        )
        return [edge["citedPaper"] for edge in edges if "citedPaper" in edge]
