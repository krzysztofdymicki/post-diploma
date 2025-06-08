"""
Result Filtering Module for Research Workflow

This module handles filtering of assessed query results to select the top N% 
of results by source type (internet, paper/research_papers) based on their 
weighted_average_score from quality assessments.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from database import Database

logger = logging.getLogger(__name__)


class ResultFilteringModule:
    """
    Handles filtering of assessed query results to get top N% by source type.
    """
    
    def __init__(self, db_path: str = None):
        """Initialize the filtering module with database connection."""
        self.db = Database(db_path=db_path)
        logger.info("ResultFilteringModule initialized")
    
    def get_top_n_percent_results_by_source(self, source_type: str, percentage: float = 10.0) -> List[Dict[str, Any]]:
        """
        Get the top N% of results for a specific source type based on weighted_average_score.
        
        Args:
            source_type: Either 'internet' or 'paper' (or 'research_papers')
            percentage: Percentage of top results to return (default 10.0)
            
        Returns:
            List of filtered results with assessment scores
        """
        # Remove duplicates before filtering
        self.db.remove_duplicates()
        
        logger.info(f"Filtering top {percentage}% results for source_type: {source_type}")
        
        # If percentage is zero or negative, return no results immediately
        if percentage <= 0:
            logger.info(f"Percentage set to {percentage}%, returning no results for source_type: {source_type}")
            return []
        # Normalize source_type (handle both 'paper' and 'research_papers')
        if source_type in ['research_papers', 'paper']:
            source_type = 'paper'
        elif source_type != 'internet':
            logger.warning(f"Unknown source_type: {source_type}. Proceeding anyway.")
        
        # Get all assessed results for this source type, ordered by score DESC
        all_results = self.db.get_results_for_filtering(source_type)
        
        if not all_results:
            logger.warning(f"No assessed results found for source_type: {source_type}")
            return []
        
        logger.info(f"Found {len(all_results)} assessed results for source_type: {source_type}")
        
        # Calculate how many results to return (top N%)
        total_count = len(all_results)
        top_count = max(1, int(total_count * percentage / 100))  # At least 1 result
        
        # Take the top N% results (already ordered by weighted_average_score DESC)
        filtered_results = all_results[:top_count]
        
        logger.info(f"Filtered to top {top_count} results ({percentage}% of {total_count})")
        
        return filtered_results
    
    def filter_and_save_results(self, 
                               internet_percentage: float = 10.0,
                               research_percentage: float = 10.0,
                               output_file: Optional[str] = None) -> str:
        """
        Filter results for both internet and research sources and save to JSON file.
        
        Args:
            internet_percentage: Percentage of top internet results to keep
            research_percentage: Percentage of top research results to keep
            output_file: Optional output file path. If None, generates timestamp-based name.
            
        Returns:
            Path to the saved results file
        """
        logger.info(f"Starting filtering: {internet_percentage}% internet, {research_percentage}% research")
        
        # Filter internet results
        internet_results = self.get_top_n_percent_results_by_source('internet', internet_percentage)
        logger.info(f"Filtered {len(internet_results)} internet results")
        
        # Filter research paper results
        research_results = self.get_top_n_percent_results_by_source('paper', research_percentage)
        logger.info(f"Filtered {len(research_results)} research paper results")
        
        # Combine results
        all_filtered_results = internet_results + research_results
        logger.info(f"Total filtered results: {len(all_filtered_results)}")
        
        # Generate output filename if not provided
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_dir = Path("outputs")
            output_dir.mkdir(exist_ok=True)
            output_file = str(output_dir / f"filtered_results_{timestamp}.json")
        
        # Save to JSON file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(all_filtered_results, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Filtered results saved to: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Error saving filtered results to {output_file}: {e}")
            raise
    
    def get_filtering_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about available results for filtering.
        
        Returns:
            Dictionary with counts and statistics for each source type
        """
        stats = {}
        
        for source_type in ['internet', 'paper']:
            results = self.db.get_results_for_filtering(source_type)
            
            if results:
                scores = [r['weighted_average_score'] for r in results if r['weighted_average_score'] is not None]
                stats[source_type] = {
                    'total_count': len(results),
                    'avg_score': sum(scores) / len(scores) if scores else 0,
                    'min_score': min(scores) if scores else 0,
                    'max_score': max(scores) if scores else 0,
                    'top_10_percent_count': max(1, int(len(results) * 0.1)),
                    'top_15_percent_count': max(1, int(len(results) * 0.15))
                }
            else:
                stats[source_type] = {
                    'total_count': 0,
                    'avg_score': 0,
                    'min_score': 0,
                    'max_score': 0,
                    'top_10_percent_count': 0,
                    'top_15_percent_count': 0
                }
        
        logger.info(f"Filtering statistics: {stats}")
        return stats


def main():
    """Command-line interface for the filtering module."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Filter assessed query results by source type and quality score",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to the SQLite database file"
    )
    parser.add_argument(
        "--internet-percentage",
        type=float,
        default=10.0,
        help="Percentage of top internet results to keep"
    )
    parser.add_argument(
        "--research-percentage", 
        type=float,
        default=10.0,
        help="Percentage of top research paper results to keep"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Output JSON file path (default: auto-generated with timestamp)"
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only show filtering statistics, don't filter results"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    )
    
    # Initialize filtering module
    filtering_module = ResultFilteringModule(db_path=args.db_path)
    
    if args.stats_only:
        # Show statistics only
        stats = filtering_module.get_filtering_statistics()
        print("\n=== Filtering Statistics ===")
        for source_type, data in stats.items():
            print(f"\n{source_type.upper()} Results:")
            print(f"  Total assessed: {data['total_count']}")
            print(f"  Average score: {data['avg_score']:.2f}")
            print(f"  Score range: {data['min_score']:.2f} - {data['max_score']:.2f}")
            print(f"  Top 10% count: {data['top_10_percent_count']}")
            print(f"  Top 15% count: {data['top_15_percent_count']}")
    else:
        # Filter and save results
        output_file = filtering_module.filter_and_save_results(
            internet_percentage=args.internet_percentage,
            research_percentage=args.research_percentage,
            output_file=args.output_file
        )
        print(f"\nFiltered results saved to: {output_file}")


if __name__ == "__main__":
    main()
