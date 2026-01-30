import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime
from news_utils import fetch_article_content, call_feed_summary_api, get_domain, normalize_text, calculate_similarity, get_parent_url, is_date_recent
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import requests

# =============================================================================
# DEBUG LOGGER
# =============================================================================

class DebugLogger:
    """Logs detailed debug information to a markdown file."""

    def __init__(self, cluster_id, enabled=False):
        self.enabled = enabled
        self.cluster_id = cluster_id
        self.sections = []
        self.start_time = datetime.now()

    def add_header(self, cluster_name, cluster_description):
        """Add document header."""
        if not self.enabled:
            return
        self.sections.append(f"# Debug Log: Cluster {self.cluster_id} - {cluster_name}")
        self.sections.append(f"**Description:** {cluster_description}")
        self.sections.append(f"\n**Generated:** {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.sections.append("---\n")
    
    def add_section(self, title, level=2):
        """Add a section header."""
        if not self.enabled:
            return
        prefix = "#" * level
        self.sections.append(f"\n{prefix} {title}\n")
    
    def add_text(self, text):
        """Add plain text."""
        if not self.enabled:
            return
        self.sections.append(text)
    
    def add_query(self, query, system_prompt, keywords=None):
        """Log the search query and system prompt."""
        if not self.enabled:
            return
        self.add_section("1. Search Query")
        if keywords:
            self.sections.append(f"**Keywords used:** `{', '.join(keywords)}`\n")
        self.sections.append(f"**Query:**\n```\n{query}\n```\n")
        self.sections.append(f"**System Prompt:**\n```\n{system_prompt}\n```\n")
    
    def add_citations(self, citations, removed_citations=None):
        """Log the citations/URLs returned by search."""
        if not self.enabled:
            return
        self.add_section("2. Citations (Source URLs)")
        self.sections.append(f"**Total:** {len(citations)} URLs (after filtering)\n")
        for i, url in enumerate(citations, 1):
            self.sections.append(f"{i}. {url}")
        
        # Log removed citations if any
        if removed_citations:
            self.sections.append(f"\n**Filtered out:** {len(removed_citations)} video/live/blocked URLs\n")
            for item in removed_citations:
                if isinstance(item, tuple):
                    url, reason = item
                    self.sections.append(f"- ~~{url}~~ (*{reason}*)")
                else:
                    self.sections.append(f"- ~~{item}~~")
        self.sections.append("")
    
    def add_extraction(self, url, news_items):
        """Log news items extracted from a URL."""
        if not self.enabled:
            return
        self.sections.append(f"\n### Source: `{url[:80]}`")
        self.sections.append(f"**Extracted:** {len(news_items)} items\n")
        if news_items:
            self.sections.append("| # | Title | Domain |")
            self.sections.append("|---|-------|--------|")
            for i, item in enumerate(news_items[:20], 1):  # Limit to 20 for readability
                title = item.get('title', '')[:60].replace('|', '\\|')
                domain = item.get('source_domain', '')
                self.sections.append(f"| {i} | {title}... | {domain} |")
            if len(news_items) > 20:
                self.sections.append(f"| ... | *({len(news_items) - 20} more items)* | |")
        self.sections.append("")
    
    def add_clustering(self, clusters, filtered_count, total_count):
        """Log clustering results."""
        if not self.enabled:
            return
        self.add_section("4. Clustering Results")
        self.sections.append(f"- **Total extracted:** {total_count} items")
        self.sections.append(f"- **After filtering:** {filtered_count} valid items")
        self.sections.append(f"- **Clusters created:** {len(clusters)}\n")
        
        self.sections.append("| Cluster | Size | Representative Title | Domains |")
        self.sections.append("|---------|------|---------------------|---------|")
        for i, cluster in enumerate(clusters[:15], 1):
            title = cluster[0].get('title', '')[:50].replace('|', '\\|')
            domains = set(item.get('source_domain', '') for item in cluster)
            domains_str = ", ".join(list(domains)[:3])
            if len(domains) > 3:
                domains_str += f" (+{len(domains)-3})"
            self.sections.append(f"| {i} | {len(cluster)} | {title}... | {domains_str} |")
        if len(clusters) > 15:
            self.sections.append(f"| ... | | *({len(clusters) - 15} more clusters)* | |")
        self.sections.append("")
    
    def add_selection(self, cluster_idx, item, status, reason=""):
        """Log source selection attempts."""
        if not self.enabled:
            return
        title = item.get('title', '')[:50]
        domain = item.get('source_domain', '')
        link = item.get('link', '')[:80]
        
        if status == "trying":
            self.sections.append(f"\n**Cluster {cluster_idx}:** Trying `{domain}`")
            self.sections.append(f"- Title: {title}...")
            self.sections.append(f"- URL: {link}")
        elif status == "rejected":
            self.sections.append(f"- ❌ **Rejected:** {reason}")
        elif status == "accepted":
            self.sections.append(f"- ✅ **Accepted:** {reason}")
    
    def add_final_summary(self, feed):
        """Log final feed summary."""
        if not self.enabled:
            return
        self.add_section("6. Final Feed Summary")
        self.sections.append(f"**Total articles:** {len(feed)}\n")
        
        if feed:
            self.sections.append("| # | Title | Domain | Cluster Size | Content Len | IAB Code | Products | Brands |")
            self.sections.append("|---|-------|--------|--------------|-------------|----------|----------|--------|")
            for i, article in enumerate(feed, 1):
                title = article.get('title', '')[:40].replace('|', '\\|')
                domain = article.get('source_domain', '')
                cluster_size = article.get('cluster_size', 1)
                content_len = len(article.get('content', ''))
                iab_code = ", ".join(article.get('iab_code', []))
                products = ", ".join(article.get('products', []))
                brands = ", ".join(article.get('brands', []))
                self.sections.append(f"| {i} | {title}... | {domain} | {cluster_size} | {content_len} | {iab_code} | {products} | {brands} |")
        
        # Add timing
        elapsed = datetime.now() - self.start_time
        self.sections.append(f"\n**Elapsed time:** {elapsed.total_seconds():.1f} seconds")

    def add_validation_stats(self, stats, samples):
        """Log article validation statistics and samples of discarded items."""
        if not self.enabled:
            return
        self.add_section("5. Article Validation Stats")
        
        total_discarded = sum(stats.values())
        self.sections.append(f"**Total articles discarded during validation:** {total_discarded}\n")
        
        self.sections.append("| Reason | Count |")
        self.sections.append("|--------|-------|")
        for reason, count in stats.items():
            self.sections.append(f"| {reason} | {count} |")
        
        if samples:
            self.sections.append("\n### Sample Discarded Articles (First 3)")
            self.sections.append("| # | Title | Domain | Reason |")
            self.sections.append("|---|-------|--------|--------|")
            for i, sample in enumerate(samples, 1):
                title = sample.get('title', '')[:50].replace('|', '\\|')
                domain = sample.get('domain', '')
                reason = sample.get('reason', '')
                self.sections.append(f"| {i} | {title}... | {domain} | {reason} |")
        self.sections.append("")
    
    def save(self):
        """Save the debug log to a markdown file."""
        if not self.enabled:
            return

        filename = LOCAL_OUTPUT_PATH/f"debug+{self.cluster_id}.md"
        content = "\n".join(self.sections)

        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"\n📝 Debug log saved to {filename}")


