import os
from typing import Any, Dict, Generator, List, Optional, Sequence

import requests
import urllib3

urllib3.disable_warnings()


class SemanticScholarClient:
    """
    Client for interacting with the Semantic Scholar Graph API.
    Based on the examples provided in the s2-folks repository.
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    RECOMMENDATIONS_URL = "https://api.semanticscholar.org/recommendations/v1"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the API client.
        :param api_key: Semantic Scholar API key. If not provided, it attempts to read from the
                        S2_API_KEY env variable. The API can work without a key, but with stricter
                        rate limits.
        """
        self.api_key = api_key or os.environ.get("S2_API_KEY")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-API-KEY": self.api_key})

    def close(self):
        """Close the requests session."""
        self.session.close()

    def _serialize_multi_value(self, value: Optional[Sequence[str] | str]) -> Optional[str]:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None

        items = [str(item).strip() for item in value if str(item).strip()]
        if not items:
            return None
        return ",".join(items)

    def _build_bulk_search_params(
        self,
        query: str,
        fields: str,
        token: Optional[str] = None,
        sort: Optional[str] = None,
        publication_types: Optional[Sequence[str] | str] = None,
        open_access_pdf: Optional[bool] = None,
        min_citation_count: Optional[int] = None,
        publication_date_or_year: Optional[str] = None,
        year: Optional[str] = None,
        venue: Optional[str] = None,
        fields_of_study: Optional[Sequence[str] | str] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "query": query,
            "fields": fields,
        }
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

        return params

    def get_paper(
        self,
        paper_id: str,
        fields: str = "paperId,title,authors,year,abstract",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve details for a specific paper by ID.
        """
        response = self.session.get(
            f"{self.BASE_URL}/paper/{paper_id}",
            params={"fields": fields},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_papers_batch(
        self,
        paper_ids: List[str],
        fields: str = "paperId,title,authors,year,abstract",
        batch_size: int = 100,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve details for multiple papers in batches.
        """
        results = []
        for i in range(0, len(paper_ids), batch_size):
            batch = paper_ids[i:i + batch_size]
            response = self.session.post(
                f"{self.BASE_URL}/paper/batch",
                params={"fields": fields},
                json={"ids": batch},
                timeout=timeout,
            )
            response.raise_for_status()
            results.extend(response.json())
        return results

    def search_papers(
        self,
        query: str,
        limit: int = 10,
        fields: str = "title,url,year,authors",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Search for papers based on a query.
        Returns a dictionary containing 'total' and 'data' (list of papers).
        """
        response = self.session.get(
            f"{self.BASE_URL}/paper/search",
            params={"query": query, "limit": limit, "fields": fields},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def search_papers_bulk_page(
        self,
        query: str,
        fields: str = "title,year,authors",
        token: Optional[str] = None,
        sort: Optional[str] = None,
        publication_types: Optional[Sequence[str] | str] = None,
        open_access_pdf: Optional[bool] = None,
        min_citation_count: Optional[int] = None,
        publication_date_or_year: Optional[str] = None,
        year: Optional[str] = None,
        venue: Optional[str] = None,
        fields_of_study: Optional[Sequence[str] | str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Fetch a single page from the bulk search endpoint.
        """
        params = self._build_bulk_search_params(
            query=query,
            fields=fields,
            token=token,
            sort=sort,
            publication_types=publication_types,
            open_access_pdf=open_access_pdf,
            min_citation_count=min_citation_count,
            publication_date_or_year=publication_date_or_year,
            year=year,
            venue=venue,
            fields_of_study=fields_of_study,
        )
        response = self.session.get(
            f"{self.BASE_URL}/paper/search/bulk",
            params=params,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def search_papers_bulk(
        self,
        query: str,
        fields: str = "title,year,authors",
        year: Optional[str] = None,
        max_results: Optional[int] = None,
        sort: Optional[str] = None,
        publication_types: Optional[Sequence[str] | str] = None,
        open_access_pdf: Optional[bool] = None,
        min_citation_count: Optional[int] = None,
        publication_date_or_year: Optional[str] = None,
        venue: Optional[str] = None,
        fields_of_study: Optional[Sequence[str] | str] = None,
        timeout: Optional[float] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Search bulk endpoint, fetching results page by page.
        Returns a generator yielding individual paper dictionaries.
        """
        token: Optional[str] = None
        yielded = 0

        while True:
            response = self.search_papers_bulk_page(
                query=query,
                fields=fields,
                token=token,
                sort=sort,
                publication_types=publication_types,
                open_access_pdf=open_access_pdf,
                min_citation_count=min_citation_count,
                publication_date_or_year=publication_date_or_year,
                year=year,
                venue=venue,
                fields_of_study=fields_of_study,
                timeout=timeout,
            )
            for paper in response.get("data", []):
                yield paper
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return

            token = response.get("token")
            if not token:
                return

    def get_recommendations(
        self,
        paper_id: str,
        limit: int = 10,
        fields: str = "title,url,year",
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get paper recommendations based on a single paper.
        """
        response = self.session.get(
            f"{self.RECOMMENDATIONS_URL}/papers/forpaper/{paper_id}",
            params={"fields": fields, "limit": limit},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json().get("recommendedPapers", [])

    def get_recommendations_from_lists(
        self,
        positive_paper_ids: Sequence[str],
        negative_paper_ids: Optional[Sequence[str]] = None,
        limit: int = 10,
        fields: str = "title,url,year",
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get paper recommendations using a list of positive seed papers and an optional list of
        negative seed papers.
        """
        positive_ids = [str(paper_id).strip() for paper_id in positive_paper_ids if str(paper_id).strip()]
        if not positive_ids:
            raise ValueError("positive_paper_ids must contain at least one paper ID.")

        payload: Dict[str, Any] = {
            "positivePaperIds": positive_ids,
        }
        negative_ids = [str(paper_id).strip() for paper_id in (negative_paper_ids or []) if str(paper_id).strip()]
        if negative_ids:
            payload["negativePaperIds"] = negative_ids

        response = self.session.post(
            f"{self.RECOMMENDATIONS_URL}/papers",
            params={"fields": fields, "limit": limit},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json().get("recommendedPapers", [])

    def search_author(
        self,
        query: str,
        fields: str = "authorId,name,url",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Search for an author by name.
        Returns a dictionary containing 'total' and 'data' (list of authors).
        """
        response = self.session.get(
            f"{self.BASE_URL}/author/search",
            params={"query": query, "fields": fields},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_author(
        self,
        author_id: str,
        fields: str = "authorId,name,url,paperCount,citationCount",
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve author information by ID.
        """
        response = self.session.get(
            f"{self.BASE_URL}/author/{author_id}",
            params={"fields": fields},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_author_papers(
        self,
        author_id: str,
        limit: int = 1000,
        fields: str = "title,url,year",
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get papers by a specific author.
        """
        response = self.session.get(
            f"{self.BASE_URL}/author/{author_id}/papers",
            params={"fields": fields, "limit": limit},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def download_open_access_pdf(
        self,
        paper_id: str,
        directory: str = "papers",
        user_agent: str = "requests/2.0.0",
    ) -> Optional[str]:
        """
        Download the PDF for a paper if it is Open Access.
        Returns the path to the downloaded PDF, or None if not available.
        """
        paper = self.get_paper(paper_id, fields="paperId,isOpenAccess,openAccessPdf")

        if not paper.get("isOpenAccess") or not paper.get("openAccessPdf"):
            return None

        pdf_url = paper["openAccessPdf"].get("url")
        if not pdf_url:
            return None

        os.makedirs(directory, exist_ok=True)
        pdf_path = os.path.join(directory, f"{paper_id}.pdf")

        if not os.path.exists(pdf_path):
            headers = {"user-agent": user_agent}
            with self.session.get(pdf_url, headers=headers, stream=True, verify=False) as response:
                response.raise_for_status()
                if response.headers.get("content-type") != "application/pdf":
                    print(f"Warning: URL {pdf_url} did not return a PDF.")
                    return None

                with open(pdf_path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        handle.write(chunk)

        return pdf_path

    def _get_citation_edges(
        self,
        base_url: str,
        fields: str = "title,authors",
        timeout: Optional[float] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Helper for paging through citation/reference edges."""
        page_size = 1000
        offset = 0
        while True:
            response = self.session.get(
                base_url,
                params={"fields": fields, "limit": page_size, "offset": offset},
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json().get("data", [])

            for element in data:
                yield element

            if len(data) < page_size:
                break
            offset += page_size

    def get_paper_citations(
        self,
        paper_id: str,
        fields: str = "title,authors",
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get a list of papers that cite the specified paper.
        """
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
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get a list of papers referenced by the specified paper.
        """
        edges = self._get_citation_edges(
            f"{self.BASE_URL}/paper/{paper_id}/references",
            fields=fields,
            timeout=timeout,
        )
        return [edge["citedPaper"] for edge in edges if "citedPaper" in edge]
