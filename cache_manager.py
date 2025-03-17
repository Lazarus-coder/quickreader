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
                    UNIQUE(chapter_url)
                )
            ''')
            conn.commit()

    def _get_cache_path(self, url: str) -> str:
        """Generate a cache file path for a URL"""
        url_hash = hashlib.md5(url.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{url_hash}.json")

    def cache_chapter(self, book_id: int, chapter_url: str, content: Dict):
        """Cache chapter content"""
        try:
            cache_path = self._get_cache_path(chapter_url)
            
            # Save content to file
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, ensure_ascii=False, indent=2)
            
            # Update database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now()
                cursor.execute('''
                    INSERT INTO cached_chapters 
                    (book_id, chapter_url, cache_path, cached_time, last_accessed)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(chapter_url) 
                    DO UPDATE SET 
                        book_id=excluded.book_id,
                        cache_path=excluded.cache_path,
                        cached_time=excluded.cached_time,
                        last_accessed=excluded.last_accessed
                ''', (book_id, chapter_url, cache_path, now, now))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error caching chapter: {str(e)}")
            return False

    def get_cached_chapter(self, chapter_url: str) -> Optional[Dict]:
        """Get cached chapter content"""
        cache_path = self._get_cache_path(chapter_url)
        
        if not os.path.exists(cache_path):
            return None
            
        # Update last accessed time
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE cached_chapters 
                SET last_accessed = ? 
                WHERE chapter_url = ?
            ''', (datetime.now(), chapter_url))
            conn.commit()
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None

    def is_cached(self, chapter_url: str) -> bool:
        """Check if a chapter is cached"""
        cache_path = self._get_cache_path(chapter_url)
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
            if not self.is_cached(chapter['url']):
                self.cache_chapter(book_id, chapter['url'], chapter)

    def prefetch_next_chapters(self, book_id: int, current_url: str, chapter_list: List[Dict[str, str]], count: int = 3):
        """Prefetch next few chapters"""
        try:
            current_index = next(i for i, ch in enumerate(chapter_list) if ch['url'] == current_url)
            next_chapters = chapter_list[current_index + 1:current_index + 1 + count]
            self.cache_multiple_chapters(book_id, next_chapters)
        except (StopIteration, IndexError):
            pass 