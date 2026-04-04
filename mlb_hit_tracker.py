import streamlit as st
import requests
import pandas as pd
import datetime
import plotly.express as px
import json
import os

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

# ====================== DAILY PROP HOT LISTS (SIDE-BY-SIDE) ======================
st.subheader("🔥 Today's Prop Hot Lists (≥80% Hit Rate - Last 10 Games)")

daily_file = "daily_k_props.json"
selected_game = None

# Sidebar - Game Selection
with st.sidebar:
    st.header("🎮 Game & Player Selection")
    
    today_games = get_todays_games()
    if not today_games:
        st.error("No games found for today.")
        st.stop()
    
    game_options = [g["display"] for g in today_games]
    selected_display = st.selectbox("Select a game", options=game_options, key="game_select")
    
    selected_game = next((g for g in today_games if g["display"] == selected_display), None)

# Load and filter daily hot list by selected game
if os.path.exists(daily_file) and selected_game:
    try:
        with open(daily_file, "r", encoding="utf-8") as f:
            daily_data = json.load(f)
        
        if daily_data.get("date") == datetime.date.today().strftime("%Y-%m-%d"):
            daily_df = pd.DataFrame(daily_data.get("batters", []))

            if not daily_df.empty and selected_game:
                # Filter to only players from the selected game's two teams
                away_abbrev = selected_game["awayAbbrev"]
                home_abbrev = selected_game["homeAbbrev"]
                daily_df = daily_df[daily_df["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)].copy()

                if not daily_df.empty:
                    col_hits, col_k, col_hrr = st.columns(3)

                    # ====================== HITS ======================
                    with col_hits:
                        with st.expander("Hits Hot List", expanded=False):
                            hits_df = daily_df[["player", "over_0.5_H", "over_1.5_H"]].copy()
                            hits_df = hits_df.assign(
                                avg_hit_rate = ((hits_df["over_0.5_H"] + hits_df["over_1.5_H"]) / 2).round(1)
                            )
                            st.dataframe(
                                hits_df,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "player": st.column_config.TextColumn("Player"),
                                    "over_0.5_H": st.column_config.NumberColumn("% >0.5 H", format="%.1f%%"),
                                    "over_1.5_H": st.column_config.NumberColumn("% >1.5 H", format="%.1f%%"),
                                    "avg_hit_rate": st.column_config.NumberColumn("Avg Rate", format="%.1f%%"),
                                }
                            )

                    # ====================== STRIKEOUTS ======================
                    with col_k:
                        with st.expander("Strikeouts Hot List", expanded=False):
                            k_df = daily_df[["player", "over_0.5_K", "over_1.5_K"]].copy()
                            k_df = k_df.assign(
                                avg_hit_rate = ((k_df["over_0.5_K"] + k_df["over_1.5_K"]) / 2).round(1)
                            )
                            st.dataframe(
                                k_df,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "player": st.column_config.TextColumn("Player"),
                                    "over_0.5_K": st.column_config.NumberColumn("% >0.5 K", format="%.1f%%"),
                                    "over_1.5_K": st.column_config.NumberColumn("% >1.5 K", format="%.1f%%"),
                                    "avg_hit_rate": st.column_config.NumberColumn("Avg Rate", format="%.1f%%"),
                                }
                            )

                    # ====================== H+R+RBI ======================
                    with col_hrr:
                        with st.expander("H + R + RBI Hot List", expanded=False):
                            hrr_df = daily_df[["player", "over_1.5_HRR"]].copy()
                            st.dataframe(
                                hrr_df,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "player": st.column_config.TextColumn("Player"),
                                    "over_1.5_HRR": st.column_config.NumberColumn("% >1.5 HRR", format="%.1f%%"),
                                }
                            )

                    st.caption(f"✅ Showing **{selected_game['awayAbbrev']} @ {selected_game['homeAbbrev']}** only • Updated today")
                else:
                    st.info(f"No qualifying players (≥80%) from **{selected_game['awayAbbrev']} @ {selected_game['homeAbbrev']}** today.")
            else:
                st.info("No qualifying batters today.")
        else:
            st.warning("⚠️ Daily props are outdated. Please run `python compute_daily_k_props.py`")
    except Exception as e:
        st.error(f"Could not load daily props: {e}")
else:
    st.info("👉 Select a game from the sidebar to see matchup-specific hot lists.")

st.divider()

# ====================== SIDEBAR - PLAYER SELECTION ======================
with st.sidebar:
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
            selected_stat = st.selectbox("Stat", options=stat_options, index=0, label_visibility="collapsed")
        
        with col3:
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


# ====================== MAIN PLAYER ANALYSIS ======================
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

            # Prop Hit Rate
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

                over_color = '#00ff88' if over_pct > 73 else '#ffcc00' if over_pct >= 60 else '#ff5555'
                under_color = '#00ff88' if under_pct > 73 else '#ffcc00' if under_pct >= 60 else '#ff5555'

                st.subheader(f"🎯 {selected_stat} > {threshold:.1f} — Last {n_games} Games")

                col_o, col_u = st.columns(2)
                with col_o:
                    st.markdown(f"<div style='text-align:center;'><div style='font-size:2.8em; font-weight:bold; color:{over_color};'>{over_pct:.0f}%</div><div style='color:#aaa; font-size:0.9em;'>OVER</div></div>", unsafe_allow_html=True)
                with col_u:
                    st.markdown(f"<div style='text-align:center;'><div style='font-size:2.8em; font-weight:bold; color:{under_color};'>{under_pct:.0f}%</div><div style='color:#aaa; font-size:0.9em;'>UNDER</div></div>", unsafe_allow_html=True)

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

                fig_prop = px.bar(pdata, x="Date", y=stat_col, title=f"{selected_stat} — Last {n_games} Games", text_auto=True)
                fig_prop.update_traces(textposition='inside')
                fig_prop.add_hline(y=threshold, line_dash="dash", line_color="#00ffff",
                                   annotation_text=f"Threshold = {threshold:.1f}", annotation_position="top right")
                fig_prop.update_layout(height=380, margin=dict(t=60, b=30), yaxis_title=None, xaxis_title=None)
                fig_prop.update_xaxes(type='category')
                st.plotly_chart(fig_prop, use_container_width=True)

            # Game Log Table
            st.subheader(f"Recent Games — Hitting Stats ({len(df)} games this season)")

            totals_row = pd.DataFrame([{
                "Date": "TOTAL", "Opponent": "", "Home/Away": "",
                "AB": int(df["AB"].sum()), "R": df["R"].sum(), "H": df["H"].sum(),
                "HR": int(df["HR"].sum()), "RBI": df["RBI"].sum(),
                "K": int(df["K"].sum()), "H+R+RBI": df["H+R+RBI"].sum(),
                "AVG": "", "OBP": "", "SLG": "",
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
    st.info("👈 Select a game and player from the sidebar for detailed analysis.")

st.divider()
st.caption("Active batters only • Current season • Official MLB Stats API • Hot lists filtered by selected game")
