# QuickReader

QuickReader is a novel reading application available in two versions:
1. A desktop application built with Python and PySide6
2. A web application with a Flask backend and JavaScript frontend

Both applications provide a clean, distraction-free reading experience for web novels.

## Applications

### Desktop App

The desktop application uses PySide6 (Qt) for the UI and provides a native experience on Windows, macOS, and Linux.

[Go to Desktop App →](./desktop-app/)

### Web App

The web application consists of a Flask backend and a vanilla JavaScript frontend, allowing it to run in any modern web browser.

[Go to Web App →](./web-app/)

## Features

Both applications share the following features:
- Modern and intuitive user interface
- Chapter navigation
- Bookmark management
- Library of saved books
- Content caching
- Dark mode support
- Font size customization
- Support for various novel websites

## Getting Started

### Desktop App

```bash
cd desktop-app
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Web App

```bash
cd web-app
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd backend
python app.py
```

Then open a web browser and navigate to: http://localhost:3000

## Screenshots

*[Screenshots will be added here]*

## License

MIT 