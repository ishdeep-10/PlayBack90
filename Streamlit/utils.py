import re
import random
import streamlit as st
from mplsoccer import VerticalPitch,Pitch
import matplotlib.font_manager as font_manager
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from mplsoccer import FontManager
from scipy.spatial import ConvexHull
from matplotlib.colors import LinearSegmentedColormap
from highlight_text import ax_text, fig_text
import matplotlib.patheffects as path_effects
from matplotlib.colors import to_rgba
from scipy.ndimage import gaussian_filter1d
from matplotlib.patches import Rectangle
import glob,os
import matplotlib.image as mpimg
from mplsoccer import PyPizza, add_image, FontManager
import seaborn as sns
from matplotlib import colormaps
import joblib
from unidecode import unidecode
from scipy.ndimage import gaussian_filter
import sqlite3
import pandas as pd
import numpy as np
import altair as alt
import streamlit as st
import matplotlib.patches as mpatches
import plotly.graph_objects as go
import pandas as pd
import matplotlib.pyplot as plt
from mplsoccer import Pitch
import time


team_dict = { 
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
        771 : 'Serbia',
        1234 : 'Palmeiras',
        28925 : 'Inter Miami',
        297 : 'Porto',
        4869 : 'Al Ahly',
        1227 : 'Botafogo',
        5973 : 'Seattle Sounders',
        889 : 'Boca Juniors',
        3951 : 'Auckland City',
        1239 : 'Flamengo',
        4861 : 'Esperance',
        27482 : 'Los Angeles FC',
        905 : 'River Plate',
        1452 : 'Monterrey',
        2403 : 'Urawa Red Diamonds',
        3306 : 'Mamelodi Sundowns',
        1232 : 'Fluminense',
        6327 : 'Ulsan HD FC',
        5099 : 'Wydad',
        5138 : 'Al Ain',
        361 : 'Salzburg',
        4975 : 'Al Hilal',
        1449 : 'Pachuca'
}
    
team_colors = {
    'Barcelona': '#A50044',
    'Atletico Madrid': '#CE3524',
    'Real Madrid': '#FCBF00',
    'Atletic Club': '#E0092C',
    'Villarreal': '#FFE667',
    'Real Betis': '#0BB363',
    'Rayo Vallecano': '#E53027',
    'Mallorca': '#E20613',
    'Real Sociedad': '#0067B1',
    'Celta Vigo': '#8AC3EE',
    'Osasuna': '#E60026',
    'Sevilla': '#D00027',
    'Girona': '#DA291C',
    'Getafe': '#003DA5',
    'Espanyol': '#00529F',
    'Leganes': '#005BAC',
    'Las Palmas': '#FEDD00',
    'Valencia': '#F18E00',
    'Deportivo Alaves': '#005BAC',
    'Real Valladolid': '#7A1E8B',
    'Arsenal': '#EF0107',
    'Wolves': '#FDB913',
    'Aston Villa': '#95BFE5',
    'Brighton': '#0057B8',
    'Tottenham': '#132257',
    'Man City': '#6CABDD',
    'Leicester': '#003090',
    'Southampton': '#D71920',
    'Bournemouth': '#DA291C',
    'Liverpool': '#C8102E',
    'Newcastle': "#F8F5F6",
    'Chelsea': '#034694',
    'Nottingham Forest': '#E53233',
    'West Ham': '#7A263A',
    'Man Utd': '#DA291C',
    'Fulham': "#FFFFFF",
    'Brentford': '#E30613',
    'Crystal Palace': '#1B458F',
    'Everton': '#003399',
    'Ipswich': '#005BAC',
    'Bayern Munich': '#DC052D',
    'Bayer Leverkusen': '#E30613',
    'Eintracht Frankfurt': "#FFFFFF",
    'Mainz 05': '#C8102E',
    'Freiburg': "#F9F4F4",
    'RB Leipzig': '#E4002B',
    'Wolfsburg': '#65B32E',
    'Borussia M.Gladbach': "#EEF3ED",
    'VfB Stuttgart': '#E30613',
    'Borussia Dortmund': '#FDE100',
    'Augsburg': '#C8102E',
    'Werder Bremen': '#1A9F3D',
    'Hoffenheim': '#005BAC',
    'Union Berlin': '#E30613',
    'St. Pauli': '#A45A2A',
    'Holstein Kiel': '#005BAC',
    'FC Heidenheim': '#E30613',
    'Bochum': '#005BAC',
    'Inter': '#1E2943',
    'Napoli': '#0082CA',
    'Atalanta': '#1C1C1C',
    'Juventus': "#F8F4F4",
    'Lazio': '#A8C6E5',
    'Bologna': '#D4001F',
    'Fiorentina': '#592C82',
    'Roma': '#8E1111',
    'AC Milan': '#FB090B',
    'Udinese': "#F2EBEB",
    'Torino': '#8B1B3A',
    'Genoa': '#C8102E',
    'Como': '#005BAC',
    'Verona': '#FCE500',
    'Cagliari': '#C8102E',
    'Lecce': '#FCE500',
    'Parma Calcio': '#FCE500',
    'Empoli': '#005BAC',
    'Venezia': "#F2ECEC",
    'Monza': '#E30613',
    'PSG': '#004170',
    'Marseille': '#009DDC',
    'Nice': '#E30613',
    'Monaco': '#ED1C24',
    'Lille': '#E30613',
    'Lyon': '#E30613',
    'Strasbourg': '#005BAC',
    'Toulouse': '#5F259F',
    'Lens': '#E30613',
    'Brest': '#E30613',
    'Rennes': '#E30613',
    'Auxerre': '#005BAC',
    'Angers': "#EEECEC",
    'Nantes': '#FCE500',
    'Reims': '#E30613',
    'Le Havre': '#005BAC',
    'Saint-Etienne': '#009639',
    'Montpellier': '#005BAC',
    'Benfica': '#E30613',
    'PSV': '#E30613',
    'Ajax': '#E30613',
    'Feyenoord': '#E30613',
    'Utrecht': '#E30613',
    'AZ-Alkmaar': '#E30613',
    'Twente': '#E30613',
    'Go Ahead Eagles': '#E30613',
    'FC Groningen': '#007A33',
    'Fortuna Sittard': '#FCE500',
    'Heracles': "#FAF7F7",
    'SC Heerenveen': '#005BAC',
    'NEC Nijmegen': '#E30613',
    'NAC Breda': '#FCE500',
    'PEC Zwolle': '#005BAC',
    'Sparta Rotterdam': '#E30613',
    'Willem II': '#E30613',
    'RKC Waalwijk': '#FCE500',
    'Almere City': '#E30613',
    'Palmeiras' : "#216348",
    'Inter Miami' : "#E067C2",
    'Porto' : '#005BAC',
    'Al Ahly' : '#E30613',
    'Botafogo' : "#E3DADA",
    'Seattle Sounders' : "#238486",
    'Boca Juniors' : "#E0E723",
    'Auckland City' : '#005BAC',
    'Flamengo' : '#E30613',
    'Esperance' : "#7B79D9",
    'Los Angeles FC' : "#949430",
    'River Plate' : '#E30613',
    'Monterrey' : '#005BAC',
    'Urawa Red Diamonds' : '#E30613',
    'Mamelodi Sundowns' : "#AEE54F",
    'Fluminense' : "#68202B",
    'Ulsan HD FC' : '#005BAC',
    'Wydad' : '#E30613',
    'Al Ain' : "#721A70",
    'Salzburg' : '#E30613',
    'Al Hilal' : '#005BAC',
    'Pachuca' : "#E39606"
    }

@st.cache_data(ttl=600)

def load_and_process_match_data(df, team_colors):
    df = df.sort_values(by='index').reset_index(drop=True)

    # Assign team colors
    df['teamColor'] = df['teamName'].map(team_colors)

    # Calculate event time in seconds
    df['event_time'] = df['minute'] * 60 + df['second']

    # First substitution time per team
    first_sub_times = df[df['type'] == 'SubstitutionOn'] \
        .groupby('teamName')['event_time'].min().to_dict()

    # Determine if player was in the starting XI
    def is_first_eleven(row):
        team = row['teamName']
        event_time = row['event_time']
        return event_time < first_sub_times.get(team, float('inf'))

    df['isFirstEleven'] = df.apply(is_first_eleven, axis=1)

    # Force 'SubstitutionOn' players to False regardless
    df.loc[df['type'] == 'SubstitutionOn', 'isFirstEleven'] = False

    return df


def highlight_higher(val, all_vals):
    return 'color: green; font-weight: bold' if val == max(all_vals) else ''

def insert_ball_carries(events_df, min_carry_length, max_carry_length, min_carry_duration, max_carry_duration):
    events_out = pd.DataFrame()
    # match_events = events_df[events_df['match_id'] == match_id].reset_index()
    match_events = events_df.reset_index()
    match_carries = pd.DataFrame()

    for idx, match_event in match_events.iterrows():

        if idx < len(match_events) - 1:
            prev_evt_team = match_event['teamId']
            next_evt_idx = idx + 1
            init_next_evt = match_events.loc[next_evt_idx]
            take_ons = 0
            incorrect_next_evt = True

            while incorrect_next_evt:

                if next_evt_idx >= len(match_events):
                    break
                next_evt = match_events.iloc[next_evt_idx]

                if next_evt['type'] == 'TakeOn' and next_evt['outcomeType'] == 'Successful':
                    take_ons += 1
                    incorrect_next_evt = True

                elif ((next_evt['type'] == 'TakeOn' and next_evt['outcomeType'] == 'Unsuccessful')
                      or (next_evt['teamId'] != prev_evt_team and next_evt['type'] == 'Challenge' and next_evt['outcomeType'] == 'Unsuccessful')
                      or (next_evt['type'] == 'Foul')):
                    incorrect_next_evt = True

                else:
                    incorrect_next_evt = False

                next_evt_idx += 1

            # Apply some conditioning to determine whether carry criteria is satisfied
            same_team = prev_evt_team == next_evt['teamId']
            not_ball_touch = match_event['type'] != 'BallTouch'
            dx = 105*(match_event['endX'] - next_evt['x'])/100
            dy = 68*(match_event['endY'] - next_evt['y'])/100
            far_enough = dx ** 2 + dy ** 2 >= min_carry_length ** 2
            not_too_far = dx ** 2 + dy ** 2 <= max_carry_length ** 2
            dt = 60 * (next_evt['cumulative_mins'] - match_event['cumulative_mins'])
            min_time = dt >= min_carry_duration
            same_phase = dt < max_carry_duration
            same_period = match_event['period'] == next_evt['period']

            valid_carry = same_team & not_ball_touch & far_enough & not_too_far & min_time & same_phase &same_period

            if valid_carry:
                carry = pd.DataFrame()
                prev = match_event
                nex = next_evt

                carry.loc[0, 'eventId'] = prev['eventId'] + 0.5
                carry['minute'] = np.floor(((init_next_evt['minute'] * 60 + init_next_evt['second']) + (
                        prev['minute'] * 60 + prev['second'])) / (2 * 60))
                carry['second'] = (((init_next_evt['minute'] * 60 + init_next_evt['second']) +
                                    (prev['minute'] * 60 + prev['second'])) / 2) - (carry['minute'] * 60)
                carry['teamId'] = nex['teamId']
                carry['x'] = prev['endX']
                carry['y'] = prev['endY']
                carry['expandedMinute'] = np.floor(((init_next_evt['expandedMinute'] * 60 + init_next_evt['second']) +
                                                    (prev['expandedMinute'] * 60 + prev['second'])) / (2 * 60))
                carry['period'] = nex['period']
                carry['type'] = carry.apply(lambda x: {'value': 99, 'displayName': 'Carry'}, axis=1)
                carry['outcomeType'] = 'Successful'
                carry['qualifiers'] = carry.apply(lambda x: {'type': {'value': 999, 'displayName': 'takeOns'}, 'value': str(take_ons)}, axis=1)
                carry['satisfiedEventsTypes'] = carry.apply(lambda x: [], axis=1)
                carry['isTouch'] = True
                carry['playerId'] = nex['playerId']
                carry['endX'] = nex['x']
                carry['endY'] = nex['y']
                carry['blockedX'] = np.nan
                carry['blockedY'] = np.nan
                carry['goalMouthZ'] = np.nan
                carry['goalMouthY'] = np.nan
                carry['isShot'] = np.nan
                carry['relatedEventId'] = nex['eventId']
                carry['relatedPlayerId'] = np.nan
                carry['isGoal'] = np.nan
                carry['cardType'] = np.nan
                carry['isOwnGoal'] = np.nan
                carry['type'] = 'Carry'
                carry['cumulative_mins'] = (prev['cumulative_mins'] + init_next_evt['cumulative_mins']) / 2
                carry['playerName'] = nex['playerName']

                match_carries = pd.concat([match_carries, carry], ignore_index=True, sort=False)

    match_events_and_carries = pd.concat([match_carries, match_events], ignore_index=True, sort=False)
    match_events_and_carries = match_events_and_carries.sort_values(['period', 'cumulative_mins']).reset_index(drop=True)

    # Rebuild events dataframe
    events_out = pd.concat([events_out, match_events_and_carries])

    return events_out

def cumulative_match_mins(events_df):
    events_out = pd.DataFrame()
    # Add cumulative time to events data, resetting for each unique match
    match_events = events_df.copy()
    match_events['cumulative_mins'] = match_events['minute'] + (1/60) * match_events['second']
    # Add time increment to cumulative minutes based on period of game.
    for period in np.arange(1, match_events['period'].max() + 1, 1):
        if period > 1:
            t_delta = match_events[match_events['period'] == period - 1]['cumulative_mins'].max() - \
                                   match_events[match_events['period'] == period]['cumulative_mins'].min()
        elif period == 1 or period == 5:
            t_delta = 0
        else:
            t_delta = 0
        match_events.loc[match_events['period'] == period, 'cumulative_mins'] += t_delta
    # Rebuild events dataframe
    events_out = pd.concat([events_out, match_events])
    return events_out

def insert_ball_carries(events_df, min_carry_length=3, max_carry_length=60, min_carry_duration=1, max_carry_duration=10):
    events_out = pd.DataFrame()
    # Carry conditions (convert from metres to opta)
    min_carry_length = 3.0
    max_carry_length = 60.0
    min_carry_duration = 1.0
    max_carry_duration = 10.0
    # match_events = events_df[events_df['match_id'] == match_id].reset_index()
    match_events = events_df.reset_index()
    match_carries = pd.DataFrame()

    for idx, match_event in match_events.iterrows():

        if idx < len(match_events) - 1:
            prev_evt_team = match_event['teamId']
            next_evt_idx = idx + 1
            init_next_evt = match_events.loc[next_evt_idx]
            take_ons = 0
            incorrect_next_evt = True

            while incorrect_next_evt:

                next_evt = match_events.loc[next_evt_idx]

                if next_evt['type'] == 'TakeOn' and next_evt['outcomeType'] == 'Successful':
                    take_ons += 1
                    incorrect_next_evt = True

                elif ((next_evt['type'] == 'TakeOn' and next_evt['outcomeType'] == 'Unsuccessful')
                      or (next_evt['teamId'] != prev_evt_team and next_evt['type'] == 'Challenge' and next_evt['outcomeType'] == 'Unsuccessful')
                      or (next_evt['type'] == 'Foul')):
                    incorrect_next_evt = True

                else:
                    incorrect_next_evt = False

                next_evt_idx += 1

            # Apply some conditioning to determine whether carry criteria is satisfied
            same_team = prev_evt_team == next_evt['teamId']
            not_ball_touch = match_event['type'] != 'BallTouch'
            dx = 105*(match_event['endX'] - next_evt['x'])/100
            dy = 68*(match_event['endY'] - next_evt['y'])/100
            far_enough = dx ** 2 + dy ** 2 >= min_carry_length ** 2
            not_too_far = dx ** 2 + dy ** 2 <= max_carry_length ** 2
            dt = 60 * (next_evt['cumulative_mins'] - match_event['cumulative_mins'])
            min_time = dt >= min_carry_duration
            same_phase = dt < max_carry_duration
            same_period = match_event['period'] == next_evt['period']

            valid_carry = same_team & not_ball_touch & far_enough & not_too_far & min_time & same_phase &same_period

            if valid_carry:
                carry = pd.DataFrame()
                prev = match_event
                nex = next_evt

                carry.loc[0, 'eventId'] = prev['eventId'] + 0.5
                carry['minute'] = np.floor(((init_next_evt['minute'] * 60 + init_next_evt['second']) + (
                        prev['minute'] * 60 + prev['second'])) / (2 * 60))
                carry['second'] = (((init_next_evt['minute'] * 60 + init_next_evt['second']) +
                                    (prev['minute'] * 60 + prev['second'])) / 2) - (carry['minute'] * 60)
                carry['teamId'] = nex['teamId']
                carry['x'] = prev['endX']
                carry['y'] = prev['endY']
                carry['expandedMinute'] = np.floor(((init_next_evt['expandedMinute'] * 60 + init_next_evt['second']) +
                                                    (prev['expandedMinute'] * 60 + prev['second'])) / (2 * 60))
                carry['period'] = nex['period']
                carry['type'] = carry.apply(lambda x: {'value': 99, 'displayName': 'Carry'}, axis=1)
                carry['outcomeType'] = 'Successful'
                carry['qualifiers'] = carry.apply(lambda x: {'type': {'value': 999, 'displayName': 'takeOns'}, 'value': str(take_ons)}, axis=1)
                carry['satisfiedEventsTypes'] = carry.apply(lambda x: [], axis=1)
                carry['isTouch'] = True
                carry['playerId'] = nex['playerId']
                carry['endX'] = nex['x']
                carry['endY'] = nex['y']
                carry['blockedX'] = np.nan
                carry['blockedY'] = np.nan
                carry['goalMouthZ'] = np.nan
                carry['goalMouthY'] = np.nan
                carry['isShot'] = np.nan
                carry['relatedEventId'] = nex['eventId']
                carry['relatedPlayerId'] = np.nan
                carry['isGoal'] = np.nan
                carry['cardType'] = np.nan
                carry['isOwnGoal'] = np.nan
                carry['type'] = 'Carry'
                carry['cumulative_mins'] = (prev['cumulative_mins'] + init_next_evt['cumulative_mins']) / 2
                carry['playerName'] = nex['playerName']

                match_carries = pd.concat([match_carries, carry], ignore_index=True, sort=False)

    match_events_and_carries = pd.concat([match_carries, match_events], ignore_index=True, sort=False)
    match_events_and_carries = match_events_and_carries.sort_values(['period', 'cumulative_mins']).reset_index(drop=True)

    # Rebuild events dataframe
    events_out = pd.concat([events_out, match_events_and_carries])

    return events_out