# Global debug logger instance
debug_logger = None

# Configuration
FEED_SUMMARY_API_URL = "https://ih7irzgcn7.execute-api.eu-west-1.amazonaws.com/prod/feedsummary"
LOCAL_OUTPUT_PATH = Path("../local_output")


# =============================================================================
# LOCALIZATION SETTINGS
# =============================================================================
GEO = "IT"
LOCALE = "IT"

# Domain mappings for geographic regions
GEO_DOMAINS = {
    "IT": [".it"],
    "FR": [".fr"],
    "ES": [".es"],
    "EN": [".com", ".uk", ".us", ".org"],
    "EU": [".it", ".de", ".fr", ".es", ".nl", ".be", ".at", ".pt", ".pl", ".eu"],
    "US": [".com", ".us", ".org"],
    "GLOBAL": []
}

# Language codes for search
LOCALE_LANGUAGES = {
    "IT": "italiano",
    "EN": "english",
    "DE": "deutsch",
    "FR": "français",
    "ES": "español"
}

# =============================================================================
# DATA LOADING
# =============================================================================

def load_iab_taxonomy(locale="IT"):
    """
    Loads IAB taxonomy from JSON file with cluster structure.
    """
    filepath = f"iab_taxonomy_{locale.lower()}.json"
    clusters = {}
    keywords = {}
    freshness_filter = {}
    top_sources_only_filter = {}
    iab_to_cluster = {}

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            for cluster in data.get("clusters", []):
                cluster_id = cluster.get("cluster_id")
                if cluster_id is not None:
                    clusters[cluster_id] = {
                        "cluster_name": cluster.get("cluster_name", ""),
                        "cluster_description": cluster.get("cluster_description", ""),
                        "cluster_icon": cluster.get("cluster_icon", ""),
                        "categories": cluster.get("categories", [])
                    }

                    # Process each category in the cluster
                    for category in cluster.get("categories", []):
                        iab_code = category.get("iab_code")
                        if iab_code:
                            # Store keywords
                            keywords[iab_code] = category.get("iab_keywords", [])
                            # Store freshness filter
                            freshness_filter[iab_code] = category.get("freshness", False)
                            # Store top sources only filter
                            top_sources_only_filter[iab_code] = category.get("top_sources_only", False)
                            # Map IAB code to cluster ID
                            iab_to_cluster[iab_code] = cluster_id

    except FileNotFoundError:
        print(f"⚠️ IAB taxonomy file not found: {filepath}")
    except json.JSONDecodeError:
        print(f"⚠️ Invalid JSON in: {filepath}")
    return clusters, keywords, freshness_filter, top_sources_only_filter, iab_to_cluster

def load_top_sources(locale="IT"):
    """
    Loads preferred sources by IAB category and blocked domains.
    """
    filepath = f"top_sources_{locale.lower()}.json"
    sources = {}
    blocked_domains = []
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            for category in data.get("categories", []):
                iab_code = category.get("iab_code", "")
                sites = category.get("sites", [])
                if iab_code and sites:
                    sources[iab_code] = sites
            
            # Load blocked domains
            blocked_domains = data.get("blocked_domains", [])
    except FileNotFoundError:
        print(f"⚠️ Top sources file not found: {filepath}")
    except json.JSONDecodeError:
        print(f"⚠️ Invalid JSON in: {filepath}")
    return sources, blocked_domains

# =============================================================================
# DATA LOADING
# =============================================================================

# =============================================================================
# NEWS EXTRACTION
# =============================================================================

