import requests
import re
from datetime import date, datetime
from bs4 import BeautifulSoup, NavigableString
from urllib.parse import urlparse

# include source reference TODO: retrieve from env
FEED_SUMMARY_API_URL = "https://k7ujpo4tfi.execute-api.eu-west-1.amazonaws.com/prod/feedsummary"


def get_domain(url):
    """Extracts the domain name from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    except Exception:
        return ""

def get_parent_url(url):
    """
    Returns the parent URL by removing the last path segment.
    Example: https://site.com/sport/calcio/article -> https://site.com/sport/calcio/
    Returns None if already at root level.
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        if not path or path == '/':
            return None
        parent_path = '/'.join(path.split('/')[:-1])
        if not parent_path:
            parent_path = '/'
        else:
            parent_path += '/'
        return f"{parsed.scheme}://{parsed.netloc}{parent_path}"
    except Exception:
        return None

def is_date_recent(date_str, max_days=0):
    """
    Checks if a date string represents a recent date.
    Args:
        date_str: Date string to check
        max_days: Maximum days ago (0 = today only, 10 = last 10 days including today)
    Returns tuple: (is_recent: bool, reason: str)
    """
    if not date_str:
        return False, "no date"

    date_str_lower = date_str.lower().strip()
    today_str = date.today().isoformat()

    # Check exact date match
    if date_str[:10] == today_str:
        return True, f"exact match ({today_str})"

    # Check for "today" keywords (multi-language)
    today_keywords = [
        'oggi', 'today', 'adesso', 'now', 'just now', 'appena', 
        'hoy', 'ahora', 'actualmente', 
        'aujourd\'hui', 'maintenant', 'actuellement'
    ]
    if any(kw in date_str_lower for kw in today_keywords):
        return True, f"keyword match ({date_str})"

    # Check for recent time expressions (hours, minutes ago) - multi-language regex
    time_patterns = [
        r'(\d+)\s*(ore?|hour|hours|horas?|heures?)\s*(fa|ago|antes|il y a)?',
        r'(\d+)\s*(minut[io]?|min|minutes?)\s*(fa|ago|antes|il y a)?',
        r'(\d+)\s*(second[io]?|sec|seconds?|segundos?|secondes?)\s*(fa|ago|antes|il y a)?',
    ]

    for pattern in time_patterns:
        match = re.search(pattern, date_str_lower)
        if match:
            return True, f"recent time ({date_str})"

    # Try to parse the date and check if it's within the allowed range
    try:
        # Try different date formats
        date_formats = [
            '%Y-%m-%d',      # 2026-01-14
            '%d/%m/%Y',      # 14/01/2026
            '%m/%d/%Y',      # 01/14/2026
            '%d-%m-%Y',      # 14-01-2026
            '%Y/%m/%d',      # 2026/01/14
        ]

        parsed_date = None
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str[:10], fmt).date()
                break
            except ValueError:
                continue

        if parsed_date:
            today = date.today()
            days_diff = (today - parsed_date).days

            if days_diff <= max_days:
                return True, f"within {max_days} days ({parsed_date}, {days_diff} days ago)"
            else:
                return False, f"too old ({parsed_date}, {days_diff} days ago > {max_days})"

    except Exception:
        pass

    # Check if date contains today's date components (fallback)
    today = date.today()
    if str(today.day) in date_str and str(today.year) in date_str:
        # Likely today's date in a different format
        return True, f"date components match ({date_str})"

    return False, f"not recent ({date_str})"