def get_match_df(df, home_team, away_team,team_colors):
    # Find matchId(s) where selected home_team was home ('h') AND away_team was away ('a')
    matching_matches = df[
        (df['teamName'] == home_team) & (df['h_a'] == 'h')
    ]['matchId'].unique()

    # Filter further: check that in the same matchId, the away team appears as 'a'
    valid_match_ids = []
    for match_id in matching_matches:
        away_team_rows = df[(df['matchId'] == match_id) & (df['teamName'] == away_team) & (df['h_a'] == 'a')]
        if not away_team_rows.empty:
            valid_match_ids.append(match_id)

    if not valid_match_ids:
        st.warning(f"No match found between {home_team} (home) and {away_team} (away).")
    else:
        # Assuming only 1 matchId between them per venue
        selected_match_id = valid_match_ids[0]

        # Filter df to keep only events from this match
        match_df = df[df['matchId'] == selected_match_id].copy()
        match_df = match_df.sort_values(by='index').reset_index(drop=True)

        match_df['teamColor'] = match_df['teamName'].map(team_colors)
        

        match_df['event_time'] = match_df['minute'] * 60 + match_df['second']

        # Get first sub time per team
        first_sub_times = match_df[match_df['type'] == 'SubstitutionOn'] \
            .groupby('teamName')['event_time'].min().to_dict()

        # Set isFirstEleven default
        def is_first_eleven(row):
            team = row['teamName']
            t = row['event_time']
            return t < first_sub_times.get(team, float('inf'))

        match_df['isFirstEleven'] = match_df.apply(is_first_eleven, axis=1)

        # Force all SubstitutionOn players to False
        match_df.loc[match_df['type'] == 'SubstitutionOn', 'isFirstEleven'] = False

    return match_df

def get_team_names(df,team_dict,team_colors):
    df = df.sort_values(by='matchId')
    df['teamName'] = df['teamId'].map(team_dict)
    df['teamColor'] = df['teamName'].map(team_colors)
    team_names = list(team_dict.values())
    return df,df['teamName'].unique()

@st.cache_data(ttl=600)
def summarize_player_shots(df):
    # Filter relevant shot types
    mask_shots = df['type'].isin(['Goal', 'MissedShots', 'SavedShot', 'ShotOnPost'])
    shots_df = df[mask_shots].copy()

    # Create new boolean columns
    shots_df['BlockedShots'] = ((shots_df['type'] == 'SavedShot') & (shots_df['shotBlocked'] == True)).astype(int)
    shots_df['CleanSavedShot'] = ((shots_df['type'] == 'SavedShot') & (shots_df['shotBlocked'] == False)).astype(int)

    # Summarize main shot types
    player_summary = shots_df.groupby('playerName')['type'].value_counts().unstack(fill_value=0)
    player_summary = player_summary.rename(columns={
        'Goal': 'Goals',
        'MissedShots': 'Off Target',
        'ShotOnPost': 'Woodwork',
    })

    # Add 'On Target' from CleanSavedShot column
    saved_shots = shots_df.groupby('playerName')['CleanSavedShot'].sum().rename('On Target')
    player_summary = player_summary.merge(saved_shots, left_index=True, right_index=True, how='left')

    # Add BlockedShots
    blocked = shots_df.groupby('playerName')['BlockedShots'].sum().rename('BlockedShots')
    player_summary = player_summary.merge(blocked, left_index=True, right_index=True, how='left')

    # Fill missing columns
    for col in ['Goals', 'On Target', 'Off Target', 'Woodwork', 'BlockedShots']:
        if col not in player_summary.columns:
            player_summary[col] = 0

    # Add total shots
    player_summary['Total Shots'] = (
        player_summary['Goals'] +
        player_summary['On Target'] +
        player_summary['Off Target'] +
        player_summary['Woodwork'] +
        player_summary['BlockedShots']
    )

    # Add total xG
    xg_summary = shots_df.groupby('playerName')['xG'].sum().rename('Total xG')

    # Round conditionally
    xg_summary = xg_summary.apply(lambda x: round(x, 2) if x < 0.9 else round(x, 3))

    # Merge and compute xG/Shot
    player_summary = player_summary.merge(xg_summary, left_index=True, right_index=True)
    player_summary['xG/Shot'] = (player_summary['Total xG'] / player_summary['Total Shots']).round(3)

    # Reset index
    player_summary = player_summary.reset_index()

    # Filter out players with no shots
    player_summary = player_summary[player_summary['Total Shots'] > 0]

    player_team_map = df.groupby('playerName')['teamName'].first().to_dict()
    player_summary['Team'] = player_summary['playerName'].map(player_team_map)

    # Sort by total shots
    player_summary = player_summary.sort_values(by='Total xG', ascending=False)

    return player_summary

def calculate_angle(x, y,GOAL_X,GOAL_Y):
    goal_width = 7.32
    goal_left = GOAL_Y - goal_width / 2
    goal_right = GOAL_Y + goal_width / 2
    a = np.sqrt((GOAL_X - x)**2 + (goal_left - y)**2)
    b = np.sqrt((GOAL_X - x)**2 + (goal_right - y)**2)
    c = goal_width
    try:
        angle = np.arccos((a**2 + b**2 - c**2) / (2 * a * b))
    except:
        angle = 0
    return angle

def shotMap_ws(df, axs, pitch, hteam, ateam, team1_facecolor, team2_facecolor, text_color, background,font_prop, situation, selected_player=None):
    # Filter shots by situation and selected player
    if situation == 'All':
        mask1 = ((df['teamName'] == hteam)) & ((df['type'] == 'Goal') | (df['type'] == 'MissedShots') | (df['type'] == 'SavedShot') | (df['type'] == 'ShotOnPost'))
        mask2 = ((df['teamName'] == ateam)) & ((df['type'] == 'Goal') | (df['type'] == 'MissedShots') | (df['type'] == 'SavedShot') | (df['type'] == 'ShotOnPost'))
    else:
        mask1 = ((df['teamName'] == hteam)) & (df['situation'] == situation) & ((df['type'] == 'Goal') | (df['type'] == 'MissedShots') | (df['type'] == 'SavedShot') | (df['type'] == 'ShotOnPost'))
        mask2 = ((df['teamName'] == ateam)) & (df['situation'] == situation) & ((df['type'] == 'Goal') | (df['type'] == 'MissedShots') | (df['type'] == 'SavedShot') | (df['type'] == 'ShotOnPost'))

    df['xG'] = df['xG'].fillna(0.05)

    home_shots_df = df[mask1]
    away_shots_df = df[mask2]

    # Filter by selected player if provided
    if selected_player:
        home_shots_df = home_shots_df[home_shots_df['playerName'] == selected_player]
        away_shots_df = away_shots_df[away_shots_df['playerName'] == selected_player]

    home_shots_df.reset_index(drop=True, inplace=True)
    away_shots_df.reset_index(drop=True, inplace=True)

    h_missed = home_shots_df[home_shots_df['type'] == 'MissedShots']
    h_saved = home_shots_df[(home_shots_df['type'] == 'SavedShot') & (home_shots_df['shotBlocked'] == False)]
    h_blocked = home_shots_df[(home_shots_df['type'] == 'SavedShot') & (home_shots_df['shotBlocked'] == True)]
    h_post = home_shots_df[home_shots_df['type'] == 'ShotOnPost']
    h_goals = home_shots_df[(home_shots_df['type'] == 'Goal') & (home_shots_df['goalOwn'] == False)]
    h_own_goals = home_shots_df[(home_shots_df['type'] == 'Goal') & (home_shots_df['goalOwn'] == True)]

    a_missed = away_shots_df[away_shots_df['type'] == 'MissedShots']
    a_saved = away_shots_df[(away_shots_df['type'] == 'SavedShot') & (away_shots_df['shotBlocked'] == False)]
    a_blocked = away_shots_df[(away_shots_df['type'] == 'SavedShot') & (away_shots_df['shotBlocked'] == True)]
    a_post = away_shots_df[away_shots_df['type'] == 'ShotOnPost']
    a_goals = away_shots_df[(away_shots_df['type'] == 'Goal') & (away_shots_df['goalOwn'] == False)]
    a_own_goals = away_shots_df[(away_shots_df['type'] == 'Goal') & (away_shots_df['goalOwn'] == True)]

    away_shots_df['x'] = pitch.dim.right - away_shots_df.x
    away_shots_df['y'] = pitch.dim.top - away_shots_df.y

    if not away_shots_df['y'].empty and away_shots_df['y'].nunique() > 1:
        sns.kdeplot(y=away_shots_df.y, ax=axs['left'], color=team2_facecolor, fill=True)
    if not home_shots_df['y'].empty and home_shots_df['y'].nunique() > 1:
        sns.kdeplot(y=home_shots_df.y, ax=axs['right'], color=team1_facecolor, fill=True)

    a_missed['x'] = pitch.dim.right - a_missed.x
    a_saved['x'] = pitch.dim.right - a_saved.x
    a_post['x'] = pitch.dim.right - a_post.x
    a_goals['x'] = pitch.dim.right - a_goals.x
    a_own_goals['x'] = pitch.dim.right - a_own_goals.x
    a_blocked['x'] = pitch.dim.right - a_blocked.x

    a_missed['y'] = pitch.dim.top - a_missed.y
    a_saved['y'] = pitch.dim.top - a_saved.y
    a_post['y'] = pitch.dim.top - a_post.y
    a_goals['y'] = pitch.dim.top - a_goals.y
    a_own_goals['y'] = pitch.dim.top - a_own_goals.y
    a_blocked['y'] = pitch.dim.top - a_blocked.y

    if not h_missed.empty:
        pitch.scatter(h_missed.x, h_missed.y, marker='o', edgecolors=team1_facecolor, s=8000 * h_missed['xG'], linewidth=3, c=background, ax=axs['pitch'])
    if not h_saved.empty:
        pitch.scatter(h_saved.x, h_saved.y, marker='o', edgecolors='white', s=8000 * h_saved['xG'], c=team1_facecolor, linewidth=3, zorder=4, ax=axs['pitch'])
    if not h_post.empty:
        pitch.scatter(h_post.x, h_post.y, marker='o', edgecolors='green', s=8000 * h_post['xG'], linewidth=3, c=team1_facecolor, zorder=5, ax=axs['pitch'])
    if not h_goals.empty:
        pitch.scatter(h_goals.x, h_goals.y, marker='football', edgecolors=text_color, s=10000 * h_goals['xG'], zorder=6, linewidths=3, c=team1_facecolor, ax=axs['pitch'])
    if not h_own_goals.empty:
        pitch.scatter(h_own_goals.x, h_own_goals.y, marker='football', edgecolors=team2_facecolor, s=3000, zorder=6, c=team1_facecolor, ax=axs['pitch'])
    if not h_blocked.empty:
        pitch.scatter(h_blocked.x, h_blocked.y, marker='s', edgecolors=team1_facecolor, s=6000 * h_blocked['xG'], zorder=5, linewidth=3, c=background, ax=axs['pitch'])

    if not a_missed.empty:
        pitch.scatter(a_missed.x, a_missed.y, marker='o', edgecolors=team2_facecolor, s=8000 * a_missed['xG'], linewidth=3, c=background, ax=axs['pitch'])
    if not a_saved.empty:
        pitch.scatter(a_saved.x, a_saved.y, marker='o', edgecolors='white', s=8000 * a_saved['xG'], c=team2_facecolor, linewidth=3, zorder=4, ax=axs['pitch'])
    if not a_post.empty:
        pitch.scatter(a_post.x, a_post.y, marker='o', edgecolors='green', s=8000 * a_post['xG'], c=team2_facecolor, linewidth=3, zorder=5, ax=axs['pitch'])
    if not a_goals.empty:
        pitch.scatter(a_goals.x, a_goals.y, marker='football', edgecolors=text_color, s=10000 * a_goals['xG'], zorder=6, linewidths=3, c=team2_facecolor, ax=axs['pitch'])
    if not h_own_goals.empty:
        pitch.scatter(h_own_goals.x, h_own_goals.y, marker='football', edgecolors=team1_facecolor, s=3000, zorder=6, c=team2_facecolor, ax=axs['pitch'])
    if not a_blocked.empty:
        pitch.scatter(a_blocked.x, a_blocked.y, marker='s', edgecolors=team2_facecolor, s=6000 * a_blocked['xG'], zorder=5, linewidth=3, c=background, ax=axs['pitch'])

    pitch.scatter(4,-5,marker='football', edgecolors=text_color, s=1000, c=background,ax=axs['pitch'])
    pitch.annotate('Goal', xy=(10,-5), fontsize=30,color=text_color,fontproperties=font_prop,ax=axs['pitch'], ha='center', va='center')
    
    pitch.scatter(23,-5,marker='o', edgecolors=background, s=1000, c=text_color,ax=axs['pitch'])
    pitch.annotate('On Target', xy=(33,-5), fontsize=30,color=text_color,fontproperties=font_prop,ax=axs['pitch'], ha='center', va='center')

    pitch.scatter(48,-5,marker='o', edgecolors='green',linewidth=5, s=1000, c=background,ax=axs['pitch'])
    pitch.annotate('Woodwork', xy=(58,-5), fontsize=30,color=text_color,fontproperties=font_prop,ax=axs['pitch'], ha='center', va='center')

    pitch.scatter(70,-5,marker='o', edgecolors=text_color, s=1000, c=background,ax=axs['pitch'])
    pitch.annotate('Off Target', xy=(78,-5), fontsize=30,color=text_color,fontproperties=font_prop,ax=axs['pitch'], ha='center', va='center')

    pitch.scatter(90,-5,marker='s', edgecolors=text_color,linewidth=3, s=1000, c=background,ax=axs['pitch'])
    pitch.annotate('Blocked', xy=(98,-5), fontsize=30,color=text_color,fontproperties=font_prop,ax=axs['pitch'], ha='center', va='center')

    h_xg = round(home_shots_df['xG'].sum(),2)
    a_xg = round(away_shots_df['xG'].sum(),2)
    summary_data = {
        'Team': [hteam, ateam],
        'Goals': [len(h_goals) + len(h_own_goals), len(a_goals) + len(a_own_goals)],
        'On Target': [len(h_goals) + len(h_saved), len(a_goals) + len(a_saved)],
        'Off Target': [len(h_missed), len(a_missed)],
        'Woodwork': [len(h_post), len(a_post)],
        'Blocked': [len(h_blocked), len(a_blocked)],
        'Own Goals': [len(h_own_goals), len(a_own_goals)],
        'xG': [h_xg, a_xg]
    }

    summary_df = pd.DataFrame(summary_data)
    player_df = summarize_player_shots(df)
    return summary_df, player_df, home_shots_df, away_shots_df