def extract_news_from_page(url, base_domain=None, must_be_fresh=False, is_citation=False):
    """
    Extracts individual news items from an aggregated page.
    Returns list of dicts: [{title, link, snippet}, ...]
    """
    news_items = []
    
    try:
        response = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        if response.status_code != 200:
            return news_items
            
        soup = BeautifulSoup(response.content, 'html.parser')

        # 1. If this is a direct citation (not a home page), check if the page itself is an article
        if is_citation:
            # Extract title
            article_title = ""
            title_tag = soup.find('meta', property='og:title') or soup.find('h1')
            if title_tag:
                article_title = title_tag.get('content') if title_tag.name == 'meta' else title_tag.get_text(strip=True)
            
            # Extract date
            article_date = ""
            date_tags = [
                ('meta', {'property': 'article:published_time'}),
                ('meta', {'property': 'og:article:published_time'}),
                ('meta', {'name': 'pubdate'}),
                ('meta', {'name': 'publishdate'}),
                ('meta', {'name': 'date'}),
                ('meta', {'itemprop': 'datePublished'}),
                ('time', {'itemprop': 'datePublished'}),
                ('time', {}),
            ]
            for tag, attrs in date_tags:
                elem = soup.find(tag, attrs)
                if elem:
                    date_val = elem.get('content') or elem.get('datetime') or elem.get_text(strip=True)
                    if date_val and len(date_val) >= 10:
                        article_date = date_val[:10]
                        break
            
            # Check for content length
            # Use a simplified check: length of text in main areas
            content_elem = soup.find('article') or soup.find('div', class_=re.compile(r'article-body|article-content|entry-content|post-content', re.I))
            content_len = 0
            if content_elem:
                content_len = len(content_elem.get_text(strip=True))
            else:
                # Fallback: text length excluding nav/footer (which we'll decompose later)
                # For now just use a copy to calculate length before decomposition
                temp_soup = BeautifulSoup(response.content, 'html.parser')
                for noise in temp_soup.find_all(['nav', 'footer', 'aside', 'form', 'header']):
                    noise.decompose()
                content_len = len(temp_soup.get_text(strip=True))
                
            if article_title and article_date and content_len > 1000:
                is_recent, _ = is_date_recent(article_date, 0 if must_be_fresh else 10)
                if is_recent:
                    news_items.append({
                        'title': article_title[:200],
                        'link': url,
                        'snippet': "", # Will be filled if selected
                        'source_domain': get_domain(url)
                    })
                    # print(f"      ✨ Page itself is a valid article: {article_title[:50]}...")
        
        # REMOVE NOISY AREAS: footer, nav, aside, sidebar
        for noise in soup.find_all(['nav', 'footer', 'aside', 'form', 'header']):
            noise.decompose()
        
        # Remove common sidebar/menu classes
        for div in soup.find_all('div', class_=re.compile(r'sidebar|menu|footer|nav|social|ad-|widget|header', re.I)):
            div.decompose()
            
        base_domain = base_domain or get_domain(url)
        # Clean base_domain to be just the domain part if it's a path (e.g., repubblica.it/scuola)
        if '/' in base_domain:
            base_domain = base_domain.split('/')[0]
        if base_domain.startswith('www.'):
            base_domain = base_domain[4:]
        
        seen_titles = set()
        seen_links = set()
        
        # Add already extracted self-citation to seen sets to avoid duplicates
        for item in news_items:
            seen_titles.add(normalize_text(item['title']))
            seen_links.add(item['link'])
        
        # Strategy 1: Find all links with substantial text (likely article titles)
        # Prioritize <a> inside headings or with article-like classes
        selectors = [
            'h1 a', 'h2 a', 'h3 a', 'h4 a',
            'article a', 'div.article a', 'div.post a', 'div.story a', 'div.content a'
        ]
        
        found_links = []
        for selector in selectors:
            found_links.extend(soup.select(selector))
            
        # Add general links as fallback
        found_links.extend(soup.find_all('a', href=True))
        
        for a in found_links:
            link = a.get('href', '')
            if not link or link.startswith('#') or link.startswith('javascript'):
                continue
            
            # Get link text
            title = a.get_text(strip=True)
            
            # Skip short titles or navigation links
            if not title or len(title) < 20 or len(title) > 250:
                continue
            
            # Skip common navigation patterns
            skip_patterns = ['leggi tutto', 'read more', 'continua', 'scopri', 'vedi tutti', 
                           'cookie', 'privacy', 'login', 'registrati', 'contatti', 'about',
                           'home', 'menu', 'cerca', 'search', 'abbonati', 'accedi']
            if any(p in title.lower() for p in skip_patterns):
                continue
            
            # Normalize and check for duplicates
            title_normalized = normalize_text(title)
            if title_normalized in seen_titles or len(title_normalized) < 15:
                continue
            
            # Make absolute URL
            if not link.startswith('http'):
                link = urljoin(url, link)
            
            # Skip external links (social, ads, etc.) - must be on the same domain
            link_domain = get_domain(link)
            if link_domain and link_domain != base_domain:
                continue
            
            if link in seen_links:
                continue
            
            # Skip non-article URLs
            if any(ext in link.lower() for ext in ['.jpg', '.png', '.pdf', '.mp4', '.mp3', '/tag/', '/category/']):
                continue

            # Skip URLs that look truncated (end with letter/number without proper extension)
            # This helps avoid extracting incomplete URLs from home pages
            if not any(link.endswith(ext) for ext in ['.html', '.shtml', '.php', '.asp', '/']) and not link.endswith(('/', '?')):
                # Additional check: if URL path ends with a letter (not number), likely truncated
                from urllib.parse import urlparse
                parsed = urlparse(link)
                path_parts = parsed.path.strip('/').split('/')
                if path_parts and path_parts[-1] and not path_parts[-1][-1].isdigit() and len(path_parts[-1]) < 20:
                    # Looks like a truncated slug, skip it
                    continue
            
            seen_titles.add(title_normalized)
            seen_links.add(link)
            
            # Try to find snippet near the link
            snippet = ""
            parent = a.parent
            for _ in range(4):  # Go up 4 levels
                if parent:
                    # Look for sibling or child p/div with text
                    p = parent.find('p') or parent.find('div', class_=re.compile(r'summary|snippet|desc', re.I))
                    if p:
                        snippet = p.get_text(strip=True)
                        if snippet and len(snippet) > 40:
                            break
                    parent = parent.parent
            
            news_items.append({
                'title': title[:200],
                'link': link,
                'snippet': snippet[:500] if snippet else "",
                'source_domain': link_domain or base_domain
            })
            
            if len(news_items) >= 40:  # Increased limit per page
                break
                    
    except Exception as e:
        print(f"   ⚠️ Error extracting from {url[:50]}: {e}")
    
    return news_items

# =============================================================================
# CLUSTERING
# =============================================================================

def is_valid_news_title(title, iab_keywords=None):
    """
    Checks if a title looks like a real news headline.
    Filters out navigation, login, utility pages, etc.
    Optionally checks relevance to IAB category keywords.
    """
    if not title:
        return False
    
    title_lower = title.lower()
    
    # Skip patterns that indicate non-news content
    skip_patterns = [
        'password', 'login', 'registra', 'accedi', 'iscriviti',
        'cookie', 'privacy', 'termini', 'condizioni',
        'contatti', 'about', 'chi siamo', 'redazione',
        'pubblicità', 'advertising', 'newsletter',
        'archivio', 'categori',
        'cerca', 'search', 'risultati ricerca',
        'home page', 'homepage', 'menu',
        'seguici', 'social', 'facebook', 'twitter', 'instagram',
        'copyright', 'tutti i diritti', 'all rights',
        'scopri di più', 'leggi tutto', 'read more', 'continua a leggere',
        'vedi tutti', 'mostra tutto', 'visualizza',
        'comunicati', 'press release',
        # Promotional content
        'offerta', 'promo', 'sconto', 'gratis', 'abbonamento', 'abbonati',
        'prova gratuita', 'trial', 'decoder', 'smart tv', 'sky glass', 'sky stream',
        # Unrelated content
        'lotto', 'superenalotto', 'estrazion', 'jackpot',
        'oroscopo', 'meteo', 'previsioni tempo',
        'ricetta', 'ricette',
    ]
    
    if any(pattern in title_lower for pattern in skip_patterns):
        return False
    
    # Title should have some meaningful words
    words = [w for w in title.split() if len(w) > 2]
    if len(words) < 3:
        return False
    
    return True

