#!/usr/bin/env python3
"""Quick script to check domain and locale columns in the database."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from database import Database

def check_domain_locale():
    db = Database('tests/test_sentiment_research.db')
    
    # Get all results from the database
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT id, url, title, domain, locale, found_at
            FROM query_results 
            ORDER BY id DESC 
            LIMIT 10
        """)
        results = cursor.fetchall()
    
    print("📊 Domain and Locale check for latest 10 results:")
    print(f"Found {len(results)} results\n")
    
    for result in results:
        print(f"Result ID: {result['id']}")
        print(f"URL: {result['url']}")
        print(f"Domain: {result['domain'] or 'NULL'}")
        print(f"Locale: {result['locale'] or 'NULL'}")
        print(f"Title: {(result['title'] or '')[:60]}...")
        print("-" * 60)

if __name__ == "__main__":
    check_domain_locale()
        title = result['title'] or ""
        
        print(f"{i}. Title: {title[:60]}...")
        print(f"   URL: {result['url']}")
        print(f"   Snippet length: {len(snippet)} characters")
        print(f"   Snippet preview: \"{snippet[:100]}...\"")
        if len(snippet) > 100:
            print(f"   Snippet ending: \"...{snippet[-50:]}\"")
        print()
    
    db.close()

if __name__ == "__main__":
    check_snippet_lengths()
