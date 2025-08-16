import streamlit as st
from PIL import Image
import os
import pandas as pd
import s3fs
import time
from dotenv import load_dotenv
import re
from pathlib import Path
from datetime import datetime

# --- Config ---
st.set_page_config(page_title="PlayBack90", layout="centered")
load_dotenv()





team_dict = { 
        16 : 'Sunderland',
        184 : 'Burnley',
        19 : 'Leeds',
        832 : 'Levante',
        833 : 'Elche',
        61 : 'Real Oviedo',
        2889 : 'Sassuolo',
        777 : 'Pisa',
        2731 : 'Cremonese',
        282 : 'FC Koln',
        38 : 'Hamburger SV',
        146 : 'Lorient',
        2832 : 'Paris FC',
        314 : 'Metz',
        65: 'Barcelona',
        63: 'Atletico Madrid',
        52: 'Real Madrid',
        53: 'Atletic Club',
        839: 'Villarreal',
        54: 'Real Betis',
        64: 'Rayo Vallecano',
        51: 'Mallorca',
        68: 'Real Sociedad',
        62: 'Celta Vigo',
        131: 'Osasuna',
        67: 'Sevilla',
        2783: 'Girona',
        819: 'Getafe',
        70: 'Espanyol',
        825: 'Leganes',
        838: 'Las Palmas',
        55 : 'Valencia',
        60 : 'Deportivo Alaves',
        58: 'Real Valladolid',
        13: 'Arsenal',
        161: 'Wolves',
        24: 'Aston Villa',
        211: 'Brighton',
        30: 'Tottenham',
        167: 'Man City',
        14: 'Leicester',
        18: 'Southampton',
        183: 'Bournemouth',
        26: 'Liverpool',
        23: 'Newcastle',
        15: 'Chelsea',
        174: 'Nottingham Forest',
        29: 'West Ham',
        32: 'Man Utd',
        170: 'Fulham',
        189: 'Brentford',
        162: 'Crystal Palace',
        31: 'Everton',
        165: 'Ipswich',
        37: 'Bayern Munich',
        36: 'Bayer Leverkusen',
        45: 'Eintracht Frankfurt',
        219: 'Mainz 05',
        50: 'Freiburg',
        7614: 'RB Leipzig',
        33: 'Wolfsburg',
        134: 'Borussia M.Gladbach',
        41: 'VfB Stuttgart',
        44: 'Borussia Dortmund',
        1730: 'Augsburg',
        42: 'Werder Bremen',
        1211: 'Hoffenheim',
        796: 'Union Berlin',
        283: 'St. Pauli',
        1206: 'Holstein Kiel',
        4852: 'FC Heidenheim',
        109: 'Bochum',
        75 : 'Inter',
        276 : 'Napoli',
        300 : 'Atalanta',
        87 : 'Juventus',
        77 : 'Lazio',
        71 : 'Bologna',
        73 : 'Fiorentina',
        84 : 'Roma',
        80 : 'AC Milan',
        86 : 'Udinese',
        72 : 'Torino',
        278 : 'Genoa',
        1290 : 'Como',
        76 : 'Verona',
        78 : 'Cagliari',
        79 : 'Lecce',
        24341 : 'Parma Calcio',
        272 : 'Empoli',
        85 : 'Venezia',
        269 : 'Monza',
        304 : 'PSG',
        249 : 'Marseille',
        613 : 'Nice',
        248 : 'Monaco',
        607 : 'Lille',
        228 : 'Lyon',
        148 : 'Strasbourg',
        246 : 'Toulouse',
        309 : 'Lens',
        2332 : 'Brest',
        313 : 'Rennes',
        308 : 'Auxerre',
        614 : 'Angers',
        302 : 'Nantes',
        950 : 'Reims',
        217 : 'Le Havre',
        145 : 'Saint-Etienne',
        311 : 'Montpellier',
        299 : 'Benfica',
        129 : 'PSV',
        336 : 'Germany',
        340 : 'Portugal',
        338 : 'Spain',
        341 : 'France',
        342 : 'Poland',
        424 : 'Scotland',
        337 : 'Croatia',
        339 : 'Belgium',
        343 : 'Italy',
        325 : 'Israel',
        768 : 'Bosnia',
        335 : 'Netherlands',
        327 : 'Hungary',
        425 : 'Denmark',
        423 : 'Switzerland',
        771 : 'Serbia'
}
  

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

storage_options = {
    "key": R2_ACCESS_KEY,
    "secret": R2_SECRET_KEY,
    "client_kwargs": {"endpoint_url": ENDPOINT_URL},
}