def xgFlow(ax, df, hteam, ateam, team1_facecolor, team2_facecolor, text_color, background, font_prop):
    # Combine and sort shots

    mask1 = ((df['teamName'] == hteam)) & ((df['type'] == 'Goal') | (df['type'] == 'MissedShots') | (df['type'] == 'SavedShot') | (df['type'] == 'ShotOnPost'))
    mask2 = ((df['teamName'] == ateam)) & ((df['type'] == 'Goal') | (df['type'] == 'MissedShots') | (df['type'] == 'SavedShot') | (df['type'] == 'ShotOnPost'))

    df['xG'] = df['xG'].fillna(0)

    home_shots_df = df[mask1]
    home_shots_df.reset_index(drop=True, inplace=True)

    away_shots_df = df[mask2]
    away_shots_df.reset_index(drop=True, inplace=True)

    home_shots_df = home_shots_df.sort_values(by='eventId')
    away_shots_df = away_shots_df.sort_values(by='eventId')

    dfhome_xG = home_shots_df[['playerName', 'minute', 'xG', 'type', 'situation', 'teamName']]
    dfaway_xG = away_shots_df[['playerName', 'minute', 'xG', 'type', 'situation', 'teamName']]
    df_xG = pd.concat([dfhome_xG, dfaway_xG], ignore_index=True)

    df_xG['minute'] = pd.to_numeric(df_xG['minute'], errors='coerce')
    df_xG['cumulative_xG'] = df_xG.groupby('teamName')['xG'].cumsum()

    # Set background
    ax.set_facecolor(background)

    # Team color map
    team_colors = {hteam: team1_facecolor, ateam: team2_facecolor}

    # Determine full match duration
    full_time = int(max(90, df_xG['minute'].max()))

    for team in df_xG['teamName'].unique():
        team_df = df_xG[df_xG['teamName'] == team].copy()

        # Add minute 0
        initial_row = pd.DataFrame([{
            'minute': 0,
            'xG': 0,
            'cumulative_xG': 0,
            'type': 'None',
            'playerName': '',
            'situation': '',
            'teamName': team
        }])

        team_df = pd.concat([initial_row, team_df], ignore_index=True)

        # Group by minute, keeping last xG event per minute
        team_df = team_df.sort_values('minute').groupby('minute').last().reset_index()

        # Build full grid of minutes and merge
        minute_grid = pd.DataFrame({'minute': np.arange(0, full_time + 1)})
        team_df = pd.merge(minute_grid, team_df, on='minute', how='left')

        # Forward fill to ensure continuous steps
        team_df['cumulative_xG'] = team_df['cumulative_xG'].ffill().fillna(0)

        # Plot step line
        ax.plot(
            team_df['minute'],
            team_df['cumulative_xG'],
            label=team,
            drawstyle='steps-post',
            c=team_colors[team],
            linewidth=5,
            zorder=2
        )

    # Plot goals with markers and labels
    for team in df_xG['teamName'].unique():
        goals = df_xG[(df_xG['teamName'] == team) & (df_xG['type'] == 'Goal')].to_dict(orient='records')

        for goal in goals:
            ax.scatter(
                goal['minute'],
                goal['cumulative_xG'],
                c=team_colors[team],
                edgecolor=text_color,
                s=800,
                marker='*',
                zorder=5
            )

            # Calculate vertical offset for text
            ymin, ymax = ax.get_ylim()
            offset_y = 0.08 * (ymax - ymin)

            ax.text(
                goal['minute'] + 1,
                goal['cumulative_xG'] + offset_y,
                f"{goal['playerName']}\nxG: {round(goal['xG'], 2)}",
                ha='center',
                va='center',
                c=background,
                fontproperties=font_prop,
                fontsize=20,
                zorder=10,
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor=text_color,  # or a neutral/light color
                    edgecolor=background,
                    linewidth=1.5,
                    alpha=0.9
                )
            )

    # X and Y axis formatting
    ax.set_xticks([0, 45, 90])
    ax.set_xticklabels(['0\'', '45\'', '90\''])
    ax.set_ylabel('Cumulative xG', fontfamily='monospace', fontproperties=font_prop, fontsize=22, color=text_color)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(text_color)

    ax.tick_params(axis='x', colors=text_color, labelsize=15)
    ax.tick_params(axis='y', colors=text_color, labelsize=15)

    # Half-time divider
    ax.axvline(x=45, color=text_color, linestyle='--', linewidth=1, alpha=0.5)

    #ax.legend(prop=font_prop, fontsize=20, facecolor=background)

@st.cache_data(ttl=600)
def get_passes_df(df):
    df1 = df[~df['type'].str.contains('SubstitutionOn|FormationChange|FormationSet|Card')]
    df = df1
    df.loc[:, "receiver"] = df["playerId"].shift(-1)
    passes_ids = df.index[df['type'] == 'Pass']
    df_passes = df.loc[passes_ids, ["index", "x", "y","minute", "endX", "endY", "teamName", "playerId", "receiver", "type", "outcomeType","isFirstEleven","playerName","xT","passKey"]].copy()
    id_to_name = dict(zip(df_passes['playerId'], df_passes['playerName']))
    df_passes['receiverName'] = df_passes['receiver'].map(id_to_name)

    return df_passes

def get_initials(name):
    if pd.isna(name):
        return ''
    parts = name.strip().split()
    initials = [p[0].upper() + '.' for p in parts if p]
    return ''.join(initials)

def get_pass_matrix(passes_df, teamName):
    team_passes = passes_df[passes_df["teamName"] == teamName].copy()

    # Clean and convert names to initials
    team_passes['playerName'] = team_passes['playerName'].apply(unidecode)
    team_passes['playerName'] = team_passes['playerName'].apply(get_initials)


    # Build mapping AFTER cleaning
    id_to_name = dict(zip(team_passes['playerId'], team_passes['playerName']))

    # Map receiverId to initials using cleaned playerName mapping
    team_passes['receiverName'] = team_passes['receiver'].map(id_to_name)

    # Drop any rows with missing receiverName (if any)
    team_passes = team_passes.dropna(subset=['receiverName'])

    # Create pass matrix
    pass_matrix = team_passes.groupby(['playerName', 'receiverName']).size().unstack(fill_value=0)

    return pass_matrix

def filter_passes_for_subwindow(match_df, passes_df, teamName, minute_start, minute_end):
    # Get starting players
    starting_players = match_df[
        (match_df['teamName'] == teamName) &
        (match_df['isFirstEleven'] == True)
    ]['playerId'].unique().tolist()

    # Players subbed on before the end of this window
    subs_on = match_df[
        (match_df['teamName'] == teamName) &
        (match_df['type'] == 'SubstitutionOn') &
        (match_df['minute'] < minute_end)
    ]['playerId'].tolist()

    # Players subbed off before the start of this window
    subs_off = match_df[
        (match_df['teamName'] == teamName) &
        (match_df['type'] == 'SubstitutionOff') &
        (match_df['minute'] < minute_start)
    ]['playerId'].tolist()

    # Calculate who is on the pitch in this time window
    valid_players = set(starting_players + subs_on) - set(subs_off)

    # Filter the passes
    passes_filtered = passes_df[
        (passes_df['teamName'] == teamName) &
        (passes_df['minute'] >= minute_start) &
        (passes_df['minute'] < minute_end) &
        (passes_df['playerId'].isin(valid_players)) &
        (passes_df['receiver'].isin(valid_players))
    ]
    return passes_filtered

def get_passes_between_df(teamName, passes_df):
    passes_df = passes_df[passes_df["teamName"] == teamName].copy()
    # Group by playerId and aggregate pass location + isFirstEleven
    average_locs_and_count_df = (
        passes_df.groupby('playerId').agg({
            'x': 'median',
            'y': 'median',
            'playerId': 'count',
            'playerName': 'first',
            'isFirstEleven': 'first'
        })
    )

    average_locs_and_count_df.columns = ['pass_avg_x', 'pass_avg_y', 'count', 'playerName', 'isFirstEleven']
    average_locs_and_count_df.index.name = 'playerId'

    average_locs_and_count_df['playerName'] = average_locs_and_count_df['playerName'].apply(unidecode)

    # Build pass combinations between players (order-independent)
    passes_player_ids_df = passes_df[['index', 'playerId', 'receiver', 'teamName']].copy()
    passes_player_ids_df['pos_max'] = passes_player_ids_df[['playerId', 'receiver']].max(axis=1)
    passes_player_ids_df['pos_min'] = passes_player_ids_df[['playerId', 'receiver']].min(axis=1)

    passes_between_df = (
        passes_player_ids_df
        .groupby(['pos_min', 'pos_max'])['index']
        .count()
        .reset_index()
        .rename(columns={'index': 'pass_count'})
    )

    # Merge in player locations (start and end)
    passes_between_df = passes_between_df.merge(
        average_locs_and_count_df, left_on='pos_min', right_index=True
    ).merge(
        average_locs_and_count_df, left_on='pos_max', right_index=True, suffixes=['', '_end']
    )

    return passes_between_df, average_locs_and_count_df

def calculate_centralization_index(teamName, passes_df):

    # Filter passes within the given time range and team
    passes_df = passes_df[(passes_df["teamName"] == teamName)]

    # Calculate number of passes made by each player
    player_passes_count = passes_df["playerId"].value_counts()

    # Get the total number of passes made by the team
    total_passes = player_passes_count.sum()

    # Get the maximal number of passes made by a single player
    max_passes = player_passes_count.max()

    # Number of players in the team
    num_players = len(player_passes_count)

    # Calculate the denominator (Total passes * (Number of players - 1))
    denominator = total_passes * 10

    # Calculate the numerator (sum of (Max passes - Player passes))
    numerator = sum(max_passes - player_passes_count)

    # Calculate the centralization index
    centralization_index = numerator / denominator if denominator != 0 else 0

    return centralization_index

def pass_network_visualization(ax,df, passes_between_df, average_locs_and_count_df,text_color,background, col, teamName,MAX_LINE_WIDTH,flipped,ci,font_prop):
    MAX_MARKER_SIZE = 6000
    passes_between_df['width'] = (passes_between_df.pass_count / passes_between_df.pass_count.max()) * MAX_LINE_WIDTH
    average_locs_and_count_df['marker_size'] = (average_locs_and_count_df['count']/ average_locs_and_count_df['count'].max() * MAX_MARKER_SIZE) #You can plot variable size of each player's node according to their passing volume, in the plot using this
    MIN_TRANSPARENCY = 0.55
    MAX_TRANSPARENCY = 0.95
    color = np.array(to_rgba(col))
    color = np.tile(color, (len(passes_between_df), 1))
    c_transparency = passes_between_df.pass_count / passes_between_df.pass_count.max()
    c_transparency = (c_transparency * (MAX_TRANSPARENCY - MIN_TRANSPARENCY)) + MIN_TRANSPARENCY
    color[:, 3] = c_transparency

    pitch = Pitch(pitch_type='uefa', corner_arcs=True, pitch_color=background, line_color=text_color, linewidth=1)
    pitch.draw(ax=ax)
    ax.set_aspect('equal')
    
    if flipped==True:
        ax.invert_xaxis()
        ax.invert_yaxis()
    
    # Plotting those lines between players
    pitch.lines(passes_between_df.pass_avg_x, passes_between_df.pass_avg_y, passes_between_df.pass_avg_x_end, passes_between_df.pass_avg_y_end,
                             lw=passes_between_df.width, color=text_color, zorder=2,alpha=0.5, ax=ax)

    # Plotting the player nodes
    for index, row in average_locs_and_count_df.iterrows():
        player_initials = get_initials(row['playerName'])
        pitch.scatter(row['pass_avg_x'], row['pass_avg_y'], s=row['marker_size'], marker='o', color=background, edgecolor=col,
                                    linewidth=2, alpha=1,zorder=2, ax=ax)
        pitch.annotate(player_initials, xy=(row.pass_avg_x, row.pass_avg_y), c=text_color, ha='center', va='center', size=18,zorder=2, ax=ax)

            

    dfteam = df[df['teamName'] == teamName]
    df_xT = dfteam[((dfteam['type'] == 'Pass') | (dfteam['type'] == 'Carry')) & (dfteam['xT'] > 0)]
    cmap = LinearSegmentedColormap.from_list('custom_cmap', [background, col])
    
    bin_statistic = pitch.bin_statistic(df_xT.x, df_xT.y, statistic='count', bins=(20, 20))
    bin_statistic['statistic'] = gaussian_filter(bin_statistic['statistic'], 1)
    pcm = pitch.heatmap(bin_statistic, ax=ax, cmap=cmap, edgecolors=background,alpha=0.5,zorder=1)

    pitch.annotate(f'Centralization Index: {ci:.2f}', xy=(0, -4), ha='left', va='center', fontsize=30, color=text_color, fontproperties=font_prop, ax=ax)
    
    return

@st.cache_data(ttl=600)
def get_passing_stats(match_df, teamName):
    passes_df = match_df[(match_df['type'] == 'Pass') & (match_df['teamName'] == teamName)].copy()
    total_passes = passes_df[passes_df['teamName'] == teamName].shape[0]
    successful_passes = passes_df[(passes_df['teamName'] == teamName) & (passes_df['outcomeType'] == 'Successful')].shape[0]
    passing_accuracy = (successful_passes / total_passes) * 100
    final_third_passes = passes_df[(passes_df['teamName'] == teamName) & (passes_df['x'] < 75) & (passes_df['endX'] >= 75) & (passes_df['outcomeType'] == 'Successful')].shape[0]
    key_passes = passes_df[(passes_df['teamName'] == teamName) & (passes_df['passKey'] == True)].shape[0]
    crosses = passes_df[(passes_df['teamName'] == teamName) & (passes_df['qualifiers'].str.contains('Cross'))].shape[0]
    long_balls = passes_df[(passes_df['teamName'] == teamName) & (passes_df['qualifiers'].str.contains('Longball'))].shape[0]
    through_balls = passes_df[(passes_df['teamName'] == teamName) & (passes_df['qualifiers'].str.contains('Throughball'))].shape[0]
    progressive_passes = passes_df[(passes_df['teamName'] == teamName) & (passes_df['prog_pass']>=9.11) & (passes_df['x']>=35)].shape[0]
    pen_box_passes = passes_df[(passes_df['teamName'] == teamName) & (passes_df['endX']>=88.5) & (passes_df['endY']>=13.6) & (passes_df['endY']<=54.4)].shape[0]
    xT_by_Pass = passes_df['xT'].sum().round(3)

    result_df = pd.DataFrame({
        'Team': [teamName],
        'Total Passes': [int(total_passes)],
        'Passing Accuracy (%)': [round(passing_accuracy, 2)],
        'Final Third Entries': [int(final_third_passes)],
        'Key Passes': [int(key_passes)],
        'Crosses': [int(crosses)],
        'Long Balls': [int(long_balls)],
        'Through Balls': [int(through_balls)],
        'Progressive Passes': [int(progressive_passes)],
        'Pen Box Passes': [int(pen_box_passes)],
        'Expected Threat By Pass': [xT_by_Pass]
    })

    return result_df