def is_relevant_to_iab(title, iab_code, iab_keywords):
    """
    Checks if a title is relevant to the given IAB category.
    Keywords are loaded from iab-taxonomy.json.
    """
    keywords = iab_keywords.get(iab_code, [])
    if not keywords:
        return True  # No keywords defined, accept all
    
    title_lower = title.lower()
    
    # Check for direct keyword matches
    if any(kw in title_lower for kw in keywords):
        return True
        
    # RELAXED RULES FOR HIGH-QUALITY TITLES:
    # If the title is descriptive enough (more than 10 words), 
    # we can be more lenient to avoid scarting good articles.
    words = title_lower.split()
    if len(words) >= 12:
        return True
        
    return False

def cluster_news_by_similarity(news_items, iab_code=None, iab_keywords=None, similarity_threshold=0.25):
    """
    Clusters news items by topic similarity.
    Returns list of clusters, where each cluster is a list of news items.
    """
    if not news_items:
        return []
    
    iab_keywords = iab_keywords or {}
    
    # First, filter out non-news items
    valid_items = []
    for item in news_items:
        title = item.get('title', '')
        if not is_valid_news_title(title):
            continue
        # Check IAB relevance if code is provided (ELIMINATO per specifica summary-logic.md)
        # if iab_code and not is_relevant_to_iab(title, iab_code, iab_keywords):
        #    continue
        valid_items.append(item)
    
    if not valid_items:
        return []
    
    clusters = []
    used = set()
    
    for i, item in enumerate(valid_items):
        if i in used:
            continue
        
        # Start new cluster with this item
        cluster = [item]
        used.add(i)
        
        # Find similar items
        for j, other in enumerate(valid_items):
            if j in used:
                continue
            
            # Calculate similarity based on title + snippet
            text1 = item['title'] + " " + item.get('snippet', '')
            text2 = other['title'] + " " + other.get('snippet', '')
            similarity = calculate_similarity(text1, text2)
            
            if similarity >= similarity_threshold:
                cluster.append(other)
                used.add(j)
        
        clusters.append(cluster)
    
    # Sort clusters by size (most covered topics first)
    clusters.sort(key=len, reverse=True)
    
    return clusters

# =============================================================================
# SOURCE SELECTION
# =============================================================================

def select_best_source(cluster, iab_code, top_sources):
    """
    Selects the best URL from a cluster.
    Prefers sources from top-sources.json for the given IAB category.
    """
    if not cluster:
        return None
    
    preferred_domains = top_sources.get(iab_code, [])
    
    # First, try to find a URL from preferred sources
    for item in cluster:
        domain = item.get('source_domain', '')
        for preferred in preferred_domains:
            # Check if domain matches (partial match for subdomains)
            if preferred in domain or domain in preferred:
                return item
    
    # If no preferred source found, return the first item (or random)
    return cluster[0]

# =============================================================================
# SEARCH
# =============================================================================

def extract_citations_from_home_pages(preferred_sites, iab_code, max_per_site=5):
    """
    Extracts news citations directly from top sources home pages.
    Returns list of URLs found on the home pages.
    """
    home_citations = []
    processed_sites = 0

    print(f"   🏠 DEBUG: Starting extraction from {len(preferred_sites)} preferred sites")

    for site in preferred_sites[:8]:  # Limit to first 8 preferred sites
        try:
            # Construct home page URL
            if not site.startswith('http'):
                home_url = f"https://{site}"
            else:
                home_url = site

            print(f"   🏠 Scanning home page: {site} -> {home_url}")

            # Extract news items from home page
            news_items = extract_news_from_page(home_url, base_domain=site, is_citation=False)

            # Convert news items to URLs and limit per site
            site_urls = [item['link'] for item in news_items[:max_per_site]]

            home_citations.extend(site_urls)
            processed_sites += 1

            print(f"      ✅ Found {len(site_urls)} news links from {site}")

            # Debug: Log first few URLs
            for i, url in enumerate(site_urls[:2]):
                print(f"         {i+1}. {url[:80]}...")

        except Exception as e:
            print(f"      ❌ Error scanning {site}: {str(e)}")
            import traceback
            print(f"      ❌ Traceback: {traceback.format_exc()}")

    print(f"   📄 Home pages scanned: {processed_sites}/{len(preferred_sites)} sites, {len(home_citations)} total citations")
    return home_citations


def filter_citations(citations, blocked_domains=None):
    """
    Filters out unwanted URLs from citations:
    - Video content (URLs containing 'video', YouTube, Vimeo)
    - Live/real-time content (diretta, live, tempo reale)
    - Blocked domains from top-sources.json
    Returns tuple: (filtered_citations, removed_citations)
    """
    # Patterns to exclude
    video_patterns = [
        '/video/', '/video-', '-video', 'video.',
        'youtube.com', 'youtu.be', 'vimeo.com',
        'dailymotion.com', '/watch/', '/embed/'
    ]
    
    live_patterns = [
        '/diretta/', '-diretta', 'diretta-', '/live/',
        '-live', 'live-', '/tempo-reale/', 'real-time',
        '/liveblog/', 'live-blog', '/minuto-per-minuto/'
    ]
    
    all_patterns = video_patterns + live_patterns
    
    filtered = []
    removed = []
    
    blocked_domains = blocked_domains or []
    
    for url in citations:
        url_lower = url.lower()
        domain = get_domain(url).lower()
        
        # Check if URL matches any exclusion pattern
        is_video_or_live = any(pattern in url_lower for pattern in all_patterns)
        
        # Check if domain matches any blocked domain
        # Support both exact match and subdomain match:
        # - it.marketscreener.com matches it.marketscreener.com
        # - it.marketscreener.com matches marketscreener.com
        # - fr.marketscreener.com matches marketscreener.com
        is_blocked_domain = False
        matched_blocked = None
        for blocked in blocked_domains:
            blocked_lower = blocked.lower()
            # Check exact match or if domain ends with blocked domain
            if domain == blocked_lower or domain.endswith('.' + blocked_lower) or blocked_lower in domain:
                is_blocked_domain = True
                matched_blocked = blocked
                break
        
        if is_video_or_live or is_blocked_domain:
            if is_video_or_live:
                reason = "video/live"
            else:
                reason = f"blocked domain ({matched_blocked})"
            removed.append((url, reason))
        else:
            filtered.append(url)
    
    return filtered, removed


