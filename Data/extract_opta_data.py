import sys
import os

# Add the current directory (Data/) to sys.path so imports like 'import main' work
current_dir = os.path.dirname(os.path.abspath(__file__))
if (current_dir not in sys.path):
    sys.path.append(current_dir)
import pandas as pd
from selenium import webdriver
import main
from datetime import datetime, timezone
import re
# import relevant functions
from data_utils import * 
from main import getLeagueUrls, getMatchUrls, getTeamUrls, getMatchesData, getMatchData, createEventsDF, createMatchesDF, addEpvToDataFrame

# import relevant variables
from main import main_url

import json
import os
import sqlite3
from league_sources import resolve_league_source

def extract_opta_data(country, league, season, refresh_urls=None, limit=None, discover_only=False):
    # refresh_urls: "never" | "auto" | "always"
    refresh_mode = (refresh_urls or os.getenv("REFRESH_MATCH_URLS", "auto")).lower()
    if (refresh_mode not in {"never", "auto", "always"}):
        refresh_mode = "auto"

    league_urls_file = "league_urls_updated.json"
    db_path = "playback90.db"
    processed_table = "processed_matches"
    known_table = "known_matches"
    table_name = "event_data"
    source = resolve_league_source(country, league)
    provider_competition = source.provider_competition
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")

    def save_to_json(data, filename):
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)

    def load_from_json(filename):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return None

    # Create tables and load processed IDs
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {processed_table} (
                matchId TEXT PRIMARY KEY,
                league TEXT,
                country TEXT,
                season TEXT,
                startDate TEXT,
                uploaded BOOLEAN DEFAULT 0
            )
        """)
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {known_table} (
                matchId TEXT PRIMARY KEY,
                country TEXT,
                league TEXT,
                season TEXT,
                url TEXT,
                startDate TEXT,
                score TEXT
            )
        """)
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_known_comp ON {known_table}(country, league, season)")
        processed_ids = set(row[0] for row in conn.execute(f"SELECT matchId FROM {processed_table}"))

    # Helpers to read/write cached match URLs
    def load_known_match_urls(conn, country, league, season):
        rows = conn.execute(
            f"SELECT matchId, url, startDate, score FROM {known_table} WHERE country=? AND league=? AND season=?",
            (country, league, season)
        ).fetchall()
        # getMatchUrls usually returns dicts with at least matchId, url, startDate, score
        return [
            {"matchId": r[0], "url": r[1], "startDate": r[2], "score": r[3]}
            for r in rows
        ]

    def upsert_known_match_urls(conn, country, league, season, match_urls):
        data = [
            (
                m.get("matchId"),
                country, league, season,
                m.get("url"),
                m.get("startDate"),
                m.get("score"),
            )
            for m in match_urls
            if m.get("matchId")
        ]
        conn.executemany(
            f"""
            INSERT INTO {known_table} (matchId, country, league, season, url, startDate, score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(matchId) DO UPDATE SET
                url=excluded.url,
                startDate=excluded.startDate,
                score=excluded.score
            """,
            data
        )

    # Load league URLs if available, otherwise scrape and save
    league_urls = load_from_json(league_urls_file)
    if league_urls is None:
        print("Fetching league URLs...")
        league_urls = getLeagueUrls()
        save_to_json(league_urls, league_urls_file)

    # Get today's date (timezone-aware)
    today = datetime.now(timezone.utc).date()

    # Helper to derive matchId from URL if missing
    def _extract_match_id_from_url(url: str):
        if not url:
            return None
        # pick the last 6+ digit number in the URL (works for WhoScored match URLs, e.g. 1946429)
        ids = re.findall(r'(\d{6,})', url)
        return ids[-1] if ids else None

    # Strategy to get match URLs with caching
    def fetch_and_cache_all():
        print(f"[match_urls] Refreshing {provider_competition} for {league} {season}...")
        all_urls = getMatchUrls(comp_urls=league_urls, competition=provider_competition, season=season)

        # Enrich with matchId/startDate if missing
        enriched = []
        missing = 0
        for m in all_urls or []:
            row = dict(m)
            if not row.get("matchId"):
                row["matchId"] = _extract_match_id_from_url(row.get("url"))
            if not row.get("startDate"):
                # fallback to scraped 'date' if present
                row["startDate"] = row.get("date")
            if row.get("score") is None:
                row["score"] = ""
            if row.get("matchId"):
                enriched.append(row)
            else:
                missing += 1

        # Optional: drop placeholder scores like '-:-'
        enriched = [m for m in enriched if m.get('score') != '-:-']

        with sqlite3.connect(db_path) as conn:
            upsert_known_match_urls(conn, country, league, season, enriched)
        print(f"[match_urls] Cached {len(enriched)} rows for {country}-{league} {season}. Skipped {missing} without matchId.")
        return enriched

    with sqlite3.connect(db_path) as conn:
        known_urls = load_known_match_urls(conn, country, league, season)

    match_urls = []
    if refresh_mode == "always":
        match_urls = fetch_and_cache_all()
    elif refresh_mode == "never":
        if known_urls:
            match_urls = known_urls
            print(f"[match_urls] Loaded {len(match_urls)} from cache (never refresh).")
        else:
            match_urls = fetch_and_cache_all()
    else:  # "auto"
        if known_urls:
            match_urls = known_urls
            print(f"[match_urls] Loaded {len(match_urls)} from cache (auto).")
            # Simple heuristic: if everything is processed, there may still be new matches.
            # Refresh if the freshest known match date is before today and nothing new to fetch.
            to_fetch_probe = [m for m in match_urls if m.get('matchId') not in processed_ids]
            if not to_fetch_probe:
                try:
                    latest_dt = max(pd.to_datetime([m.get('startDate') for m in match_urls if m.get('startDate')], errors='coerce'))
                    if pd.isna(latest_dt) or latest_dt.date() < today:
                        match_urls = fetch_and_cache_all()
                except Exception:
                    # If parsing fails, do not refresh automatically
                    pass
        else:
            match_urls = fetch_and_cache_all()

    if discover_only:
        print(f"[match_urls] Discovery complete with {len(match_urls)} cached completed matches.")
        return

    # Now proceed as before, leveraging processed_ids to skip known matches
    matches_to_fetch = [m for m in match_urls if m.get('matchId') not in processed_ids]
    if limit is not None:
        matches_to_fetch = matches_to_fetch[:limit]
        print(f"[pilot] Limited this run to {len(matches_to_fetch)} unprocessed matches.")
    matches_data = getMatchesData(match_urls=matches_to_fetch) 

    matches_to_process = []
    for match in matches_data:
        match_id = match.get('matchId')
        status_code = match.get('statusCode')
        print(f"Processing match ID: {match_id}, Status Code: {status_code}")

        if match_id not in processed_ids and status_code == 6:
            matches_to_process.append(match)

    print(f"Number of matches to process: {len(matches_to_process)}")
    if not matches_to_process:
        print("No new matches to process.")
        return

    # Create event DataFrames from the filtered matches
    events_ls = [createEventsDF(match) for match in matches_to_process]
    events_ls = [e for e in events_ls if e is not None and not e.empty]

    if not events_ls:
        print("No events DataFrames to concatenate. Possibly all matches are already processed or have no event data.")
        return

    # Combine event DataFrames
    events_dfs = pd.concat(events_ls)

    print(f"Total events DataFrame shape: {events_dfs.shape}")

    # Preprocess
    processed_dfs = []
    for match_id, match_df in events_dfs.groupby('matchId'):
        # Model feature builders consume canonical competition metadata. Add it
        # before preprocessing so a newly configured league is scored rather
        # than falling back to zero-valued xA/xPass columns.
        match_df = match_df.copy()
        match_df['league'] = league
        match_df['country'] = country
        match_df['season'] = season
        processed_df = data_preprocessing(match_df)
        processed_df['league'] = league
        processed_df['country'] = country
        processed_df['season'] = season
        processed_dfs.append(processed_df)

    df = pd.concat(processed_dfs, ignore_index=True)

    if df.empty:
        print("No valid event data found after preprocessing.")
        return

    print(f"Total events DataFrame shape: {df.shape}")
    # 1. Convert list columns to JSON strings
    for col in df.columns:
        if df[col].map(type).eq(list).any():
            df[col] = df[col].apply(json.dumps)

    # 2. Sanitize column names for SQLite
    df.columns = [
        str(c).strip().replace(" ", "_").replace("-", "_") if c else f"col_{i}"
        for i, c in enumerate(df.columns)
    ]
    print(f"Total events DataFrame shape: {df.shape}")

    # Store event data into SQLite
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        table_cols = [row[1] for row in cursor.fetchall()]
        for col in table_cols:
            if col not in df.columns:
                df[col] = None
        df = df[table_cols]
        df.to_sql(table_name, conn, if_exists='append', index=False)

        # Log processed matches
        processed_rows = [
            (m['matchId'], league, country, season, m['startDate'])
            for m in matches_to_process
        ]
        if processed_rows:
            conn.executemany(
                f"""INSERT OR IGNORE INTO {processed_table} 
                (matchId, league, country, season, startDate) 
                VALUES (?, ?, ?, ?, ?)""",
                processed_rows
            )

    print(f"Data saved to {db_path} in table '{table_name}'. Processed matches updated.")


