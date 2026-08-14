import os
import re
import sys
from sys import platform
import pandas as pd
import numpy as np
from unidecode import unidecode

# NEW: Get the directory where data_utils.py is located to construct absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
API_DIR = os.path.join(ROOT_DIR, "apps", "api")

def extract_version_registry(output):
    try:
        google_version = ''
        for letter in output[output.rindex('DisplayVersion    REG_SZ') + 24:]:
            if letter != '\n':
                google_version += letter
            else:
                break
        return(google_version.strip())
    except TypeError:
        return

def extract_version_folder():
    # Check if the Chrome folder exists in the x32 or x64 Program Files folders.
    for i in range(2):
        path = 'C:\\Program Files' + (' (x86)' if i else '') +'\\Google\\Chrome\\Application'
        if os.path.isdir(path):
            paths = [f.path for f in os.scandir(path) if f.is_dir()]
            for path in paths:
                filename = os.path.basename(path)
                pattern = '\d+\.\d+\.\d+\.\d+'
                match = re.search(pattern, filename)
                if match and match.group():
                    # Found a Chrome version.
                    return match.group(0)

    return None

def get_chrome_version():
    version = None
    install_path = None

    try:
        if platform == "linux" or platform == "linux2":
            # linux
            install_path = "/usr/bin/google-chrome"
        elif platform == "darwin":
            # OS X
            install_path = "/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome"
        elif platform == "win32":
            # Windows...
            try:
                # Try registry key.
                stream = os.popen('reg query "HKLM\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Google Chrome"')
                output = stream.read()
                version = extract_version_registry(output)
            except Exception as ex:
                # Try folder path.
                version = extract_version_folder()
    except Exception as ex:
        print(ex)

    version = os.popen(f"{install_path} --version").read().strip('Google Chrome ').strip() if install_path else version

    return version

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
            possession_change = prev_evt_team != next_evt['teamId']
            prev_unsuccessful_movement = (
                match_event['type'] in ['Pass', 'Carry', 'TakeOn', 'GoodSkill', 'Clearance']
                and match_event['outcomeType'] == 'Unsuccessful'
            )
            next_controlled_movement = (
                next_evt['type'] in ['Pass', 'Carry', 'TakeOn', 'GoodSkill']
                and next_evt['outcomeType'] == 'Successful'
            )
            valid_possession_change_carry = possession_change and prev_unsuccessful_movement and next_controlled_movement
            prev_end_x = match_event['endX']
            prev_end_y = match_event['endY']
            prev_end_x_num = pd.to_numeric(prev_end_x, errors='coerce')
            prev_end_y_num = pd.to_numeric(prev_end_y, errors='coerce')
            no_clear_end_point = pd.isna(prev_end_x_num) or pd.isna(prev_end_y_num)
            if not no_clear_end_point:
                no_clear_end_point = (
                    float(prev_end_x_num) == 0
                    and float(prev_end_y_num) == 0
                    and match_event['type'] in ['Tackle', 'Challenge', 'BallRecovery', 'Interception', 'Aerial', 'Foul']
                )
            if same_team and no_clear_end_point:
                prev_end_x = match_event['x']
                prev_end_y = match_event['y']
            if valid_possession_change_carry:
                prev_end_x = 100 - prev_end_x
                prev_end_y = 100 - prev_end_y
            dx = 105*(prev_end_x - next_evt['x'])/100
            dy = 68*(prev_end_y - next_evt['y'])/100
            far_enough = dx ** 2 + dy ** 2 >= min_carry_length ** 2
            not_too_far = dx ** 2 + dy ** 2 <= max_carry_length ** 2
            dt = 60 * (next_evt['cumulative_mins'] - match_event['cumulative_mins'])
            min_time = dt >= min_carry_duration
            same_phase = dt < max_carry_duration
            same_period = match_event['period'] == next_evt['period']

            valid_carry = (same_team or valid_possession_change_carry) & not_ball_touch & far_enough & not_too_far & min_time & same_phase &same_period

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
                carry['matchId'] = prev['matchId']
                carry['x'] = prev_end_x
                carry['y'] = prev_end_y
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
                if 'teamName' in match_events.columns:
                    carry['teamName'] = nex['teamName']

                match_carries = pd.concat([match_carries, carry], ignore_index=True, sort=False)

    match_events_and_carries = pd.concat([match_carries, match_events], ignore_index=True, sort=False)
    match_events_and_carries = match_events_and_carries.sort_values(['period', 'cumulative_mins']).reset_index(drop=True)

    # Rebuild events dataframe
    events_out = pd.concat([events_out, match_events_and_carries])

    return events_out