def search_news(iab_code, iab_description, max_results=10, geo=None, locale=None):
    """
    Searches for news using IAB category.
    Returns raw search results (including aggregated pages).
    """
    global debug_logger
    #from openai import OpenAI
    
    geo = geo or GEO
    locale = locale or LOCALE

    
    # Load top sources, keywords and blocked domains for the specific locale
    top_sources, blocked_domains = load_top_sources(locale)
    preferred_sites = top_sources.get(iab_code, [])

    # Load keywords for the IAB category from the specific locale taxonomy
    _, iab_keywords, _, _, _ = load_iab_taxonomy(locale)
    keywords = iab_keywords.get(iab_code, [])
    
    # Select top keywords (already localized in the json file)
    selected_keywords = keywords[:5]
    
    # Build search query based on locale
    keywords_str = ", ".join(selected_keywords) if selected_keywords else ""
    
    if locale == "IT":
        query = f"{iab_description} {keywords_str} ultime notizie oggi Italia"
    elif locale == "ES":
        query = f"{iab_description} {keywords_str} últimas noticias hoy España"
    elif locale == "FR":
        query = f"{iab_description} {keywords_str} dernières actualités aujourd'hui France"
    else:
        query = f"{iab_description} {keywords_str} latest news today"

    if preferred_sites:
        # Add some preferred sites to the query to guide Perplexity
        sites_hint = " OR ".join([f"site:{s}" for s in preferred_sites[:3]])
        query = f"({query}) ({sites_hint})"
    
    print(f"🔍 Searching IAB {iab_code} (Locale: {locale}): {iab_description}")
    print(f"   Keywords: {', '.join(selected_keywords) if selected_keywords else 'none'}")
    print(f"   Query: {query[:100]}...")
    
    # client = OpenAI(api_key=PPLX_API_KEY, base_url="https://api.perplexity.ai")
    
    # Dynamic System Prompt based on locale
    prompts = {
        "IT": {
            "role": "Sei un aggregatore di notizie professionale.",
            "task": f"Trova le {max_results} migliori fonti web italiane che riportano NOTIZIE RECENTI e approfondite su: {iab_description}.",
            "rules": [
                "Fornisci un mix di Home page/Pagine di sezione e Articoli diretti.",
                f"Donnez la priorité à queste fonti: {', '.join(preferred_sites[:5]) if preferred_sites else 'testate giornalistiche autorevoli'}.",
                "Escludi categoricamente: video, social media, forum, annunci e link di servizio.",
                "Restituisci SOLO gli URL diretti."
            ]
        },
        "ES": {
            "role": "Eres un agregador de noticias profesional.",
            "task": f"Encuentra las {max_results} mejores fuentes web españolas que informen sobre NOTICIAS RECIENTES y detalladas sobre: {iab_description}.",
            "rules": [
                "Proporciona una mezcla de páginas de inicio/sección y artículos directos.",
                f"Da prioridad a estas fuentes: {', '.join(preferred_sites[:5]) if preferred_sites else 'medios de comunicación autorizados'}.",
                "Excluye categóricamente: videos, redes sociales, foros, anuncios y enlaces de servicio.",
                "Devuelve SOLO las URL directas."
            ]
        },
        "FR": {
            "role": "Vous êtes un agrégateur de nouvelles professionnel.",
            "task": f"Trouvez les {max_results} meilleures sources web françaises rapportant des NOUVELLES RÉCENTES et approfondies sur : {iab_description}.",
            "rules": [
                "Fournissez un mélange de pages d'accueil/section et d'articles directs.",
                f"Donnez la priorité à ces sources : {', '.join(preferred_sites[:5]) if preferred_sites else 'médias d’information faisant autorité'}.",
                "Excluez catégoriquement : vidéos, médias sociaux, forums, annonces et liens de service.",
                "Renvoyez UNIQUEMENT les URL directes."
            ]
        },
        "EN": {
            "role": "You are a professional news aggregator.",
            "task": f"Find the {max_results} best web sources reporting RECENT and in-depth news specifically about: {iab_description}.",
            "rules": [
                "Provide a mix of Section/aggregation pages and Direct in-depth articles.",
                f"Prioritize these sources: {', '.join(preferred_sites[:5]) if preferred_sites else 'authoritative news outlets'}.",
                "Categorically exclude: videos, social media, forums, and service links.",
                "Return ONLY the direct URLs."
            ]
        }
    }

    p = prompts.get(locale, prompts["EN"])
    system_prompt = f"{p['role']} {p['task']}\n\nREGOLE DI SELEZIONE:\n" + \
                    "\n".join([f"{i+1}. {rule}" for i, rule in enumerate(p['rules'])])
    
    # Log query to debug
    if debug_logger:
        debug_logger.add_query(query, system_prompt, selected_keywords)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]
    

    """
    response = client.chat.completions.create(
        model="sonar",
        messages=messages
    )
    """
    import os
    from openrouter_client import OpenRouterClient
    api_key = os.getenv("OPENROUTER_API_KEY")
    or_client = OpenRouterClient(
        api_key=api_key,
        x_title="advantage-bai-feed-summary",
    )
    response = or_client.chat_completions(
            model="perplexity/sonar",
            messages=messages,
        temperature=0.1,
        )
    content=response["choices"][0]["message"]["content"]
    print("Sonar from OpenRouter response: ",content)

    """
    response = or_client.chat_completions.create(
        model="sonar",
        messages=messages
    )
    content = response.choices[0].message.content
    """
    raw_citations = getattr(response, 'citations', []) or []

    print(f"   🤖 Perplexity returned {len(raw_citations)} citations")

    # Extract additional citations from home pages of preferred sites
    print(f"   🏠 Extracting citations from {len(preferred_sites)} preferred home pages...")
    try:
        home_citations = extract_citations_from_home_pages(preferred_sites, iab_code)
        print(f"   ✅ Home page extraction completed: {len(home_citations)} citations")
    except Exception as e:
        print(f"   ❌ Error in home page extraction: {e}")
        import traceback
        print(f"      {traceback.format_exc()}")
        home_citations = []

    # Combine Perplexity citations with home page citations
    all_raw_citations = raw_citations + home_citations

    # Remove duplicates
    all_raw_citations = list(set(all_raw_citations))

    print(f"   📊 Total citations before filtering: {len(all_raw_citations)} (Perplexity: {len(raw_citations)}, Home pages: {len(home_citations)})")

    # Filter out video, live and blocked URLs
    citations, removed_citations = filter_citations(all_raw_citations, blocked_domains)
    
    if removed_citations:
        print(f"   ⚠️ Filtered out {len(removed_citations)} video/live/blocked URLs")
    
    # Log citations to debug (both filtered and removed)
    if debug_logger:
        debug_logger.add_citations(citations, removed_citations)
    
    return {
        "content": content,
        "citations": citations
    }

