# -*- coding: utf-8 -*-
"""
Created on Wed Oct 14 14:20:02 2020

@author: aliha
@twitter: rockingAli5 
"""

import warnings
import os
import shutil
import time
import pandas as pd
pd.options.mode.chained_assignment = None
import json
from bs4 import BeautifulSoup as soup
import re 
from collections import OrderedDict
from datetime import datetime as dt
import itertools
import numpy as np
try:
    from tqdm import trange
except ModuleNotFoundError:
    pass


from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service as FirefoxService

# options = webdriver.FirefoxOptions()

# options.add_experimental_option('excludeSwitches', ['enable-logging'])


TRANSLATE_DICT = {'Jan': 'Jan',
                 'Feb': 'Feb',
                 'Mac': 'Mar',
                 'Apr': 'Apr',
                 'Mei': 'May',
                 'Jun': 'Jun',
                 'Jul': 'Jul',
                 'Ago': 'Aug',
                 'Sep': 'Sep',
                 'Okt': 'Oct',
                 'Nov': 'Nov',
                 'Des': 'Dec',
                 'Jan': 'Jan',
                 'Feb': 'Feb',
                 'Mar': 'Mar',
                 'Apr': 'Apr',
                 'May': 'May',
                 'Jun': 'Jun',
                 'Jul': 'Jul',
                 'Aug': 'Aug',
                 'Sep': 'Sep',
                 'Oct': 'Oct',
                 'Nov': 'Nov',
                 'Dec': 'Dec'}

main_url = 'https://1xbet.whoscored.com/'


from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException

def close_overlay(driver, timeout=10):
    try:
        # Wait for the overlay to appear
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".webpush-swal2-container"))
        )
        # Wait for the close button to be clickable
        close_btn = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".webpush-swal2-close"))
        )
        close_btn.click()
        print("Closed overlay/pop-up.")
        # Wait for overlay to disappear
        WebDriverWait(driver, timeout).until_not(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".webpush-swal2-container"))
        )
    except Exception as e:
        print("No overlay to close or failed to close overlay:", e)


def accept_cookies(driver, timeout=10):
    """
    Attempts to find and click 'Agree' or 'Accept' buttons on cookie consent banners.

    Many cookie-consent providers (Sourcepoint, Quantcast, OneTrust, ...) render
    their banner inside its own <iframe>, which top-level find_element(s) calls
    cannot see at all regardless of selector. A fresh Selenium profile has no
    stored consent, so this wall reliably appears on first page load even when
    it never reappears in a browser that already accepted it once.
    """
    # 1. Generic text search for Agree/Accept
    # 2. QC-CMP (Quantcast) buttons often used on these sites
    cookie_xpaths = [
        '//*[@class=" css-gweyaj"]',
        '//button[contains(text(), "Agree")]',
        '//button[contains(text(), "Accept")]',
        '//*[contains(text(), "Accept All")]',
        '//div[contains(@class, "qc-cmp2-summary-buttons")]/button[last()]',
        '//button[@mode="primary"]',
    ]

    def try_click_in_current_context():
        for xpath in cookie_xpaths:
            for btn in driver.find_elements(By.XPATH, xpath):
                if btn.is_displayed():
                    btn.click()
                    return True
        return False

    try:
        # Give an async-loaded consent wall a moment to render before giving up.
        end_time = time.monotonic() + timeout
        while time.monotonic() < end_time:
            if try_click_in_current_context():
                print("Accepted cookies.")
                time.sleep(1)  # Wait for banner to disappear
                return

            for frame in driver.find_elements(By.TAG_NAME, "iframe"):
                driver.switch_to.frame(frame)
                try:
                    if try_click_in_current_context():
                        print("Accepted cookies (inside iframe).")
                        driver.switch_to.default_content()
                        time.sleep(1)
                        return
                finally:
                    driver.switch_to.default_content()

            time.sleep(0.5)
        print("No cookie consent banner accepted within timeout.")
    except Exception as e:
        driver.switch_to.default_content()
        print(f"Note: Cookie acceptance check encountered: {e}")