def passmaps(ax, match_df,passes_df, hteam, hteam_color, ateam, ateam_color, background, text_color, passtype, selected_player=None, team_filter=None, pass_kde_mode="Passes Played"):
    """
    Draws passmaps for the selected team (home or away) on the same pitch.
    If team_filter is set, only that team's passes are shown.
    If selected_player is set, only that player's passes are shown for the selected team.
    Away team passes are inverted for visualization.
    """
    # Home team passes
    h_mask_passes = (match_df.type.isin(['Pass','TakeOn','Carry'])) & (match_df.teamName == hteam)
    hteam_passes_df = match_df.loc[h_mask_passes].copy()

    # Away team passes
    a_mask_passes = (match_df.type.isin(['Pass','TakeOn','Carry'])) & (match_df.teamName == ateam)
    ateam_passes_df = match_df.loc[a_mask_passes].copy()

    # Filter by selected team
    if team_filter == hteam:
        show_home = True
        show_away = False
    elif team_filter == ateam:
        show_home = False
        show_away = True
    else:
        show_home = True
        show_away = True

    # If a player is selected, filter to only their passes for the selected team
    if selected_player:
        if team_filter == hteam:
            hteam_passes_df = hteam_passes_df[hteam_passes_df['playerName'] == selected_player]
            ateam_passes_df = ateam_passes_df.iloc[0:0]  # Empty
        elif team_filter == ateam:
            ateam_passes_df = ateam_passes_df[ateam_passes_df['playerName'] == selected_player]
            hteam_passes_df = hteam_passes_df.iloc[0:0]  # Empty
        else:
            hteam_passes_df = hteam_passes_df[hteam_passes_df['playerName'] == selected_player]
            ateam_passes_df = ateam_passes_df[ateam_passes_df['playerName'] == selected_player]

    pitch = Pitch(pitch_type='uefa', half=False, corner_arcs=True, pitch_color=background,
                  line_zorder=2, line_color=text_color, linewidth=1)
    pitch.draw(ax=ax)
    
    ax.set_facecolor(background)

    
    # Filter passes by type
    def filter_passes(df, passtype):
        if passtype == 'Carries':
            return df[(df['type'] == 'Carry')]
        elif passtype == 'Crosses':
            return df[df['qualifiers'].str.contains('Cross', na=False) & (df['outcomeType'] == 'Successful')]
        elif passtype == 'Long Balls':
            return df[df['qualifiers'].str.contains('Longball', na=False) & (df['outcomeType'] == 'Successful')]
        elif passtype == 'Through Balls':
            return df[df['qualifiers'].str.contains('Throughball', na=False) & (df['outcomeType'] == 'Successful')]
        elif passtype == 'Dribbles':
            return df[(df['type'] == 'TakeOn')]
        else:
            return df[(df['outcomeType'] == 'Successful')]

    hteam_passes_df = filter_passes(hteam_passes_df, passtype)
    ateam_passes_df = filter_passes(ateam_passes_df, passtype)

    # Invert away team passes for visualization
    if show_away and not ateam_passes_df.empty:
        ateam_passes_df['x'] = pitch.dim.right - ateam_passes_df['x']
        ateam_passes_df['y'] = pitch.dim.top - ateam_passes_df['y']
        ateam_passes_df['endX'] = pitch.dim.right - ateam_passes_df['endX']
        ateam_passes_df['endY'] = pitch.dim.top - ateam_passes_df['endY']

    if not selected_player and passtype == 'All':
        if show_home and not hteam_passes_df.empty:
            hteam_passes_df = hteam_passes_df[hteam_passes_df['type'] == 'Pass']
            bins = (6, 4)
            cmap = LinearSegmentedColormap.from_list('custom_cmap', [background, hteam_color])
            bs_heatmap = pitch.bin_statistic(hteam_passes_df.x, hteam_passes_df.y, statistic='count', bins=bins)
            hm = pitch.heatmap(bs_heatmap, ax=ax, cmap=cmap)
            # plot the pass flow map with a single color ('black') and length of the arrow (5)
            fm = pitch.flow(hteam_passes_df.x, hteam_passes_df.y, hteam_passes_df.endX, hteam_passes_df.endY,
                            color=text_color, arrow_type='same',
                            arrow_length=5, bins=bins, ax=ax)
            
            pitch.arrows(5,-2,100,-2, width=3,
             headwidth=4, headlength=3, headaxislength=2,
             color=text_color, ax=ax)
        if show_away and not ateam_passes_df.empty:
            ateam_passes_df = ateam_passes_df[ateam_passes_df['type'] == 'Pass']
            bins = (6, 4)
            cmap = LinearSegmentedColormap.from_list('custom_cmap', [background, ateam_color])
            bs_heatmap = pitch.bin_statistic(ateam_passes_df.x, ateam_passes_df.y, statistic='count', bins=bins)
            hm = pitch.heatmap(bs_heatmap, ax=ax, cmap=cmap)
            # plot the pass flow map with a single color ('black') and length of the arrow (5)
            fm = pitch.flow(ateam_passes_df.x, ateam_passes_df.y, ateam_passes_df.endX, ateam_passes_df.endY,
                            color=text_color, arrow_type='same',
                            arrow_length=5, bins=bins, ax=ax)
            
            pitch.arrows(100,-2,5,-2, width=3,
             headwidth=4, headlength=3, headaxislength=2,
             color=text_color, ax=ax)

    # Plot home team passes
    elif selected_player and passtype != 'All':  
        if show_home:
            if passtype == 'Dribbles':
                hteam_dribbles_df = hteam_passes_df[hteam_passes_df['type'] == 'TakeOn']
                for _, row in hteam_dribbles_df.iterrows():
                    if row.get('outcomeType') == 'Successful':
                        mcolor = hteam_color
                    else:
                        mcolor = 'grey'
                    pitch.scatter(row.x, row.y, marker='o', s=500, color=mcolor, edgecolor=text_color, linewidth=2, zorder=3, ax=ax)

            elif passtype == 'Carries':
                hteam_passes_df = hteam_passes_df[(hteam_passes_df['type'] == 'Carry') & (hteam_passes_df['prog_carry'] >= 5)]
                for _, row in hteam_passes_df.iterrows():
                    pitch.arrows(row.x,row.y, row.endX, row.endY, width=5,
                                 headwidth=4, headlength=3, headaxislength=2,
                                 color=hteam_color, alpha=0.8, zorder=2, ax=ax)

            else:
                for _, row in hteam_passes_df.iterrows():
                    marker = '*' if row.get('passKey', False) else 'o'
                    size = 1000 if row.get('passKey', False) else 200
                    color = 'green' if row.get('assist', False) else hteam_color
                    linewidth = 5 if row.get('assist', False) else 1
                    pitch.lines(row.x, row.y, row.endX, row.endY, lw=linewidth, color=color, alpha=0.8, zorder=2, ax=ax)
                    pitch.scatter(row.endX, row.endY, marker=marker, s=size, color=color, edgecolor=text_color, linewidth=2, zorder=3, ax=ax)

        # Plot away team passes (inverted)
        if show_away:
            if passtype == 'Dribbles':
                ateam_dribbles_df = ateam_passes_df[ateam_passes_df['type'] == 'TakeOn']
                for _, row in ateam_dribbles_df.iterrows():
                    if row.get('outcomeType') == 'Successful':
                        mcolor = ateam_color
                    else:
                        mcolor = 'grey'
                    pitch.scatter(row.x, row.y, marker='o', s=500, color=mcolor, edgecolor=text_color, linewidth=2, zorder=3, ax=ax)

            elif passtype == 'Carries':
                ateam_passes_df = ateam_passes_df[(ateam_passes_df['type'] == 'Carry') & (ateam_passes_df['prog_carry'] >= 5)]
                for _, row in ateam_passes_df.iterrows():
                    pitch.arrows(row.x,row.y, row.endX, row.endY, width=5,
                                 headwidth=4, headlength=3, headaxislength=2,
                                 color=ateam_color, alpha=0.8, zorder=2, ax=ax)
            else:
                for _, row in ateam_passes_df.iterrows():
                    marker = '*' if row.get('passKey', False) else 'o'
                    size = 1000 if row.get('passKey', False) else 200
                    color = 'green' if row.get('assist', False) else ateam_color
                    linewidth = 5 if row.get('assist', False) else 1
                    pitch.lines(row.x, row.y, row.endX, row.endY, lw=linewidth, color=color, alpha=0.8, zorder=2, ax=ax)
                    pitch.scatter(row.endX, row.endY, marker=marker, s=size, color=color, edgecolor=text_color, linewidth=2, zorder=3, ax=ax)
    
    elif passtype == "All" and selected_player:
        # Ensure receiverName exists in passes_df
        hteam_passes_df = passes_df[passes_df['teamName'] == hteam].copy()
        ateam_passes_df = passes_df[passes_df['teamName'] == ateam].copy()
        if "receiverName" not in hteam_passes_df.columns:
            # Map receiverId to playerName
            id_to_name = dict(zip(hteam_passes_df['playerId'], hteam_passes_df['playerName']))
            hteam_passes_df['receiverName'] = hteam_passes_df['receiver'].map(id_to_name)
        if "receiverName" not in ateam_passes_df.columns:
            id_to_name = dict(zip(ateam_passes_df['playerId'], ateam_passes_df['playerName']))
            ateam_passes_df['receiverName'] = ateam_passes_df['receiver'].map(id_to_name)

        if team_filter == hteam:
            if pass_kde_mode == "Passes Played":
                kde_df = hteam_passes_df[hteam_passes_df['playerName'] == selected_player]
                x_vals = kde_df['x']
                y_vals = kde_df['y']
            else:  # Passes Received
                kde_df = hteam_passes_df[hteam_passes_df['receiverName'] == selected_player]
                x_vals = kde_df['endX']
                y_vals = kde_df['endY']
            if not kde_df.empty:
                cmap = LinearSegmentedColormap.from_list('custom_cmap', [background, hteam_color])
                pitch.kdeplot(x=x_vals, y=y_vals, ax=ax, fill=True, cmap=cmap, n_levels=10, bw_adjust=1, weights=None, thresh=0.01, zorder=0)
        elif team_filter == ateam:
            if pass_kde_mode == "Passes Played":
                kde_df = ateam_passes_df[ateam_passes_df['playerName'] == selected_player]
                x_vals = kde_df['x']
                y_vals = kde_df['y']
            else:  # Passes Received
                kde_df = ateam_passes_df[ateam_passes_df['receiverName'] == selected_player]
                x_vals = kde_df['endX']
                y_vals = kde_df['endY']
            if not kde_df.empty:
                cmap = LinearSegmentedColormap.from_list('custom_cmap', [background, ateam_color])
                pitch.kdeplot(x=105-x_vals, y=68-y_vals, ax=ax, fill=True, cmap=cmap, n_levels=10, bw_adjust=1, weights=None, thresh=0.01, zorder=0)
        
    else:
        # Plot all passes for both teams
        if show_home and not hteam_passes_df.empty:
            if passtype == 'Dribbles':
                hteam_dribbles_df = hteam_passes_df[hteam_passes_df['type'] == 'TakeOn']
                for _, row in hteam_dribbles_df.iterrows():
                    if row.get('outcomeType') == 'Successful':
                        mcolor = hteam_color
                    else:
                        mcolor = 'grey'
                    pitch.scatter(row.x, row.y, marker='o', s=500, color=mcolor, edgecolor=text_color, linewidth=2, zorder=3, ax=ax)

            elif passtype == 'Carries':
                hteam_passes_df = hteam_passes_df[(hteam_passes_df['type'] == 'Carry') & (hteam_passes_df['prog_carry'] >= 5)]
                for _, row in hteam_passes_df.iterrows():
                    pitch.arrows(row.x,row.y, row.endX, row.endY, width=5,
                                 headwidth=4, headlength=3, headaxislength=2,
                                 color=hteam_color, alpha=0.8, zorder=2, ax=ax)

            else:
                for _, row in hteam_passes_df.iterrows():
                    marker = '*' if row.get('passKey', False) else 'o'
                    size = 1000 if row.get('passKey', False) else 200
                    color = 'green' if row.get('assist', False) else hteam_color
                    linewidth = 5 if row.get('assist', False) else 1
                    pitch.lines(row.x, row.y, row.endX, row.endY, lw=linewidth, color=color, alpha=0.8, zorder=2, ax=ax)
                    pitch.scatter(row.endX, row.endY, marker=marker, s=size, color=color, edgecolor=text_color, linewidth=2, zorder=3, ax=ax)

        if show_away and not ateam_passes_df.empty:
            if passtype == 'Dribbles':
                ateam_dribbles_df = ateam_passes_df[ateam_passes_df['type'] == 'TakeOn']
                for _, row in ateam_dribbles_df.iterrows():
                    if row.get('outcomeType') == 'Successful':
                        mcolor = ateam_color
                    else:
                        mcolor = 'grey'
                    pitch.scatter(row.x, row.y, marker='o', s=500, color=mcolor, edgecolor=text_color, linewidth=2, zorder=3, ax=ax)
            elif passtype == 'Carries':
                ateam_passes_df = ateam_passes_df[(ateam_passes_df['type'] == 'Carry') & (ateam_passes_df['prog_carry'] >= 5)]
                for _, row in ateam_passes_df.iterrows():
                    pitch.arrows(row.x,row.y, row.endX, row.endY, width=5,
                                 headwidth=4, headlength=3, headaxislength=2,
                                 color=ateam_color, alpha=0.8, zorder=2, ax=ax)
            else:
                for _, row in ateam_passes_df.iterrows():
                    marker = '*' if row.get('passKey', False) else 'o'
                    size = 1000 if row.get('passKey', False) else 200
                    color = 'green' if row.get('assist', False) else ateam_color
                    linewidth = 5 if row.get('assist', False) else 1
                    pitch.lines(row.x, row.y, row.endX, row.endY, lw=linewidth, color=color, alpha=0.8, zorder=2, ax=ax)
                    pitch.scatter(row.endX, row.endY, marker=marker, s=size, color=color, edgecolor=text_color, linewidth=2, zorder=3, ax=ax)
    # Top passers for each team (if not filtering by player)
    if not selected_player:
        player_pass_counts_h = hteam_passes_df.groupby(['playerName']).size().reset_index(name='Count')
        top_passers_h = player_pass_counts_h.sort_values(['Count'], ascending=[False]).head(5).reset_index(drop=True)
        player_pass_counts_a = ateam_passes_df.groupby(['playerName']).size().reset_index(name='Count')
        top_passers_a = player_pass_counts_a.sort_values(['Count'], ascending=[False]).head(5).reset_index(drop=True)
    else:
        top_passers_h = hteam_passes_df.groupby(['playerName']).size().reset_index(name='Count')
        top_passers_a = ateam_passes_df.groupby(['playerName']).size().reset_index(name='Count')

 

    return top_passers_h, top_passers_a
   
def plot_duels_by_type(ax, df, team1_name, team2_name, duel_type,
                       team1_color, team2_color, background, text_color,font_prop):

    # Define duel type filters
    offensive_types = ['TakeOn', 'GoodSkill', 'ShieldBallOpp']
    defensive_types = ['Tackle', 'Challenge', 'BallRecovery', 'BlockedPass']

    # Filter data by duel type
    if duel_type == 'Total':
        df_duel = df[
            df['type'].isin(offensive_types + defensive_types) |
            (df['duelAerialWon'] == True) |
            (df['duelAerialLost'] == True)
        ]
    elif duel_type == 'Offensive':
        df_duel = df[df['type'].isin(offensive_types)]
    elif duel_type == 'Defensive':
        df_duel = df[df['type'].isin(defensive_types)]
    elif duel_type == 'Aerial':
        df_duel = df[(df['duelAerialWon'] == True) | (df['duelAerialLost'] == True)]
    else:
        raise ValueError("Invalid duel type selected.")

    # Create team-specific dataframes
    df1 = df_duel[(df_duel['teamName'] == team1_name) & (df_duel['outcomeType'] == 'Successful')].copy()
    df2 = df_duel[(df_duel['teamName'] == team2_name) & (df_duel['outcomeType'] == 'Successful')].copy()

    # Flip team2 coordinates to match attacking direction
    df2['x'] = 105 - df2['x']
    df1['y'] = 68 - df1['y']

    # Setup pitch
    pitch = Pitch(pitch_type='uefa', pitch_color=background, line_color=text_color,
                  linewidth=2, line_zorder=3)
    pitch.draw(ax=ax)

    # Bin settings
    bins_x, bins_y = 6, 5
    bin_w, bin_h = 105 / bins_x, 68 / bins_y

    # Bin duels by zone
    stat1 = pitch.bin_statistic(df1['x'], df1['y'], statistic='count', bins=(bins_x, bins_y))['statistic']
    stat2 = pitch.bin_statistic(df2['x'], df2['y'], statistic='count', bins=(bins_x, bins_y))['statistic']

    # Draw duel bars in each bin
    for j in range(bins_y):  # row (y)
        for i in range(bins_x):  # column (x)
            x0 = i * bin_w
            y0 = j * bin_h
            t1 = stat1[j, i]
            t2 = stat2[j, i]
            total = t1 + t2
            if total == 0:
                continue
            r1 = t1 / total
            r2 = t2 / total

            # Draw rectangles
            ax.add_patch(Rectangle((x0, y0), bin_w * r1, bin_h, color=team1_color, alpha=0.7, zorder=3))
            ax.add_patch(Rectangle((x0 + bin_w * r1, y0), bin_w * r2, bin_h, color=team2_color, alpha=0.7, zorder=3))

            # Text inside bins
            ax.text(x0 + bin_w/2, y0 + bin_h/2, f"{int(t1)}/{int(t2)}",
                    ha='center', va='center', fontsize=20, color=text_color, fontproperties=font_prop, zorder=4)

    # Direction arrows
    ax.text(0,  -3, 'Attacking Direction--->', color=team1_color, fontsize=22, ha='left', va='center', fontproperties=font_prop)
    ax.text(105, -3, '<---Attacking Direction', color=team2_color, fontsize=22, ha='right', va='center', fontproperties=font_prop)

    # Dashed grid overlay
    for i in range(1, bins_x):
        ax.vlines(i * bin_w, ymin=0, ymax=68, color=background, lw=2, ls='--', zorder=5)
    for j in range(1, bins_y):
        ax.hlines(j * bin_h, xmin=0, xmax=105, color=background, lw=2, ls='--', zorder=5)

    # Get top 5 duel winners for each team
    if 'playerName' in df_duel.columns:
        top_team1 = (
            df1.groupby('playerName')
            .size()
            .reset_index(name='DuelsWon')
            .sort_values(by='DuelsWon', ascending=False)
            .head(5)
        )

        top_team2 = (
            df2.groupby('playerName')
            .size()
            .reset_index(name='DuelsWon')
            .sort_values(by='DuelsWon', ascending=False)
            .head(5)
        )
    else:
        top_team1 = pd.DataFrame(columns=['HomePlayerName', 'HomeDuelsWon'])
        top_team2 = pd.DataFrame(columns=['AwayPlayerName', 'AwayDuelsWon'])

    return top_team1, top_team2

def get_defensive_action_df(df):
    # filter only defensive actions
    defensive_actions_ids = df.index[
        ((df['type'] == 'Aerial') & (df['qualifiers'].str.contains('Defensive')) |
        (df['type'] == 'BallRecovery') |
        (df['type'] == 'BlockedPass') |
        (df['type'] == 'Challenge') |
        (df['type'] == 'Clearance') |
        (df['type'] == 'Error') |
        (df['type'] == 'Foul') |
        (df['type'] == 'Interception') |
        (df['type'] == 'Tackle'))
        & (df['outcomeType'] == 'Successful')
    ]
    
    cols_needed = ["index", "x", "y", "teamName", "playerId", "type", "outcomeType",
                   "playerName", "minute", "second", "situation"]  # ✅ include time & context

    df_defensive_actions = df.loc[defensive_actions_ids, cols_needed]
    return df_defensive_actions

def calculate_event_types(dataframe, event_types=None):
    # Group by 'teamName' and 'type', then count occurrences
    event_counts = dataframe.groupby(['teamName', 'type']).size().reset_index(name='count')
    
    # If event_types is provided, filter the event_counts DataFrame
    if event_types is not None:
        event_counts = event_counts[event_counts['type'].isin(event_types)]
    
    # Create a dictionary to hold the results
    results = {}
    
    # Populate the dictionary with team names and their event types and counts
    for team in event_counts['teamName'].unique():
        team_data = event_counts[event_counts['teamName'] == team]
        results[team] = {
            'types': team_data['type'].tolist(),
            'counts': team_data['count'].tolist()
        }
    
    return results

def get_da_count_df(team_name, defensive_actions_df, players_df):
    defensive_actions_df = defensive_actions_df[defensive_actions_df["teamName"] == team_name]
    # add column with first eleven players only
    defensive_actions_df = defensive_actions_df.merge(players_df[["playerId", "isFirstEleven"]], on='playerId', how='left')
    # calculate mean positions for players
    average_locs_and_count_df = (defensive_actions_df.groupby('playerId').agg({'x': ['median'], 'y': ['median', 'count']}))
    average_locs_and_count_df.columns = ['x', 'y', 'count']
    #average_locs_and_count_df = average_locs_and_count_df.merge(players_df[['playerId', 'name', 'shirtNo', 'position', 'isFirstEleven']], on='playerId', how='left')
    average_locs_and_count_df = average_locs_and_count_df.set_index('playerId')

    return  average_locs_and_count_df

