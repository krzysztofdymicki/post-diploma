"""
Research module for sentiment analysis thesis information gathering system.
Handles search queries using DuckDuckGo search engine.
"""

import time
import logging
import random
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse
import re
from duckduckgo_search import DDGS
from duckduckgo_search.exceptions import (
    DuckDuckGoSearchException,
    RatelimitException,
    TimeoutException,
)
from database import Database


def extract_domain_and_locale(url: str) -> tuple[str, str]:
    """
    Extract domain and locale from URL.
    
    Args:
        url: Full URL
        
    Returns:
        Tuple of (domain, locale) where:
        - domain: main domain without www. and subdomains (e.g., 'google')
        - locale: country code from domain (e.g., 'pl', 'com', 'uk')
    """
    try:
        # Handle URLs without protocol
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
            
        parsed = urlparse(url)
        hostname = parsed.netloc.lower()
        
        # Fallback: if netloc is empty, try using path (for malformed URLs)
        if not hostname and parsed.path:
            hostname = parsed.path.split('/')[0].lower()
        
        if not hostname:
            return 'unknown', 'unknown'
        # Remove www. prefix
        if hostname.startswith('www.'):
            hostname = hostname[4:]
        
        # Split domain parts
        parts = hostname.split('.')
        
        if len(parts) >= 2:
            # Extract main domain name (second to last part)
            domain = parts[-2]  # e.g., 'google' from 'www.google.com'
            
            # Extract locale (last part after the last dot)
            locale = parts[-1]  # e.g., 'com' from 'www.google.com'
            
            return domain, locale
        else:
            # Fallback for unusual domains
            return hostname, 'unknown'
            
    except Exception:
        return 'unknown', 'unknown'


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class InternetSearchProvider:
    """DuckDuckGo search engine wrapper for sentiment analysis research."""
    
    def __init__(self, timeout: int = 10, max_results: int = 10, delay_between_searches: float = 1.0):
        """
        Initialize search engine.
        
        Args:
            timeout: Timeout for search requests in seconds
            max_results: Maximum number of results per search
            delay_between_searches: Delay between searches to avoid rate limiting
        """
        self.timeout = timeout
        self.max_results = max_results
        self.delay_between_searches = delay_between_searches
    
    def search(self, query: str, query_type: str = "tools") -> List[Dict[str, Any]]:
        """
        Perform a search query using DuckDuckGo with aggressive retry mechanism.
        
        Args:
            query: Search query string
            query_type: Type of query ("tools" or "applications")
            
        Returns:
            List of search results with title, url, and snippet
            
        Raises:
            DuckDuckGoSearchException: If search fails after all retries
        """        # Very aggressive retry parameters for rate limits
        max_retries = 7  # Increased from 5  
        base_delay = 12.0  # Increased from 8.0 - start with longer delay
        
        last_exception = None
        
        for attempt in range(max_retries + 1):  # +1 for initial attempt
            try:
                return self._perform_search(query, query_type)
                
            except RatelimitException as e:
                last_exception = e
                if attempt < max_retries:
                    # Very aggressive exponential backoff with larger jitter
                    delay = base_delay * (3.0 ** attempt) + random.uniform(5, 15)  # Increased multiplier and jitter
                    logger.warning(f"Rate limit hit on attempt {attempt + 1}/{max_retries + 1} "
                                 f"for query '{query}'. Waiting {delay:.1f} seconds...")
                    time.sleep(delay)
                else:
                    logger.error(f"Rate limit exceeded after {max_retries + 1} attempts for query '{query}'")
                    
            except (TimeoutException, DuckDuckGoSearchException) as e:
                # For non-rate-limit errors, fewer retries but still some
                last_exception = e
                if attempt < min(4, max_retries):  # Max 4 retries for timeouts (increased from 3)
                    delay = base_delay + random.uniform(3, 8)  # Slightly longer delays for timeouts too
                    logger.warning(f"Search failed on attempt {attempt + 1}, retrying in {delay:.1f} seconds: {e}")
                    time.sleep(delay)
                else:
                    logger.error(f"Search failed after retries for query '{query}': {e}")
                    break
                    
        # If we get here, all retries failed
        raise DuckDuckGoSearchException(f"Search failed after {max_retries + 1} attempts: {last_exception}")
    
    def _perform_search(self, query: str, query_type: str = "tools") -> List[Dict[str, Any]]:
        """
        Perform the actual search operation (internal method).
        
        Args:
            query: Search query string  
            query_type: Type of query ("tools" or "applications")
            
        Returns:
            List of search results with title, url, and snippet
            
        Raises:
            RatelimitException, TimeoutException, DuckDuckGoSearchException: Various search errors
        """
        logger.info(f"Searching for: '{query}' (type: {query_type})")
        
        # Initialize DDGS with timeout
        ddgs = DDGS(timeout=self.timeout)
        
        # Perform text search
        raw_results = ddgs.text(
            keywords=query,
            region="wt-wt",  # Worldwide
            safesearch="moderate",
            max_results=self.max_results
        )
        
        # Convert to standardized format
        results = []
        for i, result in enumerate(raw_results, 1):
            url = result.get('href', '')
            domain, locale = extract_domain_and_locale(url)
            
            standardized_result = {
                'title': result.get('title', ''),
                'url': url,
                'snippet': result.get('body', ''),
                'position': i,
                'domain': domain,
                'locale': locale
            }
            results.append(standardized_result)
            
        logger.info(f"Found {len(results)} results for query: '{query}'")
        return results