def getLeagueUrls(minimize_window=True):
    
    options = Options()
    options.headless = True
    driver = webdriver.Firefox(options=options)

    if minimize_window:
        driver.minimize_window()

    driver.get(main_url)
    close_overlay(driver)
    accept_cookies(driver)
    league_names = []
    league_urls = []
    
    tournaments_btn = driver.find_element(By.XPATH, '//*[@id="All-Tournaments-btn"]').click()
    n_button = soup(driver.find_element(By.XPATH, '//*[@id="header-wrapper"]/div/div/div/div[4]/div[2]/div/div/div/div[1]/div/div').get_attribute('innerHTML')).find_all('button')
    n_tournaments = []
    for button in n_button:
        id_button = button.get('id')
        driver.find_element(By.ID, id_button).click()
        n_country = soup(driver.find_element(By.XPATH, '//*[@id="header-wrapper"]/div/div/div/div[4]/div[2]/div/div/div/div[2]').get_attribute('innerHTML')).find_all('div', {'class':'TournamentsDropdownMenu-module_countryDropdownContainer__I9P6n'})

        for country in n_country:
            country_id = country.find('div', {'class': 'TournamentsDropdownMenu-module_countryDropdown__8rtD-'}).get('id')

            # Trouver l'élément avec Selenium et cliquer dessus
            country_element = driver.find_element(By.ID, country_id)
            country_element.click()

            html_tournaments_list = driver.find_element(By.XPATH, '//*[@id="header-wrapper"]/div/div/div/div[4]/div[2]/div/div/div/div[2]').get_attribute('innerHTML')

            # Parse le HTML avec BeautifulSoup pour trouver les liens des tournois
            soup_tournaments = soup(html_tournaments_list, 'html.parser')
            tournaments = soup_tournaments.find_all('a')

            # Ajouter les tournois à la liste n_tournaments
            n_tournaments.extend(tournaments)

            driver.execute_script("arguments[0].click();", country_element)


    for tournament in n_tournaments:
        league_name = tournament.get('href').split('/')[-1]
        league_link = main_url[:-1]+tournament.get('href')
        league_names.append(league_name)
        league_urls.append(league_link)

    leagues = {}
    for name,link in zip(league_names,league_urls):
        leagues[name] = link

    driver.close()
    return leagues


def _configure_proxy(options):
    # Opt-in only: unset by default, so behavior is unchanged unless a proxy
    # is explicitly configured. Scoped to this one Firefox instance rather
    # than the whole droplet (no VPN tunnel), so R2 uploads, schedule syncs,
    # and the operator's own SSH session are never affected.
    #
    # No credentials in the URL: Firefox's SOCKS5 client has never
    # implemented RFC 1929 username/password auth (Mozilla bug 122752, open
    # 20+ years) -- its handshake only ever offers "no auth", so a proxy
    # that requires credentials will flatly refuse the connection. Use your
    # proxy provider's IP-whitelist feature (whitelist the droplet's public
    # IP) instead, and configure a credential-free URL here.
    proxy_url = os.environ.get("PLAYBACK90_SCRAPE_PROXY_URL")
    if not proxy_url:
        return

    from urllib.parse import urlparse

    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port:
        raise ValueError(
            "PLAYBACK90_SCRAPE_PROXY_URL must include a scheme, host, and port, "
            "e.g. socks5://host:1080 or http://host:8080"
        )
    if parsed.username or parsed.password:
        raise ValueError(
            "PLAYBACK90_SCRAPE_PROXY_URL must not embed credentials -- "
            "Firefox cannot authenticate a SOCKS5 or HTTP(S) proxy "
            "headlessly. Whitelist the droplet's public IP with your proxy "
            "provider instead and use a credential-free URL."
        )

    options.set_preference("network.proxy.type", 1)

    if parsed.scheme.startswith("socks"):
        options.set_preference("network.proxy.socks", parsed.hostname)
        options.set_preference("network.proxy.socks_port", parsed.port)
        options.set_preference("network.proxy.socks_version", 5)
        options.set_preference("network.proxy.socks_remote_dns", True)
    else:
        options.set_preference("network.proxy.http", parsed.hostname)
        options.set_preference("network.proxy.http_port", parsed.port)
        options.set_preference("network.proxy.ssl", parsed.hostname)
        options.set_preference("network.proxy.ssl_port", parsed.port)