# =============================================================================
# MAIN PIPELINE
# =============================================================================

def generate_feed(cluster_id, max_results=10, geo=None, locale=None, upto_step=None, min_len_multi=1000, min_len_single=1000):
    """
    Generates a news feed using the new aggregation strategy:
    1. Search for pages across all categories in the cluster
    2. Extract individual news from each page
    3. Cluster by topic similarity
    4. Select best source for each cluster
    5. Fetch full article content
    """
    global debug_logger
    geo = geo or GEO
    locale = locale or LOCALE

    # Load taxonomy (with clusters, keywords and freshness filter) and top sources for the specific locale
    clusters, iab_keywords, freshness_filters, top_sources_only_filters, iab_to_cluster = load_iab_taxonomy(locale)
    top_sources, blocked_domains = load_top_sources(locale)

    # Get cluster info
    cluster_info = clusters.get(cluster_id)
    if not cluster_info:
        print(f"❌ Cluster {cluster_id} not found")
        return []

    cluster_name = cluster_info["cluster_name"]
    cluster_description = cluster_info["cluster_description"]
    categories = cluster_info["categories"]

    # Initialize debug header
    if debug_logger:
        debug_logger.add_header(cluster_name, cluster_description)
    
    print(f"\n{'='*60}")
    print(f"📰 Generating feed for Cluster {cluster_id}: {cluster_name} (Locale: {locale})")
    print(f"   Description: {cluster_description}")
    print(f"   Categories: {len(categories)}")
    print(f"{'='*60}\n")

    # Determine if any category in the cluster requires freshness filtering
    must_be_fresh = any(freshness_filters.get(cat.get("iab_code"), False) for cat in categories)

    # Step 1: Search for pages across all categories in the cluster
    all_citations = []
    print("🔍 Searching across all categories in the cluster...")

    # --- HISTORICAL CORRELATION (Last 2-3 days) ---
    # We add a search for recent past news to enrich the context
    historical_days = 3
    # ----------------------------------------------

    for category in categories:
        iab_code = category.get("iab_code")
        iab_description = category.get("iab_description")
        top_sources_only = top_sources_only_filters.get(iab_code, False)

        print(f"\n   📋 Processing category: {iab_code} - {iab_description}")
        
        # Search for today's news
        search_result = search_news(iab_code, iab_description, max_results=max_results//len(categories) + 1, geo=geo, locale=locale)
        category_citations = search_result.get("citations", [])

        # Search for historical news (last 3 days) to provide depth
        if not must_be_fresh:
            print(f"      ⏳ Searching historical news (last {historical_days} days)...")
            hist_query = f"{iab_description} news last {historical_days} days"
            hist_result = search_news(iab_code, hist_query, max_results=3, geo=geo, locale=locale)
            category_citations.extend(hist_result.get("citations", []))

        if top_sources_only:
            allowed_sites = top_sources.get(iab_code, [])
            
            # 1. Prepend home page URLs of allowed sites to ensure they are scanned directly
            home_urls = []
            for site in allowed_sites:
                clean_site = site.lower().strip()
                if not clean_site.startswith('http'):
                    # standardizing to https://www.
                    url = f"https://www.{clean_site}" if not clean_site.startswith('www.') else f"https://{clean_site}"
                else:
                    url = clean_site
                home_urls.append(url)
            
            # Combine: Home pages first, then search citations
            category_citations = home_urls + category_citations

            filtered_category_citations = []
            for url in category_citations:
                domain = get_domain(url).lower()
                # Check if domain matches any allowed site
                # allowed_sites might contain "gazzetta.it" which should match "www.gazzetta.it"
                if any(site.lower() in domain or domain in site.lower() for site in allowed_sites):
                    filtered_category_citations.append(url)
                else:
                    print(f"      🚫 Filtering citation (not a top source): {domain}")
            
            if len(filtered_category_citations) < len(category_citations):
                print(f"      ⚠️ Filtered out {len(category_citations) - len(filtered_category_citations)} non-top-source citations")
            category_citations = filtered_category_citations

        print(f"      Found {len(category_citations)} citations")
        all_citations.extend(category_citations)

    # Remove duplicates while preserving order
    seen = set()
    citations = []
    for citation in all_citations:
        if citation not in seen:
            seen.add(citation)
            citations.append(citation)

    print(f"\n📄 Total citations after deduplication: {len(citations)} (from {len(all_citations)} raw)")
    
    if upto_step == 1:
        print("\n🛑 Stopping after Step 1 (Search citations)")
        return []
    
    if not citations:
        print("❌ No search results found")
        return []
    
    print(f"\n📄 Found {len(citations)} source pages")
    
    # Step 2: Extract news from each page
    if debug_logger:
        debug_logger.add_section("3. News Extraction by Source")
    
    MIN_ITEMS_THRESHOLD = 10  # If less than this, try parent URL
    all_news_raw = []
    
    for i, url in enumerate(citations[:10]):  # Process up to 10 pages
        print(f"\n🔗 [{i+1}] Extracting from: {url[:60]}...")
        news_items = extract_news_from_page(url, must_be_fresh=must_be_fresh, is_citation=True)
        print(f"   Found {len(news_items)} news items")
        
        # Log extraction to debug
        if debug_logger:
            debug_logger.add_extraction(url, news_items)
        
        # If less than threshold items, try parent URL
        if len(news_items) < MIN_ITEMS_THRESHOLD:
            parent_url = get_parent_url(url)
            if parent_url and parent_url != url:
                print(f"   ↑ Trying parent URL: {parent_url[:60]}...")
                parent_items = extract_news_from_page(parent_url, must_be_fresh=must_be_fresh, is_citation=False)
                
                # Only add items not already found
                existing_links = {item['link'] for item in news_items}
                new_items = [item for item in parent_items if item['link'] not in existing_links]
                
                print(f"   Found {len(new_items)} additional items from parent")
                
                if debug_logger and new_items:
                    debug_logger.add_extraction(f"{parent_url} (parent)", new_items)
                
                news_items.extend(new_items)
        
        all_news_raw.extend(news_items)
    
    # Deduplicate all_news by URL (Fix Punto 1)
    seen_urls = set()
    all_news = []
    for item in all_news_raw:
        url = item.get('link')
        if url and url not in seen_urls:
            seen_urls.add(url)
            all_news.append(item)
            
    print(f"\n📊 Total news items extracted: {len(all_news_raw)} (Deduplicated: {len(all_news)})")
    
    if upto_step == 2:
        print("\n🛑 Stopping after Step 2 (Extract news from pages)")
        return []
    
    if not all_news:
        print("❌ No news items extracted")
        return []
    
    # Step 3: Cluster by similarity (with IAB relevance filter)
    print("\n🔄 Clustering by topic similarity...")
    clusters = cluster_news_by_similarity(all_news, iab_code=iab_code, iab_keywords=iab_keywords, similarity_threshold=0.25)
    print(f"   Created {len(clusters)} topic clusters")
    
    # Calculate filtered count for debug
    filtered_count = sum(len(c) for c in clusters)
    if debug_logger:
        debug_logger.add_clustering(clusters, filtered_count, len(all_news))
    
    # Show cluster info
    for i, cluster in enumerate(clusters[:10]):
        print(f"   Cluster {i+1}: {len(cluster)} items - \"{cluster[0]['title'][:50]}...\"")
    
    if upto_step == 3:
        print("\n🛑 Stopping after Step 3 (Clustering)")
        return []
    
    # Step 4: Source selection & Summary Generation
    if debug_logger:
        debug_logger.add_section("5. Source Selection & AI Summary")
    
    print("\n🎯 Processing clusters for AI summary...")
    final_feed = []
    cluster_idx = 0
    
    # Stats for validation
    discard_stats = {"length": 0, "no_date": 0, "old_date": 0}
    discarded_samples = []

    def track_discard(title, domain, reason):
        discard_stats[reason] = discard_stats.get(reason, 0) + 1
        if len(discarded_samples) < 3:
            discarded_samples.append({"title": title, "domain": domain, "reason": reason})

    # Split clusters by size (Fix Punto 2)
    multi_article_clusters = [c for c in clusters if len(c) >= 2]
    single_article_clusters = [c for c in clusters if len(c) == 1]
    
    # Pass 1: Multi-article clusters
    print(f"   Pass 1: Processing {len(multi_article_clusters)} clusters with >= 2 articles")
    for cluster in multi_article_clusters:
        if len(final_feed) >= max_results:
            break
        
        cluster_idx += 1
        
        # Sort cluster by priority: preferred sources first
        ref_iab_code = categories[0].get("iab_code") if categories else None
        preferred_domains = top_sources.get(ref_iab_code, [])
        
        def get_priority(item):
            domain = item.get('source_domain', '')
            for pref in preferred_domains:
                if pref in domain or domain in pref:
                    return 0
            return 1
            
        sorted_cluster = sorted(cluster, key=get_priority)
        
        validated_articles = []
        first_valid_image = None
        
        print(f"   [{cluster_idx}] Topic: \"{sorted_cluster[0]['title'][:50]}...\" ({len(sorted_cluster)} sources)")
        
        for item in sorted_cluster:
            if len(validated_articles) >= 5:
                break
            article = fetch_article_content(item['link'])
            if not article['title']:
                article['title'] = item['title']
            if not article['content']:
                article['content'] = item.get('snippet', '')
            
            content_length = article.get('content_text_length', len(article.get('content', '')))
            if content_length < min_len_multi: 
                track_discard(article['title'], article['source_domain'], "length")
                continue
                
            pub_date = article.get('published_date', '')
            if not pub_date: 
                track_discard(article['title'], article['source_domain'], "no_date")
                continue

            max_days = 0 if must_be_fresh else 10
            date_is_recent, _ = is_date_recent(pub_date, max_days)
            if not date_is_recent: 
                track_discard(article['title'], article['source_domain'], "old_date")
                continue
            
            if not first_valid_image and article.get('image') and 'placeholder' not in article['image'].lower():
                first_valid_image = article['image']
            
            validated_articles.append(article)

        if validated_articles:
            summary_response = call_feed_summary_api(validated_articles, cluster_id, locale=locale)
            if summary_response:
                feed_item = {
                    "title": summary_response.get("title", ""),
                    "subtitle": summary_response.get("subtitle", ""),
                    "content": summary_response.get("summary", ""),
                    "image": first_valid_image or "https://via.placeholder.com/300x200?text=No+Image",
                    "published_date": datetime.now().strftime("%Y-%m-%d"),
                    "author": "",
                    "cluster_size": len(validated_articles),
                    "source_domain": [art.get('source_domain', '') for art in validated_articles],
                    "link": [art.get('link', '') for art in validated_articles],
                    "iab_code": summary_response.get("keywords", []),
                    "products": summary_response.get("products", []),
                    "brands": summary_response.get("brands", [])
                }
                final_feed.append(feed_item)
                print(f"       ✅ Summary generated ({len(validated_articles)} articles)")

    # Pass 2: Single-article clusters (only if less than max_results and content > min_len_single)
    if len(final_feed) < max_results and single_article_clusters:
        print(f"   Pass 2: Processing {len(single_article_clusters)} single-article clusters (need {max_results - len(final_feed)} more)")
        for cluster in single_article_clusters:
            if len(final_feed) >= max_results:
                break
            
            item = cluster[0]
            
            # --- FUZZY MATCHING FOR SINGLE SOURCE ---
            # Try to find similar articles in other single-article clusters to "merge" them
            # or find related articles from multi-article clusters to enrich the context.
            enriched_cluster = [item]
            ref_text = item['title'] + " " + item.get('snippet', '')
            
            # Look into other single clusters first
            for other_cluster in single_article_clusters:
                other_item = other_cluster[0]
                if other_item['link'] == item['link']:
                    continue
                
                other_text = other_item['title'] + " " + other_item.get('snippet', '')
                # Use a slightly lower threshold for fuzzy matching between clusters
                if calculate_similarity(ref_text, other_text) >= 0.15:
                    enriched_cluster.append(other_item)
                    print(f"       🔗 Fuzzy matched related article: {other_item['title'][:40]}...")
            
            # If we found matches, we treat it as a multi-source cluster
            if len(enriched_cluster) > 1:
                print(f"       ✨ Enriched single-source cluster into {len(enriched_cluster)} sources via fuzzy matching")
            
            validated_articles = []
            first_valid_image = None
            
            # Determine which length threshold to use
            # If enriched, we can be more lenient with individual article lengths
            current_min_len = min_len_multi if len(enriched_cluster) > 1 else min_len_single
            
            for candidate in enriched_cluster:
                if len(validated_articles) >= 5:
                    break
                article = fetch_article_content(candidate['link'])
                if not article['title']:
                    article['title'] = candidate['title']
                if not article['content']:
                    article['content'] = candidate.get('snippet', '')
                
                content_length = article.get('content_text_length', len(article.get('content', '')))
                
                if content_length < current_min_len:
                    track_discard(article['title'], article['source_domain'], "length")
                    continue
                    
                pub_date = article.get('published_date', '')
                if not pub_date: 
                    track_discard(article['title'], article['source_domain'], "no_date")
                    continue

                max_days = 0 if must_be_fresh else 10
                date_is_recent, _ = is_date_recent(pub_date, max_days)
                if not date_is_recent: 
                    track_discard(article['title'], article['source_domain'], "old_date")
                    continue
                
                if not first_valid_image and article.get('image') and 'placeholder' not in article['image'].lower():
                    first_valid_image = article['image']
                
                validated_articles.append(article)

            if validated_articles:
                # IMPORTANT: Only generate summary if we have at least 1 valid article, 
                # but the goal is to have more if fuzzy matching worked.
                summary_response = call_feed_summary_api(validated_articles, cluster_id, locale=locale)
                if summary_response:
                    feed_item = {
                        "title": summary_response.get("title", ""),
                        "subtitle": summary_response.get("subtitle", ""),
                        "content": summary_response.get("summary", ""),
                        "image": first_valid_image or "https://via.placeholder.com/300x200?text=No+Image",
                        "published_date": datetime.now().strftime("%Y-%m-%d"),
                        "author": "",
                        "cluster_size": len(validated_articles),
                        "source_domain": [art.get('source_domain', '') for art in validated_articles],
                        "link": [art.get('link', '') for art in validated_articles],
                        "iab_code": summary_response.get("keywords", []),
                        "products": summary_response.get("products", []),
                        "brands": summary_response.get("brands", [])
                    }
                    final_feed.append(feed_item)
                    print(f"       ✅ Summary generated ({len(validated_articles)} articles)")

    # Log validation stats before final summary
    if debug_logger:
        debug_logger.add_validation_stats(discard_stats, discarded_samples)

    # Log final summary
    if debug_logger:
        debug_logger.add_final_summary(final_feed)
    
    print(f"\n✅ Generated feed with {len(final_feed)} summary items")
    return final_feed, clusters

# =============================================================================
# EXECUTION
# =============================================================================

if __name__ == "__main__":
    # Parse command line arguments
    args = sys.argv[1:]
    

    # check if OPENROUTER_API_KEY is set
    if "OPENROUTER_API_KEY" not in os.environ:
        print("OPENROUTER_API_KEY is not set")
        sys.exit(1)
    else:
        print("OPENROUTER_API_KEY is present in env")
    
    # Check for -debug flag
    DEBUG_MODE = "-debug" in args
    if DEBUG_MODE:
        args.remove("-debug")
    
    # Check for --locale flag
    for arg in args[:]:
        if arg.startswith("--locale"):
            try:
                if "=" in arg:
                    LOCALE = arg.split("=")[1].upper()
                else:
                    idx = args.index(arg)
                    LOCALE = args[idx+1].upper()
                    args.remove(args[idx+1])
                args.remove(arg)
                GEO = LOCALE # Default GEO to LOCALE
            except (IndexError, ValueError):
                print(f"⚠️ Invalid --locale flag, using default {LOCALE}")
    
    # Check for -UPTO flag
    UPTO_STEP = None
    for arg in args[:]:
        if arg.startswith("-UPTO"):
            try:
                UPTO_STEP = int(arg.replace("-UPTO", ""))
                args.remove(arg)
                # Automatically enable debug mode if -UPTO is used
                DEBUG_MODE = True
            except ValueError:
                print(f"⚠️ Invalid -UPTO flag '{arg}', ignoring")
    
    # Check required arguments
    if len(args) < 1:
        print("\n❌ Missing CLUSTER_ID")
        print("Usage: python3 news-search.py <CLUSTER_ID> [MAX_RESULTS] [--locale IT|EN|FR|ES] [-debug] [-UPTO<1-3>]")
        print("Example: python3 news-search.py 5 10 --locale FR -UPTO2")
        print("Example with debug: python3 news-search.py 5 10 -debug")
        sys.exit(1)

    CLUSTER_ID = args[0]
    
    # Article length validation constants
    MIN_LEN_MULTI = 1000
    MIN_LEN_SINGLE = 1000
    
    # Optional MAX_RESULTS with default 10
    MAX_RESULTS = 10
    if len(args) >= 2:
        try:
            MAX_RESULTS = int(args[1])
        except ValueError:
            print(f"⚠️ Invalid MAX_RESULTS '{args[1]}', using default 10")
    
    # Initialize debug logger if enabled
    if DEBUG_MODE:
        debug_logger = DebugLogger(int(CLUSTER_ID), enabled=True)
        print("🐛 Debug mode enabled - will generate debug+{}.md".format(CLUSTER_ID))

    # Generate feed
    feed, clusters = generate_feed(
        cluster_id=int(CLUSTER_ID),  # Convert to int since cluster IDs are integers
        max_results=MAX_RESULTS,
        geo=GEO,
        locale=LOCALE,
        upto_step=UPTO_STEP,
        min_len_multi=MIN_LEN_MULTI,
        min_len_single=MIN_LEN_SINGLE
    )

    # Save to file only if not using -UPTO
    if UPTO_STEP is None:
        output_file = LOCAL_OUTPUT_PATH / f"feed{CLUSTER_ID}_{LOCALE.lower()}.json"
        with open(output_file, "w", encoding='utf-8') as f:
            json.dump(feed, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Saved {len(feed)} news items to {output_file}")

        # Save clusters for correlation step
        clusters_file = LOCAL_OUTPUT_PATH /f"clusters_{CLUSTER_ID}_{LOCALE.lower()}.json"
        with open(clusters_file, "w", encoding='utf-8') as f:
            json.dump(clusters, f, indent=2, ensure_ascii=False)
        print(f"📂 Saved {len(clusters)} clusters to {clusters_file}")
    else:
        print(f"\n🧪 Testing mode (-UPTO{UPTO_STEP}): skipping {CLUSTER_ID} feed generation")
    
    # Save debug log if enabled
    if debug_logger:
        debug_logger.save()
    
    # Print summary if full execution or feed generated
    if feed and UPTO_STEP is None:
        print("\n📋 Feed Summary:")
        for i, item in enumerate(feed, 1):
            coverage = item.get('cluster_size', 1)
            print(f"   {i}. [{coverage} sources] {item['title'][:60]}...")
            print(f"      → {item['source_domain']}")
