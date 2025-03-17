import os
import json
from typing import Optional, Dict, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ChapterCache:
    def __init__(self, cache_dir: str = "chapter_cache"):
        self.cache_dir = cache_dir
        self.index_file = os.path.join(cache_dir, "cache_index.json")
        self._ensure_cache_dir()
        self.cache_index = self._load_index()

    def _ensure_cache_dir(self):
        """Ensure the cache directory exists."""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def _load_index(self) -> Dict[str, Any]:
        """Load the cache index file."""
        try:
            if os.path.exists(self.index_file):
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading cache index: {str(e)}")
            return {}

    def _save_index(self):
        """Save the cache index file."""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache index: {str(e)}")

    def cache_chapter(self, novel_url: str, chapter_url: str, title: str, content: str):
        """Cache a chapter for offline reading."""
        try:
            # Create a unique filename for the chapter
            chapter_hash = hash(chapter_url)
            filename = f"{chapter_hash}.txt"
            filepath = os.path.join(self.cache_dir, filename)

            # Save chapter content
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Title: {title}\n\n{content}")

            # Update index
            if novel_url not in self.cache_index:
                self.cache_index[novel_url] = {}
            
            self.cache_index[novel_url][chapter_url] = {
                'filename': filename,
                'title': title,
                'cached_at': datetime.now().isoformat()
            }
            self._save_index()

        except Exception as e:
            logger.error(f"Error caching chapter: {str(e)}")

    def get_cached_chapter(self, novel_url: str, chapter_url: str) -> Optional[Dict[str, str]]:
        """Retrieve a cached chapter."""
        try:
            if novel_url in self.cache_index and chapter_url in self.cache_index[novel_url]:
                chapter_info = self.cache_index[novel_url][chapter_url]
                filepath = os.path.join(self.cache_dir, chapter_info['filename'])
                
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        title, content = content.split('\n\n', 1)
                        return {
                            'title': title.replace('Title: ', ''),
                            'content': content
                        }
            return None
        except Exception as e:
            logger.error(f"Error retrieving cached chapter: {str(e)}")
            return None

    def clear_cache(self, novel_url: Optional[str] = None):
        """Clear the cache for a specific novel or all novels."""
        try:
            if novel_url:
                if novel_url in self.cache_index:
                    # Remove cached files
                    for chapter_info in self.cache_index[novel_url].values():
                        filepath = os.path.join(self.cache_dir, chapter_info['filename'])
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    # Remove from index
                    del self.cache_index[novel_url]
            else:
                # Clear all cached files
                for filename in os.listdir(self.cache_dir):
                    if filename.endswith('.txt'):
                        os.remove(os.path.join(self.cache_dir, filename))
                self.cache_index = {}
            
            self._save_index()
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}") 