def _remote_firefox_driver():
    options = Options()
    # Selenium removed the ``options.headless`` convenience property in 4.10.
    # Passing the Firefox argument works both locally and on display-less hosts.
    options.add_argument("-headless")
    options.set_preference(
        "general.useragent.override",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    )
    _configure_proxy(options)

    firefox_binary = next(
        (
            path
            for path in (
                shutil.which("firefox-esr"),
                shutil.which("firefox"),
                "/usr/bin/firefox-esr",
                "/usr/bin/firefox",
            )
            if path and os.path.exists(path)
        ),
        None,
    )
    if firefox_binary:
        options.binary_location = firefox_binary

    geckodriver = next(
        (
            path
            for path in (
                shutil.which("geckodriver"),
                "/usr/local/bin/geckodriver",
                "/usr/bin/geckodriver",
            )
            if path and os.path.isfile(path) and os.access(path, os.X_OK)
        ),
        None,
    )
    if geckodriver:
        return webdriver.Firefox(service=FirefoxService(geckodriver), options=options)
    return webdriver.Firefox(options=options)


def getMatchUrls(comp_urls, competition, season, maximize_window=True):
    driver = _remote_firefox_driver()
    try:
        return _get_match_urls_with_driver(driver, comp_urls, competition, season, maximize_window)
    except Exception:
        _dump_driver_state(driver, competition)
        raise
    finally:
        try:
            driver.quit()
        except WebDriverException:
            # Preserve the discovery error if Firefox has already exited.
            pass


_DISCOVERY_DEBUG_DIR = "/var/lib/playback90/discovery-debug"


def _dump_driver_state(driver, label):
    # Diagnostic snapshot for provider_discovery failures: geckodriver's own
    # error strings are opaque and identical across unrelated failures, so a
    # failed discovery is otherwise a black box. Written under
    # /var/lib/playback90 rather than /tmp because the systemd unit runs with
    # PrivateTmp=true + ProtectSystem=strict, so /tmp is a private tmpfs that
    # is invisible outside the service's own mount namespace and does not
    # survive past the run -- ReadWritePaths only grants /var/lib/playback90.
    import re as _re

    safe_label = _re.sub(r"[^a-zA-Z0-9_-]+", "_", str(label))
    saved_paths = []
    try:
        os.makedirs(_DISCOVERY_DEBUG_DIR, exist_ok=True)
        html_path = os.path.join(_DISCOVERY_DEBUG_DIR, f"{safe_label}.html")
        with open(html_path, "w") as handle:
            handle.write(driver.page_source)
        saved_paths.append(html_path)
    except Exception as exc:
        print(f"Failed to dump page source for {label!r}: {exc}")
    try:
        png_path = os.path.join(_DISCOVERY_DEBUG_DIR, f"{safe_label}.png")
        driver.save_screenshot(png_path)
        saved_paths.append(png_path)
    except Exception as exc:
        print(f"Failed to save screenshot for {label!r}: {exc}")
    if saved_paths:
        print(f"Saved discovery failure snapshot for {label!r}: {saved_paths}")
    else:
        print(f"Could not save any discovery failure snapshot for {label!r}")


