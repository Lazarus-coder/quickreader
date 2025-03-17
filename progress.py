import json
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ProgressManager:
    def __init__(self, save_file: str = "reading_progress.json"):
        self.save_file = save_file
        self.progress: Dict[str, Any] = self._load_progress()

    def _load_progress(self) -> Dict[str, Any]:
        """Load progress from file or return empty dict if file doesn't exist."""
        try:
            if os.path.exists(self.save_file):
                with open(self.save_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading progress: {str(e)}")
            return {}

    def save_progress(self, novel_url: str, current_chapter: str, scroll_position: int = 0):
        """Save reading progress for a specific novel."""
        try:
            self.progress[novel_url] = {
                'current_chapter': current_chapter,
                'scroll_position': scroll_position,
                'last_updated': str(os.path.getmtime(self.save_file) if os.path.exists(self.save_file) else 0)
            }
            with open(self.save_file, 'w', encoding='utf-8') as f:
                json.dump(self.progress, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving progress: {str(e)}")

    def get_progress(self, novel_url: str) -> Optional[Dict[str, Any]]:
        """Get reading progress for a specific novel."""
        return self.progress.get(novel_url)

    def clear_progress(self, novel_url: str):
        """Clear progress for a specific novel."""
        if novel_url in self.progress:
            del self.progress[novel_url]
            self.save_progress(novel_url, "", 0) 