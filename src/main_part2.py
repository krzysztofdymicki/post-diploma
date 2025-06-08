"""
Main Part 2: Filtering and Content Fetching Workflow

This script orchestrates the second part of the research workflow:
1.  Filtering assessed results to get the top N% from each source.
2.  Using the BrowsingAgent to visit the links of filtered results.
3.  Fetching HTML content for internet sources.
4.  Attempting to download PDF files for research papers (and fetching HTML of the abstract page if PDF fails).
5.  Storing the fetched content (HTML or PDF path) in the database.
"""

import argparse
import asyncio
import logging
import os
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from browser_use import Controller, Agent as BUAgent
import shutil

from database import Database
from result_filtering_module import ResultFilteringModule
# Use our ContentExtractionAgent for browsing via browser-use
from browsing_agent import ContentExtractionAgent as BrowsingAgent
# from browser_use import Controller  # not used here
# from pydantic import BaseModel      # not used here
# from typing import Optional        # not used here

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"main_part2_workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)


async def process_filtered_results(db: Database, agent: BrowsingAgent, filtered_results: List[Dict[str, Any]]):
    logger.info(f"Processing {len(filtered_results)} filtered results.")
    for result in filtered_results:
        query_result_id = result.get('id')
        url = result.get('url')
        source_type = result.get('source_type')
        pdf_url = result.get('pdf_url') # Relevant for 'paper' or 'research_papers'

        if not query_result_id:
            logger.warning(f"Skipping result due to missing ID: {result.get('title', 'N/A')}")
            continue

        # Check if content already fetched
        existing_content = db.get_fetched_content_by_result_id(query_result_id)
        if existing_content and existing_content['status'] == 'success':
            logger.info(f"Content already successfully fetched for result ID {query_result_id} (URL: {url}). Skipping.")
            continue
        elif existing_content:
            logger.info(f"Content previously attempted for result ID {query_result_id} (status: {existing_content['status']}). Re-attempting.")
            # Optionally, delete the previous attempt before retrying
            # db.delete_fetched_content(existing_content['id'])

        content_type_stored = None
        stored_path_or_content = None
        error_message = None
        fetch_status = "pending"

        try:
            # Skip research paper fetching for now
            if source_type in ['paper', 'research_papers']:
                logger.info(f"Skipping research source ID {query_result_id}")
                fetch_status = 'skipped'
                # record minimal info and continue
                db.add_or_update_fetched_content(
                    query_result_id=query_result_id,
                    url=url or pdf_url,
                    status=fetch_status,
                    content_type=None,
                    parsed_content=None
                )
                continue
            # Internet sources only
            if source_type == 'internet' and url:
                logger.info(f"Enhanced extraction for URL: {url}")
                from browser_use import Agent as BrowserAgent
                # Build custom task prompt
                task = f"""
                Navigate to {url} and extract:
                1. Main text content.
                2. Author name (if available).
                3. Publication date (if available).

                Return a JSON object with keys: 'url', 'author', 'publication_date', 'content'.
                """
                actions = [ {'open_tab': {'url': url}}, {'wait': {'seconds': 3}} ]
                browser_agent = BrowserAgent(task=task, initial_actions=actions, llm=agent.llm)
                raw = await browser_agent.run(max_steps=50)
                result_str = str(raw)
                try:
                    parsed = json.loads(result_str)
                    content = parsed.get('content')
                    author = parsed.get('author')
                    publication_date = parsed.get('publication_date')
                except Exception:
                    content = result_str
                    author = None
                    publication_date = None
                content_type_stored = 'html'
                # Include author and date in stored content for now
                stored_path_or_content = json.dumps({ 'url': url, 'author': author, 'publication_date': publication_date, 'content': content }, ensure_ascii=False)
                fetch_status = 'success'
            else:
                logger.warning(f"Skipping result ID {query_result_id} - no URL or PDF URL provided.")
                error_message = "No URL or PDF URL available for fetching."
                fetch_status = "failed"

        except Exception as e:
            logger.error(f"Exception during content fetching for result ID {query_result_id} (URL: {url}): {e}", exc_info=True)
            error_message = str(e)
            fetch_status = "failed"
        
        # Store/update fetched content record in DB
        if content_type_stored or fetch_status == "failed": # Store even if failed
            db.add_or_update_fetched_content(
                query_result_id=query_result_id,
                url=url or pdf_url, # Store the primary URL used for fetching
                status=fetch_status,
                content_type=content_type_stored,
                # Store parsed_content for both HTML and PDF paths
                parsed_content=stored_path_or_content,
                title_extracted=result.get('title'), # Can be enhanced later with actual extraction
                content_length=len(stored_path_or_content) if stored_path_or_content else 0,
                error_message=error_message
            )
            logger.info(f"Database record for fetched content (result ID {query_result_id}) updated. Status: {fetch_status}")
        else:
            logger.debug(f"No content fetched or error to record for result ID {query_result_id}")