def _get_match_urls_with_driver(driver, comp_urls, competition, season, maximize_window=True):

    if maximize_window:
        driver.set_window_size(1920, 1080)
    
    comp_url = comp_urls[competition]
    driver.get(comp_url)
    close_overlay(driver)
    accept_cookies(driver)
    time.sleep(5)
    
    # NEW: define retry helper once
    def fetch_fixture_data_with_retry(driver, retries=3, sleep_s=1.0):
        for attempt in range(retries):
            try:
                return getFixtureData(driver)
            except StaleElementReferenceException:
                if attempt == retries - 1:
                    raise
                time.sleep(sleep_s)
        return []

    seasons_element = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "seasons"))
    )
    season_options = seasons_element.find_elements(By.TAG_NAME, "option")

    for season_option in season_options:
        if season_option.text == season:
            season_option.click()

            time.sleep(5)
            try:
                stages_element = driver.find_element(By.XPATH, '//*[@id="stages"]')
                stage_texts = [
                    option.text for option in stages_element.find_elements(By.TAG_NAME, "option")
                ]

                def click_stage_by_text(text):
                    # Selecting a stage can re-render the dropdown, so re-query
                    # fresh elements by text right before each click instead of
                    # reusing WebElement references collected earlier.
                    fresh_stages = driver.find_element(
                        By.XPATH, '//*[@id="stages"]'
                    ).find_elements(By.TAG_NAME, "option")
                    for option in fresh_stages:
                        if option.text == text:
                            option.click()
                            return
                    raise NoSuchElementException(f"Stage option {text!r} no longer present")

                all_urls = []

                for stage_text in stage_texts:
                    print(stage_text)

                    if 'Final Stage' in stage_text:
                        continue
                    if competition == 'Champions League' or competition == 'Europa League' or competition == 'Europa Conference League' or competition == 'FIFA World Cup':
                        if 'Grp' in stage_text or 'Final Stage' in stage_text:

                            click_stage_by_text(stage_text)
                            time.sleep(5)

                            driver.execute_script("window.scrollTo(0, 400)")

                            match_urls = fetch_fixture_data_with_retry(driver)

                            match_urls = getSortedData(match_urls)

                            match_urls2 = [url for url in match_urls if '?' not in url['date'] and '\n' not in url['date']]

                            all_urls += match_urls2
                        else:
                            continue

                    else:
                        click_stage_by_text(stage_text)
                        time.sleep(5)

                        driver.execute_script("window.scrollTo(0, 400)")

                        match_urls = fetch_fixture_data_with_retry(driver)

                        match_urls = getSortedData(match_urls)

                        match_urls2 = [url for url in match_urls if '?' not in url['date'] and '\n' not in url['date']]

                        all_urls += match_urls2

            except NoSuchElementException:
                all_urls = []

                driver.execute_script("window.scrollTo(0, 400)")

                match_urls = fetch_fixture_data_with_retry(driver)

                match_urls = getSortedData(match_urls)

                match_urls2 = [url for url in match_urls if '?' not in url['date'] and '\n' not in url['date']]

                all_urls += match_urls2


            remove_dup = [dict(t) for t in {tuple(sorted(d.items())) for d in all_urls}]
            all_urls = getSortedData(remove_dup)

            return all_urls

    season_names = [option.text for option in season_options]
    print('Seasons available: {}'.format(season_names))
    raise ValueError('Season Not Found.')
    




def getTeamUrls(team, match_urls):
    
    team_data = []
    for fixture in match_urls:
        if fixture['home'] == team or fixture['away'] == team:
            team_data.append(fixture)
    team_data = [a[0] for a in itertools.groupby(team_data)]
                
    return team_data


def getMatchesData(match_urls, minimize_window=True):
    
    matches = []
    
    options = Options()
    options.headless = True
    driver = webdriver.Firefox(options=options)
    if minimize_window:
        driver.minimize_window()
    
    try:
        for i in trange(len(match_urls), desc='Getting Match Data'):
            # recommended to avoid getting blocked by incapsula/imperva bots
            time.sleep(7)
            match_data = getMatchData(driver, main_url+match_urls[i]['url'], display=False, close_window=False)
            matches.append(match_data)
    except NameError:
        print('Recommended: \'pip install tqdm\' for a progress bar while the data gets scraped....')
        time.sleep(7)
        for i in range(len(match_urls)):
            match_data = getMatchData(driver, main_url+match_urls[i]['url'], display=False, close_window=False)
            matches.append(match_data)
    
    driver.close()
    
    return matches




