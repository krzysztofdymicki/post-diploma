#!/usr/bin/env python3
"""
Test script to check assessment coverage across all queries in the database.
This script verifies that assessments are being run for results from all queries,
not just the most recent one.
"""

import sqlite3
import os
from collections import defaultdict

def check_assessment_coverage():
    """Check which queries have assessments and which don't."""
    
    db_path = 'data/research_db.db'
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    print("=== Assessment Coverage Analysis ===\n")
    
    # Get all queries
    cursor = conn.execute("SELECT id, query_text, created_at FROM queries ORDER BY created_at")
    queries = cursor.fetchall()
    
    print(f"Total queries in database: {len(queries)}")
    
    # Get all query results with assessment status
    cursor = conn.execute("""
        SELECT 
            qr.id as result_id,
            qr.query_id,
            qr.title,
            q.query_text,
            CASE WHEN qra.id IS NOT NULL THEN 'assessed' ELSE 'unassessed' END as status
        FROM query_results qr
        JOIN queries q ON qr.query_id = q.id
        LEFT JOIN query_result_assessments qra ON qr.id = qra.query_result_id
        ORDER BY q.created_at, qr.found_at
    """)
    
    results = cursor.fetchall()
    print(f"Total query results: {len(results)}")
    
    # Group by query
    by_query = defaultdict(list)
    for result in results:
        by_query[result['query_id']].append(result)
    
    # Print summary for each query
    print("\n=== Per-Query Analysis ===")
    total_assessed = 0
    total_unassessed = 0
    
    for query in queries:
        query_id = query['id']
        query_text = query['query_text'][:60] + "..." if len(query['query_text']) > 60 else query['query_text']
        
        if query_id in by_query:
            query_results = by_query[query_id]
            assessed = sum(1 for r in query_results if r['status'] == 'assessed')
            unassessed = sum(1 for r in query_results if r['status'] == 'unassessed')
            total_assessed += assessed
            total_unassessed += unassessed
            
            status_icon = "✅" if unassessed == 0 else "⚠️" if assessed > 0 else "❌"
            print(f"{status_icon} Query {query_id}: {assessed}/{len(query_results)} assessed")
            print(f"   Text: {query_text}")
            print(f"   Created: {query['created_at']}")
            
            if unassessed > 0:
                print(f"   ⚠️  {unassessed} results still need assessment")
        else:
            print(f"❌ Query {query_id}: No results found")
            print(f"   Text: {query_text}")
        
        print()
    
    # Overall summary
    print("=== Overall Summary ===")
    print(f"Total results assessed: {total_assessed}")
    print(f"Total results unassessed: {total_unassessed}")
    if total_assessed + total_unassessed > 0:
        coverage = (total_assessed / (total_assessed + total_unassessed)) * 100
        print(f"Assessment coverage: {coverage:.1f}%")
    
    # Check if assessments are distributed across queries
    print("\n=== Assessment Distribution ===")
    if total_assessed > 0:
        cursor = conn.execute("""
            SELECT 
                q.id as query_id,
                q.query_text,
                COUNT(qra.id) as assessment_count
            FROM queries q
            JOIN query_results qr ON q.id = qr.query_id
            JOIN query_result_assessments qra ON qr.id = qra.query_result_id
            GROUP BY q.id, q.query_text
            ORDER BY q.created_at
        """)
        
        assessed_queries = cursor.fetchall()
        print(f"Queries with assessments: {len(assessed_queries)}/{len(queries)}")
        
        for aq in assessed_queries:
            query_text_short = aq['query_text'][:50] + "..." if len(aq['query_text']) > 50 else aq['query_text']
            print(f"  Query {aq['query_id']}: {aq['assessment_count']} assessments - {query_text_short}")
    else:
        print("No assessments found in database.")
    
    # Check original_query_text in assessments
    print("\n=== Assessment Query Text Check ===")
    cursor = conn.execute("""
        SELECT 
            qra.original_query_text,
            COUNT(*) as count
        FROM query_result_assessments qra
        GROUP BY qra.original_query_text
        ORDER BY count DESC
    """)
    
    assessment_queries = cursor.fetchall()
    if assessment_queries:
        print(f"Distinct original query texts in assessments: {len(assessment_queries)}")
        for aq in assessment_queries:
            query_text_short = aq['original_query_text'][:50] + "..." if len(aq['original_query_text']) > 50 else aq['original_query_text']
            print(f"  '{query_text_short}': {aq['count']} assessments")
    else:
        print("No assessments with original_query_text found.")
    
    conn.close()

if __name__ == "__main__":
    check_assessment_coverage()
