from abc import ABC, abstractmethod
from typing import Optional, Tuple, List, Dict
import requests
from bs4 import BeautifulSoup
import re
import json
import logging
import time
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

class NovelSource(ABC):
    def __init__(self):
        self.session = requests.Session()
        self.setup_session()
        self.content_selectors = [
            {'type': 'id', 'value': 'content'},
            {'type': 'id', 'value': 'chapter-content'},
            {'type': 'id', 'value': 'chapterContent'},
            {'type': 'class', 'value': 'chapter-content'},
            {'type': 'class', 'value': 'article-content'}
        ]
        self.nav_selectors = [
            {'type': 'id', 'value': 'next', 'text': '下一章'},
            {'type': 'id', 'value': 'prev', 'text': '上一章'},
            {'type': 'class', 'value': 'next-chapter', 'text': '下一章'},
            {'type': 'class', 'value': 'prev-chapter', 'text': '上一章'},
            {'type': 'text', 'value': '下一章'},
            {'type': 'text', 'value': '上一章'}
        ]

    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract content using multiple selectors with fallbacks"""
        content = None
        
        # Try each content selector in order
        for selector in self.content_selectors:
            try:
                if selector['type'] == 'id':
                    element = soup.find('div', id=selector['value'])
                elif selector['type'] == 'class':
                    element = soup.find('div', class_=selector['value'])
                
                if element:
                    # Remove unwanted elements
                    for unwanted in element.find_all(['script', 'style', 'a', 'div', 'span']):
                        if unwanted.get_text(strip=True) in ['上一章', '下一章', '目录']:
                            unwanted.decompose()
                    
                    # Get text content
                    content = element.get_text(strip=True)
                    if content and len(content) > 100:  # Minimum content length check
                        logger.info(f"Found content using selector: {selector}")
                        return content
            except Exception as e:
                logger.warning(f"Error with selector {selector}: {str(e)}")
        
        # Fallback: Try to find the largest text block
        if not content:
            try:
                text_blocks = []
                for tag in soup.find_all(['div', 'p']):
                    text = tag.get_text(strip=True)
                    if len(text) > 200 and not any(skip in text for skip in ['上一章', '下一章', '目录']):
                        text_blocks.append((len(text), text))
                
                if text_blocks:
                    text_blocks.sort(reverse=True)
                    logger.info("Found content using largest text block method")
                    return text_blocks[0][1]
            except Exception as e:
                logger.warning(f"Error in fallback content extraction: {str(e)}")
        
        return None

    def _extract_navigation(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Optional[str]]:
        """Extract navigation links using multiple selectors"""
        nav = {'prev_url': None, 'next_url': None, 'chapter_list_url': None}
        
        # Try each navigation selector
        for selector in self.nav_selectors:
            try:
                if selector['type'] == 'id':
                    links = soup.find_all('a', id=selector['value'])
                elif selector['type'] == 'class':
                    links = soup.find_all('a', class_=selector['value'])
                elif selector['type'] == 'text':
                    links = [a for a in soup.find_all('a') if selector['value'] in a.get_text(strip=True)]
                
                for link in links:
                    href = link.get('href')
                    text = link.get_text(strip=True)
                    if href:
                        if '下一章' in text and not nav['next_url']:
                            nav['next_url'] = urljoin(base_url, href)
                        elif '上一章' in text and not nav['prev_url']:
                            nav['prev_url'] = urljoin(base_url, href)
                        elif '目录' in text and not nav['chapter_list_url']:
                            nav['chapter_list_url'] = urljoin(base_url, href)
            except Exception as e:
                logger.warning(f"Error with nav selector {selector}: {str(e)}")
        
        return nav

    def _clean_content(self, content: str) -> str:
        """Clean and format the extracted content"""
        if not content:
            return ""
        
        # Basic HTML cleanup
        content = content.replace('&nbsp;', ' ')
        content = re.sub(r'<br\s*/?>', '\n', content)
        content = re.sub(r'<[^>]+>', '', content)
        
        # Split into paragraphs
        paragraphs = []
        
        # Try different splitting methods
        split_methods = [
            lambda x: x.split('\n\n'),  # Double newlines
            lambda x: x.split('\n'),    # Single newlines
            lambda x: re.split(r'([。！？…]+)', x)  # Chinese punctuation
        ]
        
        for split_method in split_methods:
            parts = split_method(content)
            if isinstance(parts, list) and len(parts) > 1:
                # For Chinese punctuation split, rejoin with punctuation
                if split_method == split_methods[-1]:
                    parts = [''.join(parts[i:i+2]) for i in range(0, len(parts)-1, 2)]
                
                # Process each part
                for p in parts:
                    p = p.strip()
                    if p and len(p) > 10:  # Only keep meaningful paragraphs
                        p = re.sub(r'\s+', ' ', p)  # Normalize whitespace
                        if not any(skip in p for skip in ['上一章', '下一章', '目录']):
                            paragraphs.append(p)
                
                if paragraphs:
                    break
        
        return '\n\n'.join(paragraphs) if paragraphs else content.strip()

    def _get_page_content(self, url: str, retry_count: int = 3) -> Optional[str]:
        """Get page content with retry mechanism and detailed logging"""
        for attempt in range(retry_count):
            try:
                response = self.session.get(url, timeout=10)
                
                # Log response details for debugging
                logger.debug(f"Response status: {response.status_code}")
                logger.debug(f"Response headers: {response.headers}")
                
                # Try to detect encoding
                if 'charset=' in response.headers.get('content-type', '').lower():
                    response.encoding = response.headers.get('content-type').lower().split('charset=')[-1]
                else:
                    response.encoding = response.apparent_encoding or 'utf-8'
                logger.debug(f"Using encoding: {response.encoding}")
                
                if response.status_code == 200:
                    content = response.text
                    if len(content) < 100:  # Suspiciously short content
                        logger.warning(f"Retrieved content is suspiciously short ({len(content)} chars)")
                    return content
                    
                logger.warning(f"Got status code {response.status_code} for {url}")
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
            
            if attempt < retry_count - 1:
                sleep_time = 2 ** attempt
                logger.info(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
        
        logger.error(f"Failed to get content after {retry_count} attempts: {url}")
        return None

    @abstractmethod
    def setup_session(self):
        """Set up session headers and cookies"""
        pass

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this source can handle the given URL"""
        pass

    @abstractmethod
    def extract_chapter_content(self, url: str) -> Optional[Dict]:
        """Extract chapter content and metadata"""
        pass

    @abstractmethod
    def get_chapter_list(self, url: str) -> Optional[List[Dict]]:
        """Get list of chapters"""
        pass

