#!/usr/bin/env python3
"""
Main workflow orchestrator for academic research.

This script coordinates the complete research workflow:
1. Accepts initial user query and generates detailed search queries using AI
2. Executes searches using both internet and research providers
3. Runs quality assessment on found results
4. Logs progress and provides comprehensive reporting

Usage:
    python main.py --topic "sentiment analysis applications" [options]
    
Options:
    --topic: Initial research topic/query (required for new workflow)
    --queries-file: Use existing queries JSON file instead of generating new ones
    --internet-only: Only use internet search provider
    --papers-only: Only use research papers provider
    --max-queries: Maximum number of queries to process (optional)
    --run-assessment: Run quality assessment on unassessed results
    --run-filtering: Run result filtering to keep only top-rated results
"""

import json
import os
import asyncio
import argparse
import logging
from datetime import datetime
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any

from database import Database
from internet_search_provider import InternetSearchModule
from research_papers_provider import ResearchPapersModule
from quality_assessment_module import QualityAssessmentModule
from result_filtering_module import ResultFilteringModule
from query_agent import generate_queries_programmatically
from browsing_agent import ContentExtractionAgent
from main_part2 import process_filtered_results


class ResearchWorkflow:
    """Main orchestrator for the research workflow."""
    
    def __init__(self, db_path: str = "data/research_db.db"):
        """Initialize the workflow with database connection."""
        self.database = Database(db_path)
        self.internet_provider = InternetSearchModule(db_path)
        self.research_provider = ResearchPapersModule(db_path)
        self.initial_user_query = None  # Store initial query for all steps
        
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
                    query_id = self.internet_provider.search_and_store(query, topic)
                    
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
                    query_id = await self.research_provider.search_and_store(query, topic)
                    
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
        report.append("ACADEMIC RESEARCH WORKFLOW REPORT")
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
        
        # Quality Assessment Results
        if 'assessment' in results:
            assessment = results['assessment']
            report.append("QUALITY ASSESSMENT RESULTS:")
            report.append("-" * 30)
            report.append(f"Processed: {assessment.get('processed_count', 0)}")
            report.append(f"Successful assessments: {assessment.get('success_count', 0)}")
            report.append(f"Failed assessments: {assessment.get('error_count', 0)}")
            
            # Show assessment statistics if available
            stats = assessment.get('statistics', {})
            if stats:
                if 'avg_relevance_score' in stats:
                    report.append(f"Average relevance score: {stats['avg_relevance_score']:.2f}")
                    report.append(f"Average credibility score: {stats['avg_credibility_score']:.2f}")
                    report.append(f"Average usefulness score: {stats['avg_usefulness_score']:.2f}")
                
                if stats.get('score_distribution'):
                    report.append("Score distribution:")
                    for score_range, count in stats['score_distribution'].items():
                        report.append(f"  • {score_range}: {count}")
            
            # Show assessment errors if any
            if assessment.get('errors'):
                error_count = len(assessment['errors'])
                report.append(f"Assessment errors: {error_count}")
                for error in assessment['errors'][:3]:  # Show first 3 errors
                    if isinstance(error, dict) and 'query_result_id' in error:
                        report.append(f"  • Result ID {error['query_result_id']}: {error.get('error', 'Unknown error')}")
                    else:
                        report.append(f"  • {error}")
            report.append("")
        
        # Database statistics
        report.append("DATABASE STATISTICS:")
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
        except Exception as e:            self.logger.error(f"Error saving results: {e}")
            
    async def run(self,
                  topic: Optional[str] = None,
                  queries_file: Optional[Path] = None,
                  use_internet: bool = True,
                  use_papers: bool = True,
                  max_queries: Optional[int] = None,
                  pages_to_visit: int = 5,
                  run_assessment: bool = True,
                  assessment_batch_size: int = 10,
                  run_fetching: bool = False,
                  research_filter_percent: float = 10.0,
                  internet_filter_percent: float = 10.0):
        """
        Run the complete workflow.
        
        Args:
            topic: Initial research topic (for new query generation)
            queries_file: Path to existing queries file (skips generation)
            use_internet: Whether to use internet search
            use_papers: Whether to use papers search  
            max_queries: Maximum queries to process            pages_to_visit: Pages to visit for query generation
            run_assessment: Whether to run quality assessment after searches            assessment_batch_size: Number of results to assess in one batch
        """
        try:
            # Generate or load queries
            if topic and not queries_file:
                # Generate new queries from topic
                self.logger.info("Generating queries from initial topic...")
                queries_data = self.generate_queries_from_topic(topic, pages_to_visit)
                if not queries_data:
                    raise Exception("Failed to generate queries from topic")
            else:
                # Load existing queries
                queries_data = self.load_queries(queries_file)
                # Extract topic from queries data for initial_user_query
                self.initial_user_query = queries_data.get('topic', 'unknown')
              # Execute searches
            results = await self.execute_searches(
                queries_data, use_internet, use_papers, max_queries
            )
            
            # Run quality assessment if enabled
            if run_assessment:
                self.logger.info("Starting quality assessment on search results...")
                assessment_results = await self.run_quality_assessment(
                    initial_user_query=self.initial_user_query,
                    batch_size=assessment_batch_size
                )
                
                # Add assessment results to main results
                results['assessment'] = assessment_results
                self.logger.info("Quality assessment completed")
            
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
            self.logger.error(f"Workflow failed: {e}")
            raise

    def generate_queries_from_topic(self, topic: str, pages_to_visit: int = 5) -> Optional[Dict]:
        """
        Generate search queries from initial topic using query_agent.
        
        Args:
            topic: Initial research topic/query
            pages_to_visit: Number of web pages to visit for exploration
            
        Returns:
            Dictionary with queries data or None if failed
        """
        self.logger.info(f"Starting query generation for topic: {topic}")
        self.initial_user_query = topic  # Store for later use in assessment
        
        try:
            result = generate_queries_programmatically(topic, pages_to_visit)
            
            if result.get('success'):
                self.logger.info(f"Successfully generated {len(result['queries'])} queries")
                return {
                    'topic': result['topic'],
                    'queries': result['queries'],
                    'queries_file': result.get('queries_file')
                }
            else:
                self.logger.error(f"Query generation failed: {result.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error in query generation: {e}")
            return None

    async def run_quality_assessment(self, initial_user_query: str, batch_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Run quality assessment on unassessed query results.
        
        Args:
            initial_user_query: The original research topic/query
            batch_size: Number of results to assess in one batch (None = assess all unassessed results)
            
        Returns:
            Dictionary with assessment results and statistics
        """
        try:
            assessment_module = QualityAssessmentModule(self.database)
            
            # Get unassessed results count
            unassessed_count = len(self.database.get_unassessed_query_results())
            self.logger.info(f"Found {unassessed_count} unassessed results")
            
            if unassessed_count == 0:
                self.logger.info("No unassessed results found - skipping assessment")
                return {
                    'processed_count': 0,
                    'success_count': 0,
                    'error_count': 0,
                    'errors': [],
                    'statistics': {}
                }
              # Run batch assessment
            results = assessment_module.run_assessment_workflow(
                batch_size=batch_size
            )
            
            # Get updated statistics
            stats = assessment_module.get_assessment_statistics()
            results['statistics'] = stats or {}
            
            self.logger.info(f"Assessment completed: {results['success_count']}/{results['processed_count']} successful")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Quality assessment failed: {e}")
            return {
                'processed_count': 0,
                'success_count': 0,
                'error_count': 1,
                'errors': [{'error': str(e)}],
                'statistics': {}
            }

async def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Execute academic research workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                          # Use latest queries file, both providers
    python main.py --internet-only          # Only internet search
    python main.py --papers-only            # Only research papers
    python main.py --max-queries 5          # Process only first 5 queries
    python main.py --run-assessment         # Run assessment on unassessed results
    python main.py --run-filtering          # Filter results to keep top 10% from each source
    python main.py --queries-file outputs/query_agent_search_queries_20250606_155559.json
        """
    )
    
    parser.add_argument(
        '--queries-file',        type=Path,
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
        '--max-queries',        type=int,
        help='Maximum number of queries to process'
    )
    
    parser.add_argument(
        '--run-assessment',
        action='store_true',
        help='Run quality assessment on unassessed results instead of search'
    )
    
    parser.add_argument(
        '--assessment-batch-size',
        type=int,
        default=None,
        help='Number of results to assess in one batch (default: all unassessed results)'
    )
    
    parser.add_argument(
        '--topic',
        type=str,
        help='Initial research topic/query (for new query generation)'
    )
    
    parser.add_argument(
        '--pages',
        type=int,
        default=10,
        help='Number of web pages to visit for query generation (default: 10)'
    )
    
    parser.add_argument(
        '--skip-assessment',
        action='store_true',
        help='Skip automatic quality assessment after searches'
    )
    
    parser.add_argument(
        '--clear-db',
        action='store_true',
        help='Clear database before starting workflow'
    )
    parser.add_argument(
        '--run-fetching',
        action='store_true',
        help='Run filtering and internet content fetching after assessment'
    )
    
    parser.add_argument(
        '--run-filtering',
        action='store_true',
        help='Run result filtering to keep only top-rated results'
    )
    
    parser.add_argument(
        '--research-filter-percent',
        type=float,
        default=10.0,
        help='Percentage of research paper results to keep in filtering (default: 10)'
    )
    
    parser.add_argument(
        '--internet-filter-percent',
        type=float,
        default=10.0,
        help='Percentage of internet results to keep in filtering (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Handle filtering workflow separately
    if args.run_filtering:
        return await run_filtering_workflow(args)
    
    # Handle assessment workflow separately
    if args.run_assessment:
        return await run_assessment_workflow(args)
    
    # Validate provider selection
    use_internet = not args.papers_only
    use_papers = not args.internet_only    
    if not use_internet and not use_papers:
        print("Error: Cannot disable both providers")
        return 1
          # Initialize and run search workflow
    workflow = ResearchWorkflow()
    
    # Clear database if requested
    if args.clear_db:
        print("🗑️ Clearing database...")
        workflow.database.clear_database()
        print("✓ Database cleared")
    
    try:
        await workflow.run(
            topic=args.topic,
            queries_file=args.queries_file,
            use_internet=use_internet,
            use_papers=use_papers,
            max_queries=args.max_queries,
            run_assessment=not args.skip_assessment,
            assessment_batch_size=args.assessment_batch_size,
            pages_to_visit=args.pages,
            run_fetching=args.run_fetching,
            research_filter_percent=args.research_filter_percent,
            internet_filter_percent=args.internet_filter_percent
        )
        print("\n✓ Workflow completed successfully!")
        return 0
        
    except Exception as e:
        print(f"\n✗ Workflow failed: {e}")
        return 1


async def run_filtering_workflow(args):
    """Run result filtering workflow to keep only top-rated results."""
    print("🔍 Starting Result Filtering Workflow...")
    
    try:
        # Initialize database and filtering module
        db = Database()
        # Pass the database path to the filtering module (avoid passing Database object)
        filtering_module = ResultFilteringModule(db_path=db.db_path)
        
        # Show current statistics
        print("\n📊 Current Database Statistics:")
        stats = filtering_module.get_filtering_statistics()
        
        total_assessed = 0
        for source_type, source_stats in stats.items():
            source_name = source_type.replace('_', ' ').title()
            print(f"\n{source_name}:")
            print(f"  Total assessed results: {source_stats['total_count']}")
            if source_stats['total_count'] > 0:
                print(f"  Average score: {source_stats['avg_score']:.2f}")
                print(f"  Score range: {source_stats['score_range']}")
            total_assessed += source_stats['total_count']
        
        if total_assessed == 0:
            print("\nNo assessed results found. Run assessment workflow first.")
            return 1
        
        # Perform filtering
        print(f"\n🔍 Filtering results...")
        print(f"Research papers: keeping top {args.research_filter_percent}%")
        print(f"Internet sources: keeping top {args.internet_filter_percent}%")
        
        filtered_results = filtering_module.get_filtered_results(
            research_percentage=args.research_filter_percent,
            internet_percentage=args.internet_filter_percent
        )
        
        summary = filtered_results['summary']
        print(f"\n📈 Filtering Results:")
        print(f"Research papers: {summary['research_papers_total']} → {summary['research_papers_filtered']}")
        print(f"Internet sources: {summary['internet_total']} → {summary['internet_filtered']}")
        print(f"Total filtered results: {summary['total_filtered']}")
        
        # Save filtered results
        output_file = filtering_module.save_filtered_results(filtered_results)
        print(f"\n✅ Filtered results saved to: {output_file}")
        # --- Now fetch content for internet sources ---
        print("\n🔗 Fetching content for filtered internet sources...")
        # Reset any previous fetched_content records
        db.reset_fetched_content()
        # Prepare browsing agent
        from browsing_agent import ContentExtractionAgent
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash-preview-05-20')
        agent = ContentExtractionAgent(llm)
        # Fetch only internet sources
        internet_items = filtered_results.get('internet_sources', [])
        # Ensure async context
        import asyncio
        asyncio.run(process_filtered_results(db, agent, internet_items))
        print("✅ Content fetching completed for internet sources")
        
        # Show some examples if available
        if filtered_results['research_papers']:
            print(f"\n📚 Top 3 Research Paper Results:")
            for i, result in enumerate(filtered_results['research_papers'][:3]):
                score = result.get('weighted_average_score', 0)
                title = result.get('title', 'No title')[:60]
                print(f"  {i+1}. Score: {score:.2f} - {title}...")
        
        if filtered_results['internet_sources']:
            print(f"\n🌐 Top 3 Internet Results:")
            for i, result in enumerate(filtered_results['internet_sources'][:3]):
                score = result.get('weighted_average_score', 0)
                title = result.get('title', 'No title')[:60]
                print(f"  {i+1}. Score: {score:.2f} - {title}...")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Filtering workflow failed: {e}")
        return 1


async def run_assessment_workflow(args):
    """Run quality assessment workflow on unassessed results."""
    print("🔍 Starting Quality Assessment Workflow...")
    
    try:
        db = Database()
        assessment_module = QualityAssessmentModule(db)
          # Get unassessed results count
        unassessed_count = len(db.get_unassessed_query_results())
        print(f"Found {unassessed_count} unassessed results")
        
        if unassessed_count == 0:
            print("No unassessed results found. Run search workflow first.")
            return 1
            
        # Run batch assessment
        results = assessment_module.run_assessment_workflow(
            batch_size=args.assessment_batch_size
        )
        
        print(f"\n✅ Assessment completed!")
        print(f"Processed: {results['processed_count']}")
        print(f"Successful assessments: {results['success_count']}")
        print(f"Failed assessments: {results['error_count']}")
        
        if results['errors']:
            print(f"Errors encountered: {len(results['errors'])}")
            for error in results['errors'][:3]:  # Show first 3 errors
                print(f"  • Result ID {error['query_result_id']}: {error['error']}")
        
        # Show statistics
        stats = assessment_module.get_assessment_statistics()
        if stats:
            print(f"\n📊 Assessment Statistics:")
            print(f"Total assessments: {stats.get('total_assessments', 0)}")
            if 'avg_relevance_score' in stats:
                print(f"Average relevance: {stats['avg_relevance_score']:.2f}")
                print(f"Average credibility: {stats['avg_credibility_score']:.2f}")
                print(f"Average usefulness: {stats['avg_usefulness_score']:.2f}")
            
            if stats.get('score_distribution'):
                print(f"Score distribution:")
                for score_range, count in stats['score_distribution'].items():
                    print(f"  • {score_range}: {count}")
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Assessment workflow failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
