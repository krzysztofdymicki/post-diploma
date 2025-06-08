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
import logging
import os
import json
from datetime import datetime
from pathlib import Path

from src.database import Database
from src.result_filtering_module import ResultFilteringModule
from src.browsing_agent import BrowsingAgent

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

def main():
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
        "--output-dir",
        type=str,
        default="outputs/retrieved_content",
        help="Directory to store downloaded PDFs and potentially other content."
    )
    parser.add_argument(
        "--gemini-api-key",
        type=str,
        default=os.environ.get("GEMINI_API_KEY"),
        help="Gemini API Key. Can also be set via GEMINI_API_KEY environment variable."
    )
    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless_helium", # When --no-headless is present, headless_helium becomes False
        help="Run Helium (Chrome) in non-headless mode for debugging."
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

    args = parser.parse_args()

    if not args.gemini_api_key:
        logger.error("GEMINI_API_KEY is required. Please provide it via --gemini-api-key or set the environment variable.")
        return

    logger.info("Starting Main Workflow Part 2: Filtering and Content Fetching.")
    logger.info(f"Log file: {log_file.resolve()}")
    logger.info(f"Arguments: {args}")

    db = None
    browsing_agent = None

    try:
        # Initialize Database
        logger.info(f"Initializing database at: {args.db_path or 'data/research_db.db'}")
        db = Database(db_path=args.db_path)

        filtered_results_to_process = {}

        if args.filtered_input_file:
            logger.info(f"Loading pre-filtered results from: {args.filtered_input_file}")
            try:
                with open(args.filtered_input_file, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                # The structure from save_filtered_results is:
                # { 'metadata': {...}, 'research_papers': [...], 'internet': [...] }
                # The BrowsingAgent expects a dict like: { 'paper': [...], 'internet': [...] }
                filtered_results_to_process['paper'] = loaded_data.get('research_papers', [])
                filtered_results_to_process['internet'] = loaded_data.get('internet', [])
                
                paper_count = len(filtered_results_to_process['paper'])
                internet_count = len(filtered_results_to_process['internet'])
                logger.info(f"Loaded {paper_count} paper items and {internet_count} internet items from file.")

            except FileNotFoundError:
                logger.error(f"Filtered input file not found: {args.filtered_input_file}")
                return
            except json.JSONDecodeError:
                logger.error(f"Error decoding JSON from filtered input file: {args.filtered_input_file}")
                return
            except Exception as e:
                logger.error(f"Error loading filtered input file {args.filtered_input_file}: {e}")
                return
        elif args.skip_filtering:
            logger.warning("Skipping filtering. Attempting to process ALL assessed results.")
            # This requires fetching all assessed results directly
            # This part needs careful implementation if truly needed, as it bypasses the typical filtering.
            # For now, let's assume this means taking all *assessed* results.
            # The ResultFilteringModule can provide this.
            filtering_module = ResultFilteringModule(db)
            all_assessed_papers = filtering_module.get_assessed_results_by_source('paper')
            all_assessed_internet = filtering_module.get_assessed_results_by_source('internet')
            filtered_results_to_process['paper'] = all_assessed_papers
            filtered_results_to_process['internet'] = all_assessed_internet
            logger.info(f"Processing {len(all_assessed_papers)} assessed paper items and {len(all_assessed_internet)} assessed internet items.")
        else:
            # 1. Filter Results
            logger.info("Initializing Result Filtering Module...")
            filtering_module = ResultFilteringModule(db)
            
            logger.info(f"Filtering top {args.research_filter_percentage}% research papers and {args.internet_filter_percentage}% internet results.")
            # The get_filtered_results returns a dict with 'research_papers' and 'internet' keys
            # and a 'summary'. We need to map 'research_papers' to 'paper' for the agent.
            raw_filtered = filtering_module.get_filtered_results(
                research_percentage=args.research_filter_percentage,
                internet_percentage=args.internet_filter_percentage
            )
            filtered_results_to_process['paper'] = raw_filtered.get('research_papers', [])
            filtered_results_to_process['internet'] = raw_filtered.get('internet', [])
            
            summary = raw_filtered.get('summary', {})
            logger.info(f"Filtering summary: {summary}")
            if summary.get('total_filtered', 0) == 0:
                logger.info("No results to process after filtering. Exiting.")
                return

        # 2. Initialize Browsing Agent
        logger.info("Initializing Browsing Agent...")
        browsing_agent = BrowsingAgent(
            database=db,
            output_dir=args.output_dir,
            gemini_api_key=args.gemini_api_key,
            headless_helium=args.headless_helium
        )

        # 3. Process Filtered Results with Agent
        logger.info("Starting content fetching process with Browsing Agent...")
        browsing_agent.process_filtered_results(filtered_results_to_process)
        
        logger.info("Content fetching process completed.")

    except Exception as e:
        logger.error(f"An error occurred in the main workflow: {e}", exc_info=True)
    finally:
        if browsing_agent:
            logger.info("Closing Browsing Agent...")
            browsing_agent.close()
        if db:
            logger.info("Closing database connection...")
            db.close()
        logger.info("Main Workflow Part 2 finished.")

if __name__ == "__main__":
    main()
