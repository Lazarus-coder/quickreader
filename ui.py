from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QTextEdit, QLineEdit, QLabel,
                             QMessageBox, QScrollArea)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QPalette, QColor
import logging

logger = logging.getLogger(__name__)

class ReaderWindow(QMainWindow):
    def __init__(self, crawler, progress_manager, chapter_cache):
        super().__init__()
        self.crawler = crawler
        self.progress_manager = progress_manager
        self.chapter_cache = chapter_cache
        self.current_novel_url = None
        self.current_chapter_url = None
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface."""
        self.setWindowTitle("QuickReader - Chinese Web Novel Reader")
        self.setMinimumSize(800, 600)

        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # URL input area
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter novel URL...")
        self.url_input.returnPressed.connect(self.load_novel)
        url_layout.addWidget(self.url_input)
        layout.addLayout(url_layout)

        # Title label
        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: white; font-size: 18px; margin: 10px;")
        layout.addWidget(self.title_label)

        # Reading area
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setStyleSheet("""
            QTextEdit {
                background-color: black;
                color: white;
                font-size: 16px;
                line-height: 1.6;
                padding: 20px;
            }
        """)
        layout.addWidget(self.text_area)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_button = QPushButton("Previous Chapter")
        self.prev_button.clicked.connect(self.previous_chapter)
        self.next_button = QPushButton("Next Chapter")
        self.next_button.clicked.connect(self.next_chapter)
        nav_layout.addWidget(self.prev_button)
        nav_layout.addWidget(self.next_button)
        layout.addLayout(nav_layout)

        # Set dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: black;
            }
            QPushButton {
                background-color: #333;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #444;
            }
            QLineEdit {
                background-color: #333;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
        """)

        # Auto-save timer
        self.save_timer = QTimer()
        self.save_timer.timeout.connect(self.save_progress)
        self.save_timer.start(30000)  # Save every 30 seconds

    def load_novel(self):
        """Load a novel from the entered URL."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a valid URL")
            return

        self.current_novel_url = url
        self.load_chapter(url)

    def load_chapter(self, url: str):
        """Load a specific chapter."""
        try:
            # Try to load from cache first
            if self.current_novel_url:
                cached_chapter = self.chapter_cache.get_cached_chapter(
                    self.current_novel_url, url)
                if cached_chapter:
                    self.display_chapter(cached_chapter['title'],
                                       cached_chapter['content'])
                    return

            # If not in cache, fetch from web
            result = self.crawler.extract_chapter_content(url)
            if result:
                title, content, next_url = result
                self.current_chapter_url = url
                self.display_chapter(title, content)
                
                # Cache the chapter
                if self.current_novel_url:
                    self.chapter_cache.cache_chapter(
                        self.current_novel_url, url, title, content)
            else:
                QMessageBox.warning(self, "Error", "Failed to load chapter")
        except Exception as e:
            logger.error(f"Error loading chapter: {str(e)}")
            QMessageBox.warning(self, "Error", "Failed to load chapter")

    def display_chapter(self, title: str, content: str):
        """Display chapter content in the text area."""
        self.title_label.setText(title)
        self.text_area.setText(content)
        self.save_progress()

    def next_chapter(self):
        """Load the next chapter."""
        if self.current_chapter_url:
            result = self.crawler.extract_chapter_content(self.current_chapter_url)
            if result and result[2]:  # If next chapter URL exists
                self.load_chapter(result[2])

    def previous_chapter(self):
        """Load the previous chapter."""
        # This would require maintaining a history of visited chapters
        # For now, we'll just show a message
        QMessageBox.information(self, "Info", "Previous chapter feature coming soon!")

    def save_progress(self):
        """Save current reading progress."""
        if self.current_novel_url and self.current_chapter_url:
            scroll_pos = self.text_area.verticalScrollBar().value()
            self.progress_manager.save_progress(
                self.current_novel_url,
                self.current_chapter_url,
                scroll_pos
            )

    def restore_progress(self):
        """Restore previous reading progress."""
        if self.current_novel_url:
            progress = self.progress_manager.get_progress(self.current_novel_url)
            if progress:
                self.load_chapter(progress['current_chapter'])
                # Restore scroll position after a short delay to ensure content is loaded
                QTimer.singleShot(100, lambda: self.text_area.verticalScrollBar().setValue(
                    progress['scroll_position'])) 