class DXMWXSource(NovelSource):
    def setup_session(self):
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': 'https://www.dxmwx.org/'
        })

    def can_handle(self, url: str) -> bool:
        return 'dxmwx.org' in url

    def _extract_js_variables(self, html_content: str) -> dict:
        """Extract variables from JavaScript"""
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
            match = re.search(pattern, html_content, re.DOTALL)
            if match:
                value = match.group(1)
                # Decode escaped content
                if key == 'content':
                    value = value.encode().decode('unicode_escape')
                variables[key] = value
        
        # Extract character names array
        names_match = re.search(r'var\s+names\s*=\s*(\[[^\]]+\])', html_content)
        if names_match:
            try:
                names_str = names_match.group(1).replace("'", '"')
                variables['names'] = json.loads(names_str)
            except json.JSONDecodeError:
                variables['names'] = []
        
        # Extract book and chapter IDs
        book_id_match = re.search(r'/read/(\d+)_\d+\.html', html_content)
        if book_id_match:
            variables['book_id'] = book_id_match.group(1)
            
        chapter_id_match = re.search(r'/read/\d+_(\d+)\.html', html_content)
        if chapter_id_match:
            variables['chapter_id'] = chapter_id_match.group(1)
            
        return variables

    def _extract_content_from_api(self, book_id: str, chapter_id: str) -> Optional[str]:
        """Try to get content from API"""
        try:
            # Try the chapter API endpoint
            api_url = f"https://www.dxmwx.org/api/chapter/{book_id}/{chapter_id}"
            response = self.session.get(api_url)
            if response.status_code == 200:
                data = response.json()
                return data.get('content')

            # Try the content API endpoint
            api_url = f"https://www.dxmwx.org/api/content/{book_id}/{chapter_id}"
            response = self.session.get(api_url)
            if response.status_code == 200:
                data = response.json()
                return data.get('content')

            return None
        except Exception as e:
            logger.warning(f"API extraction failed: {str(e)}")
            return None

    def _extract_content_from_html(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract content from HTML"""
        try:
            # First try to find the main article content
            content_div = soup.find('div', id='Lab_Contents')
            if content_div:
                # Remove unwanted elements
                for unwanted in content_div.find_all(['script', 'style', 'a', 'div']):
                    unwanted.decompose()
                
                # Get text content
                content = content_div.get_text(strip=True)
                if content:
                    return content

            # Try alternative content divs
            for div_id in ['content', 'chapterContent', 'chapter-content']:
                content_div = soup.find('div', id=div_id)
                if content_div:
                    # Remove unwanted elements
                    for unwanted in content_div.find_all(['script', 'style', 'a', 'div']):
                        unwanted.decompose()
                    content = content_div.get_text(strip=True)
                    if content:
                        return content

            # Try to find the largest text block
            text_blocks = []
            for tag in soup.find_all(['div', 'p']):
                text = tag.get_text(strip=True)
                if len(text) > 100 and not any(skip in text for skip in ['上一章', '下一章', '目录', '书页']):
                    text_blocks.append((len(text), text))
            
            if text_blocks:
                # Sort by length and get the largest text block
                text_blocks.sort(reverse=True)
                return text_blocks[0][1]

            return None
        except Exception as e:
            logger.warning(f"HTML extraction failed: {str(e)}")
            return None

    def _extract_content_from_js(self, html_content: str) -> Optional[str]:
        """Extract content from JavaScript variables"""
        try:
            # Try to find TxtContents variable
            match = re.search(r'var\s+TxtContents\s*=\s*["\']([^"\']+)["\']', html_content)
            if match:
                content = match.group(1)
                # Unescape content if needed
                content = content.encode().decode('unicode_escape')
                return content

            return None
        except Exception as e:
            logger.warning(f"JavaScript extraction failed: {str(e)}")
            return None

    def extract_chapter_content(self, url: str) -> Optional[Dict]:
        try:
            html_content = self._get_page_content(url)
            if not html_content:
                logger.error(f"Failed to get page content from {url}")
                return None

            logger.info(f"Extracting content from {url}")
            soup = BeautifulSoup(html_content, 'lxml')
            content = None
            title = None
            js_vars = {}

            # 1. First try JavaScript extraction
            logger.info("Trying JavaScript extraction")
            js_vars = self._extract_js_variables(html_content)
            content = js_vars.get('content')
            title = js_vars.get('title')
            
            if content:
                logger.info("Found content in JavaScript variables")
            
            # 2. Try direct TxtContents regex if JS vars didn't work
            if not content:
                logger.info("Trying direct TxtContents regex")
                txt_contents_match = re.search(r'TxtContents\s*=\s*[\'"]([^\'"]+)[\'"]', html_content, re.DOTALL)
                if txt_contents_match:
                    content = txt_contents_match.group(1).encode().decode('unicode_escape')
                    logger.info("Found content in TxtContents")

            # 3. Try HTML parsing if still no content
            if not content:
                logger.info("Trying HTML parsing")
                content = self._extract_content_from_html(soup)
                if content:
                    logger.info("Found content in HTML")

            # 4. Try API extraction as last resort
            if not content:
                book_id_match = re.search(r'/read/(\d+)_(\d+)\.html', url)
                if book_id_match:
                    logger.info("Trying API extraction")
                    book_id = book_id_match.group(1)
                    chapter_id = book_id_match.group(2)
                    content = self._extract_content_from_api(book_id, chapter_id)
                    if content:
                        logger.info("Found content from API")

            if not content:
                logger.error(f"Failed to extract content from {url}")
                return None

            # Clean up the content
            content = content.replace('&nbsp;', ' ')
            content = re.sub(r'<br\s*/?>', '\n', content)
            content = re.sub(r'<[^>]+>', '', content)
            
            # Split into paragraphs and clean
            paragraphs = []
            # First try splitting by double newlines
            parts = content.split('\n\n')
            if len(parts) <= 1:
                # If no double newlines, try single newlines
                parts = content.split('\n')
            if len(parts) <= 1:
                # If still no parts, try splitting by Chinese punctuation
                parts = re.split(r'([。！？…]+)', content)
                # Rejoin punctuation marks with the text
                parts = [''.join(parts[i:i+2]) for i in range(0, len(parts)-1, 2)]
            
            for p in parts:
                p = p.strip()
                if p and len(p) > 10:  # Only keep non-empty paragraphs with meaningful content
                    # Remove extra spaces and normalize whitespace
                    p = re.sub(r'\s+', ' ', p)
                    # Remove common navigation text
                    if not any(skip in p for skip in ['上一章', '下一章', '目录', '书页']):
                        paragraphs.append(p)
            
            if not paragraphs:
                logger.error("No valid paragraphs found after cleaning")
                return None
            
            content = '\n\n'.join(paragraphs)
            logger.info(f"Final content has {len(paragraphs)} paragraphs")

            # Get title if not found in JS variables
            if not title:
                title_element = soup.find(['h1', 'h2', 'h3'])
                if title_element:
                    title = title_element.get_text(strip=True)

            # Get book name
            book_name = js_vars.get('book_name')
            if not book_name:
                book_name_element = soup.find('meta', {'property': 'og:novel:book_name'})
                if book_name_element:
                    book_name = book_name_element.get('content')
            if not book_name:
                book_name = '人道大圣'

            # Get navigation URLs
            base_url = 'https://www.dxmwx.org'
            prev_url = js_vars.get('prev_url')
            next_url = js_vars.get('next_url')
            chapter_list_url = js_vars.get('chapter_list_url')

            # If URLs not found in JS, try HTML
            if not all([prev_url, next_url, chapter_list_url]):
                for link in soup.find_all('a'):
                    text = link.get_text(strip=True)
                    href = link.get('href', '')
                    if '上一章' in text and not prev_url:
                        prev_url = href
                    elif '下一章' in text and not next_url:
                        next_url = href
                    elif '目录' in text and not chapter_list_url:
                        chapter_list_url = href

            # Process URLs
            nav_urls = {
                'prev_url': prev_url,
                'next_url': next_url,
                'chapter_list_url': chapter_list_url
            }
            
            for key, link in nav_urls.items():
                if link and not link.startswith('http'):
                    nav_urls[key] = urljoin(base_url, link)

            return {
                'title': title or 'Unknown Title',
                'content': content,
                'book_name': book_name,
                'prev_url': nav_urls['prev_url'],
                'next_url': nav_urls['next_url'],
                'chapter_list_url': nav_urls['chapter_list_url'],
                'url': url
            }

        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None

    def get_chapter_list(self, url: str) -> Optional[List[Dict]]:
        try:
            logger.info(f"Attempting to get chapter list from {url}")
            
            # Convert any URL to chapter list URL format
            book_id = None
            if '/read/' in url:
                book_id_match = re.search(r'/read/(\d+)_\d+\.html', url)
                if book_id_match:
                    book_id = book_id_match.group(1)
            elif '/book/' in url:
                book_id_match = re.search(r'/book/(\d+)\.html', url)
                if book_id_match:
                    book_id = book_id_match.group(1)
            elif '/chapter/' in url:
                book_id_match = re.search(r'/chapter/(\d+)\.html', url)
                if book_id_match:
                    book_id = book_id_match.group(1)
                    
            if not book_id:
                logger.error("Could not extract book ID from URL")
                return None
                
            # Use the chapter list URL format
            url = f'https://www.dxmwx.org/chapter/{book_id}.html'
            logger.info(f"Using chapter list URL: {url}")

            # Get the chapter list page content
            html_content = self._get_page_content(url)
            if not html_content:
                logger.error("Failed to get page content")
                return None

            soup = BeautifulSoup(html_content, 'lxml')
            chapters = []
            base_url = 'https://www.dxmwx.org'
            seen_urls = set()  # To avoid duplicates

            # Find all chapter links in divs with height:40px style
            for div in soup.find_all('div', style=lambda s: s and 'height:40px' in s):
                for span in div.find_all('span', style=lambda s: s and 'width:31%' in s):
                    link = span.find('a')
                    if link and link.get('href'):
                        href = link.get('href')
                        if href and href not in seen_urls and '/read/' in href:
                            chapter_url = urljoin(base_url, href)
                            title = link.get_text(strip=True)
                            if title:
                                chapters.append({
                                    'title': title,
                                    'url': chapter_url
                                })
                                seen_urls.add(href)

            # Sort chapters by their numeric ID to ensure correct order
            def get_chapter_id(chapter):
                match = re.search(r'/read/\d+_(\d+)\.html', chapter['url'])
                try:
                    return int(match.group(1)) if match else float('inf')
                except (AttributeError, ValueError):
                    return float('inf')
                
            chapters.sort(key=get_chapter_id)

            if chapters:
                logger.info(f"Successfully extracted {len(chapters)} chapters")
                return chapters
            else:
                logger.error("No chapters found in the chapter list")
                return None

        except Exception as e:
            logger.error(f"Error processing chapter list: {str(e)}")
            return None

class HetuShuSource(NovelSource):
    def setup_session(self):
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
            'Referer': 'https://www.hetushu.com/'
        })

    def can_handle(self, url: str) -> bool:
        return 'hetushu.com' in url

    def get_chapter_list(self, url: str) -> Optional[List[Dict]]:
        try:
            # Convert any book URL to index URL format
            if '/book/' not in url:
                return None
            
            book_id = re.search(r'/book/(\d+)', url)
            if not book_id:
                return None
                
            book_id = book_id.group(1)
            index_url = f'https://www.hetushu.com/book/{book_id}/index.html'
            
            logger.info(f"Getting chapter list from {index_url}")
            html_content = self._get_page_content(index_url)
            if not html_content:
                return None

            soup = BeautifulSoup(html_content, 'lxml')
            chapters = []
            base_url = 'https://www.hetushu.com'

            # Find all chapter links in the directory
            for link in soup.select('#dir dt a, #dir dd a'):
                href = link.get('href')
                if href and '/book/' in href:
                    chapter_url = urljoin(base_url, href)
                    title = link.get_text(strip=True)
                    if title:
                        chapters.append({
                            'title': title,
                            'url': chapter_url
                        })

            if chapters:
                logger.info(f"Found {len(chapters)} chapters")
                return chapters
            else:
                logger.error("No chapters found")
                # Log the HTML for debugging
                logger.debug(f"HTML content: {html_content}")
                return None

        except Exception as e:
            logger.error(f"Error getting chapter list: {str(e)}")
            return None

    def extract_chapter_content(self, url: str) -> Optional[Dict]:
        try:
            html_content = self._get_page_content(url)
            if not html_content:
                return None

            soup = BeautifulSoup(html_content, 'lxml')
            base_url = 'https://www.hetushu.com'
            
            # Extract content using base class method
            content = self._extract_content(soup)
            if not content:
                logger.error(f"No content found for {url}")
                logger.debug(f"HTML content: {html_content}")
                return None

            # Clean content
            content = self._clean_content(content)
            if not content:
                logger.error("Content cleaning resulted in empty text")
                return None

            # Get title
            title = None
            title_elem = soup.select_one('.body .title')
            if title_elem:
                title = title_elem.get_text(strip=True).split('>')[-1]

            # Get book name
            book_name = None
            book_info = soup.select_one('.book_info h2')
            if book_info:
                book_name = book_info.get_text(strip=True)

            # Get navigation using base class method
            nav = self._extract_navigation(soup, base_url)

            return {
                'title': title or 'Unknown Title',
                'content': content,
                'book_name': book_name,
                'prev_url': nav['prev_url'],
                'next_url': nav['next_url'],
                'chapter_list_url': nav['chapter_list_url'],
                'url': url
            }

        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None

class SourceManager:
    def __init__(self):
        self.sources = [DXMWXSource(), HetuShuSource()]

    def get_source_for_url(self, url: str) -> Optional[NovelSource]:
        for source in self.sources:
            if source.can_handle(url):
                return source
        return None 