import os
import logging
from pathlib import Path
import helium
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time

from smolagents import Agent

# Configure logging
logger = logging.getLogger(__name__)
# Add a handler if not configured by main application
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')


class BrowsingAgent(Agent):
    def __init__(self, database, output_dir="outputs/retrieved_content", gemini_api_key=None, headless_helium=True):
        if not gemini_api_key:
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if not gemini_api_key:
                raise ValueError("GEMINI_API_KEY must be provided or set as an environment variable.")

        super().__init__(
            name="ContentBrowsingAgent",
            role="An AI agent that browses web pages from a given list, fetches their content, and attempts to download PDF files for academic papers.",
            system_prompt="You are a web browsing and content retrieval assistant. Your primary task is to fetch content accurately.",
            model_config={'api_key': gemini_api_key, 'model_name': 'gemini-1.5-flash-latest'},
            verbose=True
        )

        self.database = database
        self.output_dir = Path(output_dir)
        self.pdf_output_dir = self.output_dir / "pdfs"
        self.html_output_dir = self.output_dir / "html" # Optional: if saving HTML to files too

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_output_dir.mkdir(parents=True, exist_ok=True)
        self.html_output_dir.mkdir(parents=True, exist_ok=True) # Optional

        try:
            logger.info(f"Starting Helium with headless={headless_helium}...")
            helium.start_chrome(headless=headless_helium)
            logger.info("Helium started successfully with Chrome.")
        except Exception as e:
            logger.error(f"Failed to start Helium: {e}. Ensure ChromeDriver is in PATH or check permissions.")
            raise

    def process_filtered_results(self, filtered_results: dict):
        all_items = []
        if 'paper' in filtered_results:
            all_items.extend(filtered_results['paper'])
        if 'internet' in filtered_results:
            all_items.extend(filtered_results['internet'])

        logger.info(f"BrowsingAgent will process {len(all_items)} items.")

        for i, item in enumerate(all_items):
            url = item.get('url')
            source_type = item.get('source_type')
            # query_result_id is the ID from the query_results table,
            # which is stored as query_result_id in the assessments table.
            query_result_id = item.get('query_result_id') 
            title = item.get('title', f"item_{query_result_id}")

            if not url or not query_result_id:
                logger.warning(f"Skipping item with missing URL or query_result_id: {title}")
                continue

            logger.info(f"Processing item {i+1}/{len(all_items)}: {source_type} - {url} (QueryResultID: {query_result_id})")
            
            # Check if content already fetched to avoid re-processing
            # This requires a DB method like `has_fetched_content(query_result_id)`
            # For now, we'll always process. Add this optimization later if needed.

            try:
                if source_type == 'paper':
                    self._process_paper_item(url, query_result_id, title)
                elif source_type == 'internet':
                    self._process_internet_item(url, query_result_id, title)
                else:
                    logger.warning(f"Unknown source type '{source_type}' for URL: {url}")
                    self.database.add_fetched_content_typed(query_result_id, "unknown_type", None, f"Unknown source type: {source_type}")
                time.sleep(1) # Small delay between requests
            except Exception as e:
                logger.error(f"Error processing QueryResultID {query_result_id} ({url}): {e}", exc_info=True)
                # Use the new database method
                self.database.update_or_insert_fetched_content(query_result_id, "error", None, f"Error processing item: {str(e)[:500]}")

    def _process_internet_item(self, url: str, query_result_id: int, title: str):
        try:
            helium.go_to(url)
            helium.wait_until(helium.S("body").exists, timeout_secs=30) # Increased timeout
            page_content = helium.get_driver().page_source
            
            # Use the new database method
            self.database.update_or_insert_fetched_content(query_result_id, "html", page_content, None)
            logger.info(f"Successfully fetched and stored HTML content for {url}")

        except Exception as e:
            logger.error(f"Helium error fetching {url}: {e}")
            # Use the new database method
            self.database.update_or_insert_fetched_content(query_result_id, "html", None, f"Helium fetch error: {str(e)[:500]}")

    def _process_paper_item(self, url: str, query_result_id: int, title: str):
        page_content_for_pdf_search = None
        pdf_downloaded_path = None
        
        try:
            logger.debug(f"Navigating to paper page: {url}")
            helium.go_to(url)
            helium.wait_until(helium.S("body").exists, timeout_secs=30)
            page_content_for_pdf_search = helium.get_driver().page_source
            
            pdf_url = self._find_pdf_link_in_page(page_content_for_pdf_search, url)
            
            if pdf_url:
                logger.info(f"Found potential PDF link: {pdf_url} for {url}")
                
                # Sanitize filename
                safe_title = "".join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in title)
                safe_title = safe_title[:100] # Limit length
                pdf_filename = f"paper_{query_result_id}_{safe_title}.pdf"
                filepath = self.pdf_output_dir / pdf_filename
                
                self._download_file(pdf_url, filepath)
                pdf_downloaded_path = str(filepath.resolve())
                # Use the new database method
                self.database.update_or_insert_fetched_content(query_result_id, "pdf_path", pdf_downloaded_path, None)
                logger.info(f"Successfully downloaded PDF for {url} to {pdf_downloaded_path}")
                return # PDF successfully downloaded and recorded
            else:
                logger.info(f"No direct PDF link found on page {url}. Storing page HTML instead.")
                
        except Exception as e:
            logger.warning(f"Error during PDF search/download for {url}: {e}. Will attempt to save page HTML.")
            # Record PDF search/download error, but still try to get HTML
            # Use the new database method
            self.database.update_or_insert_fetched_content(query_result_id, "pdf_path_error", None, f"PDF search/download error: {str(e)[:500]}")

        # If PDF not found/downloaded, or an error occurred before PDF download was confirmed:
        if not pdf_downloaded_path:
            if page_content_for_pdf_search:
                 # Use the new database method
                 self.database.update_or_insert_fetched_content(query_result_id, "html", page_content_for_pdf_search, None)
                 logger.info(f"Stored HTML of abstract page for {url} (no PDF found/downloaded or error in PDF step).")
            else: # Fetch again if initial fetch failed or wasn't done
                try:
                    logger.debug(f"Re-fetching HTML for paper page: {url}")
                    helium.go_to(url)
                    helium.wait_until(helium.S("body").exists, timeout_secs=30)
                    page_content = helium.get_driver().page_source
                    # Use the new database method
                    self.database.update_or_insert_fetched_content(query_result_id, "html", page_content, None)
                    logger.info(f"Successfully fetched and stored HTML for paper page {url} (no PDF).")
                except Exception as e_html:
                    logger.error(f"Helium error fetching HTML for paper page {url} after PDF attempt: {e_html}")
                    # Use the new database method
                    self.database.update_or_insert_fetched_content(query_result_id, "html", None, f"Helium HTML fetch error: {str(e_html)[:500]}")

    def _find_pdf_link_in_page(self, page_html: str, base_url: str) -> str | None:
        soup = BeautifulSoup(page_html, 'html.parser')
        potential_links = []

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            link_text = a_tag.get_text().strip().lower()
            
            abs_href = urljoin(base_url, href)

            # Priority 1: Direct .pdf extension
            if abs_href.lower().endswith('.pdf'):
                potential_links.append({'url': abs_href, 'priority': 1, 'text': link_text})
                continue

            # Priority 2: Link text indicates PDF
            pdf_keywords = ['pdf', 'download pdf', 'full text', 'download article', 'view pdf']
            if any(keyword in link_text for keyword in pdf_keywords):
                potential_links.append({'url': abs_href, 'priority': 2, 'text': link_text})
                continue
            
            # Priority 3: URL contains 'pdf', 'download', 'fulltext' etc.
            url_keywords = ['.pdf', 'download', 'fulltext', 'article', 'paper', 'viewdoc']
            if any(keyword in abs_href.lower() for keyword in url_keywords):
                 # Avoid generic download pages not specific to PDF
                if 'download' in abs_href.lower() and not any(kw in link_text for kw in ['pdf', 'article']):
                    potential_links.append({'url': abs_href, 'priority': 4, 'text': link_text}) # Lower priority
                else:
                    potential_links.append({'url': abs_href, 'priority': 3, 'text': link_text})

        if not potential_links:
            return None

        # Sort by priority (lower number is better), then by length of text (prefer more descriptive links)
        potential_links.sort(key=lambda x: (x['priority'], -len(x['text'])))
        
        logger.debug(f"Found potential PDF links for {base_url}: {potential_links}")
        return potential_links[0]['url']


    def _download_file(self, url: str, filepath: Path):
        try:
            logger.info(f"Attempting to download file from {url} to {filepath}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8', # More general accept
                'Accept-Language': 'en-US,en;q=0.5',
                'DNT': '1', 
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            # Try to get the actual filename from Content-Disposition if possible
            # For now, using the generated filepath directly.
            response = requests.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True) # Increased timeout, allow redirects
            response.raise_for_status()
            
            # Check content type if it's obviously not a PDF
            content_type = response.headers.get('Content-Type', '').lower()
            if 'html' in content_type and not 'pdf' in content_type:
                logger.warning(f"Link {url} returned HTML content, not PDF. Skipping download to {filepath}.")
                # Optionally save this HTML if it's different from the main page
                raise ValueError(f"Expected PDF, got HTML from {url}")

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info(f"File downloaded successfully: {filepath}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {url}: {e}")
            if filepath.exists(): # Clean up partial download
                filepath.unlink()
            raise
        except ValueError as e: # Custom error for wrong content type
            logger.error(f"Download integrity check failed for {url}: {e}")
            if filepath.exists():
                 filepath.unlink()
            raise


    def close(self):
        try:
            logger.info("Attempting to kill Helium browser...")
            helium.kill_browser()
            logger.info("Helium browser killed successfully.")
        except Exception as e:
            # It's possible an error occurred if browser was already closed or never started
            logger.warning(f"Error killing Helium browser (might be normal if already closed): {e}")

