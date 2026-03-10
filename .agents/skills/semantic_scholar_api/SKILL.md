---
name: Semantic Scholar API
description: A built-in skill for querying academic papers, authors, citations, and downloading Open Access PDFs using the Semantic Scholar Graph API.
---

# Semantic Scholar API Skill

This skill provides instructions on how to interact with the Semantic Scholar Graph API using the local `SemanticScholarApi` module.

## When to Use This Skill

Use this skill when the user asks to:
- Find academic literature or papers on a specific topic.
- Retrieve details about a specific academic paper (e.g., abstract, year, authors, DOI).
- Download Open Access PDFs for academic papers.
- Explore academic citations or find recommendations for a paper.
- Find researchers (authors) and list their papers.

## Prerequisites

The API client reads the API key from the environment variable (`S2_API_KEY`). It works without a key but is subject to stricter rate limits.

## How to Use `SemanticScholarClient`

The Python client is located in the local `SemanticScholarApi` module within the project. You can write scripts or use it directly wherever Python is executed.

### Initialization

```python
import os
from SemanticScholarApi import SemanticScholarClient

# Initialize the client (auto-detects S2_API_KEY from env var)
client = SemanticScholarClient()
```

### 1. Fetching Paper Details

```python
# Get basic paper details
paper_id = "CorpusID:205399909" # Can also use DOI, PMID, arXiv ID, etc.
paper = client.get_paper(paper_id, fields="paperId,title,authors,year,abstract")
print(f"Title: {paper['title']}, Year: {paper['year']}")

# Batch fetching multiple papers
papers = client.get_papers_batch(["CorpusID:205399909", "10.1038/nrn3241"])
```

### 2. Searching for Papers

```python
# Search by keyword
results = client.search_papers(query="machine learning prompt engineering", limit=5)
for p in results['data']:
    print(f"{p['title']} ({p['year']})")

# Bulk search (returns a generator, good for large datasets)
# E.g., Retrieve all covid-19 papers from 2023 onwards
for paper in client.search_papers_bulk(query="covid-19", year="2023-"):
    print(paper['title'])
    break # Remove break to process all
```

### 3. Downloading Open Access PDFs

```python
# Returns the absolute path to the downloaded PDF if available, otherwise None
pdf_path = client.download_open_access_pdf("CorpusID:205399909", directory="downloaded_pdfs")
if pdf_path:
    print(f"Downloaded securely to {pdf_path}")
```

### 4. Exploring Citations, References, and Recommendations

```python
# Get papers that cite a specific paper
citations = client.get_paper_citations("CorpusID:205399909", fields="title,authors")
for citing_paper in citations:
    print(citing_paper['title'])

# Get papers that are referenced by a specific paper
references = client.get_paper_references("CorpusID:205399909", fields="title,authors")

# Get algorithmic recommendations based on a paper
recommendations = client.get_recommendations("CorpusID:205399909", limit=5)
```

### 5. Author Information

```python
# Search for an author
authors = client.search_author(query="Geoffrey Hinton")

if authors.get('data'):
    # Get author's papers
    author_id = authors['data'][0]['authorId']
    papers = client.get_author_papers(author_id, limit=10)
```

## Best Practices
1. **Optimize Network Calls:** Always specify the `fields` parameter explicitly to minimize payload size and improve API response speed.
2. **Resource Management:** Call `client.close()` when done to close the connections cleanly if you aren't reusing the instance anymore.
3. **Identifiers:** Semantic Scholar supports various IDs (`CorpusID:...`, `DOI:...`, `PMID:...`, `ARXIV:...`, etc.). They can be directly passed as `paper_id`.