def defensive_block(ax,df, team_name, col,background,text_color,flipped=True):
    defensive_actions_df = get_defensive_action_df(df)
    pitch = Pitch(pitch_type='uefa', pitch_color=background, line_color=text_color, linewidth=1.5, line_zorder=2, corner_arcs=True,
                  positional=True, shade_middle=True, positional_color=text_color, shade_color=text_color, shade_alpha=0.1, positional_alpha=0.5)
    pitch.draw(ax=ax)
    ax.set_facecolor(background)

    color = np.array(to_rgba(col))
    cmap = LinearSegmentedColormap.from_list("Flamingo - 100 colors", [background, col], N=500)
    bin_statistic = pitch.bin_statistic_positional(defensive_actions_df.x, defensive_actions_df.y, statistic='count',
                                               positional='full', normalize=True)
    pitch.heatmap_positional(bin_statistic, ax=ax, cmap=cmap, edgecolors=text_color)
    path_eff = [path_effects.Stroke(linewidth=3, foreground='grey'), path_effects.Normal()]
    #pitch.scatter(defensive_actions_df.x, defensive_actions_df.y, c='black',marker='*', s=2,alpha=0.5, ax=ax)
    labels = pitch.label_heatmap(bin_statistic, color=text_color, fontsize=22,
                                ax=ax, ha='center', va='center',
                                str_format='{:.0%}', path_effects=path_eff)



    if flipped == True:
        ax.invert_xaxis()
        ax.invert_yaxis()

def get_defensive_action_distribution_by_type(defensive_actions_df, zone='All', halves='All'):
    """
    Returns a DataFrame with players as rows and defensive action types as columns.
    Column names include marker symbols.
    """
    df = get_defensive_action_df(defensive_actions_df)

    # Define zones
    def classify_zone(x):
        if x > 75:
            return "Attacking Third"
        elif x > 30:
            return "Middle Third"
        else:
            return "Defensive Third"

    df["zone"] = df["x"].apply(classify_zone)

    # Filter by zone if specified
    if zone != "All":
        df = df[df["zone"] == zone]

    # Group by player and action type
    action_counts = (
        df.groupby(["playerName", "type"])
        .size()
        .reset_index(name="count")
    )

    # Pivot so types are columns
    action_distribution = action_counts.pivot_table(
        index=["playerName"],
        columns="type",
        values="count",
        fill_value=0
    ).reset_index()

    # Define marker mapping
    marker_mapping = {
        "Aerial": "x",
        "BallRecovery": "o",
        "Challenge": "^",
        "Interception": "+",
        "Tackle": "*",
        "Clearance": ".",
        "Foul": "!",
        "BlockedPass": "#",
        "Error": "E"
    }

    # Rename columns to include marker types
    new_columns = {
        col: f"{col} ({marker_mapping[col]})"
        for col in action_distribution.columns
        if col in marker_mapping
    }

    action_distribution = action_distribution.rename(columns=new_columns)

    return action_distribution


def defensive_block_with_player_actions(ax, df, team_name, col, background, text_color,font_prop,
                                        flipped=True, selected_player_name=None):
    defensive_actions_df = get_defensive_action_df(df)
    defensive_actions_team_df = defensive_actions_df[defensive_actions_df["teamName"] == team_name]

    pitch = Pitch(
        pitch_type='uefa',
        pitch_color=background,
        line_color=text_color,
        linewidth=1,
        line_zorder=1,
        corner_arcs=True,
        positional=True,
        shade_middle=False,
        positional_color=text_color,
        shade_color=text_color,
        shade_alpha=0.1,
        positional_alpha=0.4
    )
    pitch.draw(ax=ax)
    ax.set_facecolor(background)
    if selected_player_name == None:
        # Positional heatmap
        cmap = LinearSegmentedColormap.from_list("Flamingo - 100 colors", [background, col], N=500)
        bin_statistic = pitch.bin_statistic_positional(
            defensive_actions_team_df.x,
            defensive_actions_team_df.y,
            statistic='count',
            positional='full',
            normalize=True
        )
        pitch.heatmap_positional(bin_statistic, ax=ax, cmap=cmap, edgecolors=text_color)

        path_eff = [path_effects.Stroke(linewidth=3, foreground='grey'), path_effects.Normal()]
        pitch.label_heatmap(
            bin_statistic,
            color=text_color,
            fontsize=22,
            ax=ax,
            ha='center',
            va='center',
            str_format='{:.0%}',
            path_effects=path_eff
        )

    # If player is selected, highlight their defensive actions
    elif selected_player_name:
        player_events = defensive_actions_team_df[defensive_actions_team_df["playerName"] == selected_player_name]

        for _, row in player_events.iterrows():
            marker_style = {
                "Aerial": 'x',
                "BallRecovery": 'o',
                "Challenge": '^',
                "Interception": '+',
                "Tackle": '*',
            }.get(row['type'], '.')

            pitch.scatter(
                row.x,
                row.y,
                s=800,
                marker=marker_style,
                color=text_color,
                edgecolors=col,
                linewidth=2,
                alpha=0.9,
                ax=ax,
                zorder=3
            )

        pitch.scatter(1,-2, s=400, marker='x', color=text_color, edgecolors=col, linewidth=2, alpha=0.9, ax=ax, zorder=3)
        pitch.annotate('Aerial',xy=(7,-2), c=text_color, ha='center', va='center', size=22, fontproperties=font_prop, ax=ax)
        pitch.scatter(15,-2, s=800, marker='o', color=text_color, edgecolors=col, linewidth=2, alpha=0.9, ax=ax, zorder=3)
        pitch.annotate('Ball Recovery',xy=(25,-2), c=text_color, ha='center', va='center', size=22, fontproperties=font_prop, ax=ax)
        pitch.scatter(36,-2, s=800, marker='^', color=text_color, edgecolors=col, linewidth=2, alpha=0.9, ax=ax, zorder=3)
        pitch.annotate('Challenge',xy=(44,-2), c=text_color, ha='center', va='center', size=22, fontproperties=font_prop, ax=ax)
        pitch.scatter(54,-2, s=800, marker='+', color=text_color, edgecolors=col, linewidth=2, alpha=0.9, ax=ax, zorder=3)
        pitch.annotate('Interception',xy=(64,-2), c=text_color, ha='center', va='center', size=22, fontproperties=font_prop, ax=ax)
        pitch.scatter(74,-2, s=800, marker='*', color=text_color, edgecolors=col, linewidth=2, alpha=0.9, ax=ax, zorder=3)
        pitch.annotate('Tackle',xy=(80,-2), c=text_color, ha='center', va='center', size=22, fontproperties=font_prop, ax=ax)


    if flipped:
        ax.invert_xaxis()
        ax.invert_yaxis()


def xT_momemtum(ax,df,team1_name,team2_name,team1_facecolor,team2_facecolor,background,text_color,font_prop):
    xT_data = df[((df['type'] == 'Pass') | (df['type'] == 'Carry')) & (df['outcomeType'] == 'Successful')]
    xT_data = xT_data[['xT', 'minute', 'second', 'teamName', 'type']]
    xT_data['xT_clipped'] = np.clip(xT_data['xT'], 0, 0.1)

    max_xT_per_minute = xT_data.groupby(['teamName', 'minute'])['xT_clipped'].max().reset_index()

    minutes = sorted(xT_data['minute'].unique())
    weighted_xT_sum = {
        team1_name: [],
        team2_name: []
    }
    momentum = []
    
    window_size = 3
    decay_rate = 0.1
    
    
    for current_minute in minutes:
        for team in weighted_xT_sum.keys():
            
            recent_xT_values = max_xT_per_minute[
                                                (max_xT_per_minute['teamName'] == team) & 
                                                (max_xT_per_minute['minute'] <= current_minute) & 
                                                (max_xT_per_minute['minute'] > current_minute - window_size)
                                            ]
            
            weights = np.exp(-decay_rate * (current_minute - recent_xT_values['minute'].values))
            weighted_sum = np.sum(weights * recent_xT_values['xT_clipped'].values)
            weighted_xT_sum[team].append(weighted_sum)
    
        momentum.append(weighted_xT_sum[team1_name][-1] - weighted_xT_sum[team2_name][-1])
    
    momentum_df = pd.DataFrame({
        'minute': minutes,
        'momentum': momentum
    })

    ax.set_facecolor(background)

    ax.tick_params(axis='x', colors='white')
    ax.margins(x=0)
    ax.set_xticks([0,15,30,45,60,75,90])
    ax.set_xticklabels([0,15,30,45,60,75,90], color=text_color, fontproperties=font_prop, fontsize=20)
    
    ax.tick_params(axis='y', which='both', left=False, right=False, labelleft=False)
    #ax.set_ylim(-0.5, 0.2)
    
    for spine in ['top', 'right', 'bottom', 'left']:
        ax.spines[spine].set_visible(False)
    
    momentum_df['smoothed_momentum'] = gaussian_filter1d(momentum_df['momentum'], sigma=0.2)
    ax.plot(momentum_df['minute'], momentum_df['smoothed_momentum'], color=text_color, linewidth=2, zorder=1)
    #ax.set_facecolor(background)
    
    ax.axhline(0, color=text_color, linestyle='--', linewidth=0.5)
    ax.fill_between(momentum_df['minute'], momentum_df['smoothed_momentum'], where=(momentum_df['smoothed_momentum'] > 0), color=team1_facecolor, alpha=0.9, interpolate=True)
    ax.fill_between(momentum_df['minute'], momentum_df['smoothed_momentum'], where=(momentum_df['smoothed_momentum'] < 0), color=team2_facecolor, alpha=0.9, interpolate=True) 
    
    ax.set_ylabel('xT', color=text_color,fontproperties=font_prop,fontsize=30)
    #ax.text(30,0.2,f'xT Momentum Flow', color='white', fontsize=25, fontproperties=font_prop)

    
    goals = df[df['type']=='Goal'][['minute', 'teamName','isOwnGoal']]
    goals.loc[(goals['teamName'] == team1_name) & (goals['isOwnGoal'] == True), 'teamName'] = team2_name
    goals.loc[(goals['teamName'] == team2_name) & (goals['isOwnGoal'] == True), 'teamName'] = team1_name
    # --- Dynamic marker and line placement ---
    # Get the y-value of the momentum line at each goal minute
    for _, row in goals.iterrows():
        goal_minute = row['minute']
        team = row['teamName']

        y_val_series = momentum_df.loc[momentum_df['minute'] == goal_minute, 'smoothed_momentum']
        if not y_val_series.empty:
            y_val = float(y_val_series.values[0])
        else:
            y_val = float(np.interp(goal_minute, momentum_df['minute'], momentum_df['smoothed_momentum']))

        # Draw a line from the edge (top for home, bottom for away) to the curve
        if team == team1_name:
            ax.vlines(goal_minute, 0.15, y_val, color=team1_facecolor, linestyle='-', linewidth=3, alpha=0.8, zorder=15)
            ax.scatter(goal_minute, 0.15, color=team1_facecolor, s=500, zorder=11, edgecolor='white', linewidth=2)
        else:
            ax.vlines(goal_minute, -0.15, y_val, color=team2_facecolor, linestyle='-', linewidth=3, alpha=0.8, zorder=15)
            ax.scatter(goal_minute, -0.15, color=team2_facecolor, s=500, zorder=11, edgecolor='white', linewidth=2)