def get_xT_values(df):
    df_base  = df
    dfxT = df_base.copy()
    dfxT['qualifiers'] = dfxT['qualifiers'].astype(str)
    dfxT = dfxT[(~dfxT['qualifiers'].str.contains('Corner'))]
    dfxT = dfxT[(dfxT['type'].isin(['Pass', 'Carry'])) & (dfxT['outcomeType']=='Successful')]


    xT = pd.read_csv('https://raw.githubusercontent.com/mckayjohns/youtube-videos/main/data/xT_Grid.csv', header=None) # use this if you don't have your own xT value Grid
    # xT = pd.read_csv("/content/xT_Grid.csv", header=None)    # use this if you have your own xT value Grid, then place your file path here
    xT = np.array(xT)
    xT_rows, xT_cols = xT.shape

    dfxT['x1_bin_xT'] = pd.cut(dfxT['x'], bins=xT_cols, labels=False)
    dfxT['y1_bin_xT'] = pd.cut(dfxT['y'], bins=xT_rows, labels=False)
    dfxT['x2_bin_xT'] = pd.cut(dfxT['endX'], bins=xT_cols, labels=False)
    dfxT['y2_bin_xT'] = pd.cut(dfxT['endY'], bins=xT_rows, labels=False)

    dfxT['start_zone_value_xT'] = np.nan
    start_mask = dfxT['x1_bin_xT'].notna() & dfxT['y1_bin_xT'].notna()
    dfxT.loc[start_mask, 'start_zone_value_xT'] = xT[
        dfxT.loc[start_mask, 'y1_bin_xT'].astype(int),
        dfxT.loc[start_mask, 'x1_bin_xT'].astype(int)
    ]

    dfxT['end_zone_value_xT'] = np.nan
    end_mask = dfxT['x2_bin_xT'].notna() & dfxT['y2_bin_xT'].notna()
    dfxT.loc[end_mask, 'end_zone_value_xT'] = xT[
        dfxT.loc[end_mask, 'y2_bin_xT'].astype(int),
        dfxT.loc[end_mask, 'x2_bin_xT'].astype(int)
    ]

    dfxT['xT'] = dfxT['end_zone_value_xT'] - dfxT['start_zone_value_xT']
    # Merge only the values calculated here. Keeping arbitrary source columns in
    # this frame creates ``league_x``/``league_y`` style suffixes as new match
    # metadata is added, which makes the downstream model feature builders lose
    # their canonical competition columns.
    dfxT = dfxT[
        [
            'index',
            'x1_bin_xT',
            'y1_bin_xT',
            'x2_bin_xT',
            'y2_bin_xT',
            'start_zone_value_xT',
            'end_zone_value_xT',
            'xT',
        ]
    ]

    df = df.merge(dfxT, on='index', how='left')
    return df

def get_xA_values(df):
    try:
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)
        if API_DIR not in sys.path:
            sys.path.insert(0, API_DIR)
        from app.services.xa_model import apply_pass_xa

        return apply_pass_xa(df, version="v1", force=True)
    except Exception as e:
        print(f"Warning: Could not apply v1 xA model. xA will be 0. Error: {e}")
        df = df.copy()
        df['xA'] = 0.0
        df['xa_model_version'] = None
        return df

def get_xPass_values(df):
    try:
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)
        if API_DIR not in sys.path:
            sys.path.insert(0, API_DIR)
        from app.services.xpass_model import apply_pass_xpass

        return apply_pass_xpass(df, version="v1", force=True)
    except Exception as e:
        print(f"Warning: Could not apply v1 xPass model. xPass will be 0. Error: {e}")
        df = df.copy()
        df['xPass'] = 0.0
        df['xpass_model_version'] = None
        return df

def get_EPV_values(df):
    try:
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)
        if API_DIR not in sys.path:
            sys.path.insert(0, API_DIR)
        from app.services.epv_model import apply_epv_values

        return apply_epv_values(df, version="v1", force=True)
    except Exception as e:
        print(f"Warning: Could not apply v1 EPV grid. EPV will be NaN. Error: {e}")
        df = df.copy()
        df['epv_start'] = np.nan
        df['epv_end'] = np.nan
        df['epv_added'] = np.nan
        df['epv_model_version'] = None
        df['epv_grid_version'] = None
        df['epv_feature_version'] = None
        df['epv_action_eligible'] = False
        return df