class InternetSearchModule:
    """Main research module that coordinates search operations with database."""
    
    def __init__(self, db_path: str = None, search_config: Dict[str, Any] = None):
        """
        Initialize research module.
        
        Args:
            db_path: Path to database file
            search_config: Configuration for search engine
        """
        self.database = Database(db_path)
          # Default search configuration with more conservative delays
        default_config = {
            'timeout': 10,
            'max_results': 10,
            'delay_between_searches': 3.0  # Increased from 1.0 to be more conservative
        }
        
        if search_config:
            default_config.update(search_config)
            
        self.search_engine = InternetSearchProvider(**default_config)
        
    def process_query(self, query_id: int) -> bool:
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
            logger.info(f"Processing query {query_id}: '{query_text}'")
            
            # Perform search
            search_results = self.search_engine.search(query_text, query_type)
              # Store results in database
            for result in search_results:
                self.database.add_query_result(
                    query_id=query_id,
                    url=result['url'],
                    title=result['title'],
                    snippet=result['snippet'],
                    position=result['position'],
                    domain=result['domain'],
                    locale=result['locale']
                )
            
            # Update query status to completed
            self.database.update_query_status(query_id, 'completed')
            
            logger.info(f"Successfully processed query {query_id}: {len(search_results)} results stored")
            return True
            
        except DuckDuckGoSearchException as e:
            logger.error(f"Search error for query {query_id}: {e}")
            self.database.update_query_status(query_id, 'failed')
            return False
            
        except Exception as e:
            logger.error(f"Unexpected error processing query {query_id}: {e}")
            self.database.update_query_status(query_id, 'failed')
            return False
    
    def process_pending_queries(self) -> Dict[str, int]:
        """
        Process all pending queries in the database.
        
        Returns:
            Dictionary with processing statistics
        """
        # Get all pending queries
        pending_queries = self.database.get_queries_by_status('pending')
        
        stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0
        }
        
        logger.info(f"Processing {len(pending_queries)} pending queries")
        
        for query in pending_queries:
            query_id = query['id']
            
            # Add delay between searches to avoid rate limiting
            if stats['total_processed'] > 0:
                time.sleep(self.search_engine.delay_between_searches)
            
            success = self.process_query(query_id)
            stats['total_processed'] += 1
            
            if success:
                stats['successful'] += 1
            else:
                stats['failed'] += 1
                
        logger.info(f"Processing complete: {stats['successful']} successful, {stats['failed']} failed")
        return stats
    
    def search_and_store(self, query_text: str, query_type: str) -> Optional[int]:
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
            success = self.process_query(query_id)
            
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
        
        # Add research-specific statistics
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
                'timeout': self.search_engine.timeout,
                'max_results': self.search_engine.max_results,
                'delay_between_searches': self.search_engine.delay_between_searches
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



