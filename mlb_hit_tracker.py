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

# ====================== ODDS OPTIONS & SESSION STATE ======================
odds_options = ["", "-300", "-275", "-250", "-245", "-240", "-235", "-230", "-225", "-220",
                "-215", "-210", "-205", "-200", "-195", "-190", "-185", "-180", "-175", "-170",
                "-165", "-160", "-155", "-150", "-145", "-140", "-135", "-130", "-125",
                "-120", "-115", "-112", "-110", "-105", "-100", "+100", "+102", "+105",
                "+110", "+115", "+118", "+120", "+125", "+130", "+135", "+140", "+145",
                "+150", "+155", "+160", "+165", "+170", "+175", "+180", "+185", "+190",
                "+195", "+200", "+210", "+220", "+230", "+240", "+250", "+275", "+300"]

if 'my_board' not in st.session_state:
    st.session_state.my_board = []

# ====================== CACHED API FUNCTIONS ======================
@st.cache_data(ttl=1800)
def get_todays_games():
    today = dt.date.today().strftime("%Y-%m-%d")
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
    if not df.empty:
        df = df.sort_values("Date", ascending=False)
    return df

# ====================== MAIN APP ======================
st.title("⚾ MLB Active Batter Recent Game Stats")

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

    # Hot Lists
    daily_file = "daily_k_props.json"
    if os.path.exists(daily_file) and selected_game:
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)

            if daily_data.get("date") == dt.date.today().strftime("%Y-%m-%d"):
                away_abbrev = selected_game["awayAbbrev"]
                home_abbrev = selected_game["homeAbbrev"]

                col1, col2, col3 = st.columns(3)

                with col1:
                    with st.expander("Hits Hot List", expanded=False):
                        hits_list = daily_data.get("hits_qualifiers", [])
                        df = pd.DataFrame(hits_list)
                        if not df.empty:
                            df = df[df["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                            if not df.empty:
                                df_display = df[["player", "over_0.5_H", "over_1.5_H"]].copy()
                                df_display["avg_rate"] = ((df_display["over_0.5_H"] + df_display["over_1.5_H"]) / 2).round(1)
                                st.dataframe(df_display, use_container_width=True, hide_index=True,
                                    column_config={
                                        "player": st.column_config.TextColumn("Player"),
                                        "over_0.5_H": st.column_config.NumberColumn("% >0.5 H", format="%.1f%%"),
                                        "over_1.5_H": st.column_config.NumberColumn("% >1.5 H", format="%.1f%%"),
                                        "avg_rate": st.column_config.NumberColumn("Avg Rate", format="%.1f%%"),
                                    })

                with col2:
                    with st.expander("Strikeouts Hot List", expanded=False):
                        k_list = daily_data.get("strikeouts_qualifiers", [])
                        df = pd.DataFrame(k_list)
                        if not df.empty:
                            df = df[df["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                            if not df.empty:
                                df_display = df[["player", "over_0.5_K", "over_1.5_K"]].copy()
                                df_display["avg_rate"] = ((df_display["over_0.5_K"] + df_display["over_1.5_K"]) / 2).round(1)
                                st.dataframe(df_display, use_container_width=True, hide_index=True,
                                    column_config={
                                        "player": st.column_config.TextColumn("Player"),
                                        "over_0.5_K": st.column_config.NumberColumn("% >0.5 K", format="%.1f%%"),
                                        "over_1.5_K": st.column_config.NumberColumn("% >1.5 K", format="%.1f%%"),
                                        "avg_rate": st.column_config.NumberColumn("Avg Rate", format="%.1f%%"),
                                    })

                with col3:
                    with st.expander("H + R + RBI Hot List", expanded=False):
                        hrr_list = daily_data.get("hrr_qualifiers", [])
                        df = pd.DataFrame(hrr_list)
                        if not df.empty:
                            df = df[df["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                            if not df.empty:
                                st.dataframe(df[["player", "over_1.5_HRR"]], use_container_width=True, hide_index=True,
                                    column_config={
                                        "player": st.column_config.TextColumn("Player"),
                                        "over_1.5_HRR": st.column_config.NumberColumn("% >1.5 HRR", format="%.1f%%"),
                                    })

                st.caption(f"✅ Showing **{away_abbrev} @ {home_abbrev}** only • Updated today")
            else:
                st.warning("⚠️ Daily props are outdated. Run `python compute_daily_k_props.py`")
        except Exception as e:
            st.error(f"Could not load daily props: {e}")
    else:
        st.info("Run `python compute_daily_k_props.py` to generate hot lists.")

    st.divider()

    # ====================== SIDEBAR: PLAYER ANALYSIS + PIN BOARD ======================
    with st.sidebar:
        st.header("🎮 Individual Player Analysis")

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

            col1, col2, col3, col4 = st.columns([3.2, 1.8, 1.6, 1.6])

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

            with col4:
                odds_key = f"mlb_odds_{player_id}_{selected_stat}" if player_id and selected_stat else "dummy"
                selected_odds = st.selectbox("Odds", options=odds_options, key=odds_key, label_visibility="collapsed")

            # Pin Button
            if selected_batter and selected_stat and threshold is not None:
                if st.button("📌 Pin to Board", use_container_width=True, type="primary"):
                    df_pin = get_player_game_df(player_id)
                    if df_pin.empty:
                        st.warning("No game data available for this player.")
                    else:
                        stat_col_map = {
                            "Hits": "H", "Runs": "R", "RBI": "RBI",
                            "H+R+RBI": "H+R+RBI", "Strikeouts": "K"
                        }
                        stat_col = stat_col_map.get(selected_stat)

                        if stat_col:
                            windows = [w for w in [5, 10] if len(df_pin) >= w]
                            over_list = [(df_pin.head(w)[stat_col] > threshold).mean() * 100 for w in windows]
                            
                            parts = []
                            for pct, w in zip(over_list, windows):
                                color = '#00ff88' if pct > 73 else '#ffcc00' if pct >= 60 else '#ff5555'
                                parts.append(f"<span style='color:{color}'>{pct:.0f}%</span> (L{w})")
                            hit_str = " | ".join(parts)

                            # Current streak
                            results = (df_pin[stat_col] > threshold).tolist()
                            streak_type = "O" if results and results[0] else "U"
                            streak_count = 0
                            for r in results:
                                if (r and streak_type == "O") or (not r and streak_type == "U"):
                                    streak_count += 1
                                else:
                                    break

                            avg_o = np.mean(over_list) if over_list else 0
                            hitrate_str = f"{hit_str} | AVG: <span style='color:#00ff88'>{avg_o:.0f}%</span> | **{streak_type}{streak_count}**"

                            entry = {
                                "player": selected_label,
                                "matchup": selected_game["display"] if selected_game else "N/A",
                                "stat": selected_stat,
                                "line": f"{threshold:.1f}",
                                "odds": selected_odds,
                                "hitrate_str": hitrate_str,
                                "timestamp": datetime.now()
                            }

                            # Avoid duplicates
                            if not any(
                                e['player'] == entry['player'] and 
                                e['stat'] == entry['stat'] and 
                                e['line'] == entry['line']
                                for e in st.session_state.my_board
                            ):
                                st.session_state.my_board.append(entry)
                                st.toast(f"✅ Pinned {selected_stat} > {threshold}", icon="📌")
                                st.rerun()

        # ====================== PINNED PROPS DASHBOARD ======================
        st.divider()
        st.subheader("📌 Pinned Props Dashboard")

        if st.session_state.my_board:
            board_df = pd.DataFrame(st.session_state.my_board)
            for match, group in board_df.groupby("matchup"):
                with st.expander(f"⚾ {match} ({len(group)} props)", expanded=True):
                    for _, row in group.iterrows():
                        odds_text = f" @ **{row['odds']}**" if row.get('odds') else ""
                        st.markdown(
                            f"**{row['player']}** | {row['stat']} > {row['line']}{odds_text}  \n"
                            f"{row['hitrate_str']}",
                            unsafe_allow_html=True
                        )
        else:
            st.info("No props pinned yet. Use the controls above to pin.")

        # Download & Upload
        if st.button("📥 Download Board"):
            data = [{**e, "timestamp": e["timestamp"].isoformat()} for e in st.session_state.my_board]
            st.download_button(
                label="Click to Download JSON",
                data=json.dumps(data),
                file_name=f"mlb_board_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json"
            )

        uploaded_file = st.file_uploader("📤 Upload Board", type="json")
        if uploaded_file:
            try:
                data = json.load(uploaded_file)
                for e in data:
                    if isinstance(e.get('timestamp'), str):
                        e['timestamp'] = datetime.fromisoformat(e['timestamp'])
                st.session_state.my_board = data
                st.success("Board restored!")
                st.rerun()
            except Exception as e:
                st.error(f"Upload error: {e}")

    # ====================== MAIN PLAYER ANALYSIS ======================
    if player_id and selected_game:
        df = get_player_game_df(player_id)
        if not df.empty and selected_stat and threshold is not None:
            st.subheader(f"🎯 {selected_stat} > {threshold:.1f} Analysis")

            n_games = min(10, len(df))
            pdata = df.head(n_games)

            stat_col_map = {"Hits": "H", "Runs": "R", "RBI": "RBI", "H+R+RBI": "H+R+RBI", "Strikeouts": "K"}
            stat_col = stat_col_map.get(selected_stat)

            if stat_col:
                over_pct = (pdata[stat_col] > threshold).mean() * 100
                color = '#00ff88' if over_pct > 73 else '#ffcc00' if over_pct >= 60 else '#ff5555'

                st.markdown(f"<h3 style='color:{color}; text-align:center;'>{over_pct:.0f}% Hit Rate (Last {n_games} Games)</h3>", unsafe_allow_html=True)

                fig = px.bar(pdata, x="Date", y=stat_col, text=stat_col)
                fig.add_hline(y=threshold, line_dash="dash", line_color="#00ffff")
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

            st.subheader("Recent Game Log")
            st.dataframe(df.head(15), use_container_width=True, hide_index=True)
        else:
            st.info("Select a player and stat from the sidebar to see detailed analysis.")
    else:
        st.info("👈 Select a game and player in the sidebar.")

st.divider()
st.caption("MLB Hit Tracker • Pin Board + Odds • Powered by MLB Stats API")
