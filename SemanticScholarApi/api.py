import os
import requests
from typing import List, Dict, Any, Generator, Optional
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
        :param api_key: Semantic Scholar API key. If not provided, it attempts to read from the S2_API_KEY env variable.
                        The API can work without a key, but with stricter rate limits.
        """
        self.api_key = api_key or os.environ.get('S2_API_KEY')
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-API-KEY": self.api_key})

    def close(self):
        """Close the requests session."""
        self.session.close()

    def get_paper(self, paper_id: str, fields: str = "paperId,title,authors,year,abstract") -> Dict[str, Any]:
        """
        Retrieve details for a specific paper by ID.
        """
        response = self.session.get(
            f"{self.BASE_URL}/paper/{paper_id}",
            params={"fields": fields}
        )
        response.raise_for_status()
        return response.json()

    def get_papers_batch(self, paper_ids: List[str], fields: str = "paperId,title,authors,year,abstract", batch_size: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve details for multiple papers in batches.
        """
        results = []
        for i in range(0, len(paper_ids), batch_size):
            batch = paper_ids[i:i + batch_size]
            response = self.session.post(
                f"{self.BASE_URL}/paper/batch",
                params={"fields": fields},
                json={"ids": batch}
            )
            response.raise_for_status()
            results.extend(response.json())
        return results

    def search_papers(self, query: str, limit: int = 10, fields: str = "title,url,year,authors") -> Dict[str, Any]:
        """
        Search for papers based on a query.
        Returns a dictionary containing 'total' and 'data' (list of papers).
        """
        response = self.session.get(
            f"{self.BASE_URL}/paper/search",
            params={"query": query, "limit": limit, "fields": fields}
        )
        response.raise_for_status()
        return response.json()

    def search_papers_bulk(self, query: str, fields: str = "title,year,authors", year: Optional[str] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Search bulk endpoint, fetching all results page by page.
        Returns a generator yielding individual paper dictionaries.
        """
        params = {"query": query, "fields": fields}
        if year:
            params["year"] = year

        url = f"{self.BASE_URL}/paper/search/bulk"
        response = self.session.get(url, params=params).json()

        while True:
            if "data" in response:
                for paper in response["data"]:
                    yield paper
            
            if "token" not in response:
                break
            
            token_params = params.copy()
            token_params["token"] = response["token"]
            response = self.session.get(url, params=token_params).json()

    def get_recommendations(self, paper_id: str, limit: int = 10, fields: str = "title,url,year") -> List[Dict[str, Any]]:
        """
        Get paper recommendations based on a single paper.
        """
        response = self.session.get(
            f"{self.RECOMMENDATIONS_URL}/papers/forpaper/{paper_id}",
            params={"fields": fields, "limit": limit}
        )
        response.raise_for_status()
        return response.json().get("recommendedPapers", [])

    def search_author(self, query: str, fields: str = "authorId,name,url") -> Dict[str, Any]:
        """
        Search for an author by name.
        Returns a dictionary containing 'total' and 'data' (list of authors).
        """
        response = self.session.get(
            f"{self.BASE_URL}/author/search",
            params={"query": query, "fields": fields}
        )
        response.raise_for_status()
        return response.json()

    def get_author(self, author_id: str, fields: str = "authorId,name,url,paperCount,citationCount") -> Dict[str, Any]:
        """
        Retrieve author information by ID.
        """
        response = self.session.get(
            f"{self.BASE_URL}/author/{author_id}",
            params={"fields": fields}
        )
        response.raise_for_status()
        return response.json()

    def get_author_papers(self, author_id: str, limit: int = 1000, fields: str = "title,url,year") -> List[Dict[str, Any]]:
        """
        Get papers by a specific author.
        """
        response = self.session.get(
            f"{self.BASE_URL}/author/{author_id}/papers",
            params={"fields": fields, "limit": limit}
        )
        response.raise_for_status()
        return response.json().get("data", [])

    def download_open_access_pdf(self, paper_id: str, directory: str = "papers", user_agent: str = "requests/2.0.0") -> Optional[str]:
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
                    
                with open(pdf_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

        return pdf_path

    def _get_citation_edges(self, base_url: str, fields: str = "title,authors") -> Generator[Dict[str, Any], None, None]:
        """Helper for paging through citation/reference edges."""
        page_size = 1000
        offset = 0
        while True:
            response = self.session.get(
                base_url,
                params={"fields": fields, "limit": page_size, "offset": offset}
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            
            for element in data:
                yield element

            if len(data) < page_size:
                break
            offset += page_size

    def get_paper_citations(self, paper_id: str, fields: str = "title,authors") -> List[Dict[str, Any]]:
        """
        Get a list of papers that cite the specified paper.
        """
        edges = self._get_citation_edges(
            f"{self.BASE_URL}/paper/{paper_id}/citations",
            fields=fields
        )
        return [edge["citingPaper"] for edge in edges if "citingPaper" in edge]

    def get_paper_references(self, paper_id: str, fields: str = "title,authors") -> List[Dict[str, Any]]:
        """
        Get a list of papers referenced by the specified paper.
        """
        edges = self._get_citation_edges(
            f"{self.BASE_URL}/paper/{paper_id}/references",
            fields=fields
        )
        return [edge["citedPaper"] for edge in edges if "citedPaper" in edge]