def plot_ppda(pos_df, ax, team1_name, team2_name, team1_facecolor, team2_facecolor, background, text_color, font_prop):
    """
    Plot PPDA values over 15-minute intervals for both teams using possession-level data.

    Parameters
    ----------
    pos_df : pd.DataFrame
        DataFrame containing at least: 'teamName', 'oppositionTeamName', 'possession_id', 'sequence_id', 
        'minute', 'second', 'type', 'outcomeType'.
    """
    
    df = pos_df.copy()
    df['timestamp'] = df['minute'] * 60 + df['second']

    # Defensive actions
    def_actions = ['Interception', 'Tackle', 'Clearance', 'BlockedPass', 'BallRecovery', 'Challenge']

    # Assign time bins (0–15, 15–30, ..., 75–90)
    df['time_bin'] = ((df['timestamp'] // 900).replace([np.inf, -np.inf], np.nan).fillna(-1).astype(int))

    # Calculate possession-level stats
    def is_successful_def_action(row):
        return row['type'] in def_actions and (
            'outcomeType' not in row or pd.isna(row['outcomeType']) or row['outcomeType'] == 'Successful'
        )

    df['is_pass'] = df['type'] == 'Pass'
    df['is_def_action'] = df.apply(is_successful_def_action, axis=1)

    def add_opposition_team_name(df):
    # Get all teams per match
        match_teams = df.groupby('matchId')['teamName'].unique().to_dict()
        # Map opposition for each row
        def get_opposition(row):
            teams = match_teams.get(row['matchId'], [])
            return next((t for t in teams if t != row['teamName']), None)
        df['oppositionTeamName'] = df.apply(get_opposition, axis=1)
        return df
    df = add_opposition_team_name(df)

    # Aggregate possession-level data
    poss_summary = df.groupby('possession_id').agg(
        team=('teamName', 'first'),
        opposition=('oppositionTeamName', 'first'),
        passes=('is_pass', 'sum'),
        def_actions=('is_def_action', 'sum'),
        time_bin=('time_bin', 'first')
    ).reset_index()

    # Calculate PPDA: passes made by opposition / defensive actions
    ppda = poss_summary.groupby(['time_bin', 'opposition']).agg(
        total_passes=('passes', 'sum'),
        total_def_actions=('def_actions', 'sum')
    ).reset_index()

    ppda['PPDA'] = ppda['total_passes'] / ppda['total_def_actions']
    ppda['PPDA'] = ppda['PPDA'].replace([np.inf, -np.inf], np.nan).fillna(0)

    # Plotting
    ax.set_facecolor(background)
    # Fixed x-axis range for 0–90 minutes
    ax.set_xticks(range(0, 7))
    ax.set_xticklabels(['0', '15', '30', '45', '60', '75', '90'])
    ax.set_xlim(0, 6)

    for team, color in zip([team1_name, team2_name], [team1_facecolor, team2_facecolor]):
        team_data = ppda[ppda['opposition'] == team]
        ax.plot(team_data['time_bin'], team_data['PPDA'], marker='o', label=team, color=color, linewidth=6)

    ax.invert_yaxis()
    ax.tick_params(axis='x', colors=text_color, labelsize=16)
    ax.tick_params(axis='y', colors=text_color, labelsize=16)
    for spine in ax.spines.values():
        spine.set_color(text_color)
    
    ax.grid(alpha=0.3, color=text_color)
    ax.set_xlabel('Minute',fontproperties=font_prop, fontsize=18,  color=text_color)
    ax.set_ylabel('PPDA', fontproperties=font_prop, fontsize=18, color=text_color)

    return

def plot_turnovers(df, ax, team1_name, team2_name, team1_facecolor, team2_facecolor, background, text_color, font_prop, window_size=15):
    """
    Plots total turnovers (turnover + dispossessed) per team per 15-minute window as a line chart.
    X-axis: 0 to 90, no labels.
    """
    df = df.copy()
    df['timestamp'] = df['minute'] * 60 + df['second']
    df['time_bin'] = ((df['timestamp'] // (window_size * 60)).replace([np.inf, -np.inf], np.nan).fillna(-1).astype(int))

    # Count turnovers + dispossessed together
    df['total_turnover'] = df['turnover'].astype(int) + df['dispossessed'].astype(int)
    grouped = (
        df.groupby(['time_bin', 'teamName'])['total_turnover']
        .sum()
        .reset_index()
    )

    # Plotting
    ax.set_facecolor(background)
    x_bins = sorted(grouped['time_bin'].unique())
    x_vals = [i * window_size for i in x_bins]
    ax.set_xticks([0, 15, 30, 45, 60, 75, 90])
    ax.set_xlim(0, 90)
    ax.set_xticklabels(['0', '15', '30', '45', '60', '75', '90'])

    for team, color in zip([team1_name, team2_name], [team1_facecolor, team2_facecolor]):
        team_data = grouped[grouped['teamName'] == team]
        ax.plot(team_data['time_bin'] * window_size, team_data['total_turnover'], marker='o', label=team, color=color, linewidth=6)

    ax.set_xlabel('Minute', fontproperties=font_prop, fontsize=18, color=text_color)
    ax.set_ylabel('Turnovers', fontproperties=font_prop, fontsize=18, color=text_color)
    ax.grid(alpha=0.3, color=text_color)
    ax.set_facecolor(background)
    ax.tick_params(axis='x', colors=text_color, labelsize=16)
    ax.tick_params(axis='y', colors=text_color, labelsize=16)
    for spine in ax.spines.values():
        spine.set_color(text_color)
    #ax.legend(prop=font_prop, fontsize=14)
    return ax

def get_next_events_by_index(df, current_index, num_events, target_types=None):
    """
    Get the next consecutive rows based on DataFrame indices and filter by event type.
    Only process if the current event is of type 'Pass'.
    """
    # Check if the current event is a 'Pass'
    if df.loc[current_index, 'type'] != 'Pass':
        return []  # Return an empty list if the type is not 'Pass'

    # Get the valid range of indices for the next events
    max_index = len(df) - 1
    next_indices = [i for i in range(current_index + 1, current_index + 1 + num_events) if i <= max_index]
    
    # Fetch the rows using the valid indices
    next_events = df.iloc[next_indices].reset_index(drop=True)
    
    # Filter for relevant types, if provided
    if target_types:
        next_events = next_events[next_events['type'].isin(target_types)]
    
    return next_events.to_dict('records')

def extract_last_shot_coordinates(next_events):
    if next_events:
        # Filter out events that are shots (Shot types: 'SavedShot', 'MissedShot', 'ShotOnPost', 'Goal')
        shot_events = [event for event in next_events if event['type'] in ['SavedShot', 'MissedShots', 'ShotOnPost', 'Goal']]
        if shot_events:
            # Get the coordinates of the last shot event
            last_shot = shot_events[-1]
            return last_shot['x'], last_shot['y']
    return None, None  # Return None if no shots found

def plot_corners(corners,team1,team2,team1_color,team2_color):
    corners_1 = corners[(corners['side'] == 'Left') & (corners['teamName'] == team1)].copy()
    corners_2 = corners[(corners['side'] == 'Right')  & (corners['teamName'] == team1)].copy()
    corners_3 = corners[(corners['side'] == 'Left') & (corners['teamName'] == team2)].copy()
    corners_4 = corners[(corners['side'] == 'Right')  & (corners['teamName'] == team2)].copy()

    def process_corners(df):
        if df.empty:
            return pd.DataFrame({'x':[0],'endX':[0],'endY':[0], 'y':[0],'next_shot_x':[0],'next_shot_y':[0],'total_shots': [0], 'goals': [0], 'shots_ot': [0]}, index=pd.Index(['Empty'], name='type'))
        
        # Calculate the number of shots (next_events_type is not None)
        df['total_shots'] = df['next_events_type'].apply(
            lambda x: 1 if x is not None else 0
        )
        df['goals'] = df['next_events_type'].apply(
            lambda x: 1 if 'Goal' in (x if isinstance(x, list) else [x]) else 0
        )
        #df['shots_ot'] = df['next_events_type'].apply(
        #    lambda x: 1 if 'SavedShot' in (x if isinstance(x, list) else [x]) else 0
        #)
        df['shots_ot'] = df['next_events_type'].apply(
            lambda x: 1 if any(event in (x if isinstance(x, list) else [x]) for event in ['SavedShot', 'Goal']) else 0
        )

        
        return df

    # Process both sides
    corners_1 = process_corners(corners_1)
    corners_2 = process_corners(corners_2)
    corners_3 = process_corners(corners_3)
    corners_4 = process_corners(corners_4)

    # Now you can calculate the total number of shots and goals by corner type
    shots_by_corner_type_1 = corners_1.groupby('type')['total_shots'].sum()
    goals_by_corner_type_1 = corners_1.groupby('type')['goals'].sum()
    shots_ot_by_corner_type_1 = corners_1.groupby('type')['shots_ot'].sum()
    
    shots_by_corner_type_2 = corners_2.groupby('type')['total_shots'].sum()
    goals_by_corner_type_2 = corners_2.groupby('type')['goals'].sum()
    shots_ot_by_corner_type_2 = corners_2.groupby('type')['shots_ot'].sum()

    shots_by_corner_type_3 = corners_3.groupby('type')['total_shots'].sum()
    goals_by_corner_type_3 = corners_3.groupby('type')['goals'].sum()
    shots_ot_by_corner_type_3 = corners_3.groupby('type')['shots_ot'].sum()

    shots_by_corner_type_4 = corners_4.groupby('type')['total_shots'].sum()
    goals_by_corner_type_4 = corners_4.groupby('type')['goals'].sum()
    shots_ot_by_corner_type_4 = corners_4.groupby('type')['shots_ot'].sum()
    
    # Combine them to get a complete picture
    corner_summary_1 = pd.DataFrame({
        'total_shots': shots_by_corner_type_1,
        'goals': goals_by_corner_type_1,
        'shots_ot': shots_ot_by_corner_type_1
    })
    
    corner_summary_2 = pd.DataFrame({
        'total_shots': shots_by_corner_type_2,
        'goals': goals_by_corner_type_2,
        'shots_ot': shots_ot_by_corner_type_2
    })

    corner_summary_3 = pd.DataFrame({
        'total_shots': shots_by_corner_type_3,
        'goals': goals_by_corner_type_3,
        'shots_ot': shots_ot_by_corner_type_3
    })

    corner_summary_4 = pd.DataFrame({
        'total_shots': shots_by_corner_type_4,
        'goals': goals_by_corner_type_4,
        'shots_ot': shots_ot_by_corner_type_4
    })

    FIGWIDTH = 12
    FIGHEIGHT = 9
    NROWS = 2
    NCOLS = 2
    SPACE = 0
    MAX_GRID = 0.95
    
    pitch = VerticalPitch(pitch_type='uefa',pad_bottom=-15,line_color='white',goal_type='box', linewidth=0.5, half=True,
                          pitch_color=background)
    
    GRID_WIDTH, GRID_HEIGHT = pitch.grid_dimensions(figwidth=FIGWIDTH, figheight=FIGHEIGHT,
                                                    nrows=NROWS, ncols=NCOLS,
                                                    max_grid=MAX_GRID, space=SPACE)
    TITLE_HEIGHT = 0.01
    ENDNOTE_HEIGHT = 0
    
    fig, ax = pitch.grid(figheight=FIGHEIGHT, grid_width=GRID_WIDTH, grid_height=GRID_HEIGHT,
                         space=SPACE, ncols=NCOLS, nrows=NROWS, title_height=TITLE_HEIGHT,
                         endnote_height=ENDNOTE_HEIGHT, axis=False)
    fig.set_facecolor(background)
    fig.suptitle(f'Corner Analysis', fontsize=30,fontproperties=font_prop, color='white', y=0.92)
    img_team1 = mpimg.imread(f'C:/Users/acer/Documents/GitHub/IndianCitizen/ScorePredict/Images/TeamLogos/{team1}.png')
    ax_image = add_image(
        img_team1, fig, left=0.2, bottom=0.85, width=0.12, height=0.12,aspect='equal'
    )

    img_team2 = mpimg.imread(f'C:/Users/acer/Documents/GitHub/IndianCitizen/ScorePredict/Images/TeamLogos/{team2}.png')
    ax_image = add_image(
        img_team2, fig, left=0.68, bottom=0.85, width=0.12, height=0.12,aspect='equal'
    )

    if not corners_1.empty:
        pitch.arrows(corners_1.x, corners_1.y,
                     corners_1.endX, corners_1.endY, width=1.5,alpha=0.8,zorder=3,
                     headwidth=8, headlength=5, color='white', ax=ax['pitch'][0,0], label='Corners From Left')
        pitch.scatter(corners_1.next_shot_x, corners_1.next_shot_y,s=500,marker='p',color=team1_color,zorder=2,alpha=0.9, ax=ax['pitch'][0,0], edgecolors='white')

    if not corners_2.empty:
        pitch.arrows(corners_2.x, corners_2.y,
                     corners_2.endX, corners_2.endY, width=1.5,alpha=0.8,zorder=3,
                     headwidth=8, headlength=5, color='white', ax=ax['pitch'][1,0], label='Corners From Right')
        pitch.scatter(corners_2.next_shot_x, corners_2.next_shot_y,s=500,marker='p',color=team1_color,zorder=2,alpha=0.9, ax=ax['pitch'][1,0], edgecolors='white')

    pitch.scatter(80,45,color=team1_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][0,0])
    pitch.annotate(corner_summary_1['total_shots'][0],xy = (80,45),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,0])
    pitch.annotate('Shots',xy = (75,45),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,0])
    
    pitch.scatter(80,34,color=team1_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][0,0])
    pitch.annotate(corner_summary_1['shots_ot'][0],xy = (80,34),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,0])
    pitch.annotate('Shots(OT)',xy = (75,34),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,0])
    
    pitch.scatter(80,23,color=team1_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][0,0])
    pitch.annotate(corner_summary_1['goals'][0],xy = (80,23),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,0])
    pitch.annotate('Goals',xy = (75,23),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,0])
    
    
    pitch.scatter(80,45,color=team1_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][1,0])
    pitch.annotate(corner_summary_2['total_shots'][0],xy = (80,45),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,0])
    pitch.annotate('Shots',xy = (75,45),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,0])
    
    pitch.scatter(80,34,color=team1_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][1,0])
    pitch.annotate(corner_summary_2['shots_ot'][0],xy = (80,34),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,0])
    pitch.annotate('Shots(OT)',xy = (75,34),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,0])
    
    
    pitch.scatter(80,23,color=team1_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][1,0])
    pitch.annotate(corner_summary_2['goals'][0],xy = (80,23),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,0])
    pitch.annotate('Goals',xy = (75,23),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,0])

    if not corners_3.empty:
        pitch.arrows(corners_3.x, corners_3.y,
                     corners_3.endX, corners_3.endY, width=1.5,alpha=0.8,zorder=3,
                     headwidth=8, headlength=5, color='white', ax=ax['pitch'][0,1], label='Corners From Left')
        pitch.scatter(corners_3.next_shot_x, corners_3.next_shot_y,s=500,marker='p',color=team2_color,zorder=2,alpha=0.5, ax=ax['pitch'][0,1], edgecolors='white')

    if not corners_4.empty:
        pitch.arrows(corners_4.x, corners_4.y,
                     corners_4.endX, corners_4.endY, width=1.5,alpha=0.8,zorder=3,
                     headwidth=8, headlength=5, color='white', ax=ax['pitch'][1,1], label='Corners From Right')
        pitch.scatter(corners_4.next_shot_x, corners_4.next_shot_y,s=500,marker='p',color=team2_color,zorder=2,alpha=0.9, ax=ax['pitch'][1,1], edgecolors='white')

    pitch.scatter(80,45,color=team2_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][0,1])
    pitch.annotate(corner_summary_3['total_shots'][0],xy = (80,45),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,1])
    pitch.annotate('Shots',xy = (75,45),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,1])
    
    pitch.scatter(80,34,color=team2_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][0,1])
    pitch.annotate(corner_summary_3['shots_ot'][0],xy = (80,34),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,1])
    pitch.annotate('Shots(OT)',xy = (75,34),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,1])
    
    pitch.scatter(80,23,color=team2_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][0,1])
    pitch.annotate(corner_summary_3['goals'][0],xy = (80,23),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,1])
    pitch.annotate('Goals',xy = (75,23),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][0,1])
    
    
    pitch.scatter(80,45,color=team2_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][1,1])
    pitch.annotate(corner_summary_4['total_shots'][0],xy = (80,45),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,1])
    pitch.annotate('Shots',xy = (75,45),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,1])
    
    pitch.scatter(80,34,color=team2_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][1,1])
    pitch.annotate(corner_summary_4['shots_ot'][0],xy = (80,34),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,1])
    pitch.annotate('Shots(OT)',xy = (75,34),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,1])
    
    
    pitch.scatter(80,23,color=team2_color, s=1000, edgecolor='white', linewidth=2, alpha=0.7,marker='o',zorder=2,ax=ax['pitch'][1,1])
    pitch.annotate(corner_summary_4['goals'][0],xy = (80,23),color='white',ha='center', va='center',fontsize=15,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,1])
    pitch.annotate('Goals',xy = (75,23),color='white',ha='center', va='center',fontsize=12,zorder=3,fontproperties=font_prop,ax=ax['pitch'][1,1])

    #fig.savefig(f'C:/Users/acer/Documents/GitHub/IndianCitizen/ScorePredict/MatchReports/ACVInter/10.png',dpi=500,bbox_inches = 'tight',facecolor=background)

def plot_lost_pos(df,ax,team1_name,team2_name,team1_facecolor,team2_facecolor):
    df_lost_pos = df[
    ((df['type'] == 'Dispossessed') & (df['outcomeType'] == 'Successful')) |
    ((df['type'] == 'BallTouch') & (df['outcomeType'] == 'Unsuccessful'))
    ]
    
    # Group by 'teamName' and 'name', then get the counts
    grouped_df = df_lost_pos.groupby(['teamName', 'name']).size().reset_index(name='counts')
    
    # Filter for Team A
    team_a_df = grouped_df[grouped_df['teamName'] == team1_name]
    players_team_a = team_a_df['name'].tolist()
    counts_team_a = team_a_df['counts'].tolist()
    
    # Filter for Team B
    team_b_df = grouped_df[grouped_df['teamName'] == team2_name]
    players_team_b = team_b_df['name'].tolist()
    counts_team_b = team_b_df['counts'].tolist()
    # Comparing open play touches of both teams in each zones of the pitch, if more than 55% touches for a team it will be coloured of that team, otherwise gray to represent contested
    pcmap = LinearSegmentedColormap.from_list("Pearl Earring - 10 colors",  [team2_facecolor, 'gray', team1_facecolor], N=20)
    df1 = df[(df['teamName']==team1_name)]
    df2 = df[(df['teamName']==team2_name)]
    df2['x'] = 105-df2['x']
    df2['y'] =  68-df2['y']
    pitch = Pitch(pitch_type='uefa', corner_arcs=True, pitch_color=background, line_color='white', linewidth=1, line_zorder=4)
    pitch.draw(ax=ax)
    #ax.set_ylim(-0.5,68.5)
    #ax.set_xlim(-0.5,105.5)

    pitch.scatter(df1.x, df1.y,s=500,marker='p',color=team1_facecolor,zorder=4,alpha=0.9, ax=ax, edgecolors='white')

    pitch.scatter(df2.x, df2.y,s=500,marker='p',color=team2_facecolor,zorder=4,alpha=0.9, ax=ax, edgecolors='white')
    ax.text(0,  -3, 'Attacking Direction--->', color=team1_facecolor, fontsize=15, ha='left', va='center',font_properties=font_prop)
    ax.text(105,-3, '<---Attacking Direction', color=team2_facecolor, fontsize=15, ha='right', va='center',font_properties=font_prop)

    ax.text(53,  73, 'Possession Lost', color='white', fontsize=30, ha='center', va='center',font_properties=font_prop)

    grouped_df = df.groupby(['teamName', 'name']).size().reset_index(name='counts')

    # Filter for Team A
    team_a_df = grouped_df[grouped_df['teamName'] == team1_name]
    players_team_a = team_a_df['name'].tolist()
    counts_team_a = team_a_df['counts'].tolist()
    
    # Filter for Team B
    team_b_df = grouped_df[grouped_df['teamName'] == team2_name]
    players_team_b = team_b_df['name'].tolist()
    counts_team_b = team_b_df['counts'].tolist()
    # Display the player names and counts for Team 1 on the left side
    for i, (player, count) in enumerate(zip(players_team_a, counts_team_a)):
        ax.text(-25, 68 - (i * 6.5), f"{player}: {count}", color=team1_facecolor, fontsize=15, ha='left', va='top', font_properties=font_prop)
    
    # Display the player names and counts for Team 2 on the right side
    for i, (player, count) in enumerate(zip(players_team_b, counts_team_b)):
        ax.text(130, 68 - (i * 6.5), f"{player}: {count}", color=team2_facecolor, fontsize=15, ha='right', va='top', font_properties=font_prop)
        
    return

def classify_defensive_zones(df, team_name, home_team):
    df = df.copy()
    is_home = team_name == home_team
    df["defensive_zone"] = np.where(
        (df["x"] < 50) if is_home else (df["x"] > 50),
        "Own Half",
        "Opponent Half"
    )
    return df

def plot_defensive_zone_bar(df, team_name):

    df_team = df[df['teamName'] == team_name]
    zone_counts = df_team['defensive_zone'].value_counts().reset_index()
    zone_counts.columns = ['Zone', 'Count']

    chart = alt.Chart(zone_counts).mark_bar().encode(
        x=alt.X('Count:Q'),
        y=alt.Y('Zone:N', sort=['Opponent Half', 'Own Half']),
        color=alt.Color('Zone:N', legend=None),
        tooltip=['Zone', 'Count']
    ).properties(
        width=300,
        height=150,
        title="Defensive Actions by Zone"
    )

    return chart

