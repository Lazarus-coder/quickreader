import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QPushButton, QLabel, QTextEdit, QLineEdit,
                           QListWidget, QMessageBox, QProgressBar, QSplitter,
                           QMenu, QToolBar, QStatusBar, QListWidgetItem,
                           QInputDialog)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QTextCursor, QFont, QAction
import os
from sources import SourceManager
from reading_progress import ReadingProgress
from cache_manager import CacheManager
from typing import Optional, Dict, List
import logging
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json

# Set up logging with more detail
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('quickreader.log'),  # Log to file
        logging.StreamHandler()  # Also log to console
    ]
)
logger = logging.getLogger(__name__)

class ChapterLoader(QThread):
    loading_started = Signal()
    chapter_loaded = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, source_manager=None, cache_manager=None):
        super().__init__()
        self._is_loading = False
        self.url = None
        self.book_id = None
        self.source_manager = source_manager or SourceManager()
        self.cache_manager = cache_manager or CacheManager()

    @property
    def is_loading(self):
        return self._is_loading

    def set_url(self, book_id: int, url: str):
        """Set the URL and book ID to load"""
        self.url = url
        self.book_id = book_id

    def run(self):
        """Load chapter content"""
        if not self.url:
            self.error_occurred.emit("No URL set")
            return

        try:
            self._is_loading = True
            self.loading_started.emit()

            # Check cache first
            cached_content = self.cache_manager.get_cached_chapter(self.book_id, self.url)
            if cached_content:
                logger.info("Using cached content")
                self.chapter_loaded.emit(cached_content)
                return

            # Get source handler
            source = self.source_manager.get_source_for_url(self.url)
            if not source:
                self.error_occurred.emit("Unsupported source")
                return

            # Extract content
            content = source.extract_chapter_content(self.url)
            if not content:
                self.error_occurred.emit("Failed to extract content")
                return

            # Cache content
            self.cache_manager.cache_chapter(self.book_id, self.url, content)

            # Emit loaded content
            self.chapter_loaded.emit(content)

        except Exception as e:
            logger.error(f"Error loading chapter: {str(e)}", exc_info=True)
            self.error_occurred.emit(str(e))
        finally:
            self._is_loading = False

    def _extract_js_variables(self, html_content: str) -> dict:
        """Extract variables from JavaScript with improved error handling"""
        variables = {}
        
        # Extract all relevant variables using regex
        patterns = {
            'title': r'var\s+ChapterTitle\s*=\s*["\']([^"\']+)["\']',
            'book_name': r'var\s+BookName\s*=\s*["\']([^"\']+)["\']',
            'prev_url': r'var\s+prevpage\s*=\s*["\']([^"\']+)["\']',
            'next_url': r'var\s+nextpage\s*=\s*["\']([^"\']+)["\']',
            'chapter_list_url': r'var\s+chapterpage\s*=\s*["\']([^"\']+)["\']',
            'content': r'var\s+TxtContents\s*=\s*["\']([^"\']+)["\']'
        }
        
        for key, pattern in patterns.items():
            try:
                match = re.search(pattern, html_content, re.DOTALL)
                if match:
                    value = match.group(1)
                    # Handle escaped content
                    if key == 'content':
                        value = value.encode().decode('unicode_escape')
                    variables[key] = value
                    logger.debug(f"Found {key}: {value[:50]}...")
            except Exception as e:
                logger.warning(f"Error extracting {key}: {str(e)}")
        
        return variables

    def _extract_nav_variables(self, html_content: str) -> dict:
        """Extract navigation variables from JavaScript"""
        nav = {}
        
        # Extract navigation variables using regex
        patterns = {
            'prev_url': r'var\s+prevpage\s*=\s*["\']([^"\']+)["\']',
            'next_url': r'var\s+nextpage\s*=\s*["\']([^"\']+)["\']',
            'chapter_list_url': r'var\s+chapterpage\s*=\s*["\']([^"\']+)["\']'
        }
        
        for key, pattern in patterns.items():
            try:
                match = re.search(pattern, html_content, re.DOTALL)
                if match:
                    value = match.group(1)
                    nav[key] = value
                    logger.debug(f"Found {key}: {value[:50]}...")
            except Exception as e:
                logger.warning(f"Error extracting {key}: {str(e)}")
        
        return nav

