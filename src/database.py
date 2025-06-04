"""
Database module for sentiment analysis thesis information gathering system.
Handles SQLite database operations for managing search queries and their status.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Any


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
                    results_count INTEGER DEFAULT 0,
                    notes TEXT
                )
            ''')
            conn.commit()
    
    def add_query(self, query_text: str, query_type: str, notes: str = None) -> int:
        """Add a new search query to the database."""
        if query_type not in ['tools', 'applications']:
            raise ValueError("query_type must be 'tools' or 'applications'")
        
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO queries (query_text, query_type, notes)
                VALUES (?, ?, ?)
            ''', (query_text, query_type, notes))
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
    
    def update_query_status(self, query_id: int, status: str, results_count: int = None, notes: str = None) -> bool:
        """Update the status of a query and optionally results count and notes."""
        if status not in ['pending', 'processing', 'completed', 'failed']:
            raise ValueError("Invalid status")
        
        update_parts = ['status = ?', 'updated_at = CURRENT_TIMESTAMP']
        params = [status]
        
        if results_count is not None:
            update_parts.append('results_count = ?')
            params.append(results_count)
        
        if notes is not None:
            update_parts.append('notes = ?')
            params.append(notes)
        
        params.append(query_id)
        
        with self.get_connection() as conn:
            cursor = conn.execute(f'''
                UPDATE queries 
                SET {', '.join(update_parts)}
                WHERE id = ?
            ''', params)
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
        """Get basic statistics about queries in the database."""
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
        self.close()
