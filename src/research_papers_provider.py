"""
Research papers provider for sentiment analysis thesis information gathering system.
Handles search queries using Semantic Scholar and Crossref APIs.
"""

import logging
import time
import random
import unicodedata
from typing import List, Dict, Optional, Any
from datetime import datetime
import httpx
from database import Database


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Constants
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
CROSSREF_API = "https://api.crossref.org/works"
USER_AGENT = "scientific-literature-app/1.0"


async def make_api_request(url: str, headers: dict = None, params: dict = None) -> dict[str, Any] | None:
    """Make a request to the API with proper error handling."""
    if headers is None:
        headers = {"User-Agent": USER_AGENT}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.warning(f"Timeout for request to {url}")
            return None
        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error {e.response.status_code} for {url}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")
            return None


def format_paper_data(data: dict, source: str) -> Dict[str, Any]:
    """Format paper data from different sources into a consistent dictionary format."""
    if not data:
        return {}
        
    try:
        result = {}
        
        if source == "semantic_scholar":
            result.update({
                'title': unicodedata.normalize('NFKD', str(data.get('title', 'No title available'))),
                'authors': ', '.join([author.get('name', 'Unknown Author') for author in data.get('authors', [])]),
                'year': data.get('year') or 'Year unknown',
                'doi': (data.get('externalIds', {}) or {}).get('DOI', 'No DOI available'),
                'venue': data.get('venue') or 'Venue unknown',
                'abstract': data.get('abstract') or 'No abstract available',
                'tldr': (data.get('tldr') or {}).get('text', ''),
                'is_open_access': "Yes" if data.get('isOpenAccess') else "No",
                'pdf_url': (data.get('openAccessPdf', {}) or {}).get('url', 'Not available'),
                'source': 'semantic_scholar'
            })

        elif source == "crossref":
            result.update({
                'title': (data.get('title') or ['No title available'])[0],
                'authors': ', '.join([
                    f"{author.get('given', '')} {author.get('family', '')}".strip() or 'Unknown Author'
                    for author in data.get('author', [])
                ]),
                'year': str((data.get('published-print', {}).get('date-parts', [['']])[0][0]) or 'Year unknown'),
                'doi': data.get('DOI') or 'No DOI available',
                'venue': (data.get('container-title') or ['Venue unknown'])[0] if data.get('container-title') else 'Venue unknown',
                'abstract': 'Available via DOI',
                'source': 'crossref'
            })
                
        return result
        
    except Exception as e:
        logger.error(f"Error formatting paper data: {e}")
        return {}


