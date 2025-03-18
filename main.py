#!/usr/bin/env python3
"""
QuickReader - A simple novel reader application.
"""

import sys
import os
import logging
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow

def setup_logging():
    """Set up logging configuration."""
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / "quickreader.log"),
            logging.StreamHandler()
        ]
    )

def main():
    """Main application entry point."""
    try:
        # Set up logging
        setup_logging()
        logger = logging.getLogger(__name__)
        logger.info("Starting QuickReader application...")
        
        # Add the current directory to Python path
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        
        # Create application
        app = QApplication(sys.argv)
        
        # Create and show main window
        window = MainWindow()
        window.show()
        
        # Run application
        sys.exit(app.exec())
        
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == '__main__':
    main() 