def getFixtureData(driver):
    # Robust, HTML-snapshot-based parser to avoid stale element references
    wait = WebDriverWait(driver, 10)
    matches_ls = []
    seen = set()

    while True:
        # Wait for fixtures to be present
        try:
            wait.until(EC.presence_of_all_elements_located((By.CLASS_NAME, 'Accordion-module_accordion__UuHD0')))
        except Exception:
            pass

        before = driver.page_source
        page = soup(before, 'lxml')

        accordions = page.find_all('div', class_=re.compile(r'Accordion-module_accordion'))
        for acc in accordions:
            header = acc.find('div', class_=re.compile(r'Accordion-module_header'))
            date_text = header.get_text(strip=True) if header else ''
            rows = acc.find_all('div', class_=re.compile(r'Match-module_row'))
            for row in rows:
                link = row.find('a', href=True)
                if not link:
                    continue
                href = link['href']
                if 'live' not in href:
                    continue

                # Try to extract teams
                home, away = '', ''
                teams_tag = row.find("div", {"class": re.compile(r'Match-module_teams')})
                if teams_tag:
                    names = [a.get_text(strip=True) for a in teams_tag.find_all('a')]
                    if len(names) >= 2:
                        home, away = names[0], names[1]
                if not home or not away:
                    # Fallback: first two anchors in the row (excluding the main link if duplicated)
                    anchors = [a.get_text(strip=True) for a in row.find_all('a')]
                    if len(anchors) >= 3:
                        home, away = anchors[0], anchors[1]

                score_spans = link.find_all('span')
                score = ':'.join([t.get_text(strip=True) for t in score_spans]) if score_spans else ''

                match = {
                    'date': date_text,
                    'home': home,
                    'away': away,
                    'score': score,
                    'url': href
                }
                key = href
                if key not in seen:
                    seen.add(key)
                    matches_ls.append(match)

        # Go to previous day and stop if page doesn’t change
        try:
            prev_btn = wait.until(EC.element_to_be_clickable((By.ID, 'dayChangeBtn-prev')))
            driver.execute_script("arguments[0].click();", prev_btn)
            time.sleep(1.5)
            after = driver.page_source
            if after == before:
                break
        except Exception:
            break

    return matches_ls






def translateDate(data):
    
    unwanted = []
    for match in data:
        date = match['date'].split()
        if '?' not in date[0]:
            try:
                match['date'] = ' '.join([TRANSLATE_DICT[date[0]], date[1], date[2]])
            except KeyError:
                print(date)
        else:
            unwanted.append(data.index(match))
    
    # remove matches that got suspended/postponed
    for i in sorted(unwanted, reverse = True):
        del data[i]
    
    return data


def getSortedData(data):
    data = sorted(data, key = lambda i: dt.strptime(i['date'], '%A, %b %d %Y'))
    return data
    



