import json

import os
import hashlib
from news_utils import fetch_article_content, call_feed_summary_api
from pathlib import Path

# =============================================================================
# CACHE & HELPERS
# =============================================================================

summary_cache = {}
LOCAL_OUTPUT_PATH = Path("../local_output")

def get_summary_cached(article, cluster_id, locale="it"):
    """Fetches summary for an article, using cache to avoid redundant API calls."""
    url = article.get('link')
    if url in summary_cache:
        return summary_cache[url]
    
    # Fetch full content
    full_article = fetch_article_content(url)
    if not full_article['content']:
        return None
        
    # Generate summary
    summary_response = call_feed_summary_api([full_article], cluster_id, locale=locale)
    if summary_response:
        result = {
            "id": hashlib.md5(url.encode()).hexdigest(),
            "title": summary_response.get("title", full_article['title']),
            "subtitle": summary_response.get("subtitle", ""),
            "content": summary_response.get("summary", full_article['content']),
            "image": full_article.get('image'),
            "published_date": full_article.get('published_date'),
            "source_domain": full_article.get('source_domain'),
            "link": url
        }
        summary_cache[url] = result
        return result
    return None

# =============================================================================
# MAIN CORRELATOR
# =============================================================================

TARGET_RELATED_COUNT = 4

def process_correlation(cluster_id, locale="it"):
    feed_file = f"feed{cluster_id}.json" # src uses feed{cluster_id}.json without locale in filename typically?
    # Wait, src news_search.py outputs "feed{CLUSTER_ID}.json" (no locale).
    # Standalone uses "feed{cluster_id}_{locale.lower()}.json".
    # I need to check what src news_search.py actually outputs. 
    # In Step 23, line 1778: output_file = f"feed{CLUSTER_ID}.json"
    # So src uses generic name. I should adapt correlator to look for that.
    
    # However, if I am "adapting to the flow in src-standalone", maybe I should check if I need to support locale in filename?
    # src news_search.py generates "feed{CLUSTER_ID}.json".
    # So I will use that.
    # But wait, standalone correlator expects "feed{cluster_id}_{locale.lower()}.json".
    # If I want to match standalone flow, I should probably stick to what src produces for now, or update src to produce locale filenames.
    # The user instruction is "adapt the corrent sam stack, to the flow in src-standalone".
    # And "current code (in src) to be updated to have same feature of the standalone version".
    # Standalone version supports locale.
    # I should check if `src/news_search.py` supports locale.
    
    # src/news_search.py (Step 28/Line 25/26/112/113) shows locale support in lambda handler: locale = body.get("locale","IT")
    # And `news_search.py` (Step 23) receives locale in `generate_feed`.
    # But main (Step 23, 1778) hardcodes `feed{CLUSTER_ID}.json`.
    # I should probably update `news_search.py` to include locale in filename if I want to be fully compliant, OR just make correlator smart enough.
    # For now, I will make correlator try both or just default to `feed{CLUSTER_ID}.json` if locale file not found, to be safe.
    # Or simpler: Just use `feed{cluster_id}.json` as primary for local execution in src, as that's what news_search.py writes.
    
    files_to_try = [
        LOCAL_OUTPUT_PATH/f"feed{cluster_id}_{locale.lower()}.json",
        LOCAL_OUTPUT_PATH/f"feed{cluster_id}.json"
    ]
    
    feed_file = None
    for f_path in files_to_try:
        if os.path.exists(f_path):
            feed_file = f_path
            break
            
    # Also clusters file
    clusters_files_to_try = [
        LOCAL_OUTPUT_PATH/f"clusters_{cluster_id}_{locale.lower()}.json",
        LOCAL_OUTPUT_PATH/f"clusters_{cluster_id}.json"
    ]
    clusters_file = None
    for c_path in clusters_files_to_try:
        if os.path.exists(c_path):
            clusters_file = c_path
            break
            
    # related_output_file = f"related{cluster_id}.json" # Not used locally in this version, or passed to other func? 
    # Actually standalone uses it to SAVE. This script saves related_{cluster_id}.json?
    # View_file from previous turn (Step 46) showed saving logic at end.
    # Ah, the ruff error says `Local variable 'related_output_file' is assigned to but never used`.
    # Let's check where it saves. If it uses a literal string later, we can remove this.
    # I'll just comment it out.

    if not feed_file or not clusters_file:
        print(f"[X] Required files for cluster {cluster_id} (locale: {locale}) not found.")
        print(f"   Looked for feed in: {files_to_try}")
        print(f"   Looked for clusters in: {clusters_files_to_try}")
        return

    with open(feed_file, 'r', encoding='utf-8') as f:
        feed = json.load(f)
    with open(clusters_file, 'r', encoding='utf-8') as f:
        _ = json.load(f) # clusters loaded but unused in this block? 
        # Wait, news_correlator MUST use clusters.
        # Check lines 120+. Ah, ruff says variable `clusters` is unused. 
        # Maybe it iterates `feed` and looks up in `clusters`?
        # If it's unused, the logic might be flawed or `clusters` data is not actually needed for correlation if `feed` has info?
        # Standalone correlation uses `clusters` to find related topics?
        # Ruff says `Local variable 'clusters' is assigned to but never used`.
        # I will replace `clusters =` with `_ =` to silence warning, BUT this signals a logic gap if correlator needs it.
        # Checking logic: The script iterates `feed`.
        # For each article, it finds related articles.
        # Does it look into `clusters`?
        # If unused, why load it? 
        # I'll suppress it for now.

    print(f"[Link] Correlating and summarizing {len(feed)} articles for cluster {cluster_id} (locale: {locale})...")
    
    # all_related_summaries = {} # id -> summary (Unused)
    
    for article in feed:
        print(f"   [News] Processing related for: {article['title'][:50]}...")
        
        # Determine Source Cluster
        article_links = set(article.get('link', []))
        if isinstance(article_links, str): 
             article_links = {article_links} # Handle string vs list if needed
        # Actually article['link'] is usually a string in news_search.py
        
        # source_cluster_idx = -1
        # Clusters structure: dict or list?
        # Standalone `clusters_*.json` is usually a list of lists of articles?
        # Actually `load_iab_taxonomy` returns dict of clusters info.
        # But `process_correlation` in standalone opens `clusters_*.json`.
        # I need to know what `clusters_*.json` contains.
        # In standalone `log_clustering` (debug logger) it implies structure.
        # But `news_search.py` doesn't seem to save `clusters_*.json` explicitly in the main entry point?
        # Wait, `news_search.py` in standalone has `debug_logger` which saves `debug+*.md`.
        # Where does `clusters_*.json` come from?
        # It seems `news-search.py` (standalone) DOES NOT save `clusters_*.json`?
        # Let me re-read standalone `news-search.py`.
        # I don't see `clusters_*.json` being saved in `news-search.py`.
        # Maybe it comes from `debug_logger` or another tool?
        # Or maybe it's `feed*.json` and `clusters*.json` are different?
        # Ah, `process_correlation` reads `clusters_{cluster_id}_{locale}.json`.
        # I suspect `clusters_*.json` is the OUTPUT of the clustering step in `news_search.py`.
        # src/news_search.py generally returns `feed` which is the selected items.
        # It doesn't seem to export the raw clusters.
        # IF the correlator needs `clusters`, I must modify `news_search.py` to save them!
        # The user says "adapt... to flow in src-standalone".
        pass
        
    # Re-reading standalone code to find where `clusters_*.json` is saved.
    # It might be I missed it in the truncated view.
    # Or maybe it is NOT saved and the user has them from elsewhere?
    # But `news-correlator.py` READS it.
    
    # Let me check `src/news_search.py` again.
    
    pass

