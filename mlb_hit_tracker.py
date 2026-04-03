import streamlit as st
import requests
import pandas as pd
import datetime
import plotly.express as px

# ====================== CACHED API FUNCTIONS ======================
@st.cache_data(ttl=1800)
def get_todays_games():
    """Fetches the MLB schedule for the current day."""
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
                    "display": f"{away.get('abbreviation', '???')} @ {home.get('abbreviation', '???')}"
                })
        return games
    except Exception:
        return []

@st.cache_data(ttl=3600)
def get_team_roster(team_id: int):
    """Fetches active non-pitchers for a given team."""
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/roster?rosterType=active"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        roster = resp.json().get("roster", [])
        return [{
            "id": r["person"]["id"], 
            "name": r["person"]["fullName"],
            "pos": r["position"]["abbreviation"]
        } for r in roster if r["position"]["code"] != "P"]
    except Exception:
        return []

@st.cache_data(ttl=3600)
def get_game_log(player_id: int):
    """Fetches the current season hitting game log for a player."""
    year = datetime.datetime.now().year
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&group=hitting&season={year}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        stats = resp.json().get("stats", [])
        return stats[0].get("splits", []) if stats else []
    except Exception:
        return []

# ====================== DATA PROCESSING ======================
@st.cache_data(ttl=3600)
def compute_daily_club():
    """Computes hit rates for all players in today's games to find 80%+ qualifiers."""
    games = get_todays_games()
    if not games:
        return pd.DataFrame()

    results = []
    # Use a progress bar for this potentially long-running task
    for game in games:
        # Combine rosters
        away_roster = get_team_roster(game["awayId"])
        home_roster = get_team_roster(game["homeId"])
        
        all_batters = []
        for b in away_roster: all_batters.append((b, game["awayAbbrev"]))
        for b in home_roster: all_batters.append((b, game["homeAbbrev"]))

        for batter, abbrev in all_batters:
            logs = get_game_log(batter["id"])
            if len(logs) < 5: continue
            
            # Extract last 10 games
            pdata = logs[:10]
            n = len(pdata)
            
            records = []
            for split in pdata:
                s = split.get("stat", {})
                h = int(s.get("hits", 0))
                r = int(s.get("runs", 0))
                rbi = int(s.get("rbi", 0))
                k = int(s.get("strikeOuts", 0))
                records.append({"H": h, "K": k, "HRR": h + r + rbi})
            
            df = pd.DataFrame(records)
            
            stats_dict = {
                "player": f"{batter['name']} ({abbrev})",
                "over_0.5_H": round((df["H"] > 0.5).sum() / n * 100, 1),
                "over_1.5_H": round((df["H"] > 1.5).sum() / n * 100, 1),
                "over_0.5_K": round((df["K"] > 0.5).sum() / n * 100, 1),
                "over_1.5_K": round((df["K"] > 1.5).sum() / n * 100, 1),
                "over_1.5_HRR": round((df["HRR"] > 1.5).sum() / n * 100, 1),
                "games": n,
                "player_id": batter["id"]
            }

            # Only add if at least one category hits the 80% threshold
            if any(v >= 80 for k, v in stats_dict.items() if k.startswith("over_")):
                results.append(stats_dict)

    return pd.DataFrame(results)

# ====================== STREAMLIT UI ======================
st.set_page_config(page_title="MLB Prop Lab", page_icon="⚾", layout="wide")

tab1, tab2 = st.tabs(["🔥 Daily 80%+ Club", "🔍 Player Deep-Dive"])

