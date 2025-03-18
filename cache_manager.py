import os
import json
import hashlib
from typing import Optional, Dict, List
import sqlite3
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, cache_dir: str = 'cache', db_path: str = 'cache.db'):
        self.cache_dir = cache_dir
        self.db_path = db_path
        os.makedirs(cache_dir, exist_ok=True)
        self.init_db()

    def init_db(self):
        """Initialize the cache database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cached_chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id INTEGER,
                    chapter_url TEXT NOT NULL,
                    cache_path TEXT NOT NULL,
                    cached_time TIMESTAMP,
                    last_accessed TIMESTAMP,
                    UNIQUE(book_id, chapter_url)
                )
            ''')
            conn.commit()

    def _get_cache_path(self, book_id: int, url: str) -> str:
        """Generate a cache file path for a URL"""
        url_hash = hashlib.md5(f"{book_id}_{url}".encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{url_hash}.json")

    def cache_chapter(self, book_id: int, chapter_url: str, content: dict):
        """Cache a chapter's content"""
        try:
            # Validate content has all required fields
            if not content.get('content') or not content.get('title') or not content.get('url'):
                logger.error(f"Invalid content format: {content}")
                return False

            # Save content to file
            cache_path = self._get_cache_path(book_id, chapter_url)
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            
            # Update database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # First try to update existing record
                cursor.execute("""
                    UPDATE cached_chapters 
                    SET cache_path = ?, cached_time = CURRENT_TIMESTAMP, last_accessed = CURRENT_TIMESTAMP
                    WHERE book_id = ? AND chapter_url = ?
                """, (cache_path, book_id, chapter_url))
                
                # If no record was updated, insert new one
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO cached_chapters (book_id, chapter_url, cache_path, cached_time, last_accessed)
                        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (book_id, chapter_url, cache_path))
                
                conn.commit()
                logger.info(f"Cached chapter: {chapter_url}")
                return True
                
        except Exception as e:
            logger.error(f"Error caching chapter: {str(e)}", exc_info=True)
            return False

    def get_cached_chapter(self, book_id: int, chapter_url: str) -> Optional[Dict]:
        """Get cached chapter content"""
        cache_path = self._get_cache_path(book_id, chapter_url)
        
        if not os.path.exists(cache_path):
            return None
            
        # Update last accessed time
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE cached_chapters 
                SET last_accessed = ? 
                WHERE book_id = ? AND chapter_url = ?
            ''', (datetime.now(), book_id, chapter_url))
            conn.commit()
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
                
            # Validate content has all required fields
            if not content.get('content') or not content.get('title') or not content.get('url'):
                logger.warning(f"Invalid cached content for {chapter_url}, removing from cache")
                # Remove invalid cache entry
                os.remove(cache_path)
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        DELETE FROM cached_chapters 
                        WHERE book_id = ? AND chapter_url = ?
                    ''', (book_id, chapter_url))
                    conn.commit()
                return None
                
            return content
            
        except Exception as e:
            logger.error(f"Error reading cached chapter: {str(e)}")
            # Remove corrupted cache file
            try:
                os.remove(cache_path)
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        DELETE FROM cached_chapters 
                        WHERE book_id = ? AND chapter_url = ?
                    ''', (book_id, chapter_url))
                    conn.commit()
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up invalid cache: {str(cleanup_error)}")
            return None

    def is_cached(self, book_id: int, chapter_url: str) -> bool:
        """Check if a chapter is cached"""
        cache_path = self._get_cache_path(book_id, chapter_url)
        return os.path.exists(cache_path)

    def get_book_cache_status(self, book_id: int) -> Dict[str, datetime]:
        """Get cache status for all chapters of a book"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT chapter_url, cached_time 
                FROM cached_chapters 
                WHERE book_id = ?
            ''', (book_id,))
            return {row['chapter_url']: row['cached_time'] for row in cursor.fetchall()}

    def clear_old_cache(self, days: int = 30):
        """Clear cache files older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get old cache files
            cursor.execute('''
                SELECT cache_path 
                FROM cached_chapters 
                WHERE last_accessed < ?
            ''', (cutoff_date,))
            
            # Delete files
            for (cache_path,) in cursor.fetchall():
                try:
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
                except:
                    pass
            
            # Remove from database
            cursor.execute('''
                DELETE FROM cached_chapters 
                WHERE last_accessed < ?
            ''', (cutoff_date,))
            
            conn.commit()

    def clear_book_cache(self, book_id: int):
        """Clear all cached chapters for a book"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get cache files for the book
            cursor.execute('''
                SELECT cache_path 
                FROM cached_chapters 
                WHERE book_id = ?
            ''', (book_id,))
            
            # Delete files
            for (cache_path,) in cursor.fetchall():
                try:
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
                except:
                    pass
            
            # Remove from database
            cursor.execute('DELETE FROM cached_chapters WHERE book_id = ?', (book_id,))
            conn.commit()

    def cache_multiple_chapters(self, book_id: int, chapters: List[Dict[str, str]]):
        """Cache multiple chapters at once"""
        for chapter in chapters:
            if not self.is_cached(book_id, chapter['url']):
                self.cache_chapter(book_id, chapter['url'], chapter)

    def prefetch_next_chapters(self, book_id: int, current_url: str, chapter_list: List[Dict[str, str]], count: int = 3):
        """Prefetch next few chapters"""
        try:
            current_index = next(i for i, ch in enumerate(chapter_list) if ch['url'] == current_url)
            next_chapters = chapter_list[current_index + 1:current_index + 1 + count]
            self.cache_multiple_chapters(book_id, next_chapters)
        except (StopIteration, IndexError):
            pass

    def clear_invalid_cache(self):
        """Clear any invalid cache entries from the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Delete entries that don't have all required fields
                cursor.execute("""
                    DELETE FROM cached_chapters 
                    WHERE content IS NULL 
                    OR title IS NULL 
                    OR url IS NULL
                """)
                conn.commit()
                logger.info(f"Cleared {cursor.rowcount} invalid cache entries from database")
        except Exception as e:
            logger.error(f"Error clearing invalid cache: {str(e)}", exc_info=True) 