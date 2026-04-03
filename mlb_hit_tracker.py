import streamlit as st
import requests
import pandas as pd
import datetime
import plotly.express as px

# ====================== CACHED API FUNCTIONS ======================
@st.cache_data(ttl=1800)
def get_todays_games():
    today = datetime.date.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=team"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        games = []
        for date in data.get("dates", []):
            for game in date.get("games", []):
                away = game.get("teams", {}).get("away", {}).get("team", {})
                home = game.get("teams", {}).get("home", {}).get("team", {})
                games.append({
                    "gamePk": game.get("gamePk"),
                    "awayTeam": away.get("name"),
                    "awayAbbrev": away.get("abbreviation"),
                    "awayId": away.get("id"),
                    "homeTeam": home.get("name"),
                    "homeAbbrev": home.get("abbreviation"),
                    "homeId": home.get("id"),
                    "display": f"{away.get('abbreviation', '???')} @ {home.get('abbreviation', '???')} ({game.get('status', {}).get('detailedState', 'Scheduled')})"
                })
        return games
    except Exception:
        return []

@st.cache_data(ttl=1800)
def get_team_active_roster(team_id: int):
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        roster = resp.json().get("roster", [])
        batters = []
        for entry in roster:
            pos_code = entry.get("position", {}).get("code")
            if pos_code and pos_code != "P":
                person = entry.get("person", {})
                batters.append({
                    "id": person.get("id"),
                    "fullName": person.get("fullName"),
                    "position": entry.get("position", {}).get("abbreviation", "?")
                })
        return batters
    except Exception:
        return []

@st.cache_data(ttl=3600)
def get_player_info(player_id: int):
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        people = resp.json().get("people", [])
        return people[0] if people else None
    except Exception:
        return None

# Current season only
@st.cache_data(ttl=3600)
def get_game_log(player_id: int):
    current_year = datetime.datetime.now().year
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group=hitting&season={current_year}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        stats = resp.json().get("stats", [])
        return stats[0].get("splits", []) if stats else []
    except Exception:
        return []


# ====================== STREAMLIT APP ======================
st.set_page_config(page_title="MLB Batter Stats", page_icon="⚾", layout="wide")

st.title("⚾ MLB Active Batter Recent Game Stats")

# ====================== SIDEBAR FILTERS ======================
with st.sidebar:
    st.header("🎮 Filters")
    
    today_games = get_todays_games()
    if not today_games:
        st.error("No games found for today.")
        st.stop()
    
    game_options = [g["display"] for g in today_games]
    selected_display = st.selectbox("Select a game", options=game_options)
    
    selected_game = next((g for g in today_games if g["display"] == selected_display), None)
    
    # Build batter list
    batter_list = []
    if selected_game:
        with st.spinner("Loading active batters..."):
            away_batters = get_team_active_roster(selected_game["awayId"])
            home_batters = get_team_active_roster(selected_game["homeId"])
            
            for b in away_batters:
                label = f"{b['fullName']} ({b['position']} - {selected_game['awayAbbrev']})"
                batter_list.append({"label": label, "id": b["id"], "name": b["fullName"]})
            
            for b in home_batters:
                label = f"{b['fullName']} ({b['position']} - {selected_game['homeAbbrev']})"
                batter_list.append({"label": label, "id": b["id"], "name": b["fullName"]})
        
        batter_list = sorted(batter_list, key=lambda x: x["name"])
    
    # Player, Stat, Threshold on same row - compact
    if batter_list:
        player_options = [b["label"] for b in batter_list]
        
        col1, col2, col3 = st.columns([3, 2, 2])
        
        with col1:
            selected_label = st.selectbox(
                "Player", 
                options=["— Choose player —"] + player_options,
                label_visibility="collapsed"
            )
        
        selected_batter = next((b for b in batter_list if b["label"] == selected_label), None)
        player_id = selected_batter["id"] if selected_batter else None
        
        with col2:
            stat_options = ["Hits", "Runs", "RBI", "H+R+RBI", "Strikeouts"]
            selected_stat = st.selectbox(
                "Stat", 
                options=stat_options, 
                index=0,
                label_visibility="collapsed"
            )
        
        with col3:
            # Dynamic thresholds based on selected stat
            if selected_stat == "Strikeouts":
                threshold_options = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
                default_threshold = 2.5
            else:
                threshold_options = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
                default_threshold = 1.5
            
            threshold = st.selectbox(
                "Threshold",
                options=threshold_options,
                index=threshold_options.index(default_threshold) if default_threshold in threshold_options else 0,
                format_func=lambda x: f"{x:.1f}",
                label_visibility="collapsed"
            )
    else:
        player_id = None
        selected_stat = None
        threshold = None