# --- TAB 1: AUTOMATED HOT LIST ---
with tab1:
    st.title("⚾ Today's High-Probability Prop Qualifiers")
    st.markdown("Players with **≥ 80% hit rate** on at least one threshold (Last 10 Games).")
    
    with st.spinner("Analyzing all active rosters..."):
        df_club = compute_daily_club()

    if df_club.empty:
        st.info("No players met the 80% threshold for today's games.")
    else:
        # SECTION: HITS
        st.header("Hits (H)")
        df_h = df_club[(df_club["over_0.5_H"] >= 80) | (df_club["over_1.5_H"] >= 80)].copy()
        if not df_h.empty:
            df_h = df_h.sort_values("over_1.5_H", ascending=False)
            fig_h = px.bar(df_h, x="player", y=["over_0.5_H", "over_1.5_H"], 
                           barmode="group", title="Top Hit Qualifiers",
                           color_discrete_sequence=['#1f77b4', '#aec7e8'])
            st.plotly_chart(fig_h, use_container_width=True)
            st.dataframe(df_h[["player", "over_0.5_H", "over_1.5_H", "games"]], hide_index=True, use_container_width=True)
        else:
            st.write("No Hit qualifiers today.")

        st.divider()

        # SECTION: STRIKEOUTS
        st.header("Strikeouts (K)")
        df_k = df_club[(df_club["over_0.5_K"] >= 80) | (df_club["over_1.5_K"] >= 80)].copy()
        if not df_k.empty:
            df_k = df_k.sort_values("over_1.5_K", ascending=False)
            fig_k = px.bar(df_k, x="player", y=["over_0.5_K", "over_1.5_K"], 
                           barmode="group", title="Batter Strikeout Trends (K)",
                           color_discrete_sequence=['#d62728', '#ff9896'])
            st.plotly_chart(fig_k, use_container_width=True)
            st.dataframe(df_k[["player", "over_0.5_K", "over_1.5_K", "games"]], hide_index=True, use_container_width=True)
        else:
            st.write("No Strikeout qualifiers today.")

        st.divider()

        # SECTION: HRR
        st.header("Hits + Runs + RBI (HRR)")
        df_hrr = df_club[df_club["over_1.5_HRR"] >= 80].copy()
        if not df_hrr.empty:
            df_hrr = df_hrr.sort_values("over_1.5_HRR", ascending=False)
            fig_hrr = px.bar(df_hrr, x="player", y="over_1.5_HRR", 
                             title="Top HRR Qualifiers (Over 1.5)",
                             color_discrete_sequence=['#2ca02c'])
            st.plotly_chart(fig_hrr, use_container_width=True)
            st.dataframe(df_hrr[["player", "over_1.5_HRR", "games"]], hide_index=True, use_container_width=True)
        else:
            st.write("No HRR qualifiers today.")

# --- TAB 2: MANUAL PLAYER SEARCH ---
with tab2:
    st.header("Search Player Game Logs")
    
    # Sidebar for search controls
    today_games = get_todays_games()
    if today_games:
        game_display = [g["display"] for g in today_games]
        selected_display = st.selectbox("Select a game", options=["— Select Game —"] + game_display)
        
        selected_game = next((g for g in today_games if g["display"] == selected_display), None)
        
        if selected_game:
            col1, col2, col3 = st.columns([3, 2, 2])
            
            with col1:
                away_b = get_team_roster(selected_game["awayId"])
                home_b = get_team_roster(selected_game["homeId"])
                
                # Combine and format for selectbox
                batter_options = []
                for b in away_b: batter_options.append({"label": f"{b['name']} ({b['pos']} - {selected_game['awayAbbrev']})", "id": b["id"]})
                for b in home_b: batter_options.append({"label": f"{b['name']} ({b['pos']} - {selected_game['homeAbbrev']})", "id": b["id"]})
                batter_options = sorted(batter_options, key=lambda x: x["label"])
                
                chosen_batter_label = st.selectbox("Player", options=[o["label"] for o in batter_options])
                chosen_id = next(o["id"] for o in batter_options if o["label"] == chosen_batter_label)

            with col2:
                stat_map = {"Hits": "H", "Runs": "R", "RBI": "RBI", "H+R+RBI": "HRR", "Strikeouts": "K"}
                selected_stat_name = st.selectbox("Stat", options=list(stat_map.keys()))
                stat_key = stat_map[selected_stat_name]

            with col3:
                threshold = st.number_input("Threshold", value=1.5, step=0.5, format="%.1f")

            # FETCH AND DISPLAY PLAYER DATA
            logs = get_game_log(chosen_id)
            if logs:
                records = []
                for split in logs:
                    s = split.get("stat", {})
                    h, r, rbi, k = int(s.get("hits", 0)), int(s.get("runs", 0)), int(s.get("rbi", 0)), int(s.get("strikeOuts", 0))
                    records.append({
                        "Date": split.get("date"),
                        "Opponent": split.get("opponent", {}).get("name"),
                        "H": h, "R": r, "RBI": rbi, "K": k, "HRR": h + r + rbi,
                        "AB": s.get("atBats", 0),
                        "AVG": s.get("avg")
                    })
                
                df_player = pd.DataFrame(records).sort_values("Date", ascending=False)
                pdata = df_player.head(10).copy()
                
                # Plotly Chart for individual
                fig_p = px.bar(pdata, x="Date", y=stat_key, text_auto=True, 
                               title=f"{selected_stat_name} Trend (Last {len(pdata)} Games)")
                fig_p.add_hline(y=threshold, line_dash="dash", line_color="cyan", annotation_text=f"Line: {threshold}")
                st.plotly_chart(fig_p, use_container_width=True)

                # Game Log Table
                st.subheader("Season Game Log")
                st.dataframe(df_player, use_container_width=True, hide_index=True)
                
                csv = df_player.to_csv(index=False)
                st.download_button("📥 Download CSV", data=csv, file_name=f"mlb_stats_{chosen_id}.csv")
            else:
                st.warning("No game logs found for this player in the current season.")
    else:
        st.error("No games scheduled for today.")

st.divider()
st.caption("Data provided via MLB Stats API. Analysis based on Last 10 Games played.")