async def main():
    parser = argparse.ArgumentParser(
        description="Workflow Part 2: Filter results and fetch content using BrowsingAgent.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None, # Will use default in Database class: data/research_db.db
        help="Path to the SQLite database file."
    )
    parser.add_argument(
        "--research-filter-percentage",
        type=float,
        default=10.0,
        help="Percentage of top research paper results to process."
    )
    parser.add_argument(
        "--internet-filter-percentage",
        type=float,
        default=10.0,
        help="Percentage of top internet results to process."
    )
    parser.add_argument(
        "--output-dir", # This is now primarily for BrowsingAgent's downloads
        type=str,
        default="outputs/retrieved_content", # Default download dir for agent
        help="Directory for the BrowsingAgent to store downloaded PDFs."
    )
    parser.add_argument(
        "--headless-browser", # Changed argument name for clarity with browser-use
        action=argparse.BooleanOptionalAction, # Allows --headless-browser / --no-headless-browser
        default=True, 
        help="Run browser in headless mode. Use --no-headless-browser for visible mode."
    )
    parser.add_argument(
        "--skip-filtering",
        action="store_true",
        help="Skip the filtering step and attempt to process all assessed results (not recommended for large datasets)."
    )
    parser.add_argument(
        "--filtered-input-file",
        type=str,
        default=None,
        help="Path to a JSON file containing pre-filtered results (e.g., from result_filtering_module.py). If provided, filtering percentages are ignored."
    )
    parser.add_argument(
        "--max-results-to-process",
        type=int,
        default=None,
        help="Optional: Maximum total number of filtered results to process in this run (for testing/limiting scope)."
    )

    args = parser.parse_args()

    logger.info("Starting Main Workflow Part 2: Filtering and Content Fetching.")
    logger.info(f"Log file: {log_file.resolve()}")
    logger.info(f"Arguments: {args}")

    # Reset fetched_content in original DB
    db = Database(db_path=args.db_path)
    db.reset_fetched_content()

    # Ensure the output directory for agent downloads exists
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    # Initialize browsing agent for internet sources
    agent = BrowsingAgent(llm=ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-05-20'), output_dir=args.output_dir)

    all_filtered_results: List[Dict[str, Any]] = []

    if args.filtered_input_file:
        logger.info(f"Loading pre-filtered results from: {args.filtered_input_file}")
        try:
            with open(args.filtered_input_file, 'r', encoding='utf-8') as f:
                all_filtered_results = json.load(f)
            logger.info(f"Loaded {len(all_filtered_results)} results from file.")
        except Exception as e:
            logger.error(f"Failed to load filtered results from {args.filtered_input_file}: {e}", exc_info=True)
            await agent.close()
            return
    elif args.skip_filtering:
        logger.info("Skipping filtering. Attempting to fetch all assessed results.")
        all_filtered_results = db.get_all_assessed_results() # Needs implementation in Database class
        logger.info(f"Fetched {len(all_filtered_results)} assessed results (filtering skipped).")
    else:
        logger.info("Applying filtering to assessed results...")
        filtering_module = ResultFilteringModule(db_path=args.db_path)
        
        # Filter research papers
        logger.info(f"Filtering top {args.research_filter_percentage}% research papers.")
        research_results = filtering_module.get_top_n_percent_results_by_source(
            source_type='paper', # Assuming 'paper' is the type used for research papers
            percentage=args.research_filter_percentage
        )
        all_filtered_results.extend(research_results)
        logger.info(f"Found {len(research_results)} research paper results after filtering.")

        # Filter internet results
        logger.info(f"Filtering top {args.internet_filter_percentage}% internet results.")
        internet_results = filtering_module.get_top_n_percent_results_by_source(
            source_type='internet',
            percentage=args.internet_filter_percentage
        )
        all_filtered_results.extend(internet_results)
        logger.info(f"Found {len(internet_results)} internet results after filtering.")
        
        # Deduplicate (in case a result somehow got into both lists, though unlikely with source_type)
        seen_ids = set()
        deduplicated_results = []
        for item in all_filtered_results:
            if item.get('id') not in seen_ids:
                deduplicated_results.append(item)
                seen_ids.add(item['id'])
        all_filtered_results = deduplicated_results
        logger.info(f"Total unique filtered results to process: {len(all_filtered_results)}")

    if not all_filtered_results:
        logger.info("No results to process after filtering (or from input file/skip). Exiting.")
        await agent.close()
        return

    if args.max_results_to_process is not None and args.max_results_to_process < len(all_filtered_results):
        logger.info(f"Limiting processing to {args.max_results_to_process} results due to --max-results-to-process argument.")
        results_to_process = all_filtered_results[:args.max_results_to_process]
    else:
        results_to_process = all_filtered_results

    # After filtering, create filtered DB copy
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_db_path = os.path.join(os.path.dirname(db.db_path), f"filtered_results_{ts}.db")
    shutil.copyfile(db.db_path, new_db_path)
    logger.info(f"Created filtered DB: {new_db_path}")
    filtered_db = Database(db_path=new_db_path)
    # Keep only filtered query_results in filtered DB
    keep_ids = [item['id'] for item in all_filtered_results]
    filtered_db.remove_unwanted_query_results(keep_ids)
    # Clear any old fetched_content
    filtered_db.reset_fetched_content()

    # Use filtered_db for content fetching
    db = filtered_db

    try:
        await process_filtered_results(db, agent, results_to_process)
    except Exception as e:
        logger.error(f"An unhandled error occurred during the main processing loop: {e}", exc_info=True)
    finally:
        logger.info("Closing browser...")
        await agent.close()
        logger.info("Main Workflow Part 2 finished.")


if __name__ == "__main__":
    asyncio.run(main())