@st.cache_data(ttl=60)

def list_parquet_files_for_league_season(league, season):
    fs = s3fs.S3FileSystem(
        key=R2_ACCESS_KEY,
        secret=R2_SECRET_KEY,
        client_kwargs={"endpoint_url": ENDPOINT_URL},
    )
    # Adjusted for new path structure (no "league=" or "season=")
    files = fs.glob(f"{R2_BUCKET}/event_data/{league}/{season}/*.parquet")
    return files

def load_data_from_r2(league, season):
    files = list_parquet_files_for_league_season(league, season)
    dfs = []
    for file in files:
        df = pd.read_parquet(f"s3://{file}", storage_options=storage_options)
        df['league'] = df['league'].astype(str)
        df['season'] = df['season'].astype(str)
        df['matchId'] = df['matchId'].astype(str)
        dfs.append(df)
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    else:
        return pd.DataFrame()

def get_seasons_from_r2(league):
    fs = s3fs.S3FileSystem(
        key=R2_ACCESS_KEY,
        secret=R2_SECRET_KEY,
        client_kwargs={"endpoint_url": ENDPOINT_URL},
    )
    prefix = f"{R2_BUCKET}/event_data/{league}/"
    # List all directories under the league folder (each is a season)
    try:
        season_dirs = fs.ls(prefix)
    except Exception:
        return []
    seasons = []
    for path in season_dirs:
        # path example: .../event_data/premier-league/2024_25
        parts = path.rstrip("/").split("/")
        if len(parts) > 0:
            season = parts[-1]
            if season not in seasons:
                seasons.append(season)
    return sorted(seasons, reverse=True)

def get_fixtures_from_r2(league, season, limit=10):
    fs = s3fs.S3FileSystem(
        key=R2_ACCESS_KEY,
        secret=R2_SECRET_KEY,
        client_kwargs={"endpoint_url": ENDPOINT_URL},
    )
    prefix = f"{R2_BUCKET}/event_data/{league}/{season}/"
    files = fs.glob(f"{prefix}*.parquet")
    fixtures = []
    for file in files:
        # Example: 2025-05-03_1821387_31_vs_165_2___2.parquet (where 31 and 165 are team IDs)
        filename = os.path.basename(file)
        match = re.match(r"(\d{4}-\d{2}-\d{2})_(.+?)_(\d+)_vs_(\d+)_(.+)\.parquet", filename)
        if match:
            start_date_str, match_id, home_team_id, away_team_id, ft_score = match.groups()
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            except ValueError:
                continue
            # Clean up score (replace __ with -)
            ft_score_clean = ft_score.replace("__", "-").replace("_", "-")
            fixtures.append({
                "file_path": file,
                "startDate": start_date,
                "startDate_str": start_date_str,
                "matchId": match_id,
                "home_team_id": int(home_team_id),
                "away_team_id": int(away_team_id),
                "ft_score": ft_score_clean
            })
    fixtures = sorted(fixtures, key=lambda x: x["startDate"], reverse=True)[:limit]
    return fixtures

def get_match_id_from_r2(league, season, home_team, away_team):
    df = load_data_from_r2(league, season)
    if df.empty:
        return None
    home_ids = set(df[(df['teamName'] == home_team) & (df['h_a'] == 'h')]['matchId'])
    away_ids = set(df[(df['teamName'] == away_team) & (df['h_a'] == 'a')]['matchId'])
    common_ids = home_ids & away_ids
    return list(common_ids)[0] if common_ids else None

def load_match_data_from_r2(file_path):
    fs = s3fs.S3FileSystem(
        key=R2_ACCESS_KEY,
        secret=R2_SECRET_KEY,
        client_kwargs={"endpoint_url": ENDPOINT_URL},
    )
    if fs.exists(file_path):
        return pd.read_parquet(f"s3://{file_path}", storage_options=storage_options)
    else:
        return pd.DataFrame()

# --- App Logo ---
st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
BASE_DIR = Path(__file__).parent
logo_path = BASE_DIR / "logos" / "PB90.png"

