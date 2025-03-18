import sqlite3
from typing import Optional, List, Dict, Tuple
import json
import os
from datetime import datetime
import logging
import threading

logger = logging.getLogger(__name__)

class ReadingProgress:
    def __init__(self, db_path: str = 'reading_progress.db'):
        self.db_path = db_path
        self._local = threading.local()
        self.init_db()
        self.migrate_db()

    def _get_conn(self):
        """Get a thread-local database connection"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path)
        return self._local.conn

    def __del__(self):
        """Close database connection on object destruction"""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()
            del self._local.conn

    def init_db(self):
        """Initialize the database"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Create books table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    last_read_url TEXT,
                    last_read_title TEXT,
                    display_order INTEGER,
                    metadata TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # Create bookmarks table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER NOT NULL,
                    chapter_url TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT,
                    FOREIGN KEY (book_id) REFERENCES books (id)
                )
            ''')
            
            conn.commit()
            logger.info("Database initialized successfully")
            
            # Run migrations
            self.migrate_db()
            
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}", exc_info=True)
            raise

    def migrate_db(self):
        """Run database migrations"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Add last_read_title column if it doesn't exist
            cursor.execute("PRAGMA table_info(books)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'last_read_title' not in columns:
                cursor.execute('ALTER TABLE books ADD COLUMN last_read_title TEXT')
                
            if 'display_order' not in columns:
                cursor.execute('ALTER TABLE books ADD COLUMN display_order INTEGER')
                # Set initial display order based on id
                cursor.execute('UPDATE books SET display_order = id')
                
            if 'created_at' not in columns:
                cursor.execute('ALTER TABLE books ADD COLUMN created_at TEXT')
                # Set initial created_at values
                cursor.execute("UPDATE books SET created_at = datetime('now')")
                
            if 'updated_at' not in columns:
                cursor.execute('ALTER TABLE books ADD COLUMN updated_at TEXT')
                # Set initial updated_at values
                cursor.execute("UPDATE books SET updated_at = datetime('now')")
                
            conn.commit()
            logger.info("Database migration completed successfully")
            
        except Exception as e:
            logger.error(f"Error migrating database: {str(e)}", exc_info=True)
            raise

    def add_or_update_book(self, title: str, source_url: str, metadata: Dict = None) -> int:
        """Add a new book or update an existing one"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Check if book exists
            cursor.execute('SELECT id FROM books WHERE source_url = ?', (source_url,))
            result = cursor.fetchone()
            
            if result:
                book_id = result[0]
                # Update existing book
                cursor.execute('''
                    UPDATE books 
                    SET title = ?, metadata = ?, updated_at = datetime('now')
                    WHERE id = ?
                ''', (title, str(metadata) if metadata else None, book_id))
            else:
                # Add new book
                cursor.execute('''
                    INSERT INTO books (title, source_url, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, datetime('now'), datetime('now'))
                ''', (title, source_url, str(metadata) if metadata else None))
                book_id = cursor.lastrowid
                
            conn.commit()
            return book_id
            
        except Exception as e:
            logger.error(f"Error adding/updating book: {str(e)}", exc_info=True)
            if conn:
                conn.rollback()
            raise

    def update_reading_progress(self, book_id: int, chapter_url: str, chapter_title: str):
        """Update reading progress for a book"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE books 
                SET last_read_url = ?, last_read_title = ?, updated_at = datetime('now')
                WHERE id = ?
            ''', (chapter_url, chapter_title, book_id))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error updating reading progress: {str(e)}", exc_info=True)
            if conn:
                conn.rollback()
            raise

    def add_bookmark(self, book_id: int, chapter_url: str, note: str = None):
        """Add a bookmark for a chapter"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO bookmarks (book_id, chapter_url, note, created_at)
                VALUES (?, ?, ?, datetime('now'))
            ''', (book_id, chapter_url, note))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error adding bookmark: {str(e)}", exc_info=True)
            if conn:
                conn.rollback()
            raise

    def remove_bookmark(self, bookmark_id: int):
        """Remove a bookmark"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM bookmarks WHERE id = ?', (bookmark_id,))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error removing bookmark: {str(e)}", exc_info=True)
            if conn:
                conn.rollback()
            raise

    def get_bookmarks(self, book_id: int) -> List[Dict]:
        """Get all bookmarks for a book"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, chapter_url, note, created_at 
                FROM bookmarks 
                WHERE book_id = ? 
                ORDER BY created_at DESC
            ''', (book_id,))
            
            return [{
                'id': row[0],
                'chapter_url': row[1],
                'note': row[2],
                'created_at': row[3]
            } for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error getting bookmarks: {str(e)}", exc_info=True)
            return []

    def get_reading_history(self, book_id: int) -> List[Dict]:
        """Get reading history for a book"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT last_read_url, last_read_title, updated_at
                FROM books
                WHERE id = ?
            ''', (book_id,))
            
            result = cursor.fetchone()
            if result:
                return [{
                    'chapter_url': result[0],
                    'chapter_title': result[1],
                    'last_read': result[2]
                }]
            return []
            
        except Exception as e:
            logger.error(f"Error getting reading history: {str(e)}", exc_info=True)
            return []

    def get_all_books(self) -> List[Dict]:
        """Get all books"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, title, source_url, last_read_url, last_read_title, 
                       display_order, metadata, created_at, updated_at
                FROM books
                ORDER BY display_order ASC
            ''')
            
            return [{
                'id': row[0],
                'title': row[1],
                'source_url': row[2],
                'last_read_url': row[3],
                'last_read_title': row[4],
                'display_order': row[5],
                'metadata': eval(row[6]) if row[6] else None,
                'created_at': row[7],
                'updated_at': row[8]
            } for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(f"Error getting books: {str(e)}", exc_info=True)
            return []

    def get_book(self, book_id: int) -> Optional[Dict]:
        """Get a specific book"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, title, source_url, last_read_url, last_read_title, 
                       display_order, metadata, created_at, updated_at
                FROM books
                WHERE id = ?
            ''', (book_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'title': row[1],
                    'source_url': row[2],
                    'last_read_url': row[3],
                    'last_read_title': row[4],
                    'display_order': row[5],
                    'metadata': eval(row[6]) if row[6] else None,
                    'created_at': row[7],
                    'updated_at': row[8]
                }
            return None
            
        except Exception as e:
            logger.error(f"Error getting book: {str(e)}", exc_info=True)
            return None

    def delete_book(self, book_id: int):
        """Delete a book and its bookmarks"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Delete bookmarks first
            cursor.execute('DELETE FROM bookmarks WHERE book_id = ?', (book_id,))
            
            # Delete book
            cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error deleting book: {str(e)}", exc_info=True)
            if conn:
                conn.rollback()
            raise

    def update_book_order(self, books: List[Dict]):
        """Update the display order of books"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            for i, book in enumerate(books):
                cursor.execute('''
                    UPDATE books 
                    SET display_order = ?, updated_at = datetime('now')
                    WHERE id = ?
                ''', (i, book['id']))
                
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error updating book order: {str(e)}", exc_info=True)
            if conn:
                conn.rollback()
            raise 