def getMatchData(driver, url, display=True, close_window=True):
    try:
        driver.get(url)
    except WebDriverException:
        driver.get(url)

    accept_cookies(driver)
    time.sleep(5)
    # get script data from page source
    script_content = driver.find_element(By.XPATH, '//*[@id="layout-wrapper"]/script[1]').get_attribute('innerHTML')


    # clean script content
    script_content = re.sub(r"[\n\t]*", "", script_content)
    script_content = script_content[script_content.index("matchId"):script_content.rindex("}")]


    # this will give script content in list form 
    script_content_list = list(filter(None, script_content.strip().split(',            ')))
    metadata = script_content_list.pop(1) 


    # string format to json format
    match_data = json.loads(metadata[metadata.index('{'):])
    keys = [item[:item.index(':')].strip() for item in script_content_list]
    values = [item[item.index(':')+1:].strip() for item in script_content_list]
    for key,val in zip(keys, values):
        match_data[key] = json.loads(val)


    # get other details about the match
    region = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/span[1]').text
    league = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/a').text.split(' - ')[0]
    season = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/a').text.split(' - ')[1]
    if len(driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/a').text.split(' - ')) == 2:
        competition_type = 'League'
        competition_stage = ''
    elif len(driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/a').text.split(' - '))== 3:
        competition_type = 'Knock Out'
        competition_stage = driver.find_element(By.XPATH, '//*[@id="breadcrumb-nav"]/a').text.split(' - ')[-1]
    else:
        print('Getting more than 3 types of information about the competition.')

    match_data['region'] = region
    match_data['league'] = league
    match_data['season'] = season
    match_data['competitionType'] = competition_type
    match_data['competitionStage'] = competition_stage


    # sort match_data dictionary alphabetically
    match_data = OrderedDict(sorted(match_data.items()))
    match_data = dict(match_data)
    if display:
        print('Region: {}, League: {}, Season: {}, Match Id: {}'.format(region, league, season, match_data['matchId']))
    
    
    if close_window:
        driver.close()
        
    return match_data





def createEventsDF(data):
    events = data['events']
    for event in events:
        event.update({'matchId' : data['matchId'],
                        'startDate' : data['startDate'],
                        'startTime' : data['startTime'],
                        'score' : data['score'],
                        'ftScore' : data['ftScore'],
                        'htScore' : data['htScore'],
                        'etScore' : data['etScore'],
                        'venueName' : data['venueName'],
                        'maxMinute' : data['maxMinute']})
    events_df = pd.DataFrame(events)

    # clean period column
    events_df['period'] = pd.json_normalize(events_df['period'])['displayName']

    # clean type column
    events_df['type'] = pd.json_normalize(events_df['type'])['displayName']

    # clean outcomeType column
    events_df['outcomeType'] = pd.json_normalize(events_df['outcomeType'])['displayName']

    # clean outcomeType column
    try:
        x = events_df['cardType'].fillna({i: {} for i in events_df.index})
        events_df['cardType'] = pd.json_normalize(x)['displayName'].fillna(False)
    except KeyError:
        events_df['cardType'] = False

    eventTypeDict = data['matchCentreEventTypeJson']  
    events_df['satisfiedEventsTypes'] = events_df['satisfiedEventsTypes'].apply(lambda x: [list(eventTypeDict.keys())[list(eventTypeDict.values()).index(event)] for event in x])

    # clean qualifiers column
    try:
        for i in events_df.index:
            row = events_df.loc[i, 'qualifiers'].copy()
            if len(row) != 0:
                for irow in range(len(row)):
                    row[irow]['type'] = row[irow]['type']['displayName']
    except TypeError:
        pass


    # clean isShot column
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        if 'isShot' in events_df.columns:
            events_df['isShot'] = events_df['isShot'].replace(np.nan, False).infer_objects(copy=False)
        else:
            events_df['isShot'] = False

        # clean isGoal column
        if 'isGoal' in events_df.columns:
            events_df['isGoal'] = events_df['isGoal'].replace(np.nan, False).infer_objects(copy=False)
        else:
            events_df['isGoal'] = False

    # add player name column
    def normalize_player_id(player_id):
        if pd.isna(player_id):
            return np.nan
        try:
            return str(int(float(player_id)))
        except (TypeError, ValueError):
            return str(player_id)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        events_df['playerId'] = events_df['playerId'].apply(normalize_player_id)
    player_name_col = events_df.loc[:, 'playerId'].map(data['playerIdNameDictionary']) 
    events_df.insert(loc=events_df.columns.get_loc("playerId")+1, column='playerName', value=player_name_col)

    # add home/away column
    h_a_col = events_df['teamId'].map({data['home']['teamId']:'h', data['away']['teamId']:'a'})
    events_df.insert(loc=events_df.columns.get_loc("teamId")+1, column='h_a', value=h_a_col)


    # adding shot body part column
    events_df['shotBodyType'] = pd.Series([None] * len(events_df), dtype='object')
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        for i in events_df.loc[events_df.isShot==True].index:
            for j in events_df.loc[events_df.isShot==True].qualifiers.loc[i]:
                if j['type'] == 'RightFoot' or j['type'] == 'LeftFoot' or j['type'] == 'Head' or j['type'] == 'OtherBodyPart':
                    events_df.loc[i, 'shotBodyType'] = j['type']


    # adding shot situation column
    events_df['situation'] = pd.Series([None] * len(events_df), dtype='object')
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        for i in events_df.loc[events_df.isShot==True].index:
            for j in events_df.loc[events_df.isShot==True].qualifiers.loc[i]:
                if j['type'] == 'FromCorner' or j['type'] == 'SetPiece' or j['type'] == 'DirectFreekick':
                    events_df.loc[i, 'situation'] = j['type']
                if j['type'] == 'RegularPlay':
                    events_df.loc[i, 'situation'] = 'OpenPlay' 

    event_types = list(data['matchCentreEventTypeJson'].keys())
    event_type_cols = pd.DataFrame({event_type: pd.Series([event_type in row for row in events_df['satisfiedEventsTypes']]) for event_type in event_types})
    events_df = pd.concat([events_df, event_type_cols], axis=1)


    return events_df
    



def createMatchesDF(data):
    columns_req_ls = ['matchId', 'attendance', 'venueName', 'startTime', 'startDate',
                      'score', 'home', 'away', 'referee']
    matches_df = pd.DataFrame(columns=columns_req_ls)
    if type(data) == dict:
        matches_dict = dict([(key,val) for key,val in data.items() if key in columns_req_ls])
        matches_df = pd.DataFrame(matches_dict, columns=columns_req_ls).reset_index(drop=True)
        matches_df['home'] = pd.Series([None] * len(matches_df), dtype='object')
        matches_df['away'] = pd.Series([None] * len(matches_df), dtype='object')
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=FutureWarning)
            matches_df.at[0, 'home'] = [data['home']]
            matches_df.at[0, 'away'] = [data['away']]
    else:
        for match in data:
            matches_dict = dict([(key,val) for key,val in match.items() if key in columns_req_ls])
            matches_df = pd.DataFrame(matches_dict, columns=columns_req_ls).reset_index(drop=True)
    
    matches_df = matches_df.set_index('matchId')        
    return matches_df




def load_EPV_grid(fname='EPV_grid.csv'):
    """ load_EPV_grid(fname='EPV_grid.csv')
    
    # load pregenerated EPV surface from file. 
    
    Parameters
    -----------
        fname: filename & path of EPV grid (default is 'EPV_grid.csv' in the curernt directory)
        
    Returns
    -----------
        EPV: The EPV surface (default is a (32,50) grid)
    
    """
    epv = np.loadtxt(fname, delimiter=',')
    return epv






def get_EPV_at_location(position,EPV,attack_direction,field_dimen=(106.,68.)):
    """ get_EPV_at_location
    
    Returns the EPV value at a given (x,y) location
    
    Parameters
    -----------
        position: Tuple containing the (x,y) pitch position
        EPV: tuple Expected Possession value grid (loaded using load_EPV_grid() )
        attack_direction: Sets the attack direction (1: left->right, -1: right->left)
        field_dimen: tuple containing the length and width of the pitch in meters. Default is (106,68)
            
    Returrns
    -----------
        EPV value at input position
        
    """
    
    x,y = position
    if abs(x)>field_dimen[0]/2. or abs(y)>field_dimen[1]/2.:
        return 0.0 # Position is off the field, EPV is zero
    else:
        if attack_direction==-1:
            EPV = np.fliplr(EPV)
        ny,nx = EPV.shape
        dx = field_dimen[0]/float(nx)
        dy = field_dimen[1]/float(ny)
        ix = (x+field_dimen[0]/2.-0.0001)/dx
        iy = (y+field_dimen[1]/2.-0.0001)/dy
        return EPV[int(iy),int(ix)]



                

def to_metric_coordinates_from_whoscored(data,field_dimen=(106.,68.) ):
    '''
    Convert positions from Whoscored units to meters (with origin at centre circle)
    '''
    x_columns = [c for c in data.columns if c[-1].lower()=='x'][:2]
    y_columns = [c for c in data.columns if c[-1].lower()=='y'][:2]
    x_columns_mod = [c+'_metrica' for c in x_columns]
    y_columns_mod = [c+'_metrica' for c in y_columns]
    data[x_columns_mod] = (data[x_columns]/100*106)-53
    data[y_columns_mod] = (data[y_columns]/100*68)-34
    return data




def addEpvToDataFrame(data):

    # loading EPV data
    EPV = load_EPV_grid('EPV_grid.csv')

    # converting opta coordinates to metric coordinates
    data = to_metric_coordinates_from_whoscored(data)

    # calculating EPV for events
    EPV_difference = []
    for i in data.index:
        if data.loc[i, 'type'] == 'Pass' and data.loc[i, 'outcomeType'] == 'Successful':
            start_pos = (data.loc[i, 'x_metrica'], data.loc[i, 'y_metrica'])
            start_epv = get_EPV_at_location(start_pos, EPV, attack_direction=1)
            
            end_pos = (data.loc[i, 'endX_metrica'], data.loc[i, 'endY_metrica'])
            end_epv = get_EPV_at_location(end_pos, EPV, attack_direction=1)
            
            diff = end_epv - start_epv
            EPV_difference.append(diff)
            
        else:
            EPV_difference.append(np.nan)
    
    data = data.assign(EPV_difference = EPV_difference)
    
    
    # dump useless columns
    drop_cols = ['x_metrica', 'endX_metrica', 'y_metrica',
                 'endY_metrica']
    data.drop(drop_cols, axis=1, inplace=True)
    data.rename(columns={'EPV_difference': 'EPV'}, inplace=True)
    
    return data



