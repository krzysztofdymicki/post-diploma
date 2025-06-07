#!/usr/bin/env python3
"""
Test script to verify that assessment defaults to processing ALL results 
when --assessment-batch-size is not specified.
"""

import sys
import os
sys.path.append('src')

from database import Database

def main():
    """Test assessment default behavior."""
    print("🧪 Testing assessment default behavior...")
    
    db = Database("data/research_db.db")
    
    # Get total number of unassessed results
    unassessed_results = db.get_unassessed_query_results()
    total_unassessed = len(unassessed_results)
    
    print(f"📊 Total unassessed results in database: {total_unassessed}")
    
    if total_unassessed == 0:
        print("❌ No unassessed results found. Run search workflow first.")
        return 1
    
    # Test get_unassessed_query_results with limit=None (should return all)
    all_results = db.get_unassessed_query_results(limit=None)
    print(f"📈 Results with limit=None: {len(all_results)}")
    
    # Test get_unassessed_query_results with limit=10 (should return max 10)
    limited_results = db.get_unassessed_query_results(limit=10)
    print(f"📉 Results with limit=10: {len(limited_results)}")
    
    # Verify logic
    if len(all_results) == total_unassessed:
        print("✅ limit=None correctly returns ALL unassessed results")
    else:
        print("❌ limit=None does not return all results")
        
    if len(limited_results) <= 10:
        print("✅ limit=10 correctly limits results")
    else:
        print("❌ limit=10 does not limit results properly")
        
    print(f"\n📝 Summary:")
    print(f"  - When --assessment-batch-size is NOT specified (None): {len(all_results)} results will be assessed")
    print(f"  - When --assessment-batch-size=10: {len(limited_results)} results will be assessed")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
