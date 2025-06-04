"""
Database module for sentiment analysis thesis information gathering system.
Handles SQLite database operations for managing search queries and their status.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class Database:
    """Simple SQLite database manager for the sentiment analysis research system."""
    
    def __init__(self, db_path: str = None):
        """Initialize database connection and create tables if they don't exist."""
        if db_path is None:
            # Default to data directory
            db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, 'sentiment_research.db')
        self.db_path = db_path
        self._connection = None
        self.init_database()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory for dict-like access."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Create database tables if they don't exist."""
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_text TEXT NOT NULL,
                    query_type TEXT NOT NULL CHECK (query_type IN ('tools', 'applications')),
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    results_count INTEGER DEFAULT 0                )            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS query_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT,
                    snippet TEXT,
                    position INTEGER,
                    domain TEXT,
                    locale TEXT,
                    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (query_id) REFERENCES queries (id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS fetched_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_result_id INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'fetching', 'success', 'failed')),
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content_type TEXT,
                    http_status_code INTEGER,
                    parsed_content TEXT,
                    title_extracted TEXT,
                    content_length INTEGER,
                    error_message TEXT,
                    FOREIGN KEY (query_result_id) REFERENCES query_results (id)
                )
            ''')
            conn.commit()
            
            # Migration: Add domain and locale columns if they don't exist
            self._migrate_add_domain_locale(conn)

    def _migrate_add_domain_locale(self, conn):
        """Add domain and locale columns to existing query_results table if they don't exist."""
        try:
            # Check if columns exist
            cursor = conn.execute("PRAGMA table_info(query_results)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'domain' not in columns:
                conn.execute('ALTER TABLE query_results ADD COLUMN domain TEXT')
                logger.info("Added 'domain' column to query_results table")
            
            if 'locale' not in columns:
                conn.execute('ALTER TABLE query_results ADD COLUMN locale TEXT')
                logger.info("Added 'locale' column to query_results table")
                
            conn.commit()
        except Exception as e:
            logger.error(f"Migration error: {e}")

    def add_query(self, query_text: str, query_type: str) -> int:
        """Add a new search query to the database."""
        if query_type not in ['tools', 'applications']:
            raise ValueError("query_type must be 'tools' or 'applications'")
        
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO queries (query_text, query_type)
                VALUES (?, ?)
            ''', (query_text, query_type))
            conn.commit()
            return cursor.lastrowid
    
    def get_query(self, query_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific query by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM queries WHERE id = ?', (query_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_queries_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all queries with a specific status."""
        if status not in ['pending', 'processing', 'completed', 'failed']:
            raise ValueError("Invalid status")
        
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM queries WHERE status = ? ORDER BY created_at', (status,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_queries_by_type(self, query_type: str) -> List[Dict[str, Any]]:
        """Get all queries of a specific type."""
        if query_type not in ['tools', 'applications']:
            raise ValueError("query_type must be 'tools' or 'applications'")
        
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM queries WHERE query_type = ? ORDER BY created_at', (query_type,))
            return [dict(row) for row in cursor.fetchall()]

    def update_query_status(self, query_id: int, status: str, results_count: int = None) -> bool:
        """Update the status of a query and automatically sync results_count."""
        if status not in ['pending', 'processing', 'completed', 'failed']:
            raise ValueError("Invalid status")
        
        with self.get_connection() as conn:
            # Always calculate actual results_count from query_results table
            cursor = conn.execute('''
                SELECT COUNT(*) as count FROM query_results WHERE query_id = ?
            ''', (query_id,))
            actual_results_count = cursor.fetchone()['count']
            
            # Use provided results_count if given, otherwise use actual count
            final_results_count = results_count if results_count is not None else actual_results_count
            
            cursor = conn.execute('''
                UPDATE queries 
                SET status = ?, results_count = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, final_results_count, query_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_all_queries(self) -> List[Dict[str, Any]]:
        """Get all queries ordered by creation date."""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM queries ORDER BY created_at')
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_query(self, query_id: int) -> bool:
        """Delete a query by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute('DELETE FROM queries WHERE id = ?', (query_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get basic statistics about queries and results in the database."""
        with self.get_connection() as conn:
            stats = {}
            
            # Total queries
            cursor = conn.execute('SELECT COUNT(*) as total FROM queries')
            stats['total_queries'] = cursor.fetchone()['total']
            
            # By status
            cursor = conn.execute('''
                SELECT status, COUNT(*) as count 
                FROM queries 
                GROUP BY status
            ''')
            stats['by_status'] = {row['status']: row['count'] for row in cursor.fetchall()}
            
            # By type
            cursor = conn.execute('''
                SELECT query_type, COUNT(*) as count 
                FROM queries 
                GROUP BY query_type
            ''')
            stats['by_type'] = {row['query_type']: row['count'] for row in cursor.fetchall()}
            
            # Query results statistics
            cursor = conn.execute('SELECT COUNT(*) as total FROM query_results')
            stats['total_results'] = cursor.fetchone()['total']
            
            # Average results per query (only for queries with results)
            cursor = conn.execute('''
                SELECT AVG(result_count) as avg_results
                FROM (
                    SELECT query_id, COUNT(*) as result_count
                    FROM query_results
                    GROUP BY query_id
                )
            ''')
            avg_result = cursor.fetchone()['avg_results']
            stats['avg_results_per_query'] = round(avg_result, 2) if avg_result else 0
            
            return stats
    
    def close(self):
        """Close the database connection if it exists."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close database connection."""
        self.close()    # Query Results methods
    
    def add_query_result(self, query_id: int, url: str, title: str = None, snippet: str = None, 
                        position: int = None, domain: str = None, locale: str = None) -> int:
        """Add a new search result for a query and auto-update results_count."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO query_results (query_id, url, title, snippet, position, domain, locale)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (query_id, url, title, snippet, position, domain, locale))
            
            # Automatically update results_count in queries table
            cursor = conn.execute('''
                UPDATE queries 
                SET results_count = (
                    SELECT COUNT(*) FROM query_results WHERE query_id = ?
                ), updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (query_id, query_id))
            
            conn.commit()
            return cursor.lastrowid
    
    def get_query_results_by_query(self, query_id: int) -> List[Dict[str, Any]]:
        """Get all results for a specific query."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM query_results 
                WHERE query_id = ? 
                ORDER BY position ASC, id ASC
            ''', (query_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_query_results(self) -> List[Dict[str, Any]]:
        """Get all query results ordered by query_id and position."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM query_results 
                ORDER BY query_id ASC, position ASC, id ASC
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_query_results_by_query(self, query_id: int) -> int:
        """Delete all results for a specific query and update results_count."""
        with self.get_connection() as conn:
            cursor = conn.execute('DELETE FROM query_results WHERE query_id = ?', (query_id,))
            deleted_count = cursor.rowcount
            
            # Update results_count in queries table
            cursor = conn.execute('''
                UPDATE queries 
                SET results_count = 0, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (query_id,))
            
            conn.commit()
            return deleted_count

    # Fetched Content methods
    def add_fetched_content(self, query_result_id: int, url: str, status: str = 'pending',
                           content_type: str = None, http_status_code: int = None,
                           parsed_content: str = None, title_extracted: str = None,
                           content_length: int = None, error_message: str = None) -> int:
        """Add a new fetched content record."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO fetched_content (
                    query_result_id, url, status, content_type, http_status_code,
                    parsed_content, title_extracted, content_length, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (query_result_id, url, status, content_type, http_status_code,
                  parsed_content, title_extracted, content_length, error_message))
            conn.commit()
            return cursor.lastrowid

    def get_fetched_content(self, content_id: int) -> Optional[Dict[str, Any]]:
        """Get a single fetched content record by ID."""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM fetched_content WHERE id = ?', (content_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_fetched_content_by_query_result(self, query_result_id: int) -> Optional[Dict[str, Any]]:
        """Get fetched content for a specific query result."""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM fetched_content WHERE query_result_id = ?', (query_result_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_fetched_content(self) -> List[Dict[str, Any]]:
        """Get all fetched content records."""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM fetched_content ORDER BY fetched_at DESC')
            return [dict(row) for row in cursor.fetchall()]

    def get_fetched_content_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all fetched content records with specific status."""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT * FROM fetched_content WHERE status = ? ORDER BY fetched_at DESC', (status,))
            return [dict(row) for row in cursor.fetchall()]

    def update_fetched_content_status(self, content_id: int, status: str, 
                                     http_status_code: int = None, parsed_content: str = None,
                                     title_extracted: str = None, content_length: int = None,
                                     error_message: str = None) -> bool:
        """Update fetched content status and related fields."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                UPDATE fetched_content 
                SET status = ?, http_status_code = ?, parsed_content = ?, 
                    title_extracted = ?, content_length = ?, error_message = ?,
                    fetched_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (status, http_status_code, parsed_content, title_extracted, 
                  content_length, error_message, content_id))
            conn.commit()
            return cursor.rowcount > 0

    def delete_fetched_content(self, content_id: int) -> bool:
        """Delete a fetched content record."""
        with self.get_connection() as conn:
            cursor = conn.execute('DELETE FROM fetched_content WHERE id = ?', (content_id,))
            conn.commit()
            return cursor.rowcount > 0

    def count_fetched_content_by_status(self) -> Dict[str, int]:
        """Get count of fetched content records by status."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT status, COUNT(*) as count 
                FROM fetched_content 
                GROUP BY status
            ''')
            return {row[0]: row[1] for row in cursor.fetchall()}
