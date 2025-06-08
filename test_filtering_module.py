#!/usr/bin/env python3
"""
Test script for result_filtering_module.py

This script tests the filtering functionality and shows statistics
about available assessed results in the database.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.result_filtering_module import ResultFilteringModule
from src.database import Database
import logging
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

def test_filtering_statistics():
    """Test the filtering statistics functionality."""
    print("\n" + "="*60)
    print("TESTING FILTERING STATISTICS")
    print("="*60)
    
    filtering_module = ResultFilteringModule()
    stats = filtering_module.get_filtering_statistics()
    
    print("\n📊 FILTERING STATISTICS:")
    for source_type, data in stats.items():
        print(f"\n{source_type.upper()} Results:")
        print(f"  📁 Total assessed: {data['total_count']}")
        if data['total_count'] > 0:
            print(f"  📈 Average score: {data['avg_score']:.2f}")
            print(f"  📊 Score range: {data['min_score']:.2f} - {data['max_score']:.2f}")
            print(f"  🔝 Top 10% count: {data['top_10_percent_count']}")
            print(f"  🔝 Top 15% count: {data['top_15_percent_count']}")
        else:
            print("  ❌ No assessed results found")
    
    return stats

def test_filtering_by_source(source_type, percentage=15.0):
    """Test filtering for a specific source type."""
    print(f"\n" + "="*60)
    print(f"TESTING FILTERING: {source_type.upper()} - TOP {percentage}%")
    print("="*60)
    
    filtering_module = ResultFilteringModule()
    results = filtering_module.get_top_n_percent_results_by_source(source_type, percentage)
    
    print(f"\n🔍 Filtered {len(results)} results for {source_type}")
    
    if results:
        print(f"\n📋 TOP {min(5, len(results))} RESULTS:")
        for i, result in enumerate(results[:5], 1):
            title = result.get('title', 'No title')[:60] + "..." if len(result.get('title', '')) > 60 else result.get('title', 'No title')
            score = result.get('weighted_average_score', 0)
            url = result.get('url', 'No URL')[:50] + "..." if len(result.get('url', '')) > 50 else result.get('url', 'No URL')
            
            print(f"  {i}. 📄 {title}")
            print(f"     ⭐ Score: {score:.2f}")
            print(f"     🔗 URL: {url}")
            print()
    else:
        print(f"  ❌ No results found for {source_type}")
    
    return results

def test_full_filtering_and_save():
    """Test the full filtering process with saving to file."""
    print("\n" + "="*60)
    print("TESTING FULL FILTERING AND SAVE")
    print("="*60)
    
    filtering_module = ResultFilteringModule()
    
    try:
        output_file = filtering_module.filter_and_save_results(
            internet_percentage=5.0,
            research_percentage=5.0,
            output_file="test_filtered_results.json"
        )
        
        print(f"\n✅ Results saved to: {output_file}")
        
        # Read and show summary of saved file
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                saved_results = json.load(f)
            
            print(f"📁 File contains {len(saved_results)} results")
            
            # Count by source type
            internet_count = sum(1 for r in saved_results if r.get('source_type') == 'internet')
            paper_count = sum(1 for r in saved_results if r.get('source_type') in ['paper', 'research_papers'])
            
            print(f"   🌐 Internet: {internet_count}")
            print(f"   📚 Papers: {paper_count}")
            
            if saved_results:
                avg_score = sum(r.get('weighted_average_score', 0) for r in saved_results) / len(saved_results)
                print(f"   ⭐ Average score: {avg_score:.2f}")
        
        return output_file
        
    except Exception as e:
        print(f"❌ Error during filtering: {e}")
        return None

def test_database_content():
    """Check what's in the database for debugging."""
    print("\n" + "="*60)
    print("DATABASE CONTENT CHECK")
    print("="*60)
    
    db = Database()
    
    # Check total queries
    all_queries = db.get_all_queries()
    print(f"\n📝 Total queries in database: {len(all_queries)}")
    
    # Check total results by source type
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT source_type, COUNT(*) as count 
            FROM query_results 
            GROUP BY source_type
        """)
        result_counts = cursor.fetchall()
        
        print(f"\n📊 Results by source type:")
        for row in result_counts:
            print(f"   {row['source_type']}: {row['count']}")
    
    # Check assessments
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total_assessments,
                COUNT(CASE WHEN error_message IS NULL THEN 1 END) as successful_assessments,
                COUNT(CASE WHEN error_message IS NOT NULL THEN 1 END) as failed_assessments
            FROM query_result_assessments
        """)
        assessment_stats = cursor.fetchone()
        
        print(f"\n📈 Assessment statistics:")
        print(f"   Total assessments: {assessment_stats['total_assessments']}")
        print(f"   Successful: {assessment_stats['successful_assessments']}")
        print(f"   Failed: {assessment_stats['failed_assessments']}")

def main():
    """Run all tests."""
    print("🧪 TESTING RESULT FILTERING MODULE")
    print("=" * 80)
    
    # Test 1: Check database content
    test_database_content()
    
    # Test 2: Get filtering statistics
    stats = test_filtering_statistics()
    
    # Test 3: Test filtering for internet results (if available)
    if stats.get('internet', {}).get('total_count', 0) > 0:
        test_filtering_by_source('internet', 15.0)
    else:
        print("\n⚠️  Skipping internet filtering test - no internet results found")
    
    # Test 4: Test filtering for research papers (if available)
    if stats.get('paper', {}).get('total_count', 0) > 0:
        test_filtering_by_source('paper', 15.0)
    else:
        print("\n⚠️  Skipping paper filtering test - no paper results found")
    
    # Test 5: Test full filtering and save (if any results available)
    total_results = sum(s.get('total_count', 0) for s in stats.values())
    if total_results > 0:
        output_file = test_full_filtering_and_save()
        if output_file and os.path.exists(output_file):
            print(f"\n🗂️  Test file created: {output_file}")
            print("   You can examine this file or use it with main_part2.py")
    else:
        print("\n⚠️  Skipping full filtering test - no assessed results found")
    
    print("\n" + "="*80)
    print("🏁 TESTING COMPLETED")
    print("="*80)

if __name__ == "__main__":
    main()