if logo_path.exists():
    st.image(str(logo_path), width=150)
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@700&family=Roboto:wght@400&display=swap');
    h1, h2, h3, h4, h5, h6 {
        font-family: 'Montserrat', sans-serif !important;
    }
    .big-font {
        font-size:2.2em !important;
        font-family: 'Montserrat', sans-serif !important;
        font-weight:700;
    }
    .normal-font {
        font-family: 'Roboto', sans-serif !important;
        font-size:1.1em !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="big-font">PlayBack90</div>', unsafe_allow_html=True)
st.markdown('<div class="normal-font">PlayBack90 is a post-match analytics platform built for football fans, analysts, and coaches. It breaks down each game with rich visuals, performance metrics, and tactical statistics — giving you a deeper understanding of what really happened on the pitch</div>', unsafe_allow_html=True)

st.markdown("<hr style='border: 1px solid #e0e0e0; margin: 20px 0;'>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color:gray;'>Select a league to view its latest fixtures</p>", unsafe_allow_html=True)

#BASE_DIR = Path(__file__).parent  # folder where the script is located

LEAGUES = {
    "Premier League": BASE_DIR / "logos" / "premier-league.png",
    "La Liga": BASE_DIR / "logos" / "laliga.png",
    "Bundesliga": BASE_DIR / "logos" / "bundesliga.png",
    "Serie A": BASE_DIR / "logos" / "serie-a.png",
    "Ligue 1": BASE_DIR / "logos" / "ligue-1.png",
    "Champions League": BASE_DIR / "logos" / "champions-league.png",
}

def chunk_dict(d, n):
    items = list(d.items())
    return [dict(items[i:i+n]) for i in range(0, len(items), n)]

league_chunks = chunk_dict(LEAGUES, 3)


if 'selected_league' not in st.session_state:
    st.session_state['selected_league'] = None

selected_league = st.session_state['selected_league']

if not selected_league:
    for chunk in league_chunks:
        cols = st.columns(len(chunk))
        for idx, (league, logo_path) in enumerate(chunk.items()):
            with cols[idx]:
                if os.path.exists(logo_path):
                    img = Image.open(logo_path)
                    img.thumbnail((100, 100))
                    st.image(img, use_container_width=False)
                if st.button(f"{league}", key=f"select_{league}"):
                    with st.spinner(f"Loading {league} data..."):
                        st.session_state['selected_league'] = league
                        time.sleep(0.6)
                        st.rerun()
    st.stop()

LEAGUE_NAME_MAP = {
    "Premier League": "premier-league",
    "La Liga": "laliga",
    "Bundesliga": "bundesliga",
    "Serie A": "serie-a",
    "Ligue 1": "ligue-1",
    "Champions League": "champions-league",
}

display_name = st.session_state['selected_league']
db_league_name = LEAGUE_NAME_MAP[display_name]
seasons = get_seasons_from_r2(db_league_name)
if not seasons:
    st.warning(f"No seasons found for {selected_league}. Please select another league.")
    st.session_state['selected_league'] = None
    st.stop()

default_season = seasons[0]
selected_season = st.selectbox("Select Season", seasons, index=0)
st.session_state['selected_season'] = selected_season

if selected_season:
    st.markdown(f"### Last 10 Fixtures: {selected_league} ({selected_season})")
    fixtures = get_fixtures_from_r2(db_league_name, selected_season, limit=10)
    for fixture in fixtures:
        # Map team ids to names using team_dict
        home_team_name = team_dict.get(fixture['home_team_id'], str(fixture['home_team_id']))
        away_team_name = team_dict.get(fixture['away_team_id'], str(fixture['away_team_id']))
        btn_label = f"{home_team_name} {fixture['ft_score']} {away_team_name}"
        if st.button(btn_label, key=f"fixture_{fixture['matchId']}"):
            st.session_state['league'] = db_league_name
            st.session_state['season'] = selected_season
            st.session_state['matchId'] = fixture['matchId']
            st.session_state['startDate'] = fixture['startDate_str']
            st.session_state['file_path'] = fixture['file_path']
            st.session_state['home_team'] = home_team_name
            st.session_state['away_team'] = away_team_name
            st.session_state['ft_score'] = fixture['ft_score']
            st.switch_page("pages/Post Match Analysis.py")

    st.markdown("---")
    colA, colB = st.columns(2)
    with colA:
        if st.button("Change League"):
            st.session_state['selected_league'] = None
            st.session_state['selected_season'] = None
            st.rerun()
    with colB:
        if st.button("Refresh Fixtures"):
            st.cache_data.clear()
            st.rerun()



# --- Footer ---
st.markdown("<hr style='border: 1px solid #eee;'>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align: center; color: white; font-size: 0.85em;'>"
    "<a href='https://x.com/chadha_ishdeep' style='color: white;' target='_blank'>Created by @chadha_ishdeep</a>"
    "</div>",
    unsafe_allow_html=True
)