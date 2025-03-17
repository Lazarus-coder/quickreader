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
            self._local.conn.row_factory = sqlite3.Row
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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    last_read_url TEXT,
                    last_read_title TEXT,
                    metadata TEXT,
                    display_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create bookmarks table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER,
                    chapter_url TEXT NOT NULL,
                    chapter_title TEXT,
                    note TEXT,
                    created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
                    UNIQUE(book_id, chapter_url)
                )
            ''')
            conn.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")
            conn.rollback()

    def migrate_db(self):
        """Migrate database schema to latest version"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Check if last_read_title column exists
            cursor.execute("PRAGMA table_info(books)")
            columns = {col[1] for col in cursor.fetchall()}
            
            if 'last_read_title' not in columns:
                logger.info("Adding last_read_title column")
                cursor.execute("ALTER TABLE books ADD COLUMN last_read_title TEXT")
            
            if 'display_order' not in columns:
                logger.info("Adding display_order column")
                cursor.execute("ALTER TABLE books ADD COLUMN display_order INTEGER")
                # Set initial display order based on id
                cursor.execute("UPDATE books SET display_order = id")
            
            if 'created_at' not in columns:
                logger.info("Adding created_at column")
                cursor.execute("ALTER TABLE books ADD COLUMN created_at TEXT")
                # Set initial values to current timestamp
                cursor.execute("UPDATE books SET created_at = datetime('now')")
            
            if 'updated_at' not in columns:
                logger.info("Adding updated_at column")
                cursor.execute("ALTER TABLE books ADD COLUMN updated_at TEXT")
                # Set initial values to current timestamp
                cursor.execute("UPDATE books SET updated_at = datetime('now')")
            
            conn.commit()
            logger.info("Database migration completed successfully")
        except Exception as e:
            logger.error(f"Error during database migration: {str(e)}")
            conn.rollback()

    def add_or_update_book(self, title: str, source_url: str, metadata: Dict = None) -> int:
        """Add a new book or update existing one"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Check if book exists
            cursor.execute(
                'SELECT id, display_order FROM books WHERE source_url = ?',
                (source_url,)
            )
            result = cursor.fetchone()
            
            if result:
                # Update existing book
                book_id = result[0]
                cursor.execute('''
                    UPDATE books 
                    SET title = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (title, json.dumps(metadata), book_id))
                conn.commit()
                return book_id
            else:
                # Get max display order
                cursor.execute('SELECT MAX(display_order) FROM books')
                max_order = cursor.fetchone()[0] or 0
                
                # Add new book
                cursor.execute('''
                    INSERT INTO books (title, source_url, metadata, display_order)
                    VALUES (?, ?, ?, ?)
                ''', (title, source_url, json.dumps(metadata), max_order + 1))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding/updating book: {str(e)}")
            conn.rollback()
            return None

    def update_reading_progress(self, book_id: int, chapter_url: str, chapter_title: str):
        """Update reading progress for a book"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE books 
                SET last_read_url = ?, last_read_title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (chapter_url, chapter_title, book_id))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating reading progress: {str(e)}")
            conn.rollback()
            return False

    def add_bookmark(self, book_id: int, chapter_url: str, chapter_title: str, note: str = None):
        """Add a bookmark"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO bookmarks (book_id, chapter_url, chapter_title, note, created_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(book_id, chapter_url) 
                DO UPDATE SET note=excluded.note, created_time=excluded.created_time
            ''', (book_id, chapter_url, chapter_title, note, datetime.now()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding bookmark: {str(e)}")
            conn.rollback()
            return False

    def remove_bookmark(self, book_id: int, chapter_url: str):
        """Remove a bookmark"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM bookmarks 
                WHERE book_id = ? AND chapter_url = ?
            ''', (book_id, chapter_url))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error removing bookmark: {str(e)}")
            conn.rollback()
            return False

    def get_bookmarks(self, book_id: int) -> List[Dict]:
        """Get all bookmarks for a book"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM bookmarks 
                WHERE book_id = ?
                ORDER BY created_time DESC
            ''', (book_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting bookmarks: {str(e)}")
            return []

    def get_reading_history(self, book_id: int) -> List[Dict]:
        """Get reading history for a book"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM reading_history 
                WHERE book_id = ?
                ORDER BY read_time DESC
            ''', (book_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting reading history: {str(e)}")
            return []

    def get_all_books(self) -> List[Dict]:
        """Get all books ordered by display_order"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, source_url, last_read_url, last_read_title, metadata, display_order
                FROM books 
                ORDER BY display_order ASC, id ASC
            ''')
            books = []
            for row in cursor:
                book = dict(row)
                book['metadata'] = json.loads(book['metadata']) if book['metadata'] else {}
                books.append(book)
            return books
        except Exception as e:
            logger.error(f"Error getting books: {str(e)}")
            return []

    def get_book(self, book_id: int) -> Optional[Dict]:
        """Get a specific book"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, source_url, last_read_url, last_read_title, metadata, display_order
                FROM books WHERE id = ?
            ''', (book_id,))
            row = cursor.fetchone()
            if row:
                book = dict(row)
                book['metadata'] = json.loads(book['metadata']) if book['metadata'] else {}
                return book
            return None
        except Exception as e:
            logger.error(f"Error getting book: {str(e)}")
            return None

    def delete_book(self, book_id: int) -> bool:
        """Delete a book and update display order"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Get current display order
            cursor.execute('SELECT display_order FROM books WHERE id = ?', (book_id,))
            result = cursor.fetchone()
            if result:
                current_order = result[0]
                
                # Delete the book
                cursor.execute('DELETE FROM books WHERE id = ?', (book_id,))
                
                # Update display order for remaining books
                cursor.execute('''
                    UPDATE books 
                    SET display_order = display_order - 1
                    WHERE display_order > ?
                ''', (current_order,))
                
                conn.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting book: {str(e)}")
            conn.rollback()
            return False

    def update_book_order(self, books: List[Dict]) -> bool:
        """Update the display order of books"""
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Update display order for each book
            for i, book in enumerate(books, 1):
                cursor.execute('''
                    UPDATE books 
                    SET display_order = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (i, book['id']))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating book order: {str(e)}")
            conn.rollback()
            return False 