from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Generator

import httpx


DEFAULT_WORK_SELECT = (
    "id,doi,title,display_name,publication_year,publication_date,ids,authorships,"
    "primary_location,best_oa_location,open_access,cited_by_count,referenced_works,"
    "related_works,abstract_inverted_index,type,cited_by_api_url"
)
DEFAULT_AUTHOR_SELECT = (
    "id,display_name,works_count,cited_by_count,ids,last_known_institutions,"
    "summary_stats,works_api_url"
)


class OpenAlexClient:
    BASE_URL = "https://api.openalex.org"

    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        self.api_key = api_key or os.environ.get("OPENALEX_API_KEY")
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "OpenAlexClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _entity_key(value: str) -> str:
        normalized = str(value).strip().rstrip("/")
        if not normalized:
            return normalized
        return normalized.rsplit("/", 1)[-1]

    @staticmethod
    def _merge_filter(*filters: str | None) -> str | None:
        values = [item.strip() for item in filters if item and item.strip()]
        return ",".join(values) if values else None

    @staticmethod
    def _abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str | None:
        if not index:
            return None
        positions: dict[int, str] = {}
        for token, token_positions in index.items():
            for position in token_positions:
                positions[int(position)] = token
        if not positions:
            return None
        return " ".join(positions[index] for index in sorted(positions))

    @staticmethod
    def _location_pdf_url(location: dict[str, Any] | None) -> str | None:
        if not location:
            return None
        pdf_url = location.get("pdf_url")
        return str(pdf_url) if pdf_url else None

    @staticmethod
    def _safe_filename(value: str) -> str:
        name = OpenAlexClient._entity_key(value)
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", name) or "openalex_work"

    def _params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = {key: value for key, value in (params or {}).items() if value not in (None, "")}
        if self.api_key:
            merged["api_key"] = self.api_key
        return merged

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        kwargs["params"] = self._params(kwargs.get("params"))
        response = self.client.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()

    def normalize_author(self, author: dict[str, Any]) -> dict[str, Any]:
        author_id = author.get("id")
        return {
            "authorId": self._entity_key(author_id) if author_id else None,
            "openalex_id": author_id,
            "name": author.get("display_name"),
            "url": author_id,
            "paperCount": author.get("works_count"),
            "citationCount": author.get("cited_by_count"),
            "ids": author.get("ids") or {},
            "institutions": author.get("last_known_institutions") or [],
            "summary_stats": author.get("summary_stats") or {},
        }

    def normalize_work(self, work: dict[str, Any]) -> dict[str, Any]:
        work_id = work.get("id")
        ids = work.get("ids") or {}
        primary_location = work.get("primary_location") or {}
        best_oa_location = work.get("best_oa_location") or {}
        source = primary_location.get("source") or {}
        open_access = work.get("open_access") or {}
        pdf_url = self._location_pdf_url(best_oa_location) or self._location_pdf_url(primary_location)

        authors = []
        for authorship in work.get("authorships") or []:
            author = authorship.get("author") or {}
            author_id = author.get("id")
            authors.append(
                {
                    "authorId": self._entity_key(author_id) if author_id else None,
                    "openalex_id": author_id,
                    "name": author.get("display_name"),
                    "url": author_id,
                    "institutions": authorship.get("institutions") or [],
                    "raw_author_name": authorship.get("raw_author_name"),
                }
            )

        external_ids: dict[str, Any] = {
            "OpenAlex": work_id,
            "DOI": ids.get("doi") or work.get("doi"),
            "PMID": ids.get("pmid"),
            "PMCID": ids.get("pmcid"),
            "MAG": ids.get("mag"),
        }
        external_ids = {key: value for key, value in external_ids.items() if value}

        return {
            "paperId": self._entity_key(work_id) if work_id else None,
            "openalex_id": work_id,
            "title": work.get("title") or work.get("display_name"),
            "year": work.get("publication_year"),
            "publicationDate": work.get("publication_date"),
            "authors": authors,
            "venue": source.get("display_name"),
            "url": ids.get("openalex") or work_id,
            "doi": ids.get("doi") or work.get("doi"),
            "abstract": self._abstract_from_inverted_index(work.get("abstract_inverted_index")),
            "citationCount": work.get("cited_by_count"),
            "externalIds": external_ids,
            "isOpenAccess": open_access.get("is_oa"),
            "openAccessPdf": {"url": pdf_url} if pdf_url else None,
            "type": work.get("type"),
            "referencedWorks": work.get("referenced_works") or [],
            "relatedWorks": work.get("related_works") or [],
            "raw": work,
        }

    def _with_normalized_works(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = [self.normalize_work(work) for work in payload.get("results", [])]
        enriched = dict(payload)
        enriched["data"] = data
        enriched["total"] = (payload.get("meta") or {}).get("count")
        return enriched

    def get_work(
        self,
        work_id: str,
        select: str = DEFAULT_WORK_SELECT,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.BASE_URL}/works/{self._entity_key(work_id)}",
            params={"select": select},
            timeout=timeout,
        )

    def get_paper(
        self,
        paper_id: str,
        fields: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        return self.normalize_work(self.get_work(paper_id, select=fields or DEFAULT_WORK_SELECT, timeout=timeout))

    def search_works_page(
        self,
        query: str,
        per_page: int = 25,
        select: str = DEFAULT_WORK_SELECT,
        cursor: str | None = None,
        filters: str | None = None,
        sort: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "search": query,
            "per_page": max(1, min(100, per_page)),
            "select": select,
        }
        if cursor:
            params["cursor"] = cursor
        if filters:
            params["filter"] = filters
        if sort:
            params["sort"] = sort
        payload = self._request("GET", f"{self.BASE_URL}/works", params=params, timeout=timeout)
        return self._with_normalized_works(payload)

    def search_papers(
        self,
        query: str,
        limit: int = 10,
        fields: str | None = None,
        timeout: float | None = None,
        filters: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        if limit <= 200:
            payload = self.search_works_page(
                query=query,
                per_page=limit,
                select=fields or DEFAULT_WORK_SELECT,
                filters=filters,
                sort=sort,
                timeout=timeout,
            )
            payload["data"] = payload.get("data", [])[:limit]
            return payload

        papers = list(
            self.search_papers_bulk(
                query=query,
                fields=fields,
                max_results=limit,
                timeout=timeout,
                filters=filters,
                sort=sort,
            )
        )
        return {"meta": {"count": None}, "total": None, "data": papers, "results": [], "query": query}

    def search_papers_bulk(
        self,
        query: str,
        fields: str | None = None,
        max_results: int | None = None,
        timeout: float | None = None,
        filters: str | None = None,
        sort: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        cursor: str | None = "*"
        yielded = 0
        while True:
            remaining = None if max_results is None else max_results - yielded
            if remaining is not None and remaining <= 0:
                return
            payload = self.search_works_page(
                query=query,
                per_page=min(100, remaining or 100),
                select=fields or DEFAULT_WORK_SELECT,
                cursor=cursor,
                filters=filters,
                sort=sort,
                timeout=timeout,
            )
            data = payload.get("data", [])
            for paper in data:
                yield paper
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return
            cursor = (payload.get("meta") or {}).get("next_cursor")
            if not cursor or not data:
                return

    def get_recommendations(
        self,
        paper_id: str,
        limit: int = 10,
        fields: str | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        work = self.get_work(
            paper_id,
            select="id,related_works",
            timeout=timeout,
        )
        related_ids = [self._entity_key(item) for item in work.get("related_works", [])][:limit]
        recommendations: list[dict[str, Any]] = []
        for related_id in related_ids:
            recommendations.append(self.get_paper(related_id, fields=fields, timeout=timeout))
        return recommendations

    def _get_filtered_works(
        self,
        filters: str,
        limit: int,
        fields: str | None = None,
        sort: str | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        works: list[dict[str, Any]] = []
        cursor: str | None = "*"
        while len(works) < limit:
            payload = self._request(
                "GET",
                f"{self.BASE_URL}/works",
                params={
                    "filter": filters,
                    "cursor": cursor,
                    "per_page": max(1, min(100, limit - len(works))),
                    "select": fields or DEFAULT_WORK_SELECT,
                    "sort": sort,
                },
                timeout=timeout,
            )
            page = self._with_normalized_works(payload).get("data", [])
            works.extend(page)
            cursor = (payload.get("meta") or {}).get("next_cursor")
            if not cursor or not page:
                break
        return works[:limit]

    def get_paper_citations(
        self,
        paper_id: str,
        limit: int = 50,
        fields: str | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        return self._get_filtered_works(
            filters=f"cites:{self._entity_key(paper_id)}",
            limit=limit,
            fields=fields,
            sort="cited_by_count:desc",
            timeout=timeout,
        )

    def get_paper_references(
        self,
        paper_id: str,
        limit: int = 50,
        fields: str | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        return self._get_filtered_works(
            filters=f"cited_by:{self._entity_key(paper_id)}",
            limit=limit,
            fields=fields,
            sort="cited_by_count:desc",
            timeout=timeout,
        )

    def search_author(
        self,
        query: str,
        limit: int = 10,
        fields: str = DEFAULT_AUTHOR_SELECT,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"{self.BASE_URL}/authors",
            params={"search": query, "per_page": max(1, min(100, limit)), "select": fields},
            timeout=timeout,
        )
        data = [self.normalize_author(author) for author in payload.get("results", [])]
        enriched = dict(payload)
        enriched["data"] = data
        enriched["total"] = (payload.get("meta") or {}).get("count")
        return enriched

    def get_author(
        self,
        author_id: str,
        fields: str = DEFAULT_AUTHOR_SELECT,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        payload = self._request(
            "GET",
            f"{self.BASE_URL}/authors/{self._entity_key(author_id)}",
            params={"select": fields},
            timeout=timeout,
        )
        return self.normalize_author(payload)

    def get_author_papers(
        self,
        author_id: str,
        limit: int = 50,
        fields: str | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        return self._get_filtered_works(
            filters=f"author.id:{self._entity_key(author_id)}",
            limit=limit,
            fields=fields,
            sort="cited_by_count:desc",
            timeout=timeout,
        )

    def download_open_access_pdf(
        self,
        paper_id: str,
        directory: str | Path = "papers",
        user_agent: str = "AutoScholar/2.0",
        timeout: float | None = None,
    ) -> Path | None:
        work = self.get_work(
            paper_id,
            select="id,primary_location,best_oa_location,open_access",
            timeout=timeout,
        )
        pdf_url = self._location_pdf_url(work.get("best_oa_location")) or self._location_pdf_url(
            work.get("primary_location")
        )
        if not pdf_url:
            return None

        target_dir = Path(directory).resolve()
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{self._safe_filename(paper_id)}.pdf"
        if target_path.exists():
            return target_path

        headers = {"user-agent": user_agent}
        with self.client.stream("GET", pdf_url, headers=headers, timeout=timeout) as response:
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "pdf" not in content_type and not pdf_url.lower().endswith(".pdf"):
                return None
            with target_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        return target_path
