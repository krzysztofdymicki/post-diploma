#!/usr/bin/env python3
"""
Main workflow orchestrator for sentiment analysis research.

This script coordinates the complete research workflow:
1. Loads generated queries from the outputs/ directory
2. Executes searches using both internet and research paper providers
3. Logs progress and provides comprehensive reporting

Usage:
    python main.py [options]
    
Options:
    --queries-file: Specific queries JSON file to use (optional)
    --internet-only: Only use internet search provider
    --papers-only: Only use research papers provider
    --max-queries: Maximum number of queries to process (optional)
"""

import json
import os
import asyncio
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from database import Database
from internet_search_provider import InternetSearchModule
from research_papers_provider import ResearchPapersModule


class ResearchWorkflow:
    """Main orchestrator for the research workflow."""
    
    def __init__(self, db_path: str = "data/sentiment_research.db"):
        """Initialize the workflow with database connection."""
        self.database = Database(db_path)
        self.internet_provider = InternetSearchModule(db_path)
        self.research_provider = ResearchPapersModule(db_path)
        
        # Setup logging
        self.setup_logging()
        
    def setup_logging(self):
        """Setup logging configuration."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"main_workflow_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()  # Also log to console
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Starting research workflow - logs saved to {log_file}")
        
    def find_latest_queries_file(self) -> Optional[Path]:
        """Find the most recent queries file in outputs/ directory."""
        outputs_dir = Path("outputs")
        if not outputs_dir.exists():
            self.logger.error("outputs/ directory not found. Run query_agent.py first.")
            return None
            
        json_files = list(outputs_dir.glob("query_agent_search_queries_*.json"))
        if not json_files:
            self.logger.error("No query files found in outputs/. Run query_agent.py first.")
            return None
            
        # Sort by modification time, newest first
        latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
        self.logger.info(f"Using queries file: {latest_file}")
        return latest_file
        
    def load_queries(self, queries_file: Optional[Path] = None) -> Dict[str, Any]:
        """Load queries from JSON file."""
        if queries_file is None:
            queries_file = self.find_latest_queries_file()
            if queries_file is None:
                raise FileNotFoundError("No queries file found")
                
        try:
            with open(queries_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.logger.info(f"Loaded {len(data.get('queries', []))} queries for topic: {data.get('topic', 'unknown')}")
            return data
            
        except Exception as e:
            self.logger.error(f"Error loading queries file {queries_file}: {e}")
            raise
            
    async def execute_searches(self, queries_data: Dict[str, Any], 
                             use_internet: bool = True, 
                             use_papers: bool = True,
                             max_queries: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute searches for all queries using selected providers.
        
        Args:
            queries_data: Loaded queries data from JSON
            use_internet: Whether to use internet search provider
            use_papers: Whether to use research papers provider
            max_queries: Maximum number of queries to process
            
        Returns:
            Dictionary with execution results and statistics
        """
        queries = queries_data.get('queries', [])
        topic = queries_data.get('topic', 'unknown')
        
        if max_queries:
            queries = queries[:max_queries]
            self.logger.info(f"Limited to first {max_queries} queries")
            
        results = {
            'total_queries': len(queries),
            'internet_results': {},
            'papers_results': {},
            'errors': [],
            'start_time': datetime.now().isoformat(),
            'topic': topic        }
        
        self.logger.info(f"Starting searches for {len(queries)} queries")
        self.logger.info(f"Providers: Internet={use_internet}, Papers={use_papers}")
        
        for i, query in enumerate(queries, 1):
            self.logger.info(f"Processing query {i}/{len(queries)}: {query}")
            
            # Internet search
            if use_internet:
                try:
                    self.logger.info(f"  → Internet search...")
                    query_id = self.internet_provider.search_and_store(query, "tools")
                    
                    if query_id:
                        results['internet_results'][query] = {
                            'query_id': query_id,
                            'status': 'success'
                        }
                        self.logger.info(f"  ✓ Internet search completed (Query ID: {query_id})")
                    else:
                        results['internet_results'][query] = {
                            'status': 'failed'
                        }
                        self.logger.warning(f"  ✗ Internet search failed")
                        
                except Exception as e:
                    error_msg = f"Internet search error for '{query}': {e}"
                    self.logger.error(f"  ✗ {error_msg}")
                    results['errors'].append(error_msg)
                    results['internet_results'][query] = {
                        'status': 'error',
                        'error': str(e)
                    }
                    
            # Research papers search
            if use_papers:
                # Add delay between different providers to avoid rate limiting
                if use_internet:
                    await asyncio.sleep(3)  # 3-second delay between providers
                    
                try:
                    self.logger.info(f"  → Research papers search...")
                    query_id = await self.research_provider.search_and_store(query, "tools")
                    
                    if query_id:
                        results['papers_results'][query] = {
                            'query_id': query_id,
                            'status': 'success'
                        }
                        self.logger.info(f"  ✓ Research papers search completed (Query ID: {query_id})")
                    else:
                        results['papers_results'][query] = {
                            'status': 'failed'
                        }
                        self.logger.warning(f"  ✗ Research papers search failed")
                        
                except Exception as e:
                    error_msg = f"Research papers search error for '{query}': {e}"
                    self.logger.error(f"  ✗ {error_msg}")
                    results['errors'].append(error_msg)
                    results['papers_results'][query] = {
                        'status': 'error',
                        'error': str(e)
                    }
                    
            self.logger.info(f"Completed query {i}/{len(queries)}\n")
            
        results['end_time'] = datetime.now().isoformat()
        return results
        
    def generate_report(self, results: Dict[str, Any]) -> str:
        """Generate a comprehensive report of the workflow execution."""
        report = []
        report.append("=" * 60)
        report.append("SENTIMENT ANALYSIS RESEARCH WORKFLOW REPORT")
        report.append("=" * 60)
        report.append(f"Topic: {results['topic']}")
        report.append(f"Execution time: {results['start_time']} - {results['end_time']}")
        report.append(f"Total queries processed: {results['total_queries']}")
        report.append("")
        
        # Internet search results
        if results['internet_results']:
            report.append("INTERNET SEARCH RESULTS:")
            report.append("-" * 30)
            success_count = sum(1 for r in results['internet_results'].values() if r['status'] == 'success')
            report.append(f"Successful: {success_count}/{len(results['internet_results'])}")
            
            for query, result in results['internet_results'].items():
                status_icon = "✓" if result['status'] == 'success' else "✗"
                report.append(f"  {status_icon} {query} - {result['status']}")
            report.append("")
            
        # Research papers results
        if results['papers_results']:
            report.append("RESEARCH PAPERS SEARCH RESULTS:")
            report.append("-" * 35)
            success_count = sum(1 for r in results['papers_results'].values() if r['status'] == 'success')
            report.append(f"Successful: {success_count}/{len(results['papers_results'])}")
            
            for query, result in results['papers_results'].items():
                status_icon = "✓" if result['status'] == 'success' else "✗"
                report.append(f"  {status_icon} {query} - {result['status']}")
            report.append("")
            
        # Errors
        if results['errors']:
            report.append("ERRORS:")
            report.append("-" * 10)
            for error in results['errors']:
                report.append(f"  • {error}")
            report.append("")
            
        # Database statistics        report.append("DATABASE STATISTICS:")
        report.append("-" * 20)
        try:
            stats = self.database.get_statistics()
            report.append(f"Total queries in DB: {stats.get('total_queries', 'N/A')}")
            report.append(f"Total resources found: {stats.get('total_resources', 'N/A')}")
            
            # Show resources by source (current workflow)
            resources_by_source = stats.get('resources_by_source', {})
            if resources_by_source:
                report.append(f"Resources by source:")
                for source_type, count in resources_by_source.items():
                    report.append(f"  • {source_type}: {count}")
            
            # Show historical query type breakdown if exists
            resources_by_type = stats.get('resources_by_type', {})
            if resources_by_type:
                report.append(f"Resources by historical query type:")
                for db_query_type, count in resources_by_type.items():
                    report.append(f"  • {db_query_type}: {count}")
                    
        except Exception as e:
            report.append(f"Error retrieving statistics: {e}")
            
        report.append("=" * 60)
        
        return "\n".join(report)
        
    def save_results(self, results: Dict[str, Any]):
        """Save execution results to JSON file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        outputs_dir = Path("outputs")
        outputs_dir.mkdir(exist_ok=True)
        
        results_file = outputs_dir / f"workflow_results_{timestamp}.json"
        
        try:
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Results saved to {results_file}")
        except Exception as e:
            self.logger.error(f"Error saving results: {e}")
            
    async def run(self, queries_file: Optional[Path] = None,
                  use_internet: bool = True,
                  use_papers: bool = True,
                  max_queries: Optional[int] = None):
        """Run the complete workflow."""
        try:
            # Load queries
            queries_data = self.load_queries(queries_file)
            
            # Execute searches
            results = await self.execute_searches(
                queries_data, use_internet, use_papers, max_queries
            )
            
            # Generate and display report
            report = self.generate_report(results)
            print(report)
            self.logger.info("Workflow report generated")
            
            # Save results
            self.save_results(results)
            
            return results
            
        except Exception as e:
            self.logger.error(f"Workflow failed: {e}")
            raise


async def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Execute sentiment analysis research workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                          # Use latest queries file, both providers
    python main.py --internet-only          # Only internet search
    python main.py --papers-only            # Only research papers
    python main.py --max-queries 5          # Process only first 5 queries
    python main.py --queries-file outputs/query_agent_search_queries_20250606_155559.json
        """
    )
    
    parser.add_argument(
        '--queries-file',
        type=Path,
        help='Specific queries JSON file to use (default: latest in outputs/)'
    )
    
    parser.add_argument(
        '--internet-only',
        action='store_true',
        help='Only use internet search provider'
    )
    
    parser.add_argument(
        '--papers-only',
        action='store_true',
        help='Only use research papers provider'
    )
    
    parser.add_argument(
        '--max-queries',
        type=int,
        help='Maximum number of queries to process'
    )
    
    args = parser.parse_args()
    
    # Validate provider selection
    use_internet = not args.papers_only
    use_papers = not args.internet_only
    
    if not use_internet and not use_papers:
        print("Error: Cannot disable both providers")
        return 1
        
    # Initialize and run workflow
    workflow = ResearchWorkflow()
    
    try:
        await workflow.run(
            queries_file=args.queries_file,
            use_internet=use_internet,
            use_papers=use_papers,
            max_queries=args.max_queries
        )
        print("\n✓ Workflow completed successfully!")
        return 0
        
    except Exception as e:
        print(f"\n✗ Workflow failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
