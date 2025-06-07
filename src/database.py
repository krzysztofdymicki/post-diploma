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
            db_path = os.path.join(db_dir, 'research_db.db')
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
                    original_user_query TEXT,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    results_count INTEGER DEFAULT 0
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS query_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id INTEGER NOT NULL,
                    url TEXT,
                    title TEXT,
                    snippet TEXT,
                    position INTEGER,
                    domain TEXT,
                    locale TEXT,
                    source_type TEXT NOT NULL CHECK (source_type IN ('internet', 'mcp_papers', 'research_papers', 'paper')),
                    source_identifier TEXT,
                    pdf_url TEXT,
                    pdf_data TEXT,
                    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,                    FOREIGN KEY (query_id) REFERENCES queries (id)
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS fetched_content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_result_id INTEGER NOT NULL,
                    url TEXT,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'fetching', 'success', 'failed')),
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content_type TEXT,
                    http_status_code INTEGER,
                    parsed_content TEXT,
                    title_extracted TEXT,
                    content_length INTEGER,
                    error_message TEXT,
                    FOREIGN KEY (query_result_id) REFERENCES query_results (id)                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS query_result_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_result_id INTEGER NOT NULL,
                    original_query_text TEXT NOT NULL,
                    assessment_prompt TEXT,
                    llm_response_raw TEXT,
                    relevance_score INTEGER CHECK (relevance_score BETWEEN 1 AND 5),
                    credibility_score INTEGER CHECK (credibility_score BETWEEN 1 AND 5),
                    solidity_score INTEGER CHECK (solidity_score BETWEEN 1 AND 5),
                    overall_usefulness_score INTEGER CHECK (overall_usefulness_score BETWEEN 1 AND 5),
                    weighted_average_score REAL CHECK (weighted_average_score BETWEEN 1.0 AND 5.0),
                    llm_justification TEXT,
                    error_message TEXT,
                    assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (query_result_id) REFERENCES query_results (id)
                )
            ''')
            conn.commit()
            
            # Migration: Add domain and locale columns if they don't exist
            self._migrate_add_domain_locale(conn)
            
            # Migration: Add source_type and source_identifier columns, make url nullable
            self._migrate_add_source_fields(conn)
            
            # Migration: Add original_user_query column to queries table
            self._migrate_add_original_user_query(conn)

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

    def _migrate_add_source_fields(self, conn):
        """Add source_type and source_identifier columns, handle url nullable migration."""
        try:
            # Check if columns exist
            cursor = conn.execute("PRAGMA table_info(query_results)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'source_type' not in columns:
                # Add source_type column, default existing records to 'internet'
                conn.execute('ALTER TABLE query_results ADD COLUMN source_type TEXT NOT NULL DEFAULT "internet" CHECK (source_type IN ("internet", "mcp_papers", "research_papers", "paper"))')
                logger.info("Added 'source_type' column to query_results table")
            
            if 'source_identifier' not in columns:
                conn.execute('ALTER TABLE query_results ADD COLUMN source_identifier TEXT')
                logger.info("Added 'source_identifier' column to query_results table")
            # Migration: Add pdf_url and pdf_data columns if they don't exist
            if 'pdf_url' not in columns:
                conn.execute('ALTER TABLE query_results ADD COLUMN pdf_url TEXT')
                logger.info("Added 'pdf_url' column to query_results table")
            if 'pdf_data' not in columns:
                conn.execute('ALTER TABLE query_results ADD COLUMN pdf_data TEXT')
                logger.info("Added 'pdf_data' column to query_results table")
                
            # Note: SQLite doesn't support making existing columns nullable directly
            # For the url column, we'll handle this in the application logic
            # New tables created will have url as nullable
                
            conn.commit()
        except Exception as e:
            logger.error(f"Source fields migration error: {e}")

    def _migrate_add_original_user_query(self, conn):
        """Add original_user_query column to existing queries table if it doesn't exist."""
        try:
            # Check if column exists
            cursor = conn.execute("PRAGMA table_info(queries)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'original_user_query' not in columns:
                conn.execute('ALTER TABLE queries ADD COLUMN original_user_query TEXT')
                logger.info("Added 'original_user_query' column to queries table")
                
            conn.commit()
        except Exception as e:
            logger.error(f"Migration error: {e}")

    def add_query(self, query_text: str, original_user_query: str = None) -> int:
        """Add a new search query to the database."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO queries (query_text, original_user_query)
                VALUES (?, ?)
            ''', (query_text, original_user_query))
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
                WHERE id = ?            ''', (status, final_results_count, query_id))
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

    def clear_database(self):
        """Clear all data from all tables and recreate them with updated schema."""
        with self.get_connection() as conn:
            # Drop all tables to ensure fresh schema (in correct order due to foreign keys)
            conn.execute('DROP TABLE IF EXISTS query_result_assessments')
            conn.execute('DROP TABLE IF EXISTS fetched_content')
            conn.execute('DROP TABLE IF EXISTS query_results') 
            conn.execute('DROP TABLE IF EXISTS queries')
            logger.info("Dropped all tables")
              # Reset auto-increment counters - check if sqlite_sequence exists first
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
            if cursor.fetchone():
                conn.execute('DELETE FROM sqlite_sequence WHERE name IN ("queries", "query_results", "fetched_content", "query_result_assessments")')
                logger.info("Reset auto-increment counters")
            else:
                logger.info("sqlite_sequence table does not exist, skipping counter reset")
            
            conn.commit()
            
        # Recreate tables with fresh schema
        self.init_database()
        logger.info("Database cleared and recreated successfully")

    # Query Results methods
    def add_query_result(self, query_id: int, url: str = None, title: str = None, snippet: str = None,
                        position: int = None, domain: str = None, locale: str = None,
                        source_type: str = 'internet', source_identifier: str = None,
                        pdf_url: str = None, pdf_data: str = None) -> int:
        """Add a new search result for a query and auto-update results_count."""        # Validate source_type
        if source_type not in ['internet', 'mcp_papers', 'research_papers', 'paper']:
            raise ValueError("source_type must be 'internet', 'mcp_papers', 'research_papers', or 'paper'")
            
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO query_results (
                    query_id, url, title, snippet, position, domain, locale,
                    source_type, source_identifier, pdf_url, pdf_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                query_id, url, title, snippet, position, domain, locale,
                source_type, source_identifier, pdf_url, pdf_data
            ))
            
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

    def get_query_results(self, query_id: int) -> List[Dict[str, Any]]:
        """Alias for get_query_results_by_query for compatibility."""
        return self.get_query_results_by_query(query_id)

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

    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive database statistics for reporting."""
        with self.get_connection() as conn:
            stats = {}
            
            # Total queries
            cursor = conn.execute('SELECT COUNT(*) FROM queries')
            stats['total_queries'] = cursor.fetchone()[0]
            
            # Queries by status
            cursor = conn.execute('''
                SELECT status, COUNT(*) as count 
                FROM queries 
                GROUP BY status
            ''')
            stats['queries_by_status'] = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Total resources
            cursor = conn.execute('SELECT COUNT(*) FROM query_results')
            stats['total_resources'] = cursor.fetchone()[0]
            
            # Resources by source type (more useful for current workflow)
            cursor = conn.execute('''
                SELECT source_type, COUNT(*) as count
                FROM query_results
                WHERE source_type IS NOT NULL
                GROUP BY source_type
            ''')
            stats['resources_by_source'] = {row[0]: row[1] for row in cursor.fetchall()}
              # Content status statistics
            cursor = conn.execute('SELECT COUNT(*) FROM fetched_content')
            total_content = cursor.fetchone()[0]
            stats['total_content'] = total_content
            
            if total_content > 0:
                stats['content_by_status'] = self.count_fetched_content_by_status()
            else:
                stats['content_by_status'] = {}
                
            # Recent activity (queries from last 24 hours)
            cursor = conn.execute('''
                SELECT COUNT(*) FROM queries 
                WHERE created_at >= datetime('now', '-1 day')
            ''')
            stats['recent_queries_24h'] = cursor.fetchone()[0]            
            return stats

    # Assessment methods
    def add_assessment(self, query_result_id: int, original_query_text: str, 
                      assessment_prompt: str = None, llm_response_raw: str = None,
                      relevance_score: int = None, credibility_score: int = None,
                      solidity_score: int = None, overall_usefulness_score: int = None,
                      weighted_average_score: float = None,
                      llm_justification: str = None, error_message: str = None) -> int:
        """Add a new quality assessment for a query result."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO query_result_assessments (
                    query_result_id, original_query_text, assessment_prompt, llm_response_raw,
                    relevance_score, credibility_score, solidity_score, overall_usefulness_score,
                    weighted_average_score, llm_justification, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                query_result_id, original_query_text, assessment_prompt, llm_response_raw,
                relevance_score, credibility_score, solidity_score, overall_usefulness_score,
                weighted_average_score, llm_justification, error_message
            ))
            conn.commit()
            return cursor.lastrowid

    def update_or_create_assessment(self, 
                      query_result_id: int, original_query_text: str, 
                      assessment_prompt: str, llm_response_raw: str,
                      relevance_score: int = None, credibility_score: int = None,
                      solidity_score: int = None, overall_usefulness_score: int = None,
                      weighted_average_score: float = None,
                      llm_justification: str = None, error_message: str = None) -> int:
        """Update existing assessment or create new one if it doesn't exist."""
        with self.get_connection() as conn:
            # Check if assessment already exists
            cursor = conn.execute('''
                SELECT id FROM query_result_assessments 
                WHERE query_result_id = ?
            ''', (query_result_id,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing assessment
                cursor = conn.execute('''
                    UPDATE query_result_assessments SET
                        original_query_text = ?, assessment_prompt = ?, llm_response_raw = ?,
                        relevance_score = ?, credibility_score = ?, solidity_score = ?, 
                        overall_usefulness_score = ?, weighted_average_score = ?, 
                        llm_justification = ?, error_message = ?, assessed_at = CURRENT_TIMESTAMP
                    WHERE query_result_id = ?
                ''', (
                    original_query_text, assessment_prompt, llm_response_raw,
                    relevance_score, credibility_score, solidity_score, overall_usefulness_score,
                    weighted_average_score, llm_justification, error_message, query_result_id
                ))
                conn.commit()
                return existing[0]
            else:
                # Create new assessment
                cursor = conn.execute('''
                    INSERT INTO query_result_assessments (
                        query_result_id, original_query_text, assessment_prompt, llm_response_raw,
                        relevance_score, credibility_score, solidity_score, overall_usefulness_score,
                        weighted_average_score, llm_justification, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    query_result_id, original_query_text, assessment_prompt, llm_response_raw,
                    relevance_score, credibility_score, solidity_score, overall_usefulness_score,
                    weighted_average_score, llm_justification, error_message
                ))
                conn.commit()
                return cursor.lastrowid

    def get_assessment_by_query_result_id(self, query_result_id: int) -> Optional[Dict[str, Any]]:
        """Get assessment for a specific query result."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM query_result_assessments 
                WHERE query_result_id = ?
            ''', (query_result_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_unassessed_query_results(self, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
        """Get query results that haven't been assessed yet OR have assessment errors, with original query text."""
        with self.get_connection() as conn:
            if limit is None:                # Get all unassessed results when limit is None
                cursor = conn.execute('''
                    SELECT 
                        qr.id as query_result_id,
                        qr.query_id,
                        qr.url,
                        qr.title,
                        qr.snippet,
                        qr.domain,
                        qr.source_type,
                        qr.source_identifier,
                        COALESCE(q.original_user_query, q.query_text) as original_query_text
                    FROM query_results qr
                    JOIN queries q ON qr.query_id = q.id
                    LEFT JOIN query_result_assessments qra ON qr.id = qra.query_result_id
                    WHERE qra.id IS NULL OR qra.error_message IS NOT NULL
                    ORDER BY qr.found_at DESC
                ''')
            else:
                cursor = conn.execute('''
                    SELECT 
                        qr.id as query_result_id,
                        qr.query_id,
                        qr.url,
                        qr.title,
                        qr.snippet,
                        qr.domain,
                        qr.source_type,
                        qr.source_identifier,
                        COALESCE(q.original_user_query, q.query_text) as original_query_text                    FROM query_results qr
                    JOIN queries q ON qr.query_id = q.id
                    LEFT JOIN query_result_assessments qra ON qr.id = qra.query_result_id
                    WHERE qra.id IS NULL OR qra.error_message IS NOT NULL
                    ORDER BY qr.found_at DESC
                    LIMIT ?
                ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_assessments(self) -> List[Dict[str, Any]]:
        """Get all quality assessments with related query result data."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    qra.*,
                    qr.url,
                    qr.title,
                    qr.snippet,
                    qr.domain,
                    qr.source_type
                FROM query_result_assessments qra
                JOIN query_results qr ON qra.query_result_id = qr.id
                ORDER BY qra.assessed_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_assessments_by_score_range(self, min_usefulness: int = 3, max_usefulness: int = 5) -> List[Dict[str, Any]]:
        """Get assessments within a specific usefulness score range."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    qra.*,
                    qr.url,
                    qr.title,
                    qr.snippet,
                    qr.domain,
                    qr.source_type
                FROM query_result_assessments qra
                JOIN query_results qr ON qra.query_result_id = qr.id
                WHERE qra.overall_usefulness_score BETWEEN ? AND ?
                ORDER BY qra.overall_usefulness_score DESC, qra.assessed_at DESC
            ''', (min_usefulness, max_usefulness))
            return [dict(row) for row in cursor.fetchall()]

    def count_assessments_by_score(self) -> Dict[str, int]:
        """Get count of assessments by overall usefulness score."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT overall_usefulness_score, COUNT(*) as count 
                FROM query_result_assessments 
                WHERE overall_usefulness_score IS NOT NULL
                GROUP BY overall_usefulness_score
                ORDER BY overall_usefulness_score DESC
            ''')
            return {f"score_{row[0]}": row[1] for row in cursor.fetchall()}

    def get_latest_topic(self) -> Optional[str]:
        """Get the most recent topic from queries table."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT query_text 
                FROM queries 
                ORDER BY created_at DESC 
                LIMIT 1
            ''')
            result = cursor.fetchone()
            return result[0] if result else None

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
        self.close()
