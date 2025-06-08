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
    
    def remove_duplicates(self):
        """
        Remove duplicate entries from query_results and associated assessments.
        Duplicates are determined by identical URL and title; only the lowest id is kept.
        """
        with self.get_connection() as conn:
            # Delete assessments for removed query_results
            conn.execute(
                'DELETE FROM query_result_assessments WHERE query_result_id NOT IN (SELECT id FROM query_results)'
            )
            # Delete duplicate query_results, keep min(id) for each (url, title)
            conn.execute(
                'DELETE FROM query_results WHERE id NOT IN '
                '(SELECT MIN(id) FROM query_results GROUP BY COALESCE(url, \'\'), COALESCE(title, \'\'))'
            )
            conn.commit()

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
    
    def get_statistics(self) -> Dict[str, Any]:
        """Return basic database stats: total queries, total resources, and resources by source."""
        with self.get_connection() as conn:
            total_queries = conn.execute("SELECT COUNT(*) as count FROM queries").fetchone()["count"]
            total_resources = conn.execute("SELECT COUNT(*) as count FROM query_results").fetchone()["count"]
            cursor = conn.execute(
                "SELECT source_type, COUNT(*) as count FROM query_results GROUP BY source_type"
            )
            resources_by_source = {row["source_type"]: row["count"] for row in cursor.fetchall()}
        return {
            "total_queries": total_queries,
            "total_resources": total_resources,
            "resources_by_source": resources_by_source
        }
    
    # --- Assessment and Reporting Methods ---
    def get_all_assessments(self) -> List[Dict[str, Any]]:
        """Return all assessment records."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM query_result_assessments")
            return [dict(row) for row in cursor.fetchall()]

    def count_assessments_by_score(self) -> Dict[str, int]:
        """
        Count assessments grouped by weighted_average_score intervals:
        1-2, 2-3, 3-4, 4-5.
        """
        ranges = [(1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0)]
        result = {}
        with self.get_connection() as conn:
            for low, high in ranges:
                label = f"{int(low)}-{int(high)}"
                if high == 5.0:
                    cursor = conn.execute(
                        "SELECT COUNT(*) as count FROM query_result_assessments WHERE weighted_average_score >= ? AND weighted_average_score <= ?",
                        (low, high)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT COUNT(*) as count FROM query_result_assessments WHERE weighted_average_score >= ? AND weighted_average_score < ?",
                        (low, high)
                    )
                count = cursor.fetchone()["count"]
                result[label] = count
        return result

    def get_assessments_by_score_range(self, min_usefulness: int, max_usefulness: int) -> List[Dict[str, Any]]:
        """
        Retrieve assessments with overall_usefulness_score between min and max (inclusive).
        """
        with self.get_connection() as conn:
            cursor = conn.execute(
                """SELECT * FROM query_result_assessments
                    WHERE overall_usefulness_score >= ? AND overall_usefulness_score <= ?""",
                (min_usefulness, max_usefulness)
            )
            return [dict(row) for row in cursor.fetchall()]

    # Query Results methods

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
            conn.commit() # Commit insert before updating query count
            query_result_id = cursor.lastrowid

            # Automatically update results_count in queries table
            conn.execute('''
                UPDATE queries 
                SET results_count = (
                    SELECT COUNT(*) FROM query_results WHERE query_id = ?
                ), updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (query_id, query_id))
            
            conn.commit()
            return query_result_id # Return the ID of the newly inserted query_result
    
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
    def add_or_update_fetched_content(self, query_result_id: int, url: str, status: str,
                                      content_type: Optional[str] = None,
                                      http_status_code: Optional[int] = None,
                                      parsed_content: Optional[str] = None, # Can be HTML or file path for PDF
                                      title_extracted: Optional[str] = None,
                                      content_length: Optional[int] = None,
                                      error_message: Optional[str] = None) -> int:
        """
        Adds a new record to fetched_content or updates an existing one based on query_result_id.
        If content_type is 'pdf_path', parsed_content is expected to be the file path.
        """
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM fetched_content WHERE query_result_id = ?", (query_result_id,))
            existing_record = cursor.fetchone()

            current_time = datetime.now()

            if existing_record:
                # Update existing record
                record_id = existing_record['id']
                conn.execute('''
                    UPDATE fetched_content
                    SET url = ?, status = ?, fetched_at = ?, content_type = ?,
                        http_status_code = ?, parsed_content = ?, title_extracted = ?,
                        content_length = ?, error_message = ?
                    WHERE id = ?
                ''', (url, status, current_time, content_type, http_status_code,
                      parsed_content, title_extracted, content_length, error_message, record_id))
                logger.info(f"Updated fetched_content record for query_result_id {query_result_id}")
            else:
                # Insert new record
                cursor = conn.execute('''
                    INSERT INTO fetched_content (
                        query_result_id, url, status, fetched_at, content_type,
                        http_status_code, parsed_content, title_extracted,
                        content_length, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (query_result_id, url, status, current_time, content_type,
                      http_status_code, parsed_content, title_extracted,
                      content_length, error_message))
                record_id = cursor.lastrowid
                logger.info(f"Added new fetched_content record for query_result_id {query_result_id}, ID: {record_id}")
            
            conn.commit()
            return record_id

    def get_fetched_content_by_result_id(self, query_result_id: int) -> Optional[Dict[str, Any]]:
        """Get fetched content details for a specific query_result_id."""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM fetched_content WHERE query_result_id = ?", (query_result_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_fetched_content(self, fetched_content_id: int) -> bool:
        """Deletes a specific fetched_content record by its ID."""
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM fetched_content WHERE id = ?", (fetched_content_id,))
            conn.commit()
            logger.info(f"Deleted fetched_content record with ID {fetched_content_id}. Rows affected: {cursor.rowcount}")
            return cursor.rowcount > 0

    def reset_fetched_content(self):
        """
        Clear all records in fetched_content table before new workflow run.
        """
        conn = self.get_connection()
        with conn:
            conn.execute('DELETE FROM fetched_content')

    def remove_unwanted_query_results(self, keep_ids: List[int]):
        """
        In a database copy, delete all query_results, assessments, and fetched_content
        that are not in the keep_ids list.
        """
        placeholders = ",".join(["?" for _ in keep_ids]) if keep_ids else "''"
        with self.get_connection() as conn:
            # Delete assessments and fetched_content not in keep_ids
            conn.execute(f"DELETE FROM query_result_assessments WHERE query_result_id NOT IN ({placeholders})", keep_ids)
            conn.execute(f"DELETE FROM fetched_content WHERE query_result_id NOT IN ({placeholders})", keep_ids)
            # Delete other query_results
            conn.execute(f"DELETE FROM query_results WHERE id NOT IN ({placeholders})", keep_ids)
            conn.commit()

    # --- Assessment Methods ---
    # ... (existing assessment methods: add_query_result_assessment, get_assessment_by_result_id, etc.) ...

    # --- Combined/Utility Methods ---
    def get_all_assessed_results(self) -> List[Dict[str, Any]]:
        """
        Retrieves all query results that have an entry in the query_result_assessments table.
        This is used for the --skip-filtering option in main_part2.py.
        Returns a list of query_results records.
        """
        with self.get_connection() as conn:
            # Select all columns from query_results and join with assessments
            # to ensure we only get results that have been assessed.
            # We also fetch the weighted_average_score to allow potential sorting/prioritization if needed,
            # though main_part2 currently processes them as they come.
            # We only need one assessment per result, so DISTINCT or GROUP BY on qr.id might be good
            # if a result could somehow have multiple assessments (which it shouldn't by current design).
            # For simplicity, a simple join is fine if assessments are 1-to-1 with results.
            cursor = conn.execute('''
                SELECT qr.*, qra.weighted_average_score
                FROM query_results qr
                JOIN query_result_assessments qra ON qr.id = qra.query_result_id
                ORDER BY qr.id ASC  -- Or any other preferred order
            ''')
            # The schema of query_results is what main_part2.py expects for its processing loop.
            return [dict(row) for row in cursor.fetchall()]

    def get_unassessed_query_results(self, limit: int = 100, batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get query results that have not yet been assessed or have assessments with errors.
        Includes query_text from the parent query.
        """
        with self.get_connection() as conn:
            # Support unlimited fetch when limit is None
            base_query = '''
                SELECT qr.id as query_result_id, qr.url, qr.title, qr.snippet, qr.source_type, qr.pdf_url,
                       q.query_text as original_query_text, q.id as query_id
                FROM query_results qr
                JOIN queries q ON qr.query_id = q.id
                LEFT JOIN query_result_assessments qra ON qr.id = qra.query_result_id
                WHERE qra.id IS NULL OR (qra.id IS NOT NULL AND qra.error_message IS NOT NULL)
                ORDER BY qr.found_at ASC, qr.id ASC
            '''
            if limit is not None:
                cursor = conn.execute(base_query + '\nLIMIT ?', (limit,))
            else:
                cursor = conn.execute(base_query)
            return [dict(row) for row in cursor.fetchall()]

    def get_results_for_filtering(self, source_type: str) -> List[Dict[str, Any]]:
        """
        Retrieves query results and their best assessment scores for a given source_type,
        ordered by weighted_average_score descending.
        Only includes results that have a successful assessment (no error_message).
        """
        with self.get_connection() as conn:
            sql_query = '''
                SELECT qr.id, qr.url, qr.title, qr.snippet, qr.source_type, qr.pdf_url,
                       qra.weighted_average_score, qra.relevance_score, qra.credibility_score,
                       qra.solidity_score, qra.overall_usefulness_score
                FROM query_results qr
                JOIN query_result_assessments qra ON qr.id = qra.query_result_id
                WHERE qr.source_type = ? AND qra.error_message IS NULL AND qra.weighted_average_score IS NOT NULL
                ORDER BY qra.weighted_average_score DESC, qr.id ASC
            '''
            cursor = conn.execute(sql_query, (source_type,))
            return [dict(row) for row in cursor.fetchall()]

    # ... (any other existing methods like update_or_create_assessment, etc.) ...

    def update_or_create_assessment(
        self, query_result_id: int, original_query_text: str, assessment_prompt: str,
        llm_response_raw: str, relevance_score: Optional[int], credibility_score: Optional[int],
        solidity_score: Optional[int], overall_usefulness_score: Optional[int],
        weighted_average_score: Optional[float], llm_justification: Optional[str],
        error_message: Optional[str] = None
    ) -> int:
        """Updates an existing assessment or creates a new one if it doesn't exist or had an error."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, error_message FROM query_result_assessments WHERE query_result_id = ?",
                (query_result_id,)
            )
            existing_assessment = cursor.fetchone()
            # Format timestamp as ISO string for SQLite DATETIME storage
            current_time = datetime.now().isoformat()

            if existing_assessment and existing_assessment['error_message'] is None and error_message is None:
                # If an assessment exists and it's not an error, and the new one is not an error,
                # we might choose to log and not update, or update if scores are better.
                # For now, let's assume we always update if called, to reflect latest assessment attempt.
                logger.info(f"Updating existing successful assessment for query_result_id: {query_result_id}")
                assessment_id = existing_assessment['id']
                conn.execute('''
                    UPDATE query_result_assessments
                    SET original_query_text = ?, assessment_prompt = ?, llm_response_raw = ?,
                        relevance_score = ?, credibility_score = ?, solidity_score = ?,
                        overall_usefulness_score = ?, weighted_average_score = ?,
                        llm_justification = ?, error_message = ?, assessed_at = ?
                    WHERE id = ?
                ''', (original_query_text, assessment_prompt, llm_response_raw, relevance_score,
                      credibility_score, solidity_score, overall_usefulness_score,
                      weighted_average_score, llm_justification, error_message, current_time, assessment_id))
            elif existing_assessment: # Exists, but might have been an error, or new one is an error
                logger.info(f"Overwriting existing assessment (possibly an error one) for query_result_id: {query_result_id}")
                assessment_id = existing_assessment['id']
                conn.execute('''
                    UPDATE query_result_assessments
                    SET original_query_text = ?, assessment_prompt = ?, llm_response_raw = ?,
                        relevance_score = ?, credibility_score = ?, solidity_score = ?,
                        overall_usefulness_score = ?, weighted_average_score = ?,
                        llm_justification = ?, error_message = ?, assessed_at = ?
                    WHERE id = ?
                ''', (original_query_text, assessment_prompt, llm_response_raw, relevance_score,
                      credibility_score, solidity_score, overall_usefulness_score,
                      weighted_average_score, llm_justification, error_message, current_time, assessment_id))
            else: # No existing assessment
                logger.info(f"Creating new assessment for query_result_id: {query_result_id}")
                cursor = conn.execute('''
                    INSERT INTO query_result_assessments (
                        query_result_id, original_query_text, assessment_prompt, llm_response_raw,
                        relevance_score, credibility_score, solidity_score, overall_usefulness_score,
                        weighted_average_score, llm_justification, error_message, assessed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (query_result_id, original_query_text, assessment_prompt, llm_response_raw,
                      relevance_score, credibility_score, solidity_score, overall_usefulness_score,
                      weighted_average_score, llm_justification, error_message, current_time))
                assessment_id = cursor.lastrowid
            conn.commit()
            return assessment_id

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
