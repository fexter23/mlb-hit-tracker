import streamlit as st
import requests
import pandas as pd
import datetime as dt
import plotly.express as px
import json
import os
import numpy as np
from datetime import datetime

# ====================== PAGE CONFIG ======================
st.set_page_config(
    page_title="MLB Batter Stats",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ====================== ODDS & SESSION STATE ======================
odds_options = ["", "-300", "-275", "-250", "-245", "-240", "-235", "-230", "-225", "-220",
                "-215", "-210", "-205", "-200", "-195", "-190", "-185", "-180", "-175", "-170",
                "-165", "-160", "-155", "-150", "-145", "-140", "-135", "-130", "-125",
                "-120", "-115", "-112", "-110", "-105", "-100", "+100", "+102", "+105",
                "+110", "+115", "+118", "+120", "+125", "+130", "+135", "+140", "+145",
                "+150", "+155", "+160", "+165", "+170", "+175", "+180", "+185", "+190",
                "+195", "+200", "+210", "+220", "+230", "+240", "+250", "+275", "+300"]

if 'my_board' not in st.session_state:
    st.session_state.my_board = []

# ====================== CACHED FUNCTIONS ======================
@st.cache_data(ttl=1800)
def get_todays_games():
    today = dt.date.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=team"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        games = []
        for date_ in data.get("dates", []):
            for game in date_.get("games", []):
                away = game.get("teams", {}).get("away", {}).get("team", {})
                home = game.get("teams", {}).get("home", {}).get("team", {})
                games.append({
                    "gamePk": game.get("gamePk"),
                    "awayAbbrev": away.get("abbreviation"),
                    "awayId": away.get("id"),
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
        return [{
            "id": p.get("person", {}).get("id"),
            "fullName": p.get("person", {}).get("fullName"),
            "position": p.get("position", {}).get("abbreviation", "?")
        } for p in roster if p.get("position", {}).get("code") != "P"]
    except Exception:
        return []

@st.cache_data(ttl=3600)
def get_player_game_df(player_id: int):
    current_year = dt.datetime.now().year
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group=hitting&season={current_year}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        stats = resp.json().get("stats", [])
        game_splits = stats[0].get("splits", []) if stats else []
    except Exception:
        return pd.DataFrame()

    records = []
    for split in game_splits:
        stat = split.get("stat", {})
        record = {
            "Date": split.get("date", "N/A"),
            "Opponent": split.get("opponent", {}).get("name") or "N/A",
            "H": int(stat.get("hits", 0)),
            "R": int(stat.get("runs", 0)),
            "RBI": int(stat.get("rbi", 0)),
            "K": int(stat.get("strikeOuts", 0)),
            "H+R+RBI": int(stat.get("hits", 0)) + int(stat.get("runs", 0)) + int(stat.get("rbi", 0)),
        }
        records.append(record)

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("Date", ascending=False)
    return df

# ====================== MAIN APP ======================
st.title("⚾ MLB Active Batter Recent Game Stats")

tab_player, tab_parlays = st.tabs(["📊 Player Stats", "🎯 Today's Parlay Suggestions"])

# ====================== TAB 1 ======================
with tab_player:
    st.subheader("🔥 Today's Prop Hot Lists")

    today_games = get_todays_games()
    if not today_games:
        st.error("No games today.")
        st.stop()

    game_options = [g["display"] for g in today_games]
    selected_display = st.selectbox("Select a game", game_options, key="game_select")
    selected_game = next((g for g in today_games if g["display"] == selected_display), None)

    # Hot lists (kept minimal - you can expand)
    daily_file = "daily_k_props.json"
    if os.path.exists(daily_file) and selected_game:
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)
            if daily_data.get("date") == dt.date.today().strftime("%Y-%m-%d"):
                st.success("Daily props loaded")
            else:
                st.warning("Daily props outdated. Run compute_daily_k_props.py")
        except Exception as e:
            st.error(f"Could not load daily props: {e}")

    st.divider()

    # ====================== SIDEBAR ======================
    with st.sidebar:
        st.header("🎮 Individual Player Analysis")

        batter_list = []
        if selected_game:
            with st.spinner("Loading batters..."):
                away_batters = get_team_active_roster(selected_game["awayId"])
                home_batters = get_team_active_roster(selected_game["homeId"])
                for b in away_batters:
                    batter_list.append({"label": f"{b['fullName']} ({b['position']} - {selected_game['awayAbbrev']})", "id": b["id"]})
                for b in home_batters:
                    batter_list.append({"label": f"{b['fullName']} ({b['position']} - {selected_game['homeAbbrev']})", "id": b["id"]})

            batter_list = sorted(batter_list, key=lambda x: x["label"])

        if batter_list:
            col1, col2, col3, col4 = st.columns([3, 1.8, 1.6, 1.6])
            with col1:
                selected_label = st.selectbox("Player", ["— Choose player —"] + [b["label"] for b in batter_list], label_visibility="collapsed")
            selected_batter = next((b for b in batter_list if b["label"] == selected_label), None)
            player_id = selected_batter["id"] if selected_batter else None

            with col2:
                selected_stat = st.selectbox("Stat", ["Hits", "Runs", "RBI", "H+R+RBI", "Strikeouts"], label_visibility="collapsed")
            with col3:
                opts = [0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5,5.0] if selected_stat == "Strikeouts" else [0.5,1.0,1.5,2.0,2.5,3.0,3.5]
                threshold = st.selectbox("Threshold", opts, format_func=lambda x: f"{x:.1f}", label_visibility="collapsed")
            with col4:
                odds_key = f"odds_{player_id}_{selected_stat}" if player_id else "dummy"
                selected_odds = st.selectbox("Odds", odds_options, key=odds_key, label_visibility="collapsed")

            if selected_batter and st.button("📌 Pin to Board", use_container_width=True, type="primary"):
                df_pin = get_player_game_df(player_id)
                if not df_pin.empty:
                    stat_col_map = {"Hits": "H", "Runs": "R", "RBI": "RBI", "H+R+RBI": "H+R+RBI", "Strikeouts": "K"}
                    stat_col = stat_col_map.get(selected_stat)
                    if stat_col:
                        windows = [w for w in [5,10] if len(df_pin) >= w]
                        over_list = [(df_pin.head(w)[stat_col] > threshold).mean() * 100 for w in windows]
                        parts = [f"<span style='color:#00ff88'>{p:.0f}%</span>(L{w})" for p,w in zip(over_list, windows)]
                        hit_str = " | ".join(parts)

                        results = (df_pin[stat_col] > threshold).tolist()
                        streak_type = "O" if results and results[0] else "U"
                        streak_count = sum(1 for i in range(len(results)) if results[i] == results[0])

                        entry = {
                            "player": selected_label,
                            "matchup": selected_game["display"],
                            "stat": selected_stat,
                            "line": f"{threshold:.1f}",
                            "odds": selected_odds,
                            "hitrate_str": f"{hit_str} | **{streak_type}{streak_count}**",
                            "timestamp": datetime.now()
                        }
                        if not any(e['player'] == entry['player'] and e['stat'] == entry['stat'] and e['line'] == entry['line'] for e in st.session_state.my_board):
                            st.session_state.my_board.append(entry)
                            st.toast("✅ Pinned!", icon="📌")
                            st.rerun()

        # ====================== IMPROVED PINNED DASHBOARD ======================
        st.divider()
        st.subheader("📌 Pinned Props Dashboard")

        if st.session_state.my_board:
            board_df = pd.DataFrame(st.session_state.my_board)
            for match, group in board_df.groupby("matchup"):
                with st.expander(f"⚾ {match} ({len(group)})", expanded=True):
                    for idx, row in group.iterrows():
                        col_t, col_d = st.columns([0.85, 0.15])
                        with col_t:
                            odds_text = f" @ **{row.get('odds', '')}**" if row.get('odds') else ""
                            st.markdown(
                                f"**{row['player']}** | {row['stat']} > {row['line']}{odds_text}  \n"
                                f"<small>{row['hitrate_str']}</small>",
                                unsafe_allow_html=True
                            )
                        with col_d:
                            if st.button("🗑️", key=f"del_{match}_{idx}"):
                                st.session_state.my_board = [
                                    e for e in st.session_state.my_board 
                                    if not (e['player'] == row['player'] and 
                                            e['stat'] == row['stat'] and 
                                            e['line'] == row['line'])
                                ]
                                st.rerun()
        else:
            st.info("Pin some props from the player selector above.")

        # Download Button (single click)
        if st.button("📥 Download Board", use_container_width=True):
            data = [{**e, "timestamp": e["timestamp"].isoformat()} for e in st.session_state.my_board]
            st.download_button(
                label="Click here to save JSON file",
                data=json.dumps(data, indent=2),
                file_name=f"mlb_board_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json"
            )

        uploaded_file = st.file_uploader("📤 Upload Board", type="json")
        if uploaded_file:
            try:
                data = json.load(uploaded_file)
                for item in data:
                    if isinstance(item.get('timestamp'), str):
                        item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                st.session_state.my_board = data
                st.success("✅ Board restored successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Upload failed: {e}")

# ====================== TAB 2: PARLAY SUGGESTIONS ======================
with tab_parlays:
    st.subheader("🎯 Today's 3-Leg Parlay Suggestions")
    daily_file = "daily_k_props.json"
    if os.path.exists(daily_file):
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)
            suggestions = daily_data.get("parlay_suggestions", [])
            if suggestions:
                for sug in suggestions:
                    st.markdown(f"#### ⚾ {sug.get('game', 'Game')}")
                    for i, leg in enumerate(sug.get("legs", []), 1):
                        st.markdown(f"**Leg {i}**: {leg.get('player')} - {leg.get('prop')} ({leg.get('hit_rate', 0)}%)")
                    st.divider()
            else:
                st.info("No parlay suggestions yet.")
        except Exception as e:
            st.error(f"Error loading parlays: {e}")
    else:
        st.info("Run `python compute_daily_k_props.py` to generate suggestions.")

st.caption("MLB Hit Tracker • Individual Delete Buttons Added")
