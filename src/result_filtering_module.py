#!/usr/bin/env python3
"""
Result Filtering Module

This module filters assessed query results to keep only the top-rated results
from each source type (research papers and internet sources).

Functionality:
- Selects top 10% of results from research papers source
- Selects top 10% of results from internet source
- Ranks results by weighted average score
- Provides filtered dataset for further processing
"""

import logging
from typing import List, Dict, Any, Optional
from database import Database

logger = logging.getLogger(__name__)


class ResultFilteringModule:
    """Module for filtering and selecting top-rated query results."""
    
    def __init__(self, database: Database):
        """
        Initialize the filtering module.
        
        Args:
            database: Database instance for accessing results
        """
        self.database = database
        
    def get_assessed_results_by_source(self, source_type: str) -> List[Dict[str, Any]]:
        """
        Get all assessed results from a specific source type, ordered by score.
        
        Args:
            source_type: 'paper' or 'internet'
            
        Returns:
            List of assessed results ordered by weighted_average_score descending
        """
        with self.database.get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    qra.*,
                    qr.url,
                    qr.title,
                    qr.snippet,
                    qr.domain,
                    qr.source_type,
                    qr.source_identifier,
                    qr.found_at
                FROM query_result_assessments qra
                JOIN query_results qr ON qra.query_result_id = qr.id
                WHERE qr.source_type = ? 
                    AND qra.weighted_average_score IS NOT NULL 
                    AND qra.error_message IS NULL
                ORDER BY qra.weighted_average_score DESC, qra.assessed_at DESC            ''', (source_type,))
            
            return [dict(row) for row in cursor.fetchall()]
            
    def filter_top_percentage(self, results: List[Dict[str, Any]], percentage: float = 10.0) -> List[Dict[str, Any]]:
        """
        Filter results to keep only top percentage by score.
        
        Args:
            results: List of assessed results
            percentage: Percentage of top results to keep (default: 10%)
            
        Returns:
            Filtered list containing top percentage of results
        """
        if not results:
            return []
            
        # Calculate number of results to keep
        total_count = len(results)
        keep_count = max(1, int(total_count * (percentage / 100.0)))
        
        logger.info(f"Filtering {total_count} results to keep top {keep_count} ({percentage}%)")
          # Results are already sorted by score, so just take the top ones
        return results[:keep_count]
        
    def get_filtered_results(self, research_percentage: float = 10.0, 
                           internet_percentage: float = 10.0) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get filtered results from both source types.
        
        Args:
            research_percentage: Percentage of research paper results to keep
            internet_percentage: Percentage of internet results to keep
            
        Returns:
            Dictionary with 'research_papers' and 'internet' keys containing filtered results
        """
        logger.info("Starting result filtering process...")
          # Get results from research papers
        research_results = self.get_assessed_results_by_source('paper')
        filtered_research = self.filter_top_percentage(research_results, research_percentage)
        
        logger.info(f"Research papers: {len(research_results)} total → {len(filtered_research)} filtered ({research_percentage}%)")
        
        # Get results from internet sources
        internet_results = self.get_assessed_results_by_source('internet')
        filtered_internet = self.filter_top_percentage(internet_results, internet_percentage)
        
        logger.info(f"Internet sources: {len(internet_results)} total → {len(filtered_internet)} filtered ({internet_percentage}%)")
        
        return {
            'research_papers': filtered_research,
            'internet': filtered_internet,
            'summary': {
                'research_papers_total': len(research_results),
                'research_papers_filtered': len(filtered_research),
                'research_papers_percentage': research_percentage,
                'internet_total': len(internet_results),
                'internet_filtered': len(filtered_internet),
                'internet_percentage': internet_percentage,
                'total_filtered': len(filtered_research) + len(filtered_internet)
            }
        }
    
    def get_filtering_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about available results for filtering.
        
        Returns:
            Dictionary with statistics about assessed results by source
        """
        stats = {}
        
        for source_type in ['paper', 'internet']:
            results = self.get_assessed_results_by_source(source_type)
            
            if results:
                scores = [r['weighted_average_score'] for r in results if r['weighted_average_score']]
                stats[source_type] = {
                    'total_count': len(results),
                    'avg_score': sum(scores) / len(scores) if scores else 0,
                    'min_score': min(scores) if scores else 0,
                    'max_score': max(scores) if scores else 0,
                    'score_range': f"{min(scores):.2f} - {max(scores):.2f}" if scores else "N/A"
                }
            else:
                stats[source_type] = {
                    'total_count': 0,
                    'avg_score': 0,
                    'min_score': 0,
                    'max_score': 0,
                    'score_range': "N/A"
                }
        
        return stats
    
    def save_filtered_results(self, filtered_results: Dict[str, List[Dict[str, Any]]], 
                            output_file: Optional[str] = None) -> str:
        """
        Save filtered results to JSON file.
        
        Args:
            filtered_results: Results from get_filtered_results()
            output_file: Optional output file path
            
        Returns:
            Path to saved file
        """
        import json
        from datetime import datetime
        from pathlib import Path
        
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"outputs/filtered_results_{timestamp}.json"
        
        # Ensure outputs directory exists
        Path(output_file).parent.mkdir(exist_ok=True)
        
        # Prepare data for JSON serialization
        serializable_results = {
            'metadata': {
                'filtered_at': datetime.now().isoformat(),
                'summary': filtered_results.get('summary', {})
            },
            'research_papers': filtered_results['research_papers'],
            'internet': filtered_results['internet']
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"Filtered results saved to {output_file}")
        return output_file


def main():
    """CLI interface for result filtering."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Filter assessed query results to keep top-rated results from each source",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python result_filtering_module.py                    # Filter with default 10% from each source
    python result_filtering_module.py --research 20 --internet 10   # Custom percentages
    python result_filtering_module.py --stats            # Show statistics only
        """
    )
    
    parser.add_argument(
        '--research',
        type=float,        default=10.0,
        help='Percentage of research paper results to keep (default: 10)'
    )
    
    parser.add_argument(
        '--internet', 
        type=float,        default=10.0,
        help='Percentage of internet results to keep (default: 10)'
    )
    
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show filtering statistics only'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        help='Output file path for filtered results'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Initialize module
    db = Database()
    filtering_module = ResultFilteringModule(db)
    
    # Show statistics if requested
    if args.stats:
        print("📊 Result Filtering Statistics")
        print("=" * 40)
        
        stats = filtering_module.get_filtering_statistics()
        
        for source_type, source_stats in stats.items():
            print(f"\n{source_type.replace('_', ' ').title()}:")
            print(f"  Total assessed results: {source_stats['total_count']}")
            print(f"  Average score: {source_stats['avg_score']:.2f}")
            print(f"  Score range: {source_stats['score_range']}")
            
            if source_stats['total_count'] > 0:
                keep_10_percent = max(1, int(source_stats['total_count'] * 0.10))
                print(f"  Would keep (10%): {keep_10_percent} results")
        
        return 0
    
    # Perform filtering
    try:
        print(f"🔍 Filtering results...")
        print(f"Research papers: keeping top {args.research}%")
        print(f"Internet sources: keeping top {args.internet}%")
        
        filtered_results = filtering_module.get_filtered_results(
            research_percentage=args.research,
            internet_percentage=args.internet
        )
        
        # Show summary
        summary = filtered_results['summary']
        print(f"\n📈 Filtering Results:")
        print(f"Research papers: {summary['research_papers_total']} → {summary['research_papers_filtered']}")
        print(f"Internet sources: {summary['internet_total']} → {summary['internet_filtered']}")
        print(f"Total filtered results: {summary['total_filtered']}")
        
        # Save results
        output_file = filtering_module.save_filtered_results(filtered_results, args.output)
        print(f"\n✅ Results saved to: {output_file}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Filtering failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