def get_possessions(events_df):
    # 1. Filter only for possession calculation
    filtered_df = events_df[~events_df['type'].isin([
        'SubstitutionOn', 'SubstitutionOff', 'FormationChange', 'FormationSet', 'End',
        'OffsideProvoked', 'Start', 'GoodSkill', 'PenaltyFaced', 'ChanceMissed', 'CrossNotClaimed',
    ])].reset_index()

    filtered_df['possession_id'] = 0
    filtered_df['possession_team'] = None
    current_possession = 1

    # Initialize first possession
    filtered_df.at[0, 'possession_id'] = current_possession
    filtered_df.at[0, 'possession_team'] = filtered_df.at[0, 'teamName']

    for i in range(1, len(filtered_df)):
        prev_team = filtered_df.at[i - 1, 'teamName']
        current_team = filtered_df.at[i, 'teamName']
        prev_type = filtered_df.at[i - 1, 'type']
        prev_outcome = filtered_df.at[i - 1, 'outcomeType']
        prev_turnover = filtered_df.at[i - 1, 'turnover']

        change_possession = False

        if prev_type == 'Goal':
            change_possession = True
        elif prev_turnover is True and current_team != prev_team:
            change_possession = True
        elif (
            current_team != prev_team and
            filtered_df.at[i, 'type'] in [
                'Tackle', 'Interception', 'Clearance', 'BallRecovery', 'Aerial', 'BlockedPass',
                'Challenge', 'KeeperPickup', 'KeeperSweeper', 'Claim'
            ] and
            filtered_df.at[i, 'outcomeType'] == 'Successful'
        ):
            change_possession = True
        elif prev_type in [
            'Goal', 'SavedShot', 'MissedShots', 'ShotOnPost', 'OffsideGiven', 'Dispossessed', 'CornerAwarded'
        ] and current_team != prev_team:
            change_possession = True
        elif (current_team != prev_team and prev_outcome == 'Unsuccessful'):
            change_possession = True

        if change_possession:
            current_possession += 1
            filtered_df.at[i, 'possession_id'] = current_possession
            filtered_df.at[i, 'possession_team'] = current_team
        else:
            filtered_df.at[i, 'possession_id'] = filtered_df.at[i - 1, 'possession_id']
            filtered_df.at[i, 'possession_team'] = filtered_df.at[i - 1, 'possession_team']

    # 2. Map possession_id and possession_team back to the original DataFrame
    events_df['possession_id'] = events_df.index.map(filtered_df.set_index('index')['possession_id'])
    events_df['possession_team'] = events_df.index.map(filtered_df.set_index('index')['possession_team'])

    return events_df

def calculate_angle(x, y):
    goal_width = 7.32
    goal_left = 34 - goal_width / 2
    goal_right = 34 + goal_width / 2
    
    a = np.sqrt((105 - x)**2 + (goal_left - y)**2)
    b = np.sqrt((105 - x)**2 + (goal_right - y)**2)
    c = goal_width

    # Law of Cosines
    angle = np.arccos((a**2 + b**2 - c**2) / (2 * a * b))
    return angle

def get_xG_values(df):
    try:
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)
        if API_DIR not in sys.path:
            sys.path.insert(0, API_DIR)
        from app.services.xg_model import apply_shot_xg

        return apply_shot_xg(df, version="v2", force=True)
    except Exception as e:
        print(f"Warning: Could not apply v2 xG model. xG will be NaN. Error: {e}")
        df = df.copy()
        df['xG'] = np.nan
        df['xg_model_version'] = None
        return df

def get_xGOT_values(df):
    try:
        if ROOT_DIR not in sys.path:
            sys.path.insert(0, ROOT_DIR)
        if API_DIR not in sys.path:
            sys.path.insert(0, API_DIR)
        from app.services.xgot_model import apply_shot_xgot

        return apply_shot_xgot(df, version="v1", force=True)
    except Exception as e:
        print(f"Warning: Could not apply v1 xGOT model. xGOT will be 0. Error: {e}")
        df = df.copy()
        df['xGOT'] = 0.0
        df['xgot_model_version'] = None
        return df