class CacheThread(QThread):
    def __init__(self, cache_manager, book_id, chapters, source_manager=None):
        super().__init__()
        self.cache_manager = cache_manager
        self.book_id = book_id
        self.chapters = chapters
        self.source_manager = source_manager or SourceManager()
        
    def run(self):
        for chapter in self.chapters:
            try:
                # Skip if already cached
                if self.cache_manager.is_cached(self.book_id, chapter['url']):
                    continue

                # Get source handler
                source = self.source_manager.get_source_for_url(chapter['url'])
                if not source:
                    continue

                # Extract complete content
                content = source.extract_chapter_content(chapter['url'])
                if content:
                    self.cache_manager.cache_chapter(self.book_id, chapter['url'], content)
            except Exception as e:
                logger.error(f"Error caching chapter {chapter['url']}: {str(e)}")

class MainWindow(QMainWindow):
    chapter_loaded = Signal(str, str)  # Signal for chapter loaded (url, title)
    error_occurred = Signal(str)
    loading_started = Signal(str)
    book_loaded = Signal(int, list)  # book_id, chapters
    
    def __init__(self):
        super().__init__()
        self.source_manager = SourceManager()
        self.reading_progress = ReadingProgress()
        self.cache_manager = CacheManager()
        self.current_book_id = None
        self.current_chapter_list = []
        self.current_chapter_url = None  # Track current chapter URL
        self.cache_thread = None  # Keep track of cache thread
        self.cache_dir = os.path.join(os.path.expanduser('~'), '.quickreader', 'cache')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        self.clear_invalid_cache()  # Clear invalid cache entries on startup
        self.setup_ui()
        self.setup_loader()
        
    def setup_loader(self):
        """Set up the chapter loader and connect signals"""
        self.loader = ChapterLoader()
        self.loader.chapter_loaded.connect(self.on_chapter_loaded)
        self.loader.error_occurred.connect(self.show_error)
        self.loader.loading_started.connect(self.on_loading_started)
        
    def setup_ui(self):
        self.setWindowTitle("QuickReader")
        self.setMinimumSize(1200, 800)
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)
        
        # Create splitter for resizable panels
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter)
        
        # Left panel for book list and chapters
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # URL input
        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter novel URL...")
        url_layout.addWidget(self.url_input)
        
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self.load_novel)
        url_layout.addWidget(load_btn)
        left_layout.addLayout(url_layout)
        
        # Book list with management buttons
        book_header_layout = QHBoxLayout()
        book_header_layout.addWidget(QLabel("Library"))
        
        # Add book management buttons
        book_buttons_layout = QHBoxLayout()
        move_up_btn = QPushButton("↑")
        move_up_btn.setToolTip("Move book up")
        move_up_btn.clicked.connect(self.move_book_up)
        move_up_btn.setMaximumWidth(30)
        
        move_down_btn = QPushButton("↓")
        move_down_btn.setToolTip("Move book down")
        move_down_btn.clicked.connect(self.move_book_down)
        move_down_btn.setMaximumWidth(30)
        
        delete_btn = QPushButton("×")
        delete_btn.setToolTip("Delete book")
        delete_btn.clicked.connect(self.delete_book)
        delete_btn.setMaximumWidth(30)
        
        book_buttons_layout.addWidget(move_up_btn)
        book_buttons_layout.addWidget(move_down_btn)
        book_buttons_layout.addWidget(delete_btn)
        book_header_layout.addLayout(book_buttons_layout)
        
        left_layout.addLayout(book_header_layout)
        
        # Book list
        self.book_list = QListWidget()
        self.book_list.itemClicked.connect(self.on_book_selected)
        self.book_list.setDragDropMode(QListWidget.InternalMove)  # Enable drag-drop reordering
        left_layout.addWidget(self.book_list)
        
        # Chapter list
        self.chapter_list = QListWidget()
        self.chapter_list.itemClicked.connect(self.on_chapter_selected)
        left_layout.addWidget(QLabel("Chapters"))
        left_layout.addWidget(self.chapter_list)
        
        # Add left panel to splitter
        self.splitter.addWidget(left_panel)
        
        # Right panel for content
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Content area
        self.content_view = QTextEdit()
        self.content_view.setReadOnly(True)
        self.setup_content_view()
        right_layout.addWidget(self.content_view)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Previous Chapter")
        self.prev_btn.clicked.connect(self.load_prev_chapter)
        nav_layout.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("Next Chapter")
        self.next_btn.clicked.connect(self.load_next_chapter)
        nav_layout.addWidget(self.next_btn)
        right_layout.addLayout(nav_layout)
        
        # Add right panel to splitter
        self.splitter.addWidget(right_panel)
        
        # Set up toolbar
        self.setup_toolbar()
        
        # Set up status bar
        self.statusBar().showMessage("Ready")
        
        # Load saved books
        self.load_saved_books()
        
        # Set initial splitter sizes
        self.splitter.setSizes([300, 900])  # Left panel 300px, right panel 900px
        
    def setup_content_view(self):
        """Set up the content view with proper styling"""
        self.content_view.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #e6e6e6;
                border: none;
                selection-background-color: #214283;
                selection-color: #ffffff;
                padding: 20px;
            }
        """)
        # Use system fonts as fallback
        font = QFont("Arial", 16)  # Changed from Microsoft YaHei to Arial
        self.content_view.setFont(font)
        
    def setup_toolbar(self):
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        # Add bookmark action
        bookmark_action = QAction(QIcon.fromTheme("bookmark-new"), "Bookmark", self)
        bookmark_action.triggered.connect(self.add_bookmark)
        toolbar.addAction(bookmark_action)
        
        # Toggle dark mode action
        dark_mode_action = QAction(QIcon.fromTheme("weather-clear-night"), "Dark Mode", self)
        dark_mode_action.setCheckable(True)
        dark_mode_action.toggled.connect(self.toggle_dark_mode)
        toolbar.addAction(dark_mode_action)
        
        # Font size actions
        toolbar.addSeparator()
        font_decrease = QAction(QIcon.fromTheme("zoom-out"), "Decrease Font", self)
        font_decrease.triggered.connect(lambda: self.change_font_size(-1))
        toolbar.addAction(font_decrease)
        
        font_increase = QAction(QIcon.fromTheme("zoom-in"), "Increase Font", self)
        font_increase.triggered.connect(lambda: self.change_font_size(1))
        toolbar.addAction(font_increase)
        
        # Toggle sidebar action
        toolbar.addSeparator()
        self.toggle_sidebar_action = QAction(QIcon.fromTheme("view-left-close"), "Toggle Sidebar", self)
        self.toggle_sidebar_action.setCheckable(True)
        self.toggle_sidebar_action.setChecked(True)
        self.toggle_sidebar_action.triggered.connect(self.toggle_sidebar)
        toolbar.addAction(self.toggle_sidebar_action)
        
    def load_saved_books(self):
        """Load saved books into the book list"""
        self.book_list.clear()
        books = self.reading_progress.get_all_books()
        for book in books:
            item = QListWidgetItem(book['title'])
            item.setToolTip(f"Source: {book['source_url']}\nChapters: {book['metadata'].get('total_chapters', 'Unknown')}")
            self.book_list.addItem(item)
            
    def load_novel(self):
        """Load a novel from URL"""
        url = self.url_input.text().strip()
        if not url:
            return
            
        logger.info(f"Attempting to load novel from URL: {url}")
        
        source = self.source_manager.get_source_for_url(url)
        if not source:
            logger.error(f"No source handler found for URL: {url}")
            self.show_error("Unsupported source")
            return
            
        try:
            self.statusBar().showMessage("Loading chapter list...")
            
            # Convert chapter URL to book URL if needed
            if '/read/' in url:
                book_id_match = re.search(r'/read/(\d+)_\d+\.html', url)
                if book_id_match:
                    url = f'https://www.dxmwx.org/book/{book_id_match.group(1)}.html'
                    logger.info(f"Converted to book URL: {url}")
            
            # Get chapter list
            logger.info("Fetching chapter list...")
            chapters = source.get_chapter_list(url)
            if not chapters:
                logger.error("Failed to load chapter list")
                self.show_error("Failed to load chapter list")
                return
                
            logger.info(f"Found {len(chapters)} chapters")
            
            # Get first chapter for book info
            logger.info("Loading first chapter for book info...")
            first_chapter = source.extract_chapter_content(chapters[0]['url'])
            if not first_chapter:
                logger.error("Failed to load book info")
                self.show_error("Failed to load book info")
                return
                
            # Save book
            book_id = self.reading_progress.add_or_update_book(
                first_chapter['book_name'],
                url,
                {'total_chapters': len(chapters)}
            )
            logger.info(f"Saved book with ID: {book_id}")
            
            # Update UI
            self.current_book_id = book_id
            self.current_chapter_list = chapters
            self.update_chapter_list()
            self.load_saved_books()
            
            # Load first chapter
            self.load_chapter(chapters[0]['url'])
            
            # Start caching in background
            if self.cache_thread is not None:
                self.cache_thread.quit()
            self.cache_thread = CacheThread(self.cache_manager, book_id, chapters[:5], self.source_manager)
            self.cache_thread.start()
            
            self.statusBar().showMessage(f"Loaded book with {len(chapters)} chapters")
            
        except Exception as e:
            logger.error(f"Error loading novel: {str(e)}", exc_info=True)
            self.show_error(str(e))
            
    def on_book_selected(self, item):
        """Handle book selection"""
        book_title = item.text()
        books = self.reading_progress.get_all_books()
        book = next((b for b in books if b['title'] == book_title), None)
        if not book:
            return
            
        self.current_book_id = book['id']
        source = self.source_manager.get_source_for_url(book['source_url'])
        if not source:
            return
            
        # Load chapter list
        chapters = source.get_chapter_list(book['source_url'])
        if chapters:
            self.current_chapter_list = chapters
            self.update_chapter_list()
            
            # Load last read chapter if available
            if book['last_read_url']:
                self.load_chapter(book['last_read_url'])
                
    def on_chapter_selected(self, item):
        """Handle chapter selection"""
        if self.loader.is_loading:
            return  # Ignore selection if already loading
            
        chapter_url = item.data(Qt.UserRole)
        if chapter_url:
            self.load_chapter(chapter_url)
            
    def load_chapter(self, url: str):
        """Load a chapter"""
        if self.loader.is_loading:
            logger.info("Already loading a chapter, ignoring request")
            return  # Don't load if already loading
            
        logger.info(f"Loading chapter from URL: {url}")
        
        # Set current chapter URL before loading
        self.current_chapter_url = url
        
        # Update chapter list selection
        for i in range(self.chapter_list.count()):
            item = self.chapter_list.item(i)
            if item.data(Qt.UserRole) == url:
                self.chapter_list.setCurrentItem(item)
                break
                
        # Pass the current_book_id to the loader
        self.loader.set_url(self.current_book_id, url)
        # Start the loader thread
        self.loader.start()
        logger.info("Started loader thread")
        
    def on_loading_started(self):
        """Called when chapter loading starts"""
        self.content_view.setHtml("<h2>Loading chapter...</h2>")
        self.content_view.verticalScrollBar().setValue(0)
        
    def on_chapter_loaded(self, content: Dict):
        """Handle loaded chapter content"""
        logger.info(f"Received chapter content for URL: {content.get('url')}")
        logger.debug(f"Content keys: {content.keys()}")
        logger.debug(f"Content: {content}")  # Add full content debug
        
        if not content or content.get('url') != self.current_chapter_url:
            logger.warning(f"Content URL mismatch. Expected: {self.current_chapter_url}, Got: {content.get('url')}")
            return  # Ignore if not the current chapter
            
        try:
            # Update reading progress
            if self.current_book_id:
                logger.info(f"Updating reading progress for book {self.current_book_id}")
                self.reading_progress.update_reading_progress(
                    self.current_book_id,
                    content.get('url', ''),
                    content.get('title', '')
                )
                
            # Format content with proper spacing and line breaks
            formatted_content = content.get('content', '')
            logger.debug(f"Raw content length: {len(formatted_content)}")
            
            if not formatted_content:
                logger.error("Empty content received")
                logger.debug(f"Content dict: {content}")
                self.show_error("Failed to load chapter content")
                return
                
            # Split into paragraphs and format
            paragraphs = []
            raw_paragraphs = formatted_content.split('\n\n')
            logger.debug(f"Found {len(raw_paragraphs)} raw paragraphs")
            
            for p in raw_paragraphs:
                p = p.strip()
                if p:
                    logger.debug(f"Processing paragraph: {p[:50]}...")
                    # Add proper paragraph styling
                    paragraphs.append(f"""
                        <p style='
                            margin: 1.5em 0;
                            line-height: 1.8;
                            text-indent: 2em;
                            font-size: 18px;
                            letter-spacing: 0.05em;
                            text-align: justify;
                        '>
                            {p}
                        </p>
                    """)
            
            logger.debug(f"Processed {len(paragraphs)} valid paragraphs")
            
            if not paragraphs:
                logger.error("No valid paragraphs found after formatting")
                logger.debug(f"Raw content: {formatted_content[:200]}...")
                self.show_error("Failed to format chapter content")
                return
            
            formatted_content = '\n'.join(paragraphs)
            logger.debug(f"Final formatted content length: {len(formatted_content)}")
            
            # Update content view with proper styling
            self.content_view.clear()
            html_content = f"""
                <div style="
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 40px 20px;
                    font-family: 'Arial', 'PingFang SC', 'Hiragino Sans GB', 'Noto Sans CJK SC', sans-serif;
                ">
                    <h1 style="
                        font-size: 24px;
                        margin-bottom: 2em;
                        text-align: center;
                        font-weight: bold;
                    ">{content.get('title', 'No Title')}</h1>
                    <div style="
                        font-size: 18px;
                        line-height: 1.8;
                        letter-spacing: 0.05em;
                    ">
                        {formatted_content}
                    </div>
                </div>
            """
            self.content_view.setHtml(html_content)
            self.content_view.update()  # Force update
            logger.info("Content view updated successfully")
            
            # Scroll to top
            self.content_view.verticalScrollBar().setValue(0)
            
            # Cache next chapters in background
            if self.current_book_id and self.current_chapter_list:
                try:
                    current_index = next(
                        i for i, ch in enumerate(self.current_chapter_list) 
                        if ch['url'] == self.current_chapter_url
                    )
                    next_chapters = self.current_chapter_list[current_index + 1:current_index + 4]
                    if next_chapters:
                        logger.info(f"Caching {len(next_chapters)} next chapters")
                        if self.cache_thread is not None:
                            self.cache_thread.quit()
                        self.cache_thread = CacheThread(self.cache_manager, self.current_book_id, next_chapters, self.source_manager)
                        self.cache_thread.start()
                except (StopIteration, IndexError) as e:
                    logger.warning(f"Error caching next chapters: {str(e)}")
                
            self.statusBar().showMessage("Chapter loaded")
            
            # Emit chapter loaded signal
            self.chapter_loaded.emit(content.get('url', ''), content.get('title', ''))
            
        except Exception as e:
            logger.error(f"Error displaying chapter: {str(e)}", exc_info=True)
            self.show_error(f"Error displaying chapter: {str(e)}")
            self.error_occurred.emit(str(e))
            
    def update_chapter_list(self):
        """Update the chapter list widget"""
        self.chapter_list.clear()
        
        # Add chapter count label
        total_chapters = len(self.current_chapter_list)
        for i, chapter in enumerate(self.current_chapter_list, 1):
            item = QListWidgetItem(f"{i}/{total_chapters} - {chapter['title']}")
            item.setData(Qt.UserRole, chapter['url'])
            self.chapter_list.addItem(item)
            
    def load_prev_chapter(self):
        """Load previous chapter"""
        if not self.current_chapter_url or self.loader.is_loading:
            return
            
        try:
            current_index = next(
                i for i, ch in enumerate(self.current_chapter_list) 
                if ch['url'] == self.current_chapter_url
            )
            if current_index > 0:
                self.load_chapter(self.current_chapter_list[current_index - 1]['url'])
        except (StopIteration, IndexError):
            pass
            
    def load_next_chapter(self):
        """Load next chapter"""
        if not self.current_chapter_url or self.loader.is_loading:
            return
            
        try:
            current_index = next(
                i for i, ch in enumerate(self.current_chapter_list) 
                if ch['url'] == self.current_chapter_url
            )
            if current_index < len(self.current_chapter_list) - 1:
                self.load_chapter(self.current_chapter_list[current_index + 1]['url'])
        except (StopIteration, IndexError):
            pass
            
    def add_bookmark(self):
        """Add a bookmark for current chapter"""
        if not self.current_book_id or not self.loader.url:
            return
            
        note, ok = QInputDialog.getText(
            self, 'Add Bookmark', 'Enter note (optional):'
        )
        if ok:
            self.reading_progress.add_bookmark(
                self.current_book_id,
                self.loader.url,
                note
            )
            self.statusBar().showMessage("Bookmark added")
            
    def toggle_dark_mode(self, enabled: bool):
        """Toggle dark mode"""
        if enabled:
            self.content_view.setStyleSheet("""
                QTextEdit {
                    background-color: #2b2b2b;
                    color: #e6e6e6;
                    border: none;
                    selection-background-color: #214283;
                    selection-color: #ffffff;
                    padding: 20px;
                }
            """)
        else:
            self.content_view.setStyleSheet("""
                QTextEdit {
                    background-color: #ffffff;
                    color: #000000;
                    border: none;
                    selection-background-color: #214283;
                    selection-color: #ffffff;
                    padding: 20px;
                }
            """)
            
    def change_font_size(self, delta: int):
        """Change font size"""
        font = self.content_view.font()
        new_size = max(8, min(32, font.pointSize() + delta))
        font.setPointSize(new_size)
        self.content_view.setFont(font)
        
    def toggle_sidebar(self):
        """Toggle the visibility of the left sidebar"""
        if self.toggle_sidebar_action.isChecked():
            # Show sidebar
            self.splitter.widget(0).show()
            self.splitter.setSizes([300, 900])
        else:
            # Hide sidebar
            self.splitter.widget(0).hide()
            self.splitter.setSizes([0, self.width()])
            
    def show_error(self, message: str):
        """Show error message"""
        QMessageBox.critical(self, "Error", message)
        self.statusBar().showMessage("Error: " + message)

    def move_book_up(self):
        """Move selected book up in the list"""
        current_row = self.book_list.currentRow()
        if current_row > 0:
            current_item = self.book_list.takeItem(current_row)
            self.book_list.insertItem(current_row - 1, current_item)
            self.book_list.setCurrentItem(current_item)
            self.save_book_order()

    def move_book_down(self):
        """Move selected book down in the list"""
        current_row = self.book_list.currentRow()
        if current_row < self.book_list.count() - 1:
            current_item = self.book_list.takeItem(current_row)
            self.book_list.insertItem(current_row + 1, current_item)
            self.book_list.setCurrentItem(current_item)
            self.save_book_order()

    def delete_book(self):
        """Delete selected book"""
        current_item = self.book_list.currentItem()
        if current_item:
            reply = QMessageBox.question(
                self, 'Delete Book',
                f'Are you sure you want to delete "{current_item.text()}"?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # Get book info
                book_title = current_item.text()
                books = self.reading_progress.get_all_books()
                book = next((b for b in books if b['title'] == book_title), None)
                
                if book:
                    # Delete from database
                    self.reading_progress.delete_book(book['id'])
                    # Clear cache
                    self.cache_manager.clear_book_cache(book['id'])
                    # Remove from list
                    self.book_list.takeItem(self.book_list.row(current_item))
                    
                    # Clear UI if this was the current book
                    if self.current_book_id == book['id']:
                        self.current_book_id = None
                        self.current_chapter_list = []
                        self.chapter_list.clear()
                        self.content_view.clear()

    def save_book_order(self):
        """Save the current order of books"""
        books = []
        for i in range(self.book_list.count()):
            item = self.book_list.item(i)
            book_title = item.text()
            book = next((b for b in self.reading_progress.get_all_books() if b['title'] == book_title), None)
            if book:
                books.append(book)
        
        # Update order in database
        self.reading_progress.update_book_order(books)

    def clear_invalid_cache(self):
        """Clear any invalid cache entries"""
        try:
            logger.info("Clearing invalid cache entries")
            
            # Clear invalid database cache entries
            self.cache_manager.clear_invalid_cache()
            
            # Clear invalid file cache entries
            cache_files = os.listdir(self.cache_dir)
            cleared_count = 0
            
            for cache_file in cache_files:
                if not cache_file.endswith('.json'):
                    continue
                    
                file_path = os.path.join(self.cache_dir, cache_file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                        
                    # Check if cache entry is valid (has all required fields)
                    if not content.get('content') or not content.get('title') or not content.get('url'):
                        logger.debug(f"Removing invalid cache file: {cache_file}")
                        os.remove(file_path)
                        cleared_count += 1
                except Exception as e:
                    logger.error(f"Error checking cache file {cache_file}: {str(e)}")
                    # Remove corrupted cache file
                    os.remove(file_path)
                    cleared_count += 1
                    
            logger.info(f"Cleared {cleared_count} invalid cache entries")
        except Exception as e:
            logger.error(f"Error clearing invalid cache: {str(e)}", exc_info=True)

def main():
    print("Starting QuickReader application...")
    app = QApplication(sys.argv)
    print("Created QApplication instance")
    
    window = MainWindow()
    print("Created MainWindow instance")
    
    window.show()
    print("Called window.show()")
    
    window.raise_()
    print("Called window.raise_()")
    
    print("Window geometry:", window.geometry())
    print("Window is visible:", window.isVisible())
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 