def normalize_text(text):
    """Normalizes text for comparison."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def extract_keywords(text, min_length=4):
    """Extracts significant keywords from text (multi-language support)."""
    if not text:
        return set()
    
    # Remove common news prefixes/suffixes that can skew similarity
    text = re.sub(r'^(video|foto|gallery|ultim\'ora|live|diretta|esclusiva):\s*', '', text, flags=re.I)
    
    words = normalize_text(text).split()
    # Combined stop words for IT, EN, ES, FR
    stop_words = {
        # IT
        'della', 'delle', 'dello', 'degli', 'nella', 'nelle', 'nello', 
        'negli', 'come', 'cosa', 'dove', 'quando', 'perché', 'quale',
        'quali', 'sono', 'essere', 'stato', 'stata', 'stati', 'state',
        'hanno', 'avere', 'fatto', 'fare', 'dopo', 'prima', 'anche',
        'solo', 'tutto', 'tutti', 'tutte', 'ogni', 'altro', 'altra',
        'altri', 'altre', 'questo', 'questa', 'questi', 'queste',
        'quello', 'quella', 'quelli', 'quelle', 'aveva', 'avevano',
        # EN
        'with', 'from', 'that', 'this', 'have', 'been', 'will', 'would', 
        'could', 'should', 'there', 'their', 'which', 'about', 'other',
        'after', 'before', 'could', 'would', 'should',
        # ES
        'está', 'este', 'esta', 'estos', 'estas', 'como', 'cuando', 
        'donde', 'pero', 'todo', 'todos', 'sobre', 'entre', 'también',
        # FR
        'dans', 'avec', 'pour', 'plus', 'cette', 'ceux', 'elles', 'entre',
        'tout', 'tous', 'faire', 'fait', 'mais', 'aussi'
    }
    return {w for w in words if len(w) >= min_length and w not in stop_words}

def calculate_similarity(text1, text2, use_weighted=True):
    """
    Calculates Jaccard similarity between two texts.
    If use_weighted is True, it gives more importance to shared rare keywords
    or entities (capitalized words).
    """
    keywords1 = extract_keywords(text1)
    keywords2 = extract_keywords(text2)
    
    if not keywords1 or not keywords2:
        return 0.0
    
    intersection = keywords1 & keywords2
    union = keywords1 | keywords2
    
    if not union:
        return 0.0
        
    base_jaccard = len(intersection) / len(union)
    
    if not use_weighted:
        return base_jaccard

    # Weighted logic: check for shared "entities" (words that were capitalized in original text)
    # This is a heuristic: we check if the intersection contains words that are likely names/places
    entities1 = {w for w in keywords1 if any(c.isupper() for c in text1.split() if normalize_text(c) == w)}
    entities2 = {w for w in keywords2 if any(c.isupper() for c in text2.split() if normalize_text(c) == w)}
    
    shared_entities = entities1 & entities2
    if shared_entities:
        # Boost similarity if they share proper names/entities
        boost = len(shared_entities) / len(union)
        return min(1.0, base_jaccard + boost)
        
    return base_jaccard

def extract_text_with_formatting(element):
    """Extracts text from HTML element preserving bold and spaces."""
    if not element:
        return ""
    result = []
    for child in element.children:
        if isinstance(child, NavigableString):
            result.append(str(child))
        elif child.name in ['strong', 'b']:
            result.append(f'**{child.get_text()}**')
        elif child.name == 'a':
            result.append(f' {child.get_text()} ')
        elif child.name in ['em', 'i']:
            result.append(child.get_text())
        elif child.name == 'br':
            result.append(' ')
        elif child.name in ['span', 'div', 'p']:
            result.append(extract_text_with_formatting(child))
        else:
            result.append(child.get_text() if hasattr(child, 'get_text') else str(child))
    text = ''.join(result)
    return re.sub(r'\s+', ' ', text).strip()

def format_content_as_html(text, articles=None):
    """Formats text as clean HTML with <p> and <strong>."""
    if not text:
        return ""
    
    # Replace [i] references with links if articles are provided
    if articles:
        def replace_ref(match):
            try:
                idx = int(match.group(1)) - 1
                if 0 <= idx < len(articles):
                    art = articles[idx]
                    domain = art.get('source_domain', '')
                    # Handle both single string and list for link
                    link_data = art.get('link', '#')
                    link = link_data[0] if isinstance(link_data, list) and link_data else link_data
                    return f'<a href="{link}" class="article-source" target="_blank">{domain}</a>'
            except (ValueError, IndexError):
                pass
            return match.group(0)
        
        text = re.sub(r'\[(\d+)\]', replace_ref, text)

    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__([^_]+)__', r'<strong>\1</strong>', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'\.([A-Z])', r'. \1', text)
    sentences = re.split(r'(?<=\.)\s+(?=[A-Z])', text)
    paragraphs = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence and len(sentence) > 10:
            if not sentence.endswith('.') and not sentence.endswith('</strong>'):
                sentence += '.'
            paragraphs.append(f"<p>{sentence}</p>")
    return '\n'.join(paragraphs) if paragraphs else f"<p>{text.strip()}</p>"

def fetch_article_content(url):
    """Fetches and extracts full article content from a URL."""
    article = {
        "title": "", "subtitle": "", "content": "",
        "image": "https://via.placeholder.com/300x200?text=No+Image",
        "link": url, "published_date": "", "source_domain": get_domain(url), "author": ""
    }
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; NewsFeedBot/1.0)"})
        if response.status_code != 200:
            return article
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Title
        title_elem = soup.find('meta', property='og:title') or soup.find('h1')
        if title_elem:
            article['title'] = title_elem.get('content') if title_elem.name == 'meta' else title_elem.get_text(strip=True)
        article['subtitle'] = article['title']

        # Image
        img_elem = soup.find('meta', property='og:image')
        if img_elem and img_elem.get('content'):
            article['image'] = img_elem['content']

        # Date
        for tag, attrs in [('meta', {'property': 'article:published_time'}), ('time', {})]:
            elem = soup.find(tag, attrs)
            if elem:
                date_val = elem.get('content') or elem.get('datetime') or elem.get_text(strip=True)
                if date_val and len(date_val) >= 10:
                    article['published_date'] = date_val[:10]
                    break

        # Content
        content_parts = []
        desc = soup.find('meta', property='og:description')
        if desc and desc.get('content'):
            content_parts.append(desc['content'])
        
        body = soup.find('article') or soup.find('div', class_=re.compile(r'article-body|content|post', re.I))
        if body:
            for p in body.find_all(['p', 'div']):
                if p.name == 'div' and (p.find('p') or len(p.get_text(strip=True)) < 100):
                    continue
                text = extract_text_with_formatting(p)
                if text and len(text) > 40:
                    content_parts.append(text)
                if len(content_parts) >= 15:
                    break
        
        raw_content = '\n\n'.join(content_parts)[:3000].replace('"', '\\"')
        article['content'] = format_content_as_html(raw_content)
        article['content_text_length'] = len(raw_content)
    except Exception as e:
        print(f"   ⚠️ Error fetching {url[:50]}: {e}")
    return article

def call_feed_summary_api(articles, cluster_id, locale="IT",model=None):
    """Calls the feedSummary API to generate a summary."""
    try:
        contents = [{"id": i, "content": a.get('content', ''), "source": a.get('source_domain', '')} 
                    for i, a in enumerate(articles, 1)]
        payload = {
            "cluster_id": cluster_id, 
            "language": locale.lower(),
            "contents": contents,
        }
        if model:
            payload["model"] = model
        response = requests.post(FEED_SUMMARY_API_URL, json=payload, timeout=30)
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"   ❌ Error calling feedSummary API: {e}")
        return None