def data_preprocessing(df):
    df['period'] = df['period'].replace({'FirstHalf': 1, 'SecondHalf': 2, 'FirstPeriodOfExtraTime': 3, 'SecondPeriodOfExtraTime': 4,
                                     'PenaltyShootout': 5, 'PostGame': 14, 'PreMatch': 16})
    
    df = cumulative_match_mins(df)
    df = insert_ball_carries(df, min_carry_length=8, max_carry_length=60, min_carry_duration=4, max_carry_duration=10)

    df = df.reset_index(drop=True)
    df['index'] = range(1, len(df) + 1)
    df = df[['index'] + [col for col in df.columns if col != 'index']]

    df = df.sort_values(by=['matchId', 'index'])

    df = get_xT_values(df)

    teams_dict = {
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
        771 : 'Serbia',
        10 : 'FC Copenhagen',
        294 : 'Galatasaray',
        124 : 'Club Brugge',
        296 : 'Sporting CP',
        1770 : 'Kairat Almaty',
        130 :'Ajax',
        349 : 'Slavia Prague',
        439 : 'Bodo/Glimt',
        843 : 'Olympiacos',
        2748 : 'Pafos',
        2569 : 'Qarabag',
        2647 : 'Union Saint-Gilloise',
        990 : 'Stevenage',
        22 : 'Bradford',
        188 : 'Cardiff',
        172 : 'Stockport County',
        5955 : 'AFC Wimbledon',
        203 : 'Lincoln City',
        166 : 'Huddersfield',
        142 : 'Barnsley',
        92 : 'Bolton',
        910 : 'Doncaster',
        95 : 'Luton',
        99 : 'Mansfield',
        97 : 'Leyton Orient',
        316 : 'Northampton',
        91 : 'Port Vale',
        98 : 'Exeter',
        194 : 'Wigan',
        212 : 'Plymouth',
        196 : 'Wycombe',
        1786 : 'Burton',
        94 : 'Reading',
        210 : 'Rotherham',
        93 : 'Blackpool',
        215 : 'Peterborough',
        20 : 'Derby',
        169 : 'Portsmouth',
        197 : 'Oxford',
        160 : 'Charlton',
        185 : 'Bristol Rovers',
        258 : 'Cheltenham',
        3936 : 'Fleetwood',
        207 : 'Shrewsbury',
        193 : 'Cambridge U',
        322 : 'Carlisle',
        157 : 'Birmingham',
        199 : 'Wrexham',
        1994 : 'Crawley'
    }
 


    df['teamName'] = df['teamId'].map(teams_dict)
    team_names = list(teams_dict.values())

    df['x'] = df['x']*1.05
    df['y'] = df['y']*0.68
    df['endX'] = df['endX']*1.05
    df['endY'] = df['endY']*0.68
    df['goalMouthY'] = df['goalMouthY']*0.68

    df['qualifiers'] = df['qualifiers'].astype(str)
    df = get_EPV_values(df)

    # Calculating passing distance, to find out progressive pass, this will just show the distance reduced by a pass, then will be able to filter passes which has reduced distance value more than 10yds as a progressive pass
    df['prog_pass'] = np.where((df['type'] == 'Pass'),
                            np.sqrt((105 - df['x'])**2 + (34 - df['y'])**2) - np.sqrt((105 - df['endX'])**2 + (34 - df['endY'])**2), 0)
    # Calculating carrying distance, to find out progressive carry, this will just show the distance reduced by a carry, then will be able to filter carries which has reduced distance value more than 10yds as a progressive carry
    df['prog_carry'] = np.where((df['type'] == 'Carry'),
                                np.sqrt((105 - df['x'])**2 + (34 - df['y'])**2) - np.sqrt((105 - df['endX'])**2 + (34 - df['endY'])**2), 0)
    df['pass_or_carry_angle'] = np.degrees(np.arctan2(df['endY'] - df['y'], df['endX'] - df['x']))

    # Normalize names to ASCII while preserving missing values.
    def normalize_player_name(name):
        if pd.isna(name):
            return np.nan
        return unidecode(str(name))

    df['playerName'] = df['playerName'].apply(normalize_player_name)

    df['qualifiers'] = df['qualifiers'].astype(str)
    columns_to_drop2 = ['id']
    df.drop(columns=columns_to_drop2, inplace=True)

    df['period'] = df['period'].replace({1: 'FirstHalf', 2: 'SecondHalf', 3: 'FirstPeriodOfExtraTime', 4: 'SecondPeriodOfExtraTime',
                                        5: 'PenaltyShootout', 14: 'PostGame', 16: 'PreMatch'})
    df = get_xA_values(df)
    df['xA'] = df['xA'].fillna(0)

    df = get_xPass_values(df)
    df['xPass'] = df['xPass'].fillna(0)
    
    df = get_xG_values(df)
    df = get_xGOT_values(df)
    df['xG'] = df['xG'].fillna(0)
    df['xGOT'] = df['xGOT'].fillna(0)
    #df = get_possessions(df)

    return df