class ResearchPapersProvider:
    """Research papers search provider for academic literature."""
    
    def __init__(self, timeout: int = 30, max_results: int = 10, delay_between_searches: float = 2.0):
        """
        Initialize research papers provider.
        
        Args:
            timeout: Timeout for API requests in seconds
            max_results: Maximum number of results per search
            delay_between_searches: Delay between searches to avoid rate limiting
        """
        self.timeout = timeout
        self.max_results = max_results
        self.delay_between_searches = delay_between_searches
    
    async def search(self, query: str, query_type: str = "tools") -> List[Dict[str, Any]]:
        """
        Perform a search query using academic paper databases with retry mechanism.
        
        Args:
            query: Search query string
            query_type: Type of query ("tools" or "applications")
            
        Returns:
            List of search results with paper details
            
        Raises:
            Exception: If search fails after all retries
        """
        # Retry parameters for API rate limits
        max_retries = 3
        base_delay = 2.0
        
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await self._perform_search(query, query_type)
                
            except Exception as e:
                last_exception = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt) + random.uniform(1, 3)
                    logger.warning(f"Search failed on attempt {attempt + 1}/{max_retries + 1} "
                                 f"for query '{query}'. Waiting {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"Search failed after {max_retries + 1} attempts for query '{query}'")
                    
        # If we get here, all retries failed
        raise Exception(f"Research papers search failed after {max_retries + 1} attempts: {last_exception}")
    
    async def _perform_search(self, query: str, query_type: str = "tools") -> List[Dict[str, Any]]:
        """
        Perform the actual search operation (internal method).
        
        Args:
            query: Search query string  
            query_type: Type of query ("tools" or "applications")
            
        Returns:
            List of search results with paper details
        """
        logger.info(f"Searching research papers for: '{query}' (type: {query_type})")
        
        # Truncate long queries
        MAX_QUERY_LENGTH = 300
        if len(query) > MAX_QUERY_LENGTH:
            original_length = len(query)
            query = query[:MAX_QUERY_LENGTH] + "..."
            logger.info(f"Query truncated from {original_length} to {len(query)} characters")
        
        results = []
        
        try:
            # Search Semantic Scholar
            semantic_results = await self._search_semantic_scholar(query)
            results.extend(semantic_results)
            
            # If we don't have enough results, try Crossref
            if len(results) < self.max_results:
                remaining_limit = self.max_results - len(results)
                crossref_results = await self._search_crossref(query, remaining_limit)
                results.extend(crossref_results)
                
        except Exception as e:
            logger.error(f"Error in research papers search: {e}")
            raise
        
        # Limit results and add position numbers
        results = results[:self.max_results]
        for i, result in enumerate(results, 1):
            result['position'] = i
            
        logger.info(f"Found {len(results)} research paper results for query: '{query}'")
        return results
    
    async def _search_semantic_scholar(self, query: str) -> List[Dict[str, Any]]:
        """Search Semantic Scholar API."""
        semantic_url = f"{SEMANTIC_SCHOLAR_API}/paper/search"
        params = {
            "query": query.encode('utf-8').decode('utf-8'),
            "limit": self.max_results,
            "fields": "title,authors,year,paperId,externalIds,abstract,venue,isOpenAccess,openAccessPdf,tldr"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT
        }
        
        data = await make_api_request(semantic_url, headers=headers, params=params)
        
        results = []
        if data and ('data' in data or 'papers' in data):
            papers = data.get('data', data.get('papers', []))
            for paper in papers:
                formatted = format_paper_data(paper, "semantic_scholar")
                if formatted:
                    results.append(formatted)
                    
        return results
    
    async def _search_crossref(self, query: str, limit: int = None) -> List[Dict[str, Any]]:
        """Search Crossref API."""
        if limit is None:
            limit = self.max_results
            
        crossref_url = f"{CROSSREF_API}?query={query}&rows={limit}"
        data = await make_api_request(crossref_url)
        
        results = []
        if data and 'items' in data.get('message', {}):
            for paper in data['message']['items']:
                formatted = format_paper_data(paper, "crossref")
                if formatted:
                    results.append(formatted)
                    
        return results
    
    async def fetch_paper_details(self, paper_id: str, source: str = "semantic_scholar") -> Dict[str, Any]:
        """Get detailed information about a specific paper."""
        logger.info(f"Fetching paper details for {paper_id} from {source}")
        
        if source == "semantic_scholar":
            url = f"{SEMANTIC_SCHOLAR_API}/paper/{paper_id}"
        elif source == "crossref":
            url = f"{CROSSREF_API}/{paper_id}"
        else:
            raise ValueError("Unsupported source. Please use 'semantic_scholar' or 'crossref'.")

        data = await make_api_request(url)
        
        if not data:
            logger.warning(f"Unable to fetch paper details for {paper_id} from {source}")
            return {}

        if source == "crossref":
            data = data.get('message', {})

        return format_paper_data(data, source)


class ResearchPapersModule:
    """Main research papers module that coordinates search operations with database."""
    
    def __init__(self, db_path: str = None, search_config: Dict[str, Any] = None):
        """
        Initialize research papers module.
        
        Args:
            db_path: Path to database file
            search_config: Configuration for search provider
        """
        self.database = Database(db_path)
        
        # Default search configuration
        default_config = {
            'timeout': 30,
            'max_results': 10,
            'delay_between_searches': 2.0
        }
        
        if search_config:
            default_config.update(search_config)
            
        self.search_provider = ResearchPapersProvider(**default_config)
        
    async def process_query(self, query_id: int) -> bool:
        """
        Process a single query: perform search and store results.
        
        Args:
            query_id: ID of the query to process
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get query details from database
            query_data = self.database.get_query(query_id)
            if not query_data:
                logger.error(f"Query {query_id} not found in database")
                return False
                
            query_text = query_data['query_text']
            query_type = query_data['query_type']
            
            # Update status to processing
            self.database.update_query_status(query_id, 'processing')
            logger.info(f"Processing research papers query {query_id}: '{query_text}'")
            
            # Perform search
            search_results = await self.search_provider.search(query_text, query_type)
            
            # Store results in database with research papers source
            for result in search_results:
                # Create URL from DOI if available
                url = None
                if result.get('doi') and result['doi'] != 'No DOI available':
                    url = f"https://doi.org/{result['doi']}"
                
                self.database.add_query_result(
                    query_id=query_id,
                    url=url,
                    title=result.get('title', ''),
                    snippet=result.get('abstract', ''),
                    position=result.get('position', 0),
                    domain=result.get('source', 'research_papers'),
                    locale='academic',
                    source_type='research_papers',
                    source_identifier=result.get('doi', '')
                )
            
            # Update query status to completed
            self.database.update_query_status(query_id, 'completed')
            
            logger.info(f"Successfully processed research papers query {query_id}: {len(search_results)} results stored")
            return True
            
        except Exception as e:
            logger.error(f"Error processing research papers query {query_id}: {e}")
            self.database.update_query_status(query_id, 'failed')
            return False
    
    async def search_and_store(self, query_text: str, query_type: str) -> Optional[int]:
        """
        Convenience method to add a query and immediately process it.
        
        Args:
            query_text: Search query string
            query_type: Type of query ("tools" or "applications")
            
        Returns:
            Query ID if successful, None otherwise
        """
        try:
            # Add query to database
            query_id = self.database.add_query(query_text, query_type)
            
            # Process immediately
            success = await self.process_query(query_id)
            
            if success:
                return query_id
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error in search_and_store for '{query_text}': {e}")
            return None
    
    def get_search_statistics(self) -> Dict[str, Any]:
        """Get comprehensive search statistics."""
        db_stats = self.database.get_stats()
        
        # Add research papers specific statistics
        with self.database.get_connection() as conn:
            # Count queries by status
            cursor = conn.execute('''
                SELECT 
                    status,
                    COUNT(*) as count,
                    AVG(results_count) as avg_results
                FROM queries 
                GROUP BY status
            ''')
            
            status_stats = {}
            for row in cursor.fetchall():
                status_stats[row['status']] = {
                    'count': row['count'],
                    'avg_results': round(row['avg_results'] or 0, 2)
                }
        
        return {
            'database_stats': db_stats,
            'status_breakdown': status_stats,
            'search_config': {
                'timeout': self.search_provider.timeout,
                'max_results': self.search_provider.max_results,
                'delay_between_searches': self.search_provider.delay_between_searches
            }
        }
    
    def close(self):
        """Close database connection."""
        self.database.close()
        
    def __enter__(self):
        """Context manager entry."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