def plot_possession_windows_time_weighted(
    ax,
    df,
    home_team,
    away_team,
    team_colors,
    background,
    text_color,
    font_prop,
    time_col="cumulative_mins",
    poss_col="possession_id",
    team_col="teamName",
    sort_cols=["possession_id", "index"],
    window_size=15
):


    df_valid = df.dropna(subset=[poss_col, team_col, time_col]).copy()
    df_valid = df_valid.sort_values(sort_cols)
    df_valid["time_bin"] = (df_valid[time_col] // window_size).astype(int)

    # Get duration per possession
    poss_df = (
        df_valid.groupby([poss_col])
        .agg(
            team=(team_col, 'first'),
            time_bin=("time_bin", 'first'),
            start_time=(time_col, 'first'),
            end_time=(time_col, 'last')
        )
        .reset_index()
    )
    poss_df["duration"] = poss_df["end_time"] - poss_df["start_time"]
    poss_df = poss_df[poss_df["duration"] >= 0]

    # Aggregate possession duration by time window and team
    result = (
        poss_df.groupby(["time_bin", "team"])["duration"]
        .sum()
        .reset_index(name="possession_time")
    )

    # Total per bin for percentage calculation
    total_by_bin = result.groupby("time_bin")["possession_time"].sum().reset_index(name="total")
    merged = result.merge(total_by_bin, on="time_bin")
    merged["possession_pct"] = 100 * merged["possession_time"] / merged["total"]

    # Pivot to plot
    pivot_df = merged.pivot(index="time_bin", columns="team", values="possession_pct").fillna(0)

    for team in [home_team, away_team]:
        if team in pivot_df.columns:
            ax.plot(
                #(pivot_df.index + 1) * window_size,  # X-axis: end of each time bin
                pivot_df.index * window_size,
                pivot_df[team],
                marker='o',
                label=team,
                linewidth=6,
                color=team_colors.get(team, None)
            )

    # Plot formatting
    x_labels = [(i) * window_size for i in sorted(pivot_df.index.unique())]
    ax.set_xticks(x_labels)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_xlim(min(x_labels), max(x_labels))
    ax.set_ylim(0, 100)

    ax.set_xlabel('Minute',fontproperties=font_prop, fontsize=18,  color=text_color)
    ax.set_ylabel('Possession %', fontproperties=font_prop, fontsize=18, color=text_color)
    #ax.legend(prop=font_prop, fontsize=20)
    ax.grid(alpha=0.3, color=text_color)
    ax.set_facecolor(background)
    ax.tick_params(axis='x', colors=text_color, labelsize=16)
    ax.tick_params(axis='y', colors=text_color, labelsize=16)
    for spine in ax.spines.values():
        spine.set_color(text_color)

    return ax

def plot_pass_accuracy_windows(
    ax,
    df,
    home_team,
    away_team,
    team_colors,
    background,
    text_color,
    font_prop,
    time_col="minute",
    team_col="teamName",
    accurate_col="passAccurate",
    window_size=15
):

    df_passes = df[df[accurate_col].notna()].copy()
    df_passes["time_bin"] = (df_passes[time_col] // window_size).astype(int)

    # Aggregate accurate and total passes by time bin and team
    grouped = (
        df_passes.groupby(["time_bin", team_col])[accurate_col]
        .agg(['sum', 'count'])
        .reset_index()
        .rename(columns={"sum": "accurate", "count": "total"})
    )
    grouped["accuracy_pct"] = 100 * grouped["accurate"] / grouped["total"]

    # Pivot to get one column per team
    pivot_df = grouped.pivot(index="time_bin", columns=team_col, values="accuracy_pct").fillna(0)

    for team in [home_team, away_team]:
        if team in pivot_df.columns:
            ax.plot(
                pivot_df.index * window_size,  # End of bin
                pivot_df[team],
                marker='o',
                label=team,
                linewidth=6,
                color=team_colors.get(team, None)
            )

    # X-axis formatting
    x_labels = [(i) * window_size for i in sorted(pivot_df.index.unique())]
    ax.set_xticks(x_labels)
    ax.set_xlim(min(x_labels), max(x_labels))
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 20, 40, 60, 80, 100])

    ax.set_xlabel('Minute',fontproperties=font_prop, fontsize=18,  color=text_color)
    ax.set_ylabel('Pass Accuracy %', fontproperties=font_prop, fontsize=18, color=text_color)
    #ax.legend(prop=font_prop, fontsize=16)
    ax.grid(alpha=0.3,color=text_color)
    ax.set_facecolor(background)
    ax.tick_params(axis='x', colors=text_color, labelsize=16)
    ax.tick_params(axis='y', colors=text_color, labelsize=16)
    for spine in ax.spines.values():
        spine.set_color(text_color)

    return ax


def plot_on_goal_shotmap_custom(df, team, team_color, background, text_color, font_prop, selected_player, situation, ax=None):
    """
    Plots on-goal shots using GoalMouthY and GoalMouthZ coordinates,
    normalized to fit custom goal rectangle.
    If ax is provided, plot on that axis; otherwise, create a new figure.
    Applies alpha highlighting if selected_player is set.
    """
    # --- Filter shots ---
    mask = (
        (df['teamName'] == team) &
        (df['isShot'] == True) & (df['shotBlocked'] == False) & (df['shotOnTarget'] == True) &
        df['goalMouthY'].notna() & df['goalMouthZ'].notna()
    )
    if situation and situation != 'All':
        mask &= (df['situation'] == situation)
    shots = df[mask].copy()

    # Rectangle dimensions
    GOAL_LEFT = 30.8
    GOAL_WIDTH = 6.4
    GOAL_BOTTOM = 0
    GOAL_HEIGHT = 35

    if ax is None:
        fig = plt.figure(facecolor=background)
        fig.set_size_inches(15, 5)
        ax = plt.gca()
    else:
        fig = None
        ax.set_facecolor(background)

    # Draw goal posts and net
    ax.plot([30, 38], [0, 0], color=text_color, linewidth=1.5)
    ax.plot([GOAL_LEFT, GOAL_LEFT + GOAL_WIDTH], [GOAL_HEIGHT, GOAL_HEIGHT], color=text_color, linewidth=3)
    ax.plot([GOAL_LEFT + GOAL_WIDTH, GOAL_LEFT + GOAL_WIDTH], [0, GOAL_HEIGHT], color=text_color, linewidth=3)
    ax.plot([GOAL_LEFT, GOAL_LEFT], [0, GOAL_HEIGHT], color=text_color, linewidth=3)
    ax.add_patch(Rectangle((GOAL_LEFT, 0), GOAL_WIDTH, GOAL_HEIGHT, fill=False, edgecolor=text_color, hatch='+', alpha=0.2))

    # Invert x-axis for scatter points
    shots['x_inv'] = GOAL_LEFT + GOAL_WIDTH - (shots['goalMouthY'] - GOAL_LEFT)
    shots['y'] = shots['goalMouthZ']

    # --- Split shots for alpha logic ---
    if selected_player:
        selected_shots = shots[shots['playerName'] == selected_player]
        other_shots = shots[shots['playerName'] != selected_player]
    else:
        selected_shots = shots
        other_shots = pd.DataFrame(columns=shots.columns)

    # Plot other shots faded
    if not other_shots.empty:
        for _, row in other_shots.iterrows():
            marker = 'o'
            size = 2000 if row['type'] == 'Goal' else 1500
            color = team_color if row['type'] == 'Goal' else text_color
            ax.scatter(row['x_inv'], row['y'], s=size * row['xG'], marker=marker, color=color, edgecolor=text_color, linewidth=2, zorder=3, alpha=0.2)

    # Plot selected player's shots highlighted
    if not selected_shots.empty:
        for _, row in selected_shots.iterrows():
            marker = 'o'
            size = 2000 if row['type'] == 'Goal' else 1500
            color = team_color if row['type'] == 'Goal' else text_color
            ax.scatter(row['x_inv'], row['y'], s=size * row['xG'], marker=marker, color=color, edgecolor=text_color, linewidth=2, zorder=3, alpha=0.9)

    ax.axis('off')
    return fig

def plot_team_shotmaps_stacked(df, team, team_color, background, text_color, font_prop, ax_goal, ax_field, selected_player=None, situation=None):
    """
    Plots on-goal shotmap (top) and on-field shotmap (bottom) for a single team using provided axes.
    If a player is selected, their shots are highlighted and others are faded.
    """
    # --- Filter shots for the team ---
    mask = (
        (df['teamName'] == team) &
        (df['type'].isin(['Goal', 'MissedShots', 'SavedShot', 'ShotOnPost']))
    )
    if situation and situation != 'All':
        mask &= (df['situation'] == situation)
    shots_df = df[mask].copy().reset_index(drop=True)

    # --- On Goal Shotmap ---
    plot_on_goal_shotmap_custom(
        df, team, team_color, background, text_color, font_prop, selected_player, situation, ax=ax_goal
    )

    pitch = VerticalPitch(
        pitch_type='uefa',
        half=True,
        pitch_color=background,
        line_color=text_color,
        linewidth=1,
        axis=True,
        label=True,
        pad_bottom=-7
    )
    ax_field.set_facecolor(background)
    pitch.draw(ax=ax_field)

    if not shots_df.empty:
        # Split shots into selected and others
        if selected_player:
            selected_shots = shots_df[shots_df['playerName'] == selected_player]
            other_shots = shots_df[shots_df['playerName'] != selected_player]
        else:
            selected_shots = shots_df
            other_shots = pd.DataFrame(columns=shots_df.columns)

        # Plot other shots faded
        for shot_type, marker, edgecolor, color, zorder in [
            ('Goal', 'football', text_color, team_color, 6),
            ('MissedShots', 'o', team_color, background, 4),
            ('SavedShot', 'o', 'white', team_color, 4),
            ('ShotOnPost', 'o', 'green', team_color, 5),
        ]:
            others = other_shots[other_shots['type'] == shot_type]
            if not others.empty:
                pitch.scatter(
                    others['x'], others['y'],
                    marker=marker,
                    edgecolors=edgecolor,
                    s=1000 * others['xG'],
                    c=color,
                    linewidths=1,
                    alpha=0.2,  # faded
                    ax=ax_field,
                    zorder=zorder
                )
        # Blocked shots (SavedShot & shotBlocked==True)
        blocked = other_shots[(other_shots['type'] == 'SavedShot') & (other_shots['shotBlocked'] == True)]
        if not blocked.empty:
            pitch.scatter(blocked['x'], blocked['y'], marker='s', edgecolors=team_color, s=1000 * blocked['xG'], linewidths=3, c=background, alpha=0.2, ax=ax_field, zorder=5)

        # Own Goals
        own_goals = other_shots[(other_shots['type'] == 'Goal') & (other_shots['goalOwn'] == True)]
        if not own_goals.empty:
            pitch.scatter(own_goals['x'], own_goals['y'], marker='football', edgecolors=team_color, s=1000, c=text_color, linewidths=3, alpha=0.2, ax=ax_field, zorder=6)

        # Plot selected player's shots highlighted
        for shot_type, marker, edgecolor, color, zorder in [
            ('Goal', 'football', text_color, team_color, 6),
            ('MissedShots', 'o', team_color, background, 4),
            ('SavedShot', 'o', 'white', team_color, 4),
            ('ShotOnPost', 'o', 'green', team_color, 5),
        ]:
            sel = selected_shots[selected_shots['type'] == shot_type]
            if not sel.empty:
                pitch.scatter(
                    sel['x'], sel['y'],
                    marker=marker,
                    edgecolors=edgecolor,
                    s=1000 * sel['xG'],
                    c=color,
                    linewidths=1,
                    alpha=0.9,  # highlighted
                    ax=ax_field,
                    zorder=zorder
                )
        # Blocked shots (SavedShot & shotBlocked==True)
        blocked_sel = selected_shots[(selected_shots['type'] == 'SavedShot') & (selected_shots['shotBlocked'] == True)]
        if not blocked_sel.empty:
            pitch.scatter(blocked_sel['x'], blocked_sel['y'], marker='s', edgecolors=team_color, s=1000 * blocked_sel['xG'], linewidths=3, c=background, alpha=0.9, ax=ax_field, zorder=5)

        # Own Goals
        own_goals_sel = selected_shots[(selected_shots['type'] == 'Goal') & (selected_shots['goalOwn'] == True)]
        if not own_goals_sel.empty:
            pitch.scatter(own_goals_sel['x'], own_goals_sel['y'], marker='football', edgecolors=team_color, s=1000, c=text_color, linewidths=3, alpha=0.9, ax=ax_field, zorder=6)

    ax_field.axis('off')

    # Add legend markers (optional)
    pitch.scatter(107.5, 66, marker='football', edgecolors=text_color, s=300, c=background, ax=ax_field)
    pitch.annotate('Goal', xy=(107.5, 62), fontsize=15, color=text_color, fontproperties=font_prop, ax=ax_field, ha='center', va='center')
    pitch.scatter(107.5, 56, marker='o', edgecolors=background, s=300, c=text_color, ax=ax_field)
    pitch.annotate('On Target', xy=(107.5, 49), fontsize=15, color=text_color, fontproperties=font_prop, ax=ax_field, ha='center', va='center')
    pitch.scatter(107.5, 42, marker='o', edgecolors='green', linewidths=1, s=300, c=background, ax=ax_field)
    pitch.annotate('Woodwork', xy=(107.5, 34), fontsize=15, color=text_color, fontproperties=font_prop, ax=ax_field, ha='center', va='center')
    pitch.scatter(107.5, 26, marker='o', edgecolors=text_color, s=300, c=background, ax=ax_field)
    pitch.annotate('Off Target', xy=(107.5, 19), fontsize=15, color=text_color, fontproperties=font_prop, ax=ax_field, ha='center', va='center')
    pitch.scatter(107.5, 12, marker='s', edgecolors=text_color, linewidths=1, s=300, c=background, ax=ax_field)
    pitch.annotate('Blocked', xy=(107.5, 6), fontsize=15, color=text_color, fontproperties=font_prop, ax=ax_field, ha='center', va='center')

@st.cache_data(ttl=600)
def tag_sequences_and_possessions_all_matches(
        df,
        match_col="matchId",
        event_col="type",
        team_col="teamName",
        outcome_col="outcomeType",
        success_values=("Successful", 1),
        time_sort_cols=("minute", "second", "index")
    ):
    """
    Adds `sequence_id` and `possession_id` *per match*.

    Parameters
    ----------
    df : pd.DataFrame
        Event feed containing one or more matches.
    match_col : str
        Column that identifies each match.
    All other parameters are identical to the single‑match function.

    Returns
    -------
    pd.DataFrame
        Same rows plus `sequence_id` and `possession_id`.
    """

    # ---------- 1. Define event buckets ----------
    CONTROLLED_EVENTS = {
        "Pass", "BallRecovery", "BallTouch", "KeeperPickup", "TakeOn",
        "Goal", "SavedShot", "Claim", "Carry", "ShotOnPost"
    }
    DEFENSIVE_EVENTS = {
        "Tackle", "Dispossessed", "Interception", "Clearance", "BlockedPass",
        "Challenge", "Aerial", "KeeperSweeper", "Punch"
    }
    STOPPAGE_EVENTS = {
        "Foul", "OffsidePass", "OffsideGiven", "OffsideProvoked",
        "Card", "Error", "CornerAwarded", "MissedShots", "ChanceMissed",
        "End", "FormationChange", "SubstitutionOn", "SubstitutionOff",
        "FormationSet", "Start"
    }

    # ---------- 2. Helper to tag ONE match ----------
    def _tag_one_match(sub):
        # Sort chronologically inside this match
        sub = sub.sort_values(list(time_sort_cols)).reset_index(drop=True)

        poss_id = -1
        seq_id  = -1
        possessing_team = None
        open_sequence   = False

        poss_ids, seq_ids = [], []

        for _, row in sub.iterrows():
            ev   = row[event_col]
            team = row[team_col]
            ok   = row[outcome_col] in success_values

            grants_control = (ev in CONTROLLED_EVENTS) and ok

            # Turnover?
            if possessing_team is not None and grants_control and team != possessing_team:
                poss_id += 1
                seq_id  += 1
                possessing_team = team
                open_sequence   = True

            # Sequence‑ending tests
            terminate = False
            if open_sequence:
                if ev in STOPPAGE_EVENTS or ev == "Goal":
                    terminate = True
                elif team != possessing_team and ev in DEFENSIVE_EVENTS:
                    terminate = True
                elif (ev in CONTROLLED_EVENTS) and not ok:
                    terminate = True

            if terminate:
                open_sequence = False
                if team != possessing_team and ev in DEFENSIVE_EVENTS:
                    possessing_team = None

            # Sequence‑start tests
            if not open_sequence and grants_control:
                if team != possessing_team:
                    poss_id += 1
                    possessing_team = team
                seq_id      += 1
                open_sequence = True

            seq_ids.append(seq_id if open_sequence else pd.NA)
            poss_ids.append(poss_id if possessing_team is not None else pd.NA)

        sub["sequence_id"]   = seq_ids
        sub["possession_id"] = poss_ids
        return sub

    # ---------- 3. Run per‑match and concatenate ----------
    out = (
        df.groupby(match_col, group_keys=False, sort=False)
          .apply(_tag_one_match)
          .reset_index(drop=True)
    )
    return out

def get_match_id_from_db(league, season, home_team, away_team):
    base_path = '/Users/ishdeepchadha/Documents/Score/Football'
    db_path = f'{base_path}/data extraction/score_football.db'
    conn = sqlite3.connect(db_path)
    query = """
        SELECT matchId
        FROM event_data
        WHERE league = ? AND season = ? AND teamName = ? AND h_a = 'h'
    """
    home_matches = pd.read_sql_query(query, conn, params=(league, season, home_team))
    query = """
        SELECT matchId
        FROM event_data
        WHERE league = ? AND season = ? AND teamName = ? AND h_a = 'a'
    """
    away_matches = pd.read_sql_query(query, conn, params=(league, season, away_team))
    conn.close()
    # Find intersection of matchIds
    home_ids = set(home_matches['matchId'])
    away_ids = set(away_matches['matchId'])
    common_ids = home_ids & away_ids
    return list(common_ids)[0] if common_ids else None

def classify_third(x):
    # 105m pitch
    if x < 35:
        return "Defensive Third"
    elif x < 70:
        return "Middle Third"
    else:
        return "Attacking Third"

