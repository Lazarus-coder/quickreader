# QuickReader

A web-based novel reader application that allows you to read novels from various sources on your iPhone or any other device with a web browser.

## Features

- Load novels from supported sources
- Browse your library of saved books
- Read chapters with a clean, mobile-friendly interface
- Navigate between chapters easily
- Dark mode for comfortable reading
- Automatic caching of chapters for offline reading

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/quickreader.git
cd quickreader
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows, use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Running the Application

1. Start the web server:
```bash
python web_server.py
```

2. Open your web browser and navigate to:
```
http://localhost:5000
```

3. On your iPhone or other device, make sure you're connected to the same network as your computer and navigate to:
```
http://<your-computer-ip>:5000
```

Replace `<your-computer-ip>` with your computer's local IP address.

## Usage

1. Enter a novel URL in the input field and click "Load"
2. Select a book from your library to view its chapters
3. Click on a chapter to read it
4. Use the navigation buttons to move between chapters

## Supported Sources

- HetuShu
- DXMWX
- More sources coming soon...

## Development

The application is built with:
- Flask for the web server
- PyQt5 for the core functionality
- BeautifulSoup4 for web scraping
- SQLite for data storage

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 