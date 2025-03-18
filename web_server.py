from flask import Flask, render_template, jsonify, request
import queue
import threading
import logging
from main import MainWindow
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QThread
import sys

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('quickreader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Create queues for communication between web and Qt threads
command_queue = queue.Queue()
response_queue = queue.Queue()

class QtThread(QThread):
    def __init__(self):
        super().__init__()
        self.app = QApplication(sys.argv)
        self.main_window = MainWindow()
        self.web_bridge = WebBridge(self.main_window)
        
    def run(self):
        # Process Qt events
        while True:
            self.app.processEvents()
            self.msleep(100)  # Sleep to prevent high CPU usage

class WebBridge(QObject):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.command_queue = command_queue
        self.response_queue = response_queue
        
        # Connect to MainWindow signals
        self.main_window.chapter_loaded.connect(self._on_chapter_loaded)
        self.main_window.error_occurred.connect(self._on_error)
        self.main_window.loading_started.connect(self._on_loading_started)
    
    def _on_chapter_loaded(self, url: str, title: str):
        """Handle chapter loaded event"""
        self.response_queue.put({
            'type': 'chapter_loaded',
            'data': {'url': url, 'title': title}
        })
    
    def _on_error(self, error_message: str):
        """Handle error event"""
        self.response_queue.put({
            'type': 'error',
            'message': error_message
        })
        
    def _on_loading_started(self, message: str):
        """Handle loading started event"""
        self.response_queue.put({
            'type': 'loading_started',
            'message': message
        })
        
    def process_command(self, command):
        """Process a command from the web interface"""
        try:
            if command['type'] == 'load_novel':
                url = command['url']
                self.main_window.url_input.setText(url)
                self.main_window.load_novel()
            elif command['type'] == 'load_chapter':
                url = command['url']
                self.main_window.load_chapter(url)
            elif command['type'] == 'get_chapter_list':
                chapters = self.main_window.current_chapter_list
                self.response_queue.put({
                    'type': 'chapter_list',
                    'chapters': chapters
                })
            elif command['type'] == 'get_book_list':
                books = self.main_window.reading_progress.get_all_books()
                self.response_queue.put({
                    'type': 'book_list',
                    'books': books
                })
        except Exception as e:
            logger.error(f"Error processing command: {str(e)}", exc_info=True)
            self.response_queue.put({
                'type': 'error',
                'message': str(e)
            })

# Create and start Qt thread
qt_thread = QtThread()
qt_thread.start()

def process_commands():
    """Process commands from the web interface"""
    while True:
        try:
            command = command_queue.get()
            qt_thread.web_bridge.process_command(command)
        except Exception as e:
            logger.error(f"Error in command processing: {str(e)}", exc_info=True)

# Start command processing thread
command_thread = threading.Thread(target=process_commands, daemon=True)
command_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/load_novel', methods=['POST'])
def load_novel():
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400
            
        command_queue.put({
            'type': 'load_novel',
            'url': url
        })
        return jsonify({'status': 'loading'})
    except Exception as e:
        logger.error(f"Error loading novel: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/load_chapter', methods=['POST'])
def load_chapter():
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400
            
        command_queue.put({
            'type': 'load_chapter',
            'url': url
        })
        return jsonify({'status': 'loading'})
    except Exception as e:
        logger.error(f"Error loading chapter: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_chapter_list')
def get_chapter_list():
    try:
        command_queue.put({
            'type': 'get_chapter_list'
        })
        return jsonify({'status': 'requested'})
    except Exception as e:
        logger.error(f"Error getting chapter list: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_book_list')
def get_book_list():
    try:
        command_queue.put({
            'type': 'get_book_list'
        })
        return jsonify({'status': 'requested'})
    except Exception as e:
        logger.error(f"Error getting book list: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/events')
def get_events():
    try:
        events = []
        while not response_queue.empty():
            events.append(response_queue.get())
        return jsonify(events)
    except Exception as e:
        logger.error(f"Error getting events: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True) 