from utils import *
import random
import streamlit as st
import pandas as pd
import os,glob
#from st_aggrid import AgGrid
#from st_aggrid.grid_options_builder import GridOptionsBuilder
import psycopg2
from matplotlib.colors import to_rgb, to_hex
import colorsys
from pathlib import Path
import s3fs
import pandas as pd
import os

# ... your other imports ...

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

@st.cache_data(ttl=600)

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
    
team_colors = {
    'Sunderland' : '#E30613',
    'Burnley' : '#6C1D45',
    'Leeds' : '#F2F2F2',
    'Levante' : '#005BAC',
    'Elche' : '#005BAC',
    'Real Oviedo' : '#005BAC',
    'Sassuolo' : "#00AC34",
    'Pisa' : '#C49E21',
    'Cremonese' : '#E30613',
    'FC Koln' : '#E30613',
    'Hamburger SV' : "#0641E3",
    'Lorient' : "#B3E306",
    'Paris FC' : '#005BAC',
    'Metz' : "#AC002B",
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


logo_path = f'logos/PB.png'
# Set the path to the locally downloaded font file
font_path = f'Sora-Regular.ttf'

# Add the font to matplotlib
font_prop = fm.FontProperties(fname=font_path)
st.set_page_config(layout="centered")

league = st.session_state.get('league')
season = st.session_state.get('season')
home_team = st.session_state.get('home_team')
away_team = st.session_state.get('away_team')
matchId = st.session_state.get('matchId')

# Now use these variables as needed



file_path = st.session_state.get('file_path')
if not file_path:
    st.error("No match file selected.")
    st.stop()



match_df = load_match_data_from_r2(file_path)
match_df = load_and_process_match_data(match_df, team_colors)


home_team_col = match_df[match_df['teamName'] == home_team]['teamColor'].unique()[0]
away_team_col = match_df[match_df['teamName'] == away_team]['teamColor'].unique()[0]

def adjust_color_if_similar(home_color, away_color, threshold=0.2):
    # Convert hex to RGB
    home_rgb = to_rgb(home_color)
    away_rgb = to_rgb(away_color)
    # Calculate Euclidean distance
    dist = sum((h - a) ** 2 for h, a in zip(home_rgb, away_rgb)) ** 0.5
    if dist < threshold:
        # Convert to HLS, adjust lightness
        h, l, s = colorsys.rgb_to_hls(*away_rgb)
        l = min(1, l + 0.5)  # Lighten away color
        new_away_rgb = colorsys.hls_to_rgb(h, l, s)
        return to_hex(new_away_rgb)
    return away_color



# After you get home_team_col and away_team_col:
away_team_col = adjust_color_if_similar(home_team_col, away_team_col)

if 'Carry' not in match_df['type'].unique():
    match_df = insert_ball_carries(match_df, min_carry_length=10, max_carry_length=60, min_carry_duration=6, max_carry_duration=10)

    # After inserting carries
    match_df['teamId'] = pd.to_numeric(match_df['teamId'], errors='coerce').astype('Int64')

    # Map teamName and teamColor for ALL rows (not just fillna)
    match_df['teamName'] = match_df['teamId'].map(team_dict)
    match_df['teamColor'] = match_df['teamName'].map(team_colors)

    match_df['prog_carry'] = np.where((match_df['type'] == 'Carry'),
                                np.sqrt((105 - match_df['x'])**2 + (34 - match_df['y'])**2) - np.sqrt((105 - match_df['endX'])**2 + (34 - match_df['endY'])**2), 0)



# Use HTML for colored team names in the title
st.markdown(
    f"<h1 style='text-align: center;'>"
    f"<span style='color:{home_team_col};'>{home_team}</span> "
    f"<span style='color:gray;'>vs</span> "
    f"<span style='color:{away_team_col};'>{away_team}</span>"
    f"</h1>",
    unsafe_allow_html=True
)





with st.sidebar:
    theme = st.radio(
        'Theme',
        options=['🌙 Dark', '☀️ Light'],
        index=0,
        horizontal=True
    )

    viz_options = ['Match Dynamics', 'Shots', 'In Possession', 'Out of Possession', 'Duels and Transitions']
    if "selected_viz" not in st.session_state:
        st.session_state.selected_viz = viz_options[0]
    for i, option in enumerate(viz_options):
        is_selected = st.session_state.selected_viz == option
        if st.button(option, key=f"viz_{option}"):
            st.session_state.selected_viz = option
    viz = st.session_state.selected_viz

if theme == '🌙 Dark':
        background = "#010b14"
        line_color = 'white'
        text_color = 'white'
        logo = mpimg.imread(logo_path)

else:
    background = "#FFFFFF"
    line_color = 'black'
    text_color = 'black'
    logo = mpimg.imread(logo_path)


if viz == 'Match Dynamics':
    st.markdown("## Match Dynamics")

    poss_df = tag_sequences_and_possessions_all_matches(match_df)



    st.markdown("### xG Flow")
    fig4, axs4 = plt.subplots(nrows=1, ncols=1, figsize=(20,12))
    fig4.set_facecolor(background)
    axs4.set_facecolor(background)



    xgFlow(axs4,match_df,home_team,away_team,home_team_col,away_team_col,text_color,background)
    st.pyplot(fig4)

    st.markdown("### Ball Possession % and Pass Accuracy %")
    fig2, axs2 = plt.subplots(nrows=1, ncols=2, figsize=(20,9))
    fig2.set_facecolor(background)
    axs2[0].set_facecolor(background)
    axs2[1].set_facecolor(background)

    
    plot_possession_windows_time_weighted(
        ax=axs2[0],
        df=poss_df,
        home_team=home_team,
        away_team= away_team,
        team_colors={home_team: home_team_col, away_team: away_team_col},
        background=background,
        text_color=text_color,
        font_prop=font_prop
    )

    plot_pass_accuracy_windows(
        ax=axs2[1],
        df=poss_df,
        home_team=home_team,
        away_team= away_team,
        team_colors={home_team: home_team_col, away_team: away_team_col},
        background=background,
        text_color=text_color,
        font_prop=font_prop
    )
    st.pyplot(fig2)

    st.markdown('### Attack By Flanks')

    fig5, axs5 = plt.subplots(nrows=1, ncols=2, figsize=(20,12))
    fig5.set_facecolor(background)
    axs5[0].set_facecolor(background)
    axs5[1].set_facecolor(background)

    h_attacks = get_number_of_attacks(poss_df,home_team)
    a_attacks = get_number_of_attacks(poss_df,away_team)

    #st.dataframe(h_attacks, use_container_width=True)
    #st.dataframe(a_attacks, use_container_width=True)

    plot_attacks(h_attacks,home_team_col,background,text_color,font_prop,axs5[0])
    plot_attacks(a_attacks,away_team_col,background,text_color,font_prop,axs5[1])
    st.pyplot(fig5)




    st.markdown('### PPDA and Turnovers Conceded')
    fig3, axs3 = plt.subplots(nrows=1, ncols=2, figsize=(20,9))
    fig3.set_facecolor(background)
    axs3[0].set_facecolor(background)
    axs3[1].set_facecolor(background)

    plot_ppda(poss_df, axs3[0], home_team, away_team, home_team_col, away_team_col, background, text_color, font_prop)
    plot_turnovers(poss_df, axs3[1], home_team, away_team, home_team_col, away_team_col, background, text_color, font_prop)
    st.pyplot(fig3)

    fig, axs = plt.subplots(nrows=1, ncols=1, figsize=(20,12))
    fig.set_facecolor(background)
    axs.set_facecolor(background)
    st.markdown("### xT Momentum Flow")
    xT_momemtum(axs,match_df,home_team,away_team,home_team_col,away_team_col,background,text_color)
    st.pyplot(fig)

if viz == 'Shots':
    if "selected_shot_player" not in st.session_state:
        st.session_state.selected_shot_player = None

    st.markdown("## Shot Map")

    team_options = [home_team, away_team]
    selected_team = st.radio("Select Team", team_options, index=0, horizontal=True)

    pitch = Pitch(pitch_type='uefa', half=False, corner_arcs=True, pitch_color=background, line_color=line_color, linewidth=1.5)

    fig, axs = pitch.jointgrid(figheight=20, grid_width=1, left=None, bottom=None, grid_height=0.9,
                                axis=False, title_space=0, endnote_height=0, title_height=0, ax_top=False)
    fig.set_facecolor(background)
    summary_df, player_df, home_shots_df, away_shots_df = shotMap_ws(
        match_df, axs, pitch, home_team, away_team, home_team_col, away_team_col, text_color, background, situation=None, selected_player=None
    )

    #summary_df, player_df, shots_df = shotMap_ws(match_df, axs, pitch, home_team, home_team_col, text_color, background, situation=None, selected_player=None)
    player_df_filtered = player_df[player_df['Team'] == selected_team]

    # Get selected player
    selected_player = st.session_state.selected_shot_player
    situation = st.radio('', options=['All'] + match_df['situation'].dropna().unique().tolist(), index=0, horizontal=True, label_visibility='collapsed')

    # Create figure with 2 rows, ratio 1:2
    fig, (ax_goal, ax_field) = plt.subplots(2, 1, figsize=(12, 12), gridspec_kw={'height_ratios': [2, 3.5]})
    fig.set_facecolor(background)
    ax_goal.set_facecolor(background)
    ax_field.set_facecolor(background)

    # Plot on the axes
    plot_team_shotmaps_stacked(
        match_df, selected_team, team_colors[selected_team], background, text_color, font_prop,
        ax_goal, ax_field, selected_player, situation
    )

    st.pyplot(fig)
    
    # --- Player selection table with buttons ---
    st.markdown("### Player Shot Summary")
    # Clear selection button
    if st.button("Clear Shot Selection"):
        st.session_state.selected_shot_player = None
        st.rerun()

    # If a player is selected, show their shot details
    if st.session_state.selected_shot_player:
        # Filter shots for selected player and team
        shot_details = match_df[
            (match_df['teamName'] == selected_team) &
            (match_df['playerName'] == st.session_state.selected_shot_player) &
            (match_df['type'].isin(['Goal', 'MissedShots', 'SavedShot', 'ShotOnPost']))
        ][['minute', 'second', 'type', 'xG', 'situation','shotBodyType','shotBlocked','shotOffTarget', 'shotOnTarget']]
        shot_details = shot_details.sort_values(['minute', 'second'])
        st.markdown(f"#### Shots by {st.session_state.selected_shot_player}")
        st.dataframe(shot_details, use_container_width=True)
    else:
        # Show player summary table with selection buttons
        for i, row in player_df_filtered.reset_index().iterrows():
            col1, col2 = st.columns([1, 5])
            with col1:
                if st.button(row['playerName'], key=f"shot_{row['playerName']}"):
                    st.session_state.selected_shot_player = row['playerName']
                    st.rerun()
            with col2:
                st.dataframe(pd.DataFrame([row.drop(['index', 'playerName'])]), use_container_width=True)

if viz == 'In Possession':

    st.markdown("## Passing Network and Pass Combination Matrix")
    #st.dataframe(match_df[match_df['subOff'] != 0][['index','matchId','minute','second','event_time','playerName','isFirstEleven']], width=1000)
    passes_df = get_passes_df(match_df)
    team = st.radio('',options=[home_team, away_team],index=0,horizontal=True, label_visibility='collapsed')
    fig, axs = plt.subplots(nrows=1, ncols=1, figsize=(20,15))
    fig.set_facecolor(background)
    
    ax_image = add_image(
        logo, fig, left=0.82, bottom=0.83, width=0.07, height=0.07,aspect='equal'
    )


    if team == home_team:
        
        # Get and sort substitution minutes
        minute_of_subs = match_df[
            (match_df['teamName'] == home_team) & (match_df['type'] == 'SubstitutionOn')
        ]['minute'].unique()

        minute_of_subs = np.sort(minute_of_subs[minute_of_subs < 90])

        # Only keep substitutions that result in a 5+ minute window
        filtered_minutes = []
        prev = 0
        for m in minute_of_subs:
            if m - prev >= 5:
                filtered_minutes.append(m)
                prev = m

        # If the last window (from last sub to 90) is too short, drop the last one
        if len(filtered_minutes) > 0 and 90 - filtered_minutes[-1] < 5:
            filtered_minutes.pop()

        # Generate the options
        def ordinal(n):
            return ['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth'][n - 1]

        options = ['Starting 11']
        for i in range(len(filtered_minutes)):
            options.append(f'{ordinal(i+1)} Substitution')

        # Radio selector
        substitutions = st.radio('', options=options, index=0, horizontal=True, label_visibility='collapsed')

        # Determine minute_start and minute_end
        if substitutions == 'Starting 11':
            minute_start = 0
            minute_end = filtered_minutes[0] if filtered_minutes else 90
        else:
            index = options.index(substitutions) - 1
            minute_start = filtered_minutes[index]
            minute_end = filtered_minutes[index + 1] if index + 1 < len(filtered_minutes) else 90


        fig.text(
        0.16, 0.86, f"Minute {minute_start}-{minute_end}",fontproperties=font_prop,
        ha='left', va='center', fontsize=45, color=text_color
        )

        filtered_passes_df = filter_passes_for_subwindow(match_df, passes_df, home_team, minute_start, minute_end)

        home_passes_between_df, home_average_locs_and_count_df = get_passes_between_df(home_team, filtered_passes_df)
        ci = calculate_centralization_index(home_team,filtered_passes_df)
        pass_network_visualization(axs, match_df, home_passes_between_df, home_average_locs_and_count_df, text_color, background, home_team_col, home_team, 20, False,ci)
        st.pyplot(fig)

        st.markdown("##### The centralization index signifies how much a team's passing network is focused around a few players — a higher value indicates greater reliance on central figures, while a lower value reflects a more balanced, distributed passing structure.")

        fig2,ax2 = plt.subplots(nrows=1, ncols=1, figsize=(20,10))
        fig2.set_facecolor(background)
        pass_matrix = get_pass_matrix(passes_df, home_team)
        custom_cmap = LinearSegmentedColormap.from_list("custom_green", [background, home_team_col])
        annotations = pass_matrix.map(lambda x: f"{x}" if x >= 5 else "")
        sns.heatmap(pass_matrix, annot=annotations, cmap=custom_cmap, fmt='', linewidths=1, square=True,cbar=False,annot_kws={"size": 14},ax=ax2)

        #ax.set_title('Pass Combination Matrix')
        ax2.set_xlabel('Receiver', fontproperties=font_prop,fontsize=18, color=text_color)
        ax2.set_ylabel('Passer', fontproperties=font_prop,fontsize=18, color=text_color)
        plt.xticks(rotation=90, fontproperties=font_prop,fontsize=12, color=text_color)
        plt.yticks(rotation=0, fontproperties=font_prop,fontsize=12, color=text_color)
        st.pyplot(fig2)
    else:
        # Get and sort substitution minutes
        minute_of_subs = match_df[
            (match_df['teamName'] == away_team) & (match_df['type'] == 'SubstitutionOn')
        ]['minute'].unique()

        minute_of_subs = np.sort(minute_of_subs[minute_of_subs < 90])

        # Only keep substitutions that result in a 5+ minute window
        filtered_minutes = []
        prev = 0
        for m in minute_of_subs:
            if m - prev >= 5:
                filtered_minutes.append(m)
                prev = m

        # If the last window (from last sub to 90) is too short, drop the last one
        if len(filtered_minutes) > 0 and 90 - filtered_minutes[-1] < 5:
            filtered_minutes.pop()

        # Generate the options
        def ordinal(n):
            return ['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth'][n - 1]

        options = ['Starting 11']
        for i in range(len(filtered_minutes)):
            options.append(f'{ordinal(i+1)} Substitution')

        # Radio selector
        substitutions = st.radio('', options=options, index=0, horizontal=True, label_visibility='collapsed')

        # Determine minute_start and minute_end
        if substitutions == 'Starting 11':
            minute_start = 0
            minute_end = filtered_minutes[0] if filtered_minutes else 90
        else:
            index = options.index(substitutions) - 1
            minute_start = filtered_minutes[index]
            minute_end = filtered_minutes[index + 1] if index + 1 < len(filtered_minutes) else 90

        
        fig.text(
        0.16, 0.86, f"Minute {minute_start}-{minute_end}",fontproperties=font_prop,
        ha='left', va='center', fontsize=45, color=text_color
        )
        filtered_passes_df = filter_passes_for_subwindow(match_df, passes_df, away_team, minute_start, minute_end)

        away_passes_between_df, away_average_locs_and_count_df = get_passes_between_df(away_team, filtered_passes_df)
        ci = calculate_centralization_index(away_team,filtered_passes_df)
        pass_network_visualization(axs, match_df, away_passes_between_df, away_average_locs_and_count_df, text_color, background, away_team_col, away_team, 20, False,ci)
        st.pyplot(fig)

        st.markdown("##### The centralization index signifies how much a team's passing network is focused around a few players — a higher value indicates greater reliance on central figures, while a lower value reflects a more balanced, distributed passing structure.")


        fig2,ax2 = plt.subplots(nrows=1, ncols=1, figsize=(20,10))
        fig2.set_facecolor(background)
        pass_matrix = get_pass_matrix(passes_df, away_team)
        custom_cmap = LinearSegmentedColormap.from_list("custom_green", [background, away_team_col])
        annotations = pass_matrix.map(lambda x: f"{x}" if x >= 5 else "")
        sns.heatmap(pass_matrix, annot=annotations, cmap=custom_cmap, fmt='', linewidths=1, square=True,cbar=False,annot_kws={"size": 14},ax=ax2)

        #ax.set_title('Pass Combination Matrix')
        ax2.set_xlabel('Receiver', fontproperties=font_prop,fontsize=18, color=text_color)
        ax2.set_ylabel('Passer', fontproperties=font_prop,fontsize=18, color=text_color)
        plt.xticks(rotation=90, fontproperties=font_prop,fontsize=12, color=text_color)
        plt.yticks(rotation=0, fontproperties=font_prop,fontsize=12, color=text_color)
        st.pyplot(fig2)


    st.markdown("## Passing Stats Comparison")
    # Define desired order for metrics and teams
    metric_order = [
        'Total Passes', 'Passing Accuracy (%)', 'Final Third Entries',
        'Key Passes', 'Crosses', 'Long Balls',
        'Through Balls', 'Progressive Passes', 'Pen Box Passes','Expected Threat By Pass'
    ]

    team_order = [home_team, away_team]  # You can reverse this if needed

    # Get passing stats
    passes_stats_hteam = get_passing_stats(match_df, home_team)
    passes_stats_ateam = get_passing_stats(match_df, away_team)

    # Combine and reshape
    combined_stats = pd.concat([passes_stats_hteam, passes_stats_ateam], axis=0)
    combined_stats = combined_stats.melt(id_vars='Team', var_name='Metric', value_name='Value')
    combined_stats = combined_stats.pivot(index='Metric', columns='Team', values='Value')

    # Reorder rows and columns
    combined_stats = combined_stats.loc[metric_order, team_order]
    styled_stats = combined_stats.style \
    .apply(lambda row: [highlight_higher(v, row.values) for v in row], axis=1) \
    .format("{:.2f}")

    st.dataframe(styled_stats, width=1000)


    # --- Passmaps Section ---
    # Team filter above pitch and player stats
    team_filter = st.radio("Select Team", [home_team, away_team], horizontal=True, index=0)

    # Add half selection radio
    half_option = st.radio(
        "Select Half",
        options=["Full 90", "First Half", "Second Half"],
        index=0,
        horizontal=True
    )

    # Pass type selection
    passtypes = ['All', 'Crosses', 'Long Balls', 'Through Balls', 'Carries', 'Dribbles']
    passtype = st.radio('', options=passtypes, index=0, horizontal=True, label_visibility='collapsed')
    combined_df = match_df[match_df['type'].isin(['Pass', 'Carry', 'TakeOn'])].copy()

    # Filter match_df for the selected half
    if half_option == "First Half":
        match_df_half = match_df[match_df['period'] == 'FirstHalf']
    elif half_option == "Second Half":
        match_df_half = match_df[match_df['period'] == 'SecondHalf']
    else:
        match_df_half = match_df

    fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(30, 12))
    fig.set_facecolor(background)
    plt.subplots_adjust(wspace=0.02)

    if "selected_pass_player" not in st.session_state:
        st.session_state.selected_pass_player = None
    selected_player = st.session_state.selected_pass_player
    if passtype == "All" and selected_player:
            pass_kde_mode = st.radio(
                "Show KDE for:",
                options=["Passes Played", "Passes Received"],
                index=0,
                horizontal=True
            )
    else:
        pass_kde_mode = "Passes Played"  # Default/fallback
    # --- Passmaps plotting ---

    

    # Filter passes_df before passing to pass_network_visualization
    if passtype == 'All' and not selected_player:
        phase_options = ['All', 'Build Up', 'Progression', 'Chance Creation']
        selected_phase = st.radio("Select Phase of Play", phase_options, horizontal=True, index=0)

        def filter_passes_by_phase(df, phase):
            if phase == 'Build Up':
                return df[(df['type'].isin(['Pass','Carry','TakeOn'])) & (df['x'] < 52.5)]
            elif phase == 'Progression':
                return df[(df['type'].isin(['Pass','Carry','TakeOn'])) & (df['x'] >= 52.5) & (df['x'] < 75) & (df['endX'] >= 75) & ((df['prog_carry'] >= 2) | (df['prog_pass'] >= 2))]
            elif phase == 'Chance Creation':
                return df[(df['type'].isin(['Pass','Carry','TakeOn'])) & (
                    (df['endX'] >= 88.5) & (df['endY'] >= 13.6) & (df['endY'] <= 54.4) |
                    (df['passKey'] == True) |
                    (df['xT'] > 0.05)
                )]
            else:
                return df[df['type'] == 'Pass']
        filtered_passes_df = filter_passes_by_phase(match_df_half, selected_phase)
    else:
        filtered_passes_df = match_df_half

    top_passers_h, top_passers_a = passmaps(
        ax, filtered_passes_df,passes_df, home_team, home_team_col, away_team, away_team_col,
        background, text_color, passtype, selected_player, team_filter,pass_kde_mode
    )
    top_passers_h = top_passers_h.reset_index(drop=True)
    top_passers_a = top_passers_a.reset_index(drop=True)

    # --- Build pass type counts, assists, xA for each player ---
    def get_pass_type_counts(df, team):
        passes = df[(df['type'].isin(['Pass','TakeOn','Carry'])) & (df['teamName'] == team)].copy()
        #passes['Final Third Entries'] = ((passes['x'] < 75) & (passes['endX'] >= 75) & (passes['outcomeType'] == 'Successful')).astype(int)
        passes['Crosses'] = (passes['qualifiers'].str.contains('Cross', na=False) & (passes['outcomeType'] == 'Successful')).astype(int)
        passes['Long Balls'] = (passes['qualifiers'].str.contains('Longball', na=False) & (passes['outcomeType'] == 'Successful')).astype(int)
        passes['Through Balls'] = (passes['qualifiers'].str.contains('Throughball', na=False) & (passes['outcomeType'] == 'Successful')).astype(int)
        passes['Total Passes'] = 1
        #passes['Assist'] = passes['assist'].astype(int) if 'assist' in passes.columns else 0
        passes['xA'] = passes['xA'] if 'xA' in passes.columns else 0.0
        passes['Carries'] = ((passes['type'] == 'Carry') & (passes['outcomeType'] == 'Successful') & (passes['prog_carry'] >= 5)).astype(int)
        passes['Dribbles'] = (passes['type'] == 'TakeOn').astype(int)

        summary = passes.groupby('playerName').agg({
            #'Final Third Entries': 'sum',
            'Crosses': 'sum',
            'Long Balls': 'sum',
            'Through Balls': 'sum',
            'Total Passes': 'sum',
            'assist': 'sum',
            'xA': 'sum',
            'Carries': 'sum',
            'Dribbles': 'sum'
        }).reset_index()
        summary = summary.rename(columns={'assist': 'Assist'})
        summary = summary.sort_values('Total Passes', ascending=False)
        return summary

    home_pass_summary = get_pass_type_counts(match_df_half, home_team)
    away_pass_summary = get_pass_type_counts(match_df_half, away_team)

    # --- Display pitch ---
    st.pyplot(fig)
    st.markdown("Star marker indicates key pass / chance created and green line indicates an assist.")

    # --- Interactive player pass stats DataFrame ---
    if team_filter == home_team:
        pass_summary = home_pass_summary
    else:
        pass_summary = away_pass_summary

    # --- Clear selection button ---
    if st.button("Clear Selection"):
        st.session_state.selected_pass_player = None
        st.rerun()
    # Add playerName as buttons in the DataFrame
    def player_button(label, key):
        return st.button(label, key=key)


    for i, row in pass_summary.reset_index().iterrows():
        col1, col2 = st.columns([1, 7])
        with col1:
            if st.button(row['playerName'], key=f"{team_filter}_pass_{row['playerName']}_{i}"):
                st.session_state.selected_pass_player = row['playerName']
                st.rerun()
        with col2:
            st.dataframe(pd.DataFrame([row.drop(['index', 'playerName'])]), use_container_width=True)
    
