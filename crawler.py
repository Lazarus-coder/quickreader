import requests
from bs4 import BeautifulSoup
from typing import Optional, Tuple
import re
import logging
import time
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NovelCrawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://www.dxmwx.org/'
        })

    def _get_page_content(self, url: str) -> Optional[str]:
        """Get page content with retry mechanism."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=10)
                response.encoding = 'utf-8'
                if response.status_code == 200:
                    return response.text
                logger.warning(f"Got status code {response.status_code}")
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
        return None

    def _extract_js_variables(self, html_content: str) -> dict:
        """Extract variables from JavaScript."""
        variables = {}
        
        # Extract ChapterTitle
        match = re.search(r'var\s+ChapterTitle\s*=\s*["\']([^"\']+)["\']', html_content)
        if match:
            variables['title'] = match.group(1)
            
        # Extract BookName
        match = re.search(r'var\s+BookName\s*=\s*["\']([^"\']+)["\']', html_content)
        if match:
            variables['book_name'] = match.group(1)
            
        # Extract navigation URLs
        match = re.search(r'var\s+prevpage\s*=\s*["\']([^"\']+)["\']', html_content)
        if match:
            variables['prev_url'] = match.group(1)
            
        match = re.search(r'var\s+nextpage\s*=\s*["\']([^"\']+)["\']', html_content)
        if match:
            variables['next_url'] = match.group(1)
            
        match = re.search(r'var\s+chapterpage\s*=\s*["\']([^"\']+)["\']', html_content)
        if match:
            variables['chapter_list_url'] = match.group(1)
            
        # Extract character names array
        match = re.search(r'var\s+names\s*=\s*(\[[^\]]+\])', html_content)
        if match:
            try:
                names_str = match.group(1).replace("'", '"')
                variables['names'] = json.loads(names_str)
            except json.JSONDecodeError:
                variables['names'] = []
                
        return variables

    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract content from the Lab_Contents div."""
        content_div = soup.find('div', id='Lab_Contents')
        if not content_div:
            return None
            
        # Get all text nodes and preserve paragraph breaks
        paragraphs = []
        for p in content_div.stripped_strings:
            text = p.strip()
            if text:
                paragraphs.append(text)
        
        return '\n\n'.join(paragraphs)

    def _process_content(self, content: str, names: list) -> str:
        """Process content by highlighting character names."""
        if not content or not names:
            return content
            
        for name in names:
            # Skip empty names
            if not name.strip():
                continue
                
            # Escape special characters in the name
            escaped_name = re.escape(name)
            # Create a pattern that matches the name but not already highlighted text
            pattern = f'(?<!<span[^>]*>)({escaped_name})(?![^<]*</span>)'
            # Replace with highlighted version
            content = re.sub(pattern, 
                           r'<span style="color:#795548;font-weight: bold;">\1</span>', 
                           content)
        return content

    def extract_chapter_content(self, url: str) -> Optional[Tuple[str, str, str]]:
        """Extract chapter content, title, and next chapter URL."""
        try:
            html_content = self._get_page_content(url)
            if not html_content:
                logger.error(f"Failed to fetch content from {url}")
                return None

            # Parse HTML
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract JavaScript variables
            js_vars = self._extract_js_variables(html_content)
            
            # Extract content
            content = self._extract_content(soup)
            if not content:
                logger.error("Content not found in Lab_Contents div")
                return None
                
            # Process content with character names if available
            if js_vars.get('names'):
                content = self._process_content(content, js_vars['names'])
                
            # Get title
            title = js_vars.get('title', 'Unknown Title')
            
            # Get next URL
            next_url = js_vars.get('next_url')
            if next_url and not next_url.startswith('http'):
                next_url = f"https://www.dxmwx.org{next_url}"

            return title, content, next_url

        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None

    def get_chapter_list(self, url: str) -> Optional[list]:
        """Extract the list of chapter URLs."""
        try:
            html_content = self._get_page_content(url)
            if not html_content:
                return None

            soup = BeautifulSoup(html_content, 'lxml')
            
            # Try different selectors for chapter list
            chapter_list = soup.find('div', class_='chapter-list') or \
                         soup.find('ul', class_='chapter-list') or \
                         soup.find('div', id='chapter-list')

            if not chapter_list:
                logger.error("Chapter list not found")
                return None

            chapters = []
            for link in chapter_list.find_all('a'):
                if 'href' in link.attrs:
                    chapter_url = link['href']
                    if not chapter_url.startswith('http'):
                        chapter_url = f"https://www.dxmwx.org{chapter_url}"
                    chapters.append(chapter_url)

            return chapters

        except Exception as e:
            logger.error(f"Error processing chapter list: {str(e)}")
            return None 