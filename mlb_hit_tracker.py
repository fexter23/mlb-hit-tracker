import streamlit as st
import requests
import pandas as pd
import datetime
import plotly.express as px
import json
import os
from PIL import Image 

# ====================== FAVICON & PAGE CONFIG ======================
st.set_page_config(
    page_title="MLB Player Stats",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
        players = []
        for entry in roster:
            person = entry.get("person", {})
            players.append({
                "id": person.get("id"),
                "fullName": person.get("fullName"),
                "position": entry.get("position", {}).get("abbreviation", "?"),
                "posCode": entry.get("position", {}).get("code", "?")
            })
        return players
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
def get_game_log(player_id: int, group: str):
    current_year = datetime.datetime.now().year
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group={group}&season={current_year}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        stats = resp.json().get("stats", [])
        return stats[0].get("splits", []) if stats else []
    except Exception:
        return []

def calculate_outs(ip_str):
    """Converts IP string (e.g. '5.2') to total outs (17)"""
    try:
        if "." in ip_str:
            innings, partial = ip_str.split(".")
            return (int(innings) * 3) + int(partial)
        return int(ip_str) * 3
    except:
        return 0

# ====================== STREAMLIT APP ======================
st.title("⚾ MLB Active Player Recent Game Stats")

tab_player, tab_parlays = st.tabs(["📊 Player Stats", "🎯 Today's Parlay Suggestions"])

# ====================== TAB 1: PLAYER STATS ======================
with tab_player:
    st.subheader("🔥 Today's Prop Hot Lists (≥80% Hit Rate - Last 10 Games)")

    today_games = get_todays_games()
    if not today_games:
        st.error("No games found for today.")
        st.stop()

    game_options = [g["display"] for g in today_games]
    selected_display = st.selectbox("Select a game", options=game_options, key="game_select")
    selected_game = next((g for g in today_games if g["display"] == selected_display), None)

    # Hot Lists (Batter Focused - Untouched)
    daily_file = "daily_k_props.json"
    if os.path.exists(daily_file) and selected_game:
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)
            if daily_data.get("date") == datetime.date.today().strftime("%Y-%m-%d"):
                away_abbrev = selected_game["awayAbbrev"]
                home_abbrev = selected_game["homeAbbrev"]
                col1, col2, col3 = st.columns(3)
                with col1:
                    with st.expander("Hits Hot List", expanded=False):
                        hits_list = daily_data.get("hits_qualifiers", [])
                        df_h = pd.DataFrame(hits_list)
                        if not df_h.empty:
                            df_h = df_h[df_h["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                            if not df_h.empty:
                                df_display = df_h[["player", "over_0.5_H", "over_1.5_H"]].copy()
                                df_display["avg_rate"] = ((df_display["over_0.5_H"] + df_display["over_1.5_H"]) / 2).round(1)
                                st.dataframe(df_display, use_container_width=True, hide_index=True)
                with col2:
                    with st.expander("Strikeouts Hot List", expanded=False):
                        k_list = daily_data.get("strikeouts_qualifiers", [])
                        df_k = pd.DataFrame(k_list)
                        if not df_k.empty:
                            df_k = df_k[df_k["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                            if not df_k.empty:
                                df_display = df_k[["player", "over_0.5_K", "over_1.5_K"]].copy()
                                df_display["avg_rate"] = ((df_display["over_0.5_K"] + df_display["over_1.5_K"]) / 2).round(1)
                                st.dataframe(df_display, use_container_width=True, hide_index=True)
                with col3:
                    with st.expander("H + R + RBI Hot List", expanded=False):
                        hrr_list = daily_data.get("hrr_qualifiers", [])
                        df_hrr = pd.DataFrame(hrr_list)
                        if not df_hrr.empty:
                            df_hrr = df_hrr[df_hrr["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                            if not df_hrr.empty:
                                st.dataframe(df_hrr[["player", "over_1.5_HRR"]], use_container_width=True, hide_index=True)
                st.caption(f"✅ Showing **{away_abbrev} @ {home_abbrev}** only • Updated today")
        except Exception as e:
            st.error(f"Could not load daily props: {e}")

    st.divider()

    # ====================== INDIVIDUAL PLAYER ANALYSIS ======================
    with st.sidebar:
        st.header("🎮 Individual Player Analysis")
        all_players = []
        if selected_game:
            with st.spinner("Loading active roster..."):
                away_roster = get_team_active_roster(selected_game["awayId"])
                home_roster = get_team_active_roster(selected_game["homeId"])
                for p in away_roster:
                    label = f"{p['fullName']} ({p['position']} - {selected_game['awayAbbrev']})"
                    all_players.append({"label": label, "id": p["id"], "name": p["fullName"], "posCode": p["posCode"]})
                for p in home_roster:
                    label = f"{p['fullName']} ({p['position']} - {selected_game['homeAbbrev']})"
                    all_players.append({"label": label, "id": p["id"], "name": p["fullName"], "posCode": p["posCode"]})
            all_players = sorted(all_players, key=lambda x: x["name"])

        selected_label = st.selectbox("Player", options=["— Choose player —"] + [p["label"] for p in all_players], label_visibility="collapsed")
        selected_player = next((p for p in all_players if p["label"] == selected_label), None)

        if selected_player:
            player_id = selected_player["id"]
            is_pitcher = selected_player["posCode"] == "1"
            
            col_stat, col_thresh = st.columns(2)
            with col_stat:
                if is_pitcher:
                    stat_options = ["Strikeouts", "Earned Runs", "Outs", "Hits Allowed", "Walks Issued"]
                    default_thresh = 4.5
                else:
                    stat_options = ["Hits", "Runs", "RBI", "H+R+RBI", "Strikeouts"]
                    default_thresh = 1.5
                selected_stat = st.selectbox("Stat", options=stat_options, label_visibility="collapsed")
            
            with col_thresh:
                if is_pitcher and selected_stat == "Outs":
                    threshold_options = [12.5, 13.5, 14.5, 15.5, 16.5, 17.5, 18.5]
                    default_thresh = 15.5
                elif is_pitcher and selected_stat == "Strikeouts":
                    threshold_options = [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5]
                    default_thresh = 2.5
                else:
                    threshold_options = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
                
                threshold = st.selectbox("Threshold", options=threshold_options, 
                                         index=threshold_options.index(default_thresh) if default_thresh in threshold_options else 0,
                                         format_func=lambda x: f"{x:.1f}", label_visibility="collapsed")
        else:
            player_id = None

    # ====================== MAIN ANALYSIS LOGIC ======================
    if player_id:
        group = "pitching" if is_pitcher else "hitting"
        game_splits = get_game_log(player_id, group)

        if not game_splits:
            st.info(f"No {group} games found this season.")
        else:
            records = []
            for split in game_splits:
                stat = split.get("stat", {})
                opp = split.get("opponent", {}).get("name") or "N/A"
                rec = {"Date": split.get("date", "N/A"), "Opponent": opp}
                
                if is_pitcher:
                    rec.update({
                        "K": int(stat.get("strikeOuts", 0)),
                        "ER": int(stat.get("earnedRuns", 0)),
                        "Outs": calculate_outs(stat.get("inningsPitched", "0.0")),
                        "H_Allowed": int(stat.get("hits", 0)),
                        "BB": int(stat.get("baseOnBalls", 0)),
                        "IP": stat.get("inningsPitched", "0.0")
                    })
                else:
                    rec.update({
                        "H": int(stat.get("hits", 0)), "R": int(stat.get("runs", 0)),
                        "RBI": int(stat.get("rbi", 0)), "K": int(stat.get("strikeOuts", 0)),
                        "H+R+RBI": int(stat.get("hits", 0)) + int(stat.get("runs", 0)) + int(stat.get("rbi", 0))
                    })
                records.append(rec)

            df = pd.DataFrame(records).sort_values("Date", ascending=False)
            
            # Stat Mapping for Charting
            pitch_map = {"Strikeouts": "K", "Earned Runs": "ER", "Outs": "Outs", "Hits Allowed": "H_Allowed", "Walks Issued": "BB"}
            hit_map = {"Hits": "H", "Runs": "R", "RBI": "RBI", "H+R+RBI": "H+R+RBI", "Strikeouts": "K"}
            stat_col = pitch_map[selected_stat] if is_pitcher else hit_map[selected_stat]

            # Calculation & UI
            n_games = min(10, len(df))
            pdata = df.head(n_games).copy()
            over_pct = (pdata[stat_col] > threshold).sum() / n_games * 100
            
            st.subheader(f"🎯 {selected_stat} > {threshold:.1f} — Last {n_games} Games")
            c1, c2 = st.columns(2)
            c1.metric("OVER Rate", f"{over_pct:.0f}%")
            c2.metric("UNDER Rate", f"{100-over_pct:.0f}%")

            fig = px.bar(pdata, x="Date", y=stat_col, title=f"{selected_stat} History", text_auto=True)
            fig.add_hline(y=threshold, line_dash="dash", line_color="cyan")
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(df.head(20), use_container_width=True, hide_index=True)

    else:
        st.info("👈 Select a game and player from the sidebar to get started.")

# ====================== TAB 2: PARLAY SUGGESTIONS ======================
with tab_parlays:
    # (Kept exactly as original)
    st.subheader("🎯 Today's 3-Leg Parlay Suggestions")
    if os.path.exists(daily_file):
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)
            suggestions = daily_data.get("parlay_suggestions", [])
            for sug in suggestions:
                st.markdown(f"#### ⚾ {sug.get('game', 'Unknown')}")
                for i, leg in enumerate(sug.get("legs", []), 1):
                    st.write(f"Leg {i}: {leg['player']} {leg['prop']} ({leg['hit_rate']}%)")
                st.divider()
        except: st.info("Run compute script to see suggestions.")