def offensive_transition_heatmap(poss_df, team_name, ax, pitch, background, team_color, text_color, font_prop, flagged, selected_third=None):
    """
    Plots a heatmap of where team dispossessed opponent and % transitions leading to attacks.
    Returns a DataFrame with percentage values by thirds and a DataFrame of all transitions.
    If selected_third is provided, highlights that third on the pitch.
    """
    poss_df = poss_df.sort_values(['minute', 'second']).reset_index(drop=True)
    regain_events = []
    for idx, row in poss_df.iterrows():
        # Check if previous event was a dispossession/turnover by opponent
        if idx > 0:
            prev = poss_df.iloc[idx - 1]
            if (
                prev['teamName'] != team_name and
                ((prev.get('dispossessed', False) == True) or (prev.get('turnover', False) == True)) and
                row['teamName'] == team_name
            ):
                regain_events.append(row)
    if not regain_events:
        st.warning("No offensive transitions found for this team.")
        return pd.DataFrame(), pd.DataFrame()
    regain_events_df = pd.DataFrame(regain_events)
    regain_events_df['third'] = regain_events_df['x'].apply(classify_third)

    # For each regain, check if possession led to attack (any shot or pass into final third)
    results = []
    for _, row in regain_events_df.iterrows():
        poss_id = row['possession_id']
        events = poss_df[poss_df['possession_id'] == poss_id]
        led_to_attack = events[(events['type'].isin(['Goal', 'SavedShot', 'MissedShots', 'ShotOnPost'])) | ((events['x'] > 70) & (events['outcomeType'] == 'Successful'))].shape[0] > 0
        results.append({
            'x': row['x'],
            'y': row['y'],
            'third': row['third'],
            'led_to_attack': led_to_attack,
            'possession_id': row['possession_id'],
            'playerName': row.get('playerName', None),
            'minute': row.get('minute', None),
            'second': row.get('second', None),
            'type': row.get('type', None)
        })

    transitions_df = pd.DataFrame(results)
    # Heatmap
    if flagged == False:
        transitions_df['x'] = transitions_df['x'].apply(lambda x: 105 - x)
        transitions_df['y'] = transitions_df['y'].apply(lambda y: 68 - y)

    pitch.draw(ax=ax)
    ax.set_facecolor(background)
    cmap = LinearSegmentedColormap.from_list('custom_cmap', [background, team_color])
    pitch.heatmap(pitch.bin_statistic(transitions_df['x'], transitions_df['y'], statistic='count', bins=(10, 7)), ax=ax, cmap=cmap, edgecolors=background, alpha=0.7)
    pitch.scatter(transitions_df['x'], transitions_df['y'], s=200, color=team_color, alpha=0.7, ax=ax, edgecolors=text_color)
    if flagged:
        pitch.arrows(5,-2,100,-2, width=3,
                headwidth=4, headlength=3, headaxislength=2,
                color=text_color, ax=ax)
    else:
        pitch.arrows(100,-2,5,-2, width=3,
                headwidth=4, headlength=3, headaxislength=2,
                color=text_color, ax=ax)
    # Highlight selected third if provided
    if selected_third and flagged == True:
        if selected_third == "Defensive Third":
            ax.fill([0, 35, 35, 0], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
        elif selected_third == "Middle Third":
            ax.fill([35, 70, 70, 35], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
        elif selected_third == "Attacking Third":
            ax.fill([70, 105, 105, 70], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
    elif selected_third and flagged == False:
        if selected_third == "Defensive Third":
            ax.fill([70, 105, 105, 70], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
        elif selected_third == "Middle Third":  
            ax.fill([35, 70, 70, 35], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
        elif selected_third == "Attacking Third":
            ax.fill([0, 35, 35, 0], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)

    # Percentage by third
    summary = transitions_df.groupby('third')['led_to_attack'].agg(['count', 'sum'])
    summary['percent_to_attack'] = (summary['sum'] / summary['count'] * 100).round(1)
    summary = summary.rename(columns={'count': 'Transitions', 'sum': 'LedToAttack'})
    summary_df = summary.reset_index()

    return summary_df, transitions_df


def defensive_transition_heatmap(poss_df, team_name, ax, pitch, background, team_color, text_color, font_prop, flagged, selected_third=None):
    """
    Plots a heatmap of where team lost the ball (dispossessed or turnover) and % transitions leading to conceding an attack.
    Returns a DataFrame with percentage values by thirds and a DataFrame of all transitions.
    If selected_third is provided, highlights that third on the pitch.
    """
    poss_df = poss_df.sort_values(['minute', 'second']).reset_index(drop=True)
    loss_events = []
    for idx, row in poss_df.iterrows():
        # Check if previous event was a dispossession/turnover by this team
        if idx > 0:
            prev = poss_df.iloc[idx - 1]
            if (
                prev['teamName'] == team_name and
                ((prev.get('dispossessed', False) == True) or (prev.get('turnover', False) == True)) and
                row['teamName'] != team_name
            ):
                loss_events.append(prev)
    if not loss_events:
        st.warning("No defensive transitions found for this team.")
        return pd.DataFrame(), pd.DataFrame()
    loss_events_df = pd.DataFrame(loss_events)
    loss_events_df['third'] = loss_events_df['x'].apply(classify_third)

    # For each loss, check if opponent's next possession led to attack
    results = []
    for _, row in loss_events_df.iterrows():
        poss_id = row['possession_id']
        next_poss_id = poss_id + 1
        opp_events = poss_df[poss_df['possession_id'] == next_poss_id]
        led_to_attack = opp_events[(opp_events['type'].isin(['Goal', 'SavedShot', 'MissedShots', 'ShotOnPost'])) | ((opp_events['x'] > 70) & (opp_events['outcomeType'] == 'Successful'))].shape[0] > 0
        results.append({
            'x': row['x'],
            'y': row['y'],
            'third': row['third'],
            'led_to_attack': led_to_attack,
            'possession_id': row['possession_id'],
            'playerName': row.get('playerName', None),
            'minute': row.get('minute', None),
            'second': row.get('second', None),
            'type': row.get('type', None)
        })

    transitions_df = pd.DataFrame(results)
    # Heatmap
    if flagged == False:
        transitions_df['x'] = transitions_df['x'].apply(lambda x: 105 - x)
        transitions_df['y'] = transitions_df['y'].apply(lambda y: 68 - y)

    pitch.draw(ax=ax)
    ax.set_facecolor(background)
    cmap = LinearSegmentedColormap.from_list('custom_cmap', [background, team_color])
    pitch.heatmap(pitch.bin_statistic(transitions_df['x'], transitions_df['y'], statistic='count', bins=(10, 7)), ax=ax, cmap=cmap, edgecolors=background, alpha=0.7)
    pitch.scatter(transitions_df['x'], transitions_df['y'], s=200, color=team_color, alpha=0.7, ax=ax, edgecolors=text_color)
    if flagged:
        pitch.arrows(5,-2,100,-2, width=3,
                headwidth=4, headlength=3, headaxislength=2,
                color=text_color, ax=ax)
    else:
        pitch.arrows(100,-2,5,-2, width=3,
                headwidth=4, headlength=3, headaxislength=2,
                color=text_color, ax=ax)
    # Highlight selected third if provided
    if selected_third and flagged == True:
        if selected_third == "Defensive Third":
            ax.fill([0, 35, 35, 0], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
        elif selected_third == "Middle Third":
            ax.fill([35, 70, 70, 35], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
        elif selected_third == "Attacking Third":
            ax.fill([70, 105, 105, 70], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
    elif selected_third and flagged == False:
        if selected_third == "Defensive Third":
            ax.fill([70, 105, 105, 70], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
        elif selected_third == "Middle Third":  
            ax.fill([35, 70, 70, 35], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)
        elif selected_third == "Attacking Third":
            ax.fill([0, 35, 35, 0], [0, 0, 68, 68], color=text_color, alpha=0.4, zorder=0)

    # Percentage by third
    summary = transitions_df.groupby('third')['led_to_attack'].agg(['count', 'sum'])
    summary['percent_conceded_attack'] = (summary['sum'] / summary['count'] * 100).round(1)
    summary = summary.rename(columns={'count': 'Transitions', 'sum': 'ConcededAttack'})
    summary_df = summary.reset_index()

    return summary_df, transitions_df

@st.cache_data(ttl=600)
def build_transition_summary(transitions_df, third):
    """
    Returns a summary DataFrame for transitions starting in the specified third.
    Columns: Winner, End Result, Shot Player, Transition Duration (s)
    """
    filtered = transitions_df[transitions_df['third'] == third]
    summary = []
    for _, row in filtered.iterrows():
        poss_id = row['possession_id']
        events = transitions_df[transitions_df['possession_id'] == poss_id]
        winner = row.get('playerName', None)
        shot_event = events[events['type'].isin(['Goal', 'SavedShot', 'MissedShots', 'ShotOnPost'])]
        shot_player = shot_event['playerName'].iloc[0] if not shot_event.empty else None
        end_result = shot_event['type'].iloc[0] if not shot_event.empty else 'No Shot'
        start_time = row['minute'] * 60 + row['second']
        if not shot_event.empty:
            end_time = shot_event['minute'].iloc[0] * 60 + shot_event['second'].iloc[0]
        elif not events.empty:
            # Use last event in the possession if no shot
            last_event = events.iloc[-1]
            end_time = last_event['minute'] * 60 + last_event['second']
        else:
            end_time = start_time  # fallback: duration is zero if no events
        duration = end_time - start_time if end_time is not None else None
        summary.append({
            'Winner': winner,
            'End Result': end_result,
            'Shot Player': shot_player,
            'Transition Duration (s)': duration
        })
    return pd.DataFrame(summary)


def detect_offensive_transitions(events_df, team_name, time_window=10):
    events_df = events_df.sort_values(["minute", "second"]).reset_index(drop=True)
    events_df["event_time_sec"] = events_df["minute"] * 60 + events_df["second"]

    regain_events = ["BallRecovery", "Interception", "Tackle", "Challenge", "KeeperPickup", "Claim"]
    key_attacking = ["Shot", "Goal", "MissedShots", "SavedShot", "Pass", "Carry"]

    transitions = []

    for idx, row in events_df.iterrows():
        if row["teamName"] == team_name and row["type"] in regain_events:
            start_time = row["event_time_sec"]

            window_events = events_df[
                (events_df["event_time_sec"] >= start_time) &
                (events_df["event_time_sec"] <= start_time + time_window)
            ]
            window_team_events = window_events[window_events["teamName"] == team_name]

            in_box = window_team_events[
                ((window_team_events["type"].isin(["Pass", "Carry"])) &
                 (window_team_events["x"] > 102) & (window_team_events["y"].between(18, 62)))
            ]

            if in_box.shape[0] > 0 or any(window_team_events["type"].isin(["Shot", "Goal", "MissedShots", "SavedShot"])):
                transitions.append(window_team_events.reset_index(drop=True))

    return transitions

def get_number_of_attacks(poss_df, team_name):
    """
    Returns a DataFrame with number of attacks by the team from each flank (Left, Center, Right)
    and the total xG of shots resulting from attacks from each flank.
    Pitch dimensions: 105 x 68. Flanks are divided by y-coordinates:
        Left: y < 22.67
        Center: 22.67 <= y < 45.33
        Right: y >= 45.33
    """
    attack_actions = ['Pass', 'SavedShot', 'MissedShots', 'Goal', 'ShotOnPost']
    shot_actions = ['SavedShot', 'MissedShots', 'Goal', 'ShotOnPost']
    x_threshold = 70.12

    # Flank boundaries
    left_max = 22.67
    center_min = 22.67
    center_max = 45.33
    right_min = 45.33

    # Initialize counters
    flank_stats = {
        'Left': {'num_attacks': 0, 'num_attacks_with_shots': 0, 'total_xG': 0.0},
        'Center': {'num_attacks': 0, 'num_attacks_with_shots': 0, 'total_xG': 0.0},
        'Right': {'num_attacks': 0, 'num_attacks_with_shots': 0, 'total_xG': 0.0}
    }

    team_possessions = poss_df[poss_df['teamName'] == team_name].groupby('possession_id')

    for _, possession_events in team_possessions:
        # Events that qualify as an attack (final third, successful)
        qualifying = possession_events[
            (possession_events['type'].isin(attack_actions)) &
            (possession_events['outcomeType'] == 'Successful') &
            (possession_events['x'] > x_threshold)
        ]

        if not qualifying.empty:
            # Determine flank by the first qualifying event's y coordinate
            first_event = qualifying.iloc[0]
            y = first_event['y']
            if y < left_max:
                flank = 'Left'
            elif y < center_max:
                flank = 'Center'
            else:
                flank = 'Right'

            flank_stats[flank]['num_attacks'] += 1

            # Check if one of the qualifying actions was a shot
            shot_events = qualifying[qualifying['type'].isin(shot_actions)]
            if not shot_events.empty:
                flank_stats[flank]['num_attacks_with_shots'] += 1
                # Sum xG for shots in this possession from this flank
                flank_stats[flank]['total_xG'] += shot_events['xG'].sum()

    # Build dataframe
    result_df = pd.DataFrame([
        {
            'Flank': flank,
            'Num_Attacks': stats['num_attacks'],
            'Num_Attacks_With_Shots': stats['num_attacks_with_shots'],
            'Total_xG': round(stats['total_xG'], 3)
        }
        for flank, stats in flank_stats.items()
    ])

    return result_df

def plot_attacks(attacks, team_color, background, text_color, font_prop, ax):

    pitch = VerticalPitch(
        pitch_type='uefa', half=True, pitch_color=background,
        line_color=text_color, linewidth=1.5, axis=True, label=True, pad_bottom=-10
    )
    pitch.draw(ax=ax)
    ax.set_facecolor(background)

    #Normalize attack intensity for color
    max_attacks = attacks['Num_Attacks'].max()
    min_attacks = attacks['Num_Attacks'].min()
    norm = lambda x: 0.3 + 0.7 * ((x - min_attacks) / (max_attacks - min_attacks + 1e-6))

    center_alpha = norm(attacks[attacks['Flank'] == 'Center']['Num_Attacks'].values[0])
    center_text = f"{attacks[attacks['Flank'] == 'Center']['Num_Attacks'].values[0]} \n {round(attacks[attacks['Flank'] == 'Center']['Total_xG'].values[0],2)} xG"
    ax.text(34, 80, center_text, fontproperties=font_prop,fontsize=25, color=text_color, ha='center', va='center', zorder=5)

    left_alpha = norm(attacks[attacks['Flank'] == 'Left']['Num_Attacks'].values[0])
    left_text = f"{attacks[attacks['Flank'] == 'Left']['Num_Attacks'].values[0]} \n {round(attacks[attacks['Flank'] == 'Left']['Total_xG'].values[0],2)} xG"
    ax.text(10, 80, left_text, fontproperties=font_prop, fontsize=25, color=text_color, ha='center', va='center', zorder=5)
    right_alpha = norm(attacks[attacks['Flank'] == 'Right']['Num_Attacks'].values[0])
    right_text = f"{attacks[attacks['Flank'] == 'Right']['Num_Attacks'].values[0]} \n {round(attacks[attacks['Flank'] == 'Right']['Total_xG'].values[0],2)} xG"
    ax.text(58, 80, right_text, fontproperties=font_prop, fontsize=25, color=text_color, ha='center', va='center', zorder=5)

    ax.fill([20, 48, 48, 20],[105, 105, 52.5, 52.5], team_color, alpha=center_alpha, zorder=0) ## Center Flank

    ax.fill([0, 20, 20, 0],[105, 105, 52.5, 52.5], team_color, alpha=left_alpha, zorder=0) ## Left Flank

    ax.fill([48, 68, 68, 48],[105, 105, 52.5, 52.5],team_color, alpha=right_alpha, zorder=0) ## Right Flank

    ax.axis('off')
    return ax
    """
    Plots the number of attacks and xG from each flank for both teams.
    Fills the three flanks according to the intensity of number of attacks from that flank,
    with xG value shown on top and an arrow whose length depends on the amount of xG.
    """
    pitch = VerticalPitch(
        pitch_type='uefa', half=True, pitch_color=background,
        line_color=text_color, linewidth=1, axis=True, label=True, pad_bottom=-7
    )
    pitch.draw(ax=ax)
    ax.set_facecolor(background)

    # Flank boundaries
    flank_bounds = {
        'Left': (0, 22.67),
        'Center': (22.67, 45.33),
        'Right': (45.33, 68)
    }
    flank_positions = {
        'Left': 11.335,
        'Center': 34,
        'Right': 56.665
    }

    # Normalize attack intensity for color
    max_attacks = max(h_attacks['Num_Attacks'].max(), a_attacks['Num_Attacks'].max())
    min_attacks = min(h_attacks['Num_Attacks'].min(), a_attacks['Num_Attacks'].min())
    norm = lambda x: 0.3 + 0.7 * ((x - min_attacks) / (max_attacks - min_attacks + 1e-6))

    # Plot for both teams
    for team_attacks, color, x_pos in [
        (h_attacks, team1_color, 15),
        (a_attacks, team2_color, 55)
    ]:
        for _, row in team_attacks.iterrows():
            flank = row['Flank']
            y_min, y_max = flank_bounds[flank]
            intensity = norm(row['Num_Attacks'])
            rect = plt.Rectangle(
                (0, y_min), 70, y_max - y_min,
                color=color, alpha=intensity, zorder=1
            )
            ax.add_patch(rect)

            # Show xG value
            ax.text(
                x_pos, (y_min + y_max) / 2, f"xG: {row['Total_xG']:.2f}",
                fontsize=18, fontproperties=font_prop, color=text_color,
                ha='center', va='center', fontweight='bold', zorder=3
            )

            # Arrow for xG (length depends on xG value, capped for display)
            arrow_length = min(50, 10 + row['Total_xG'] * 30)
            arrow_x_start = x_pos
            arrow_y = (y_min + y_max) / 2
            arrow_x_end = x_pos + arrow_length if color == team1_color else x_pos - arrow_length
            pitch.arrow(
                arrow_x_start, arrow_y,
                arrow_x_end - arrow_x_start, 0,
                head_width=3, head_length=5, fc=text_color, ec=text_color,
                length_includes_head=True, zorder=4
            )

            # Show number of attacks
            ax.text(
                x_pos, arrow_y - 7, f"Attacks: {row['Num_Attacks']}",
                fontsize=14, fontproperties=font_prop, color=text_color,
                ha='center', va='center', zorder=3
            )

    # Add legend for flanks
    #for flank, y in flank_positions.items():
    #    ax.text(72, y, flank, fontsize=16, color=text_color, fontproperties=font_prop, va='center', ha='left', zorder=5)

    return ax