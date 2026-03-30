# --- Standard library ---
import os
import xml.etree.ElementTree as ET

# --- Third-party ---
import requests
from dotenv import load_dotenv
from tavily import TavilyClient
import wikipedia

# Init env
load_dotenv()  # load variables 

# Set user-agent for requests to arXiv
session = requests.Session()
session.headers.update({
    "User-Agent": "LF-ADP-Agent/1.0 (mailto:your.email@example.com)"
})

def arxiv_search_tool(query: str, max_results: int = 5) -> list[dict]:
    """
    Searches arXiv for research papers matching the given query.
    """
    url = f"https://export.arxiv.org/api/query?search_query=all:{query}&start=0&max_results={max_results}"

    try:
        response = session.get(url, timeout=60)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return [{"error": str(e)}]

    try:
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}

        results = []
        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text.strip()
            authors = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]
            published = entry.find('atom:published', ns).text[:10]
            url_abstract = entry.find('atom:id', ns).text
            summary = entry.find('atom:summary', ns).text.strip()

            link_pdf = None
            for link in entry.findall('atom:link', ns):
                if link.attrib.get('title') == 'pdf':
                    link_pdf = link.attrib.get('href')
                    break

            results.append({
                "title": title,
                "authors": authors,
                "published": published,
                "url": url_abstract,
                "summary": summary,
                "link_pdf": link_pdf
            })

        return results
    except Exception as e:
        return [{"error": f"Parsing failed: {str(e)}"}]


arxiv_tool_def = {
    "type": "function",
    "function": {
        "name": "arxiv_search_tool",
        "description": "Searches for research papers on arXiv by query string.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords for research papers."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}



def tavily_search_tool(query: str, max_results: int = 5, include_images: bool = False) -> list[dict]:
    """
    Perform a search using the Tavily API.

    Args:
        query (str): The search query.
        max_results (int): Number of results to return (default 5).
        include_images (bool): Whether to include image results.

    Returns:
        list[dict]: A list of dictionaries with keys like 'title', 'content', and 'url'.
    """
    params = {}
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY not found in environment variables.")
    params['api_key'] = api_key

    #client = TavilyClient(api_key)

    api_base_url = os.getenv("DLAI_TAVILY_BASE_URL")
    if api_base_url:
        params['api_base_url'] = api_base_url

    client = TavilyClient(api_key=api_key, api_base_url=api_base_url)

    try:
        response = client.search(
            query=query,
            max_results=max_results,
            include_images=include_images
        )

        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "content": r.get("content", ""),
                "url": r.get("url", "")
            })

        if include_images:
            for img_url in response.get("images", []):
                results.append({"image_url": img_url})

        return results

    except Exception as e:
        return [{"error": str(e)}]  # For LLM-friendly agents
    

tavily_tool_def = {
    "type": "function",
    "function": {
        "name": "tavily_search_tool",
        "description": "Performs a general-purpose web search using the Tavily API.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords for retrieving information from the web."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return.",
                    "default": 5
                },
                "include_images": {
                    "type": "boolean",
                    "description": "Whether to include image results.",
                    "default": False
                }
            },
            "required": ["query"]
        }
    }
}

## Wikipedia search tool

def wikipedia_search_tool(query: str, sentences: int = 5) -> list[dict]:
    """
    Searches Wikipedia for a summary of the given query.

    Args:
        query (str): Search query for Wikipedia.
        sentences (int): Number of sentences to include in the summary.

    Returns:
        list[dict]: A list with a single dictionary containing title, summary, and URL.
    """
    try:
        page_title = wikipedia.search(query)[0]
        page = wikipedia.page(page_title)
        summary = wikipedia.summary(page_title, sentences=sentences)

        return [{
            "title": page.title,
            "summary": summary,
            "url": page.url
        }]
    except Exception as e:
        return [{"error": str(e)}]

# Tool definition
wikipedia_tool_def = {
    "type": "function",
    "function": {
        "name": "wikipedia_search_tool",
        "description": "Searches for a Wikipedia article summary by query string.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords for the Wikipedia article."
                },
                "sentences": {
                    "type": "integer",
                    "description": "Number of sentences in the summary.",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}

#########################################################
def pubmed_search_tool(query: str, max_results: int = 5) -> list[dict]:
    """
    Searches Pubmed for research papers matching the given query.
    Uses NCBI E-utilities (esearch+efect)
    """
    # Step 1: Get PubMed IDs (PMIDs)
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    esearch_params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results,
        "sort": "relevance",
    }
    try:
        r = session.get(esearch_url, params=esearch_params, timeout=30)
        r.raise_for_status()
        pmids = r.json().get("esearchresult", {}).get("idlist", [])
    except requests.exceptions.RequestException as e:
        return [{"error": f"PubMed esearch failed: {str(e)}"}]

    if not pmids:
        return []

    # Step 2: Fetch paper details
    efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    efetch_params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    try:
        r2 = session.get(efetch_url, params=efetch_params, timeout=30)
        r2.raise_for_status()
        root = ET.fromstring(r2.text)
    except requests.exceptions.RequestException as e:
        return [{"error": f"PubMed efetch failed: {str(e)}"}]
    except ET.ParseError as e:
        return [{"error": f"XML parsing failed: {str(e)}"}]

    results = []
    
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID") or ""

        title = article.findtext(".//ArticleTitle") or ""
        journal = article.findtext(".//Journal/Title") or ""
        year = article.findtext(".//PubDate/Year") or ""

        # Authors
        authors = []
        for author in article.findall(".//AuthorList/Author"):
            last = author.findtext("LastName") or ""
            fore = author.findtext("ForeName") or ""
            name = f"{fore} {last}".strip()
            if name:
                authors.append(name)
        # Abstract
        abstract_parts = []
        for ab in article.findall(".//Abstract/AbstractText"):
            text = "".join(ab.itertext()).strip()
            if text:
                abstract_parts.append(text)

        abstract = "\n".join(abstract_parts)

        paper_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

        results.append({
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "pmid": pmid,
            "abstract": abstract,
            "url": paper_url,
        })

    return results

pubmed_tool_def = {
    "type": "function",
    "function": {
        "name": "pubmed_search_tool",
        "description": "Search PubMed for academic biomedical research papers by query string.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords (e.g., 'type 2 diabetes stress glucose')."},
                "max_results": {"type": "integer", "description": "Maximum results to return.", "default": 5},
            },
            "required": ["query"],
        },
    },
}

########################################################

# Tool mapping
tool_mapping = {
    "tavily_search_tool": tavily_search_tool,
    "arxiv_search_tool": arxiv_search_tool,
    "wikipedia_search_tool": wikipedia_search_tool,
    "pubmed_search_tool" : pubmed_search_tool
    
}