def extract_single_match_data(
    url,
    raise_errors=False,
    *,
    league=None,
    country=None,
    season=None,
):
    """
    Scrapes a single match URL and returns the processed DataFrame.
    Useful for 'Live' mode in Streamlit apps where a user drops a URL.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService
    import shutil
    import requests
    import tarfile
    import platform

    class _ConsoleStatus:
        @staticmethod
        def error(message):
            print(message)

        @staticmethod
        def warning(message):
            print(message)

    try:
        import streamlit as st
    except ModuleNotFoundError:
        st = _ConsoleStatus()

    def fail(message, exc=None):
        detail = f"{message}: {exc}" if exc else message
        if raise_errors:
            raise RuntimeError(detail) from exc
        try:
            st.error(detail)
        except Exception:
            print(detail)
        return None
    
    # Ensure URL is clean
    url = url.strip()
    url = url.replace("https://www.whoscored.com/", "https://1xbet.whoscored.com/")
    url = url.replace("http://www.whoscored.com/", "https://1xbet.whoscored.com/")
    url = url.replace("https://whoscored.com/", "https://1xbet.whoscored.com/")
    url = url.replace("http://whoscored.com/", "https://1xbet.whoscored.com/")

    if "/preview/" in url:
        url = url.replace("/preview/", "/live/")
        print(f"Adjusted URL to Match Centre: {url}")
    
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    options = FirefoxOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"user-agent={user_agent}")
    
    # 1. Find Firefox Binary - Aggressive Search
    firefox_binary = None
    possible_ff_paths = [
        "/usr/bin/firefox-esr",       # Standard Streamlit Cloud / Debian location
        "/usr/bin/firefox",           # Standard Linux
        shutil.which('firefox-esr'),
        shutil.which('firefox'),
        "/Applications/Firefox.app/Contents/MacOS/firefox" # Mac fallback
    ]

    for path in possible_ff_paths:
        if path and os.path.exists(path):
            firefox_binary = path
            break
            
    if firefox_binary:
        options.binary_location = firefox_binary
        print(f"Using Firefox binary at: {firefox_binary}")
    else:
        print("Warning: Could not find Firefox binary in common locations.")
    
    # 2. Find or Download Geckodriver
    def is_compatible_driver(path):
        if not path or not os.path.exists(path):
            return False
        if not os.access(path, os.X_OK):
            return False
        try:
            with open(path, "rb") as f:
                magic = f.read(4)
            if sys.platform == "darwin" and magic == b"\x7fELF":
                return False
            if sys.platform.startswith("linux") and magic in {b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"}:
                return False
        except Exception:
            return False
        return True

    def geckodriver_download_url():
        version = "v0.34.0"
        machine = platform.machine().lower()
        if sys.platform == "darwin":
            archive = "macos-aarch64" if machine in {"arm64", "aarch64"} else "macos"
        elif sys.platform.startswith("linux"):
            archive = "linux-aarch64" if machine in {"arm64", "aarch64"} else "linux64"
        else:
            return None
        return f"https://github.com/mozilla/geckodriver/releases/download/{version}/geckodriver-{version}-{archive}.tar.gz"

    geckodriver_path = None
    possible_gecko_paths = [
        shutil.which('geckodriver'),
        "/usr/bin/geckodriver",
        "/usr/local/bin/geckodriver",
        "/opt/homebrew/bin/geckodriver",
        os.path.abspath("geckodriver") 
    ]
    
    for path in possible_gecko_paths:
        if is_compatible_driver(path):
            geckodriver_path = path
            break

    # If not found, DOWNLOAD IT automatically
    if not geckodriver_path:
        print("Geckodriver not found. Attempting to download...")
        try:
            url_driver = geckodriver_download_url()
            if not url_driver:
                raise RuntimeError(f"Unsupported platform for automatic geckodriver download: {sys.platform} {platform.machine()}")
            response = requests.get(url_driver, stream=True)
            if response.status_code == 200:
                with open("geckodriver.tar.gz", "wb") as f:
                    f.write(response.content)
                
                with tarfile.open("geckodriver.tar.gz", "r:gz") as tar:
                    tar.extractall(".")
                
                if os.path.exists("geckodriver"):
                    os.chmod("geckodriver", 0o755) # Make executable
                if is_compatible_driver(os.path.abspath("geckodriver")):
                    geckodriver_path = os.path.abspath("geckodriver")
                    print(f"Successfully downloaded geckodriver to {geckodriver_path}")
                elif os.path.exists("geckodriver"):
                    print(f"Downloaded geckodriver is not compatible with this platform: {os.path.abspath('geckodriver')}")
                    geckodriver_path = None
        except Exception as e:
            print(f"Failed to download geckodriver: {e}")

    def build_chrome_options():
        chrome_options = ChromeOptions()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"user-agent={user_agent}")
        chrome_binary_paths = [
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for path in chrome_binary_paths:
            if path and os.path.exists(path):
                chrome_options.binary_location = path
                print(f"Using Chrome binary at: {path}")
                break
        return chrome_options
    
    # 3. Initialize Driver
    service = None
    if geckodriver_path:
        service = FirefoxService(geckodriver_path)

    try:
        if firefox_binary and service:
            driver = webdriver.Firefox(service=service, options=options)
        elif firefox_binary:
            driver = webdriver.Firefox(options=options)
        else:
            print("Firefox binary unavailable; falling back to Chrome.")
            driver = webdriver.Chrome(options=build_chrome_options())
    except Exception as firefox_error:
        try:
            print(f"Firefox WebDriver init failed, trying Chrome fallback: {firefox_error}")
            driver = webdriver.Chrome(options=build_chrome_options())
        except Exception as chrome_error:
            return fail("WebDriver init failed. Check Firefox/geckodriver or Chrome/chromedriver availability", chrome_error)
    
    match_data = None
    scrape_error = None
    try:
        print(f"Scraping URL: {url}")
        match_data = getMatchData(driver, url, display=True, close_window=False)
    except Exception as e:
        scrape_error = e
        if not raise_errors:
            try:
                st.warning(f"Scraping Error: {e}")
            except Exception:
                print(f"Scraping Error: {e}")
        try:
            driver.refresh()
            match_data = getMatchData(driver, url, display=True, close_window=False)
        except Exception as retry_error:
            scrape_error = retry_error
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    if not match_data:
        return fail("No match payload found in WhoScored page after retry", scrape_error)

    # Create events DataFrame
    events_df = createEventsDF(match_data)
    
    if events_df is None or events_df.empty:
        return fail("WhoScored match payload did not contain any events")

    # Scheduled workers know the canonical competition before preprocessing.
    # Model feature builders use these fields, so apply them before enrichment
    # rather than correcting metadata only after predictions have run.
    if league:
        events_df['league'] = league
    if country:
        events_df['country'] = country
    if season:
        events_df['season'] = season

    processed_df = data_preprocessing(events_df)
    
    processed_df['league'] = league or match_data.get('league', 'Unknown')
    processed_df['country'] = country or match_data.get('region', 'Unknown')
    processed_df['season'] = season or match_data.get('season', 'Unknown')

    try:
        home_id = match_data['home']['teamId']
        away_id = match_data['away']['teamId']
        home_name = match_data['home']['name']
        away_name = match_data['away']['name']
        scraped_team_map = {home_id: home_name, away_id: away_name}
        processed_df['teamName'] = processed_df['teamId'].map(scraped_team_map)
    except Exception:
        pass

    for col in processed_df.columns:
        if processed_df[col].map(type).eq(list).any():
            processed_df[col] = processed_df[col].apply(json.dumps)
    
    return processed_df

# At the bottom of extract_opta_data.py
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest completed WhoScored match event data.")
    parser.add_argument("country", help="Canonical country key, e.g. usa")
    parser.add_argument("league", help="Canonical league key, e.g. mls")
    parser.add_argument("season", help="Provider season label, e.g. 2026")
    parser.add_argument("refresh_mode", nargs="?", choices=("never", "auto", "always"), default="auto")
    parser.add_argument("--limit", type=int, help="Maximum unprocessed matches to scrape in this run")
    parser.add_argument("--discover-only", action="store_true", help="Refresh/cache fixture URLs without scraping matches")
    args = parser.parse_args()
    extract_opta_data(
        args.country,
        args.league,
        args.season,
        args.refresh_mode,
        args.limit,
        args.discover_only,
    )