# ====================== MAIN AREA ======================
if player_id:
    player_info = get_player_info(player_id)

    if player_info and player_info.get("primaryPosition", {}).get("code") != "P":
        game_splits = get_game_log(player_id)

        if not game_splits:
            st.info("No hitting games found this season for this player.")
        else:
            records = []
            for split in game_splits:
                stat = split.get("stat", {})
                opponent = split.get("opponent", {}).get("name") or split.get("team", {}).get("name", "N/A")

                hits = int(stat.get("hits", 0))
                runs = int(stat.get("runs", 0))
                rbi = int(stat.get("rbi", 0))
                strikeouts = int(stat.get("strikeOuts", 0))
                combined = hits + runs + rbi

                record = {
                    "Date": split.get("date", "N/A"),
                    "Opponent": opponent,
                    "Home/Away": "Home" if split.get("isHome") else "Away",
                    "AB": stat.get("atBats", 0),
                    "R": runs,
                    "H": hits,
                    "HR": stat.get("homeRuns", 0),
                    "RBI": rbi,
                    "K": strikeouts,
                    "H+R+RBI": combined,
                    "AVG": stat.get("avg", ".000"),
                    "OBP": stat.get("obp", ".000"),
                    "SLG": stat.get("slg", ".000"),
                }
                records.append(record)

            df = pd.DataFrame(records)
            df = df.sort_values("Date", ascending=False)

            # ====================== PROP HIT RATE (OVER + UNDER) ======================
            if selected_stat and threshold is not None:
                n_games = min(10, len(df))
                pdata = df.head(n_games).copy()

                stat_col_map = {
                    "Hits": "H",
                    "Runs": "R",
                    "RBI": "RBI",
                    "H+R+RBI": "H+R+RBI",
                    "Strikeouts": "K"
                }
                stat_col = stat_col_map[selected_stat]

                over_count = (pdata[stat_col] > threshold).sum()
                under_count = (pdata[stat_col] <= threshold).sum()
                over_pct = (over_count / n_games) * 100 if n_games > 0 else 0
                under_pct = (under_count / n_games) * 100 if n_games > 0 else 0

                # Colors
                over_color = '#00ff88' if over_pct > 73 else '#ffcc00' if over_pct >= 60 else '#ff5555'
                under_color = '#00ff88' if under_pct > 73 else '#ffcc00' if under_pct >= 60 else '#ff5555'

                st.subheader(f"🎯 {selected_stat} > {threshold:.1f} — Last {n_games} Games")

                # Hit Rate Display
                col_o, col_u = st.columns(2)
                
                with col_o:
                    st.markdown(
                        f"<div style='text-align:center;'>"
                        f"<div style='font-size:2.8em; font-weight:bold; color:{over_color};'>"
                        f"{over_pct:.0f}%</div>"
                        f"<div style='color:#aaa; font-size:0.9em;'>OVER</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                
                with col_u:
                    st.markdown(
                        f"<div style='text-align:center;'>"
                        f"<div style='font-size:2.8em; font-weight:bold; color:{under_color};'>"
                        f"{under_pct:.0f}%</div>"
                        f"<div style='color:#aaa; font-size:0.9em;'>UNDER</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

                # Streak
                results = (pdata[stat_col] > threshold).tolist()
                if results:
                    streak_type = "O" if results[0] else "U"
                    streak_count = 0
                    for r in results:
                        if (r and streak_type == "O") or (not r and streak_type == "U"):
                            streak_count += 1
                        else:
                            break
                    st.markdown(f"**Current streak:** {streak_type}{streak_count}")

                # Bar chart with threshold
                fig_prop = px.bar(
                    pdata,
                    x="Date",
                    y=stat_col,
                    title=f"{selected_stat} — Last {n_games} Games",
                    text_auto=True
                )
                fig_prop.update_traces(textposition='inside')
                fig_prop.add_hline(
                    y=threshold,
                    line_dash="dash",
                    line_color="#00ffff",
                    annotation_text=f"Threshold = {threshold:.1f}",
                    annotation_position="top right"
                )
                fig_prop.update_layout(
                    height=380,
                    margin=dict(t=60, b=30),
                    yaxis_title=None,
                    xaxis_title=None
                )
                fig_prop.update_xaxes(type='category')
                st.plotly_chart(fig_prop, use_container_width=True)

            # ====================== GAME LOG TABLE ======================
            st.subheader(f"Recent Games — Hitting Stats ({len(df)} games this season)")

            totals_row = pd.DataFrame([{
                "Date": "TOTAL",
                "Opponent": "",
                "Home/Away": "",
                "AB": int(df["AB"].sum()),
                "R": df["R"].sum(),
                "H": df["H"].sum(),
                "HR": int(df["HR"].sum()),
                "RBI": df["RBI"].sum(),
                "K": int(df["K"].sum()),
                "H+R+RBI": df["H+R+RBI"].sum(),
                "AVG": "",
                "OBP": "",
                "SLG": "",
            }])

            df_display = pd.concat([df.head(20), totals_row], ignore_index=True)

            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "H+R+RBI": st.column_config.NumberColumn("H + R + RBI", format="%d"),
                    "K": st.column_config.NumberColumn("Strikeouts", format="%d")
                }
            )

            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download full game log as CSV",
                data=csv,
                file_name=f"{player_info.get('fullName', 'batter').replace(' ', '_')}_hitting_{datetime.datetime.now().year}.csv",
                mime="text/csv"
            )
    else:
        st.error("This player is a pitcher or invalid. Please select a batter.")
else:
    st.info("👈 Select a game and player from the sidebar to get started.")

st.divider()
st.caption("Active batters only • Current season • Official MLB Stats API • Strikeouts added")