if viz == 'Duels and Transitions':
    st.markdown("## Duels")
    duel_type = st.radio(
        '',
        options = ['Total', 'Offensive', 'Defensive', 'Aerial'],
        index=0, horizontal=True, label_visibility='collapsed'
    )

    # --- Add time bin filter ---

    match_df['timestamp'] = match_df['minute'] * 60 + match_df['second']
    match_df['timestamp'] = match_df['timestamp'].replace([np.inf, -np.inf], np.nan)
    match_df = match_df.dropna(subset=['timestamp'])
    match_df['time_bin'] = (match_df['timestamp'] // 900).astype(int)

    bin_labels = ['Full 90'] + [f"{i*15}-{(i+1)*15}" for i in range(6)]
    selected_bin = st.selectbox("Select Time Bin (minutes)", bin_labels, index=0)

    if selected_bin == 'Full 90':
        duels_df = match_df
    else:
        bin_idx = bin_labels.index(selected_bin) - 1
        duels_df = match_df[match_df['time_bin'] == bin_idx]

    fig, axs = plt.subplots(nrows=1, ncols=1, figsize=(20,15))
    fig.set_facecolor(background)
    axs.set_facecolor(background)
    h_players , a_players = plot_duels_by_type(
        axs, duels_df, home_team, away_team, duel_type,
        home_team_col, away_team_col, background, text_color
    )
    h_players.columns = [f'{home_team} Player', f'{home_team} Duels Won']
    a_players.columns = [f'{away_team} Player', f'{away_team} Duels Won']

    st.pyplot(fig)
    h_players = h_players.dropna(subset=[f'{home_team} Player'])
    a_players = a_players.dropna(subset=[f'{away_team} Player'])
    st.markdown(f"### {home_team} Duels Won")
    st.dataframe(h_players, use_container_width=True)
    st.markdown(f"### {away_team} Duels Won")
    st.dataframe(a_players, use_container_width=True)


    st.markdown("## Transitions Heatmap")
    poss_df = tag_sequences_and_possessions_all_matches(match_df)
    transition_type = st.radio("Select Transition Type", ["Offensive", "Defensive"], horizontal=True)
    team_options = [home_team, away_team]
    selected_team = st.radio("Select Team", team_options, horizontal=True, index=0)

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.set_facecolor(background)
    ax.set_facecolor(background)
    pitch = Pitch(pitch_type='uefa', pitch_color=background, line_color=text_color, linewidth=1.5)

    if selected_team == home_team:
            flagged = True
    else:
            flagged = False

    if transition_type == "Offensive":

        summary_df, transitions_df = offensive_transition_heatmap(
            poss_df, selected_team, ax, pitch, background, team_colors[selected_team], text_color, font_prop, flagged, selected_third=st.session_state.get('selected_third')
        )
        st.markdown("### Offensive Transition Heatmap")
        st.pyplot(fig)
        # After summary_df is created by offensive_transition_heatmap or defensive_transition_heatmap

        st.markdown("#### Percentage of Transitions Leading to Attack (by Third)")
        if st.button("Clear Selection"):
            st.session_state.selected_third = None
            st.rerun()

        for i, row in summary_df.iterrows():
            cols = st.columns([1, 5])
            with cols[0]:
                if st.button(row['third'], key=f"third_{row['third']}_{i}"):
                    st.session_state.selected_third = row['third']
                    st.rerun()
            with cols[1]:
                st.dataframe(pd.DataFrame([row.drop(['third'])]), use_container_width=True)

        # Highlight pitch and show details if a third is selected
        if "selected_third" in st.session_state and st.session_state.selected_third:
            selected_third = st.session_state.selected_third

            # Filter transitions for the selected third and show details
            filtered_transitions = transitions_df[transitions_df['third'] == selected_third]
            st.markdown(f"#### Transition Details for {selected_third}")
            cols_to_drop = ['x', 'y', 'third', 'possession_id']
            filtered_transitions_display = filtered_transitions.drop(columns=cols_to_drop, errors='ignore')
            st.dataframe(filtered_transitions_display, use_container_width=True)

    else:

        summary_df, transitions_df = defensive_transition_heatmap(
            poss_df, selected_team, ax, pitch, background, team_colors[selected_team], text_color, font_prop,flagged,st.session_state.selected_third
        )
        st.markdown("### Defensive Transition Heatmap")
        st.pyplot(fig)
        st.markdown("#### Percentage of Defensive Transitions Leading to Conceded Attack (by Third)")
        if st.button("Clear Selection"):
            st.session_state.selected_third = None
            st.rerun()

        for i, row in summary_df.iterrows():
            cols = st.columns([1, 5])
            with cols[0]:
                if st.button(row['third'], key=f"third_{row['third']}_{i}"):
                    st.session_state.selected_third = row['third']
                    st.rerun()
            with cols[1]:
                st.dataframe(pd.DataFrame([row.drop(['third'])]), use_container_width=True)

        # Highlight pitch and show details if a third is selected
        if "selected_third" in st.session_state and st.session_state.selected_third:
            selected_third = st.session_state.selected_third

            # Filter transitions for the selected third and show details
            filtered_transitions = transitions_df[transitions_df['third'] == selected_third]
            st.markdown(f"#### Transition Details for {selected_third}")
            cols_to_drop = ['x', 'y', 'third', 'possession_id']
            filtered_transitions_display = filtered_transitions.drop(columns=cols_to_drop, errors='ignore')
            st.dataframe(filtered_transitions_display, use_container_width=True)
            st.markdown("##### BallTouch refers to miscontrol or bad first touch that leads to a transition.")

if viz == 'Out of Possession':
    st.markdown("## OOP Actions")
    team = st.radio('',options=[home_team, away_team],index=0,horizontal=True, label_visibility='collapsed')
    halves = st.radio('',options=['Full 90','First Half', 'Second Half'],index=0,horizontal=True, label_visibility='collapsed')
    fig, axs = plt.subplots(nrows=1, ncols=1, figsize=(20,16))
    fig.set_facecolor(background)
    axs.set_facecolor(background)
    if team == home_team:
        defensive_actions_df = match_df[match_df['teamName'] == home_team]
        team_color = home_team_col
        if halves == 'First Half':
            defensive_actions_df = defensive_actions_df[defensive_actions_df['period'] == 'FirstHalf']
        elif halves == 'Second Half':
            defensive_actions_df = defensive_actions_df[defensive_actions_df['period'] == 'SecondHalf']
        
        if "selected_player" not in st.session_state:
            st.session_state.selected_player = None
        #defensive_block(axs,defensive_actions_df,away_team,away_team_col,background,text_color,True)
        defensive_block_with_player_actions(axs, defensive_actions_df, home_team, home_team_col, background, text_color,
                                        flipped=False, selected_player_name=st.session_state.selected_player)
        st.pyplot(fig)

        zone_filter = st.selectbox("Select Defensive Zone", ["All", "Attacking Third", "Middle Third", "Defensive Third"])
        team_df = get_defensive_action_distribution_by_type(defensive_actions_df, zone=zone_filter, halves=halves)
        # Show table row by row with a button for each player
        if st.button("Clear Selected Player"):
            st.session_state.selected_player = None
            st.rerun()

        for i, row in team_df.reset_index().iterrows():
            col1, col2 = st.columns([1, 5])
            with col1:
                if st.button(row['playerName'], key=f"player_{row['playerName']}"):
                    st.session_state.selected_player = row['playerName']  # ✅ FIXED HERE
                    st.rerun()  # Immediately rerun to update pitch
            with col2:
                st.dataframe(pd.DataFrame([row.drop(['index', 'playerName'])]), use_container_width=True)


    else:
        defensive_actions_df = match_df[match_df['teamName'] == away_team]
        team_color = away_team_col
        if halves == 'First Half':
            defensive_actions_df = defensive_actions_df[defensive_actions_df['period'] == 'FirstHalf']
        elif halves == 'Second Half':
            defensive_actions_df = defensive_actions_df[defensive_actions_df['period'] == 'SecondHalf']
        
        if "selected_player" not in st.session_state:
            st.session_state.selected_player = None
        #defensive_block(axs,defensive_actions_df,away_team,away_team_col,background,text_color,True)
        defensive_block_with_player_actions(axs, defensive_actions_df, away_team, away_team_col, background, text_color,
                                        flipped=True, selected_player_name=st.session_state.selected_player)
        st.pyplot(fig)

        zone_filter = st.selectbox("Select Defensive Zone", ["All", "Attacking Third", "Middle Third", "Defensive Third"])
        team_df = get_defensive_action_distribution_by_type(defensive_actions_df, zone=zone_filter, halves=halves)
        # Show table row by row with a button for each player
        if st.button("Clear Selected Player"):
            st.session_state.selected_player = None
            st.rerun()

        for i, row in team_df.reset_index().iterrows():
            col1, col2 = st.columns([1, 5])
            with col1:
                if st.button(row['playerName'], key=f"player_{row['playerName']}"):
                    st.session_state.selected_player = row['playerName']  # ✅ FIXED HERE
                    st.rerun()  # Immediately rerun to update pitch
            with col2:
                st.dataframe(pd.DataFrame([row.drop(['index', 'playerName'])]), use_container_width=True)


st.markdown("<hr style='border: 1px solid #eee;'>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align: center; color: white; font-size: 0.85em;'>"
    "<a href='https://x.com/chadha_ishdeep' style='color: white;' target='_blank'>Created by @chadha_ishdeep</a>"
    "</div>",
    unsafe_allow_html=True
)


