import streamlit as st
import requests
import pandas as pd
import datetime
import plotly.express as px
import json
import os
import re

# ====================== DATA CONSTANTS ======================
PARK_FACTORS = {
    "COL": 135, "BOS": 110, "CIN": 107, "KCR": 104, "TEX": 102,
    "LAA": 101, "PHI": 101, "ATL": 100, "LAD": 100, "TOR": 100,
    "WSH": 100, "MIN": 100, "BAL": 99,  "CHW": 99,  "HOU": 98,
    "MIL": 98,  "NYY": 98,  "ARI": 97,  "CLE": 97,  "PIT": 97,
    "DET": 96,  "MIA": 96,  "SDP": 96,  "SFG": 96,  "STL": 96,
    "CHC": 95,  "NYM": 95,  "OAK": 94,  "TBR": 93,  "SEA": 92
}

# ====================== PAGE CONFIG ======================
st.set_page_config(
    page_title="MLB Player Stats Pro",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ====================== CACHED API FUNCTIONS ======================
@st.cache_data(ttl=1800)
def get_todays_games():
    today = datetime.date.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=team,probablePitcher"
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        games = []

        @st.cache_data(ttl=3600)
        def get_pitcher_era(pitcher_id: int) -> str:
            if not pitcher_id:
                return "?.??"
            try:
                year = datetime.datetime.now().year
                stats_url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=season&group=pitching&season={year}"
                s_resp = requests.get(stats_url, timeout=8)
                s_resp.raise_for_status()
                stats_data = s_resp.json()
                
                for stat_group in stats_data.get("stats", []):
                    if stat_group.get("group", {}).get("displayName") == "pitching":
                        for split in stat_group.get("splits", []):
                            era = split.get("stat", {}).get("era")
                            if era is not None:
                                return str(era)
                return "?.??"
            except Exception:
                return "?.??"

        for date in data.get("dates", []):
            for game in date.get("games", []):
                away = game.get("teams", {}).get("away", {}).get("team", {})
                home = game.get("teams", {}).get("home", {}).get("team", {})
                
                away_p_obj = game.get("teams", {}).get("away", {}).get("probablePitcher", {})
                home_p_obj = game.get("teams", {}).get("home", {}).get("probablePitcher", {})

                away_pid = away_p_obj.get("id")
                home_pid = home_p_obj.get("id")

                games.append({
                    "gamePk": game.get("gamePk"),
                    "awayTeam": away.get("name"),
                    "awayAbbrev": away.get("abbreviation"),
                    "awayId": away.get("id"),
                    "awayP": away_p_obj.get("fullName", "TBD"),
                    "awayPID": away_pid,
                    "awayPERA": get_pitcher_era(away_pid),
                    "homeTeam": home.get("name"),
                    "homeAbbrev": home.get("abbreviation"),
                    "homeId": home.get("id"),
                    "homeP": home_p_obj.get("fullName", "TBD"),
                    "homePID": home_pid,
                    "homePERA": get_pitcher_era(home_pid),
                    "display": f"{away.get('abbreviation', '???')} @ {home.get('abbreviation', '???')} ({game.get('status', {}).get('detailedState', 'Scheduled')})"
                })
        return games
    except Exception as e:
        st.error(f"Failed to load today's games: {e}")
        return []


@st.cache_data(ttl=3600)
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


@st.cache_data(ttl=3600)
def get_batter_vs_pitcher(batter_id: int, pitcher_id: int, season: int):
    if not pitcher_id:
        return None
    url = f"https://statsapi.mlb.com/api/v1/people/{batter_id}/stats?stats=vsPlayer&group=hitting&opposingPlayerId={pitcher_id}&season={season}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        stats_list = data.get("stats", [])
        if stats_list:
            splits = stats_list[0].get("splits", [])
            if splits:
                stat = splits[0].get("stat", {})
                return {
                    "atBats": stat.get("atBats", 0),
                    "hits": stat.get("hits", 0),
                    "avg": stat.get("avg", ".000"),
                    "homeRuns": stat.get("homeRuns", 0),
                    "rbi": stat.get("rbi", 0),
                    "strikeOuts": stat.get("strikeOuts", 0),
                    "baseOnBalls": stat.get("baseOnBalls", 0),
                    "ops": stat.get("ops", ".000"),
                }
        return None
    except Exception:
        return None


def calculate_outs(ip_str):
    try:
        if "." in ip_str:
            innings, partial = ip_str.split(".")
            return (int(innings) * 3) + int(partial)
        return int(ip_str) * 3
    except:
        return 0


# ====================== STREAMLIT APP ======================
st.title("⚾ MLB Active Player Stats Pro")

tab_parlays, tab_player = st.tabs(["🎯 Today's Parlay Suggestions", "📊 Player Stats"])

# ====================== TAB 1: PARLAY SUGGESTIONS ======================
with tab_parlays:
    st.subheader("🎯 Today's Parlay Suggestions & H+R+RBI Hot List")
    daily_file = "daily_k_props.json"
    if os.path.exists(daily_file):
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)
            
            date_today = datetime.date.today().strftime("%Y-%m-%d")
            if daily_data.get("date") != date_today:
                st.warning(f"⚠️ Data is from {daily_data.get('date', 'unknown')}. Today's date is {date_today}.")
            
            st.markdown("### 🔥 H+R+RBI Hot List — All Games Today")
            hrr_list = daily_data.get("hrr_qualifiers", [])
            
            if hrr_list:
                df_hrr = pd.DataFrame(hrr_list)
                if "over_1.5_HRR" in df_hrr.columns:
                    df_hrr = df_hrr.sort_values("over_1.5_HRR", ascending=False).reset_index(drop=True)

                today_games = get_todays_games()
                position_map = {}
                for g in today_games:
                    for roster in [get_team_active_roster(g["awayId"]), get_team_active_roster(g["homeId"])]:
                        for p in roster:
                            position_map[p["fullName"].strip().lower()] = p.get("position", "?")

                def add_position_to_player(player_str):
                    name = re.sub(r'\s*\([^)]+\)', '', str(player_str)).strip()
                    pos = position_map.get(name.lower(), "?")
                    team_match = re.search(r'\(([^)]+)\)', str(player_str))
                    team = f"({team_match.group(1)})" if team_match else ""
                    return f"{name} {team}({pos})"

                df_hrr["player"] = df_hrr["player"].apply(add_position_to_player)
                st.dataframe(df_hrr[["player", "over_1.5_HRR"] + [c for c in ["last_10_avg", "recent_form"] if c in df_hrr.columns]], 
                           use_container_width=True, hide_index=True)
                st.success(f"✅ **{len(df_hrr)} players** meet the H+R+RBI criteria")
            
            st.divider()
            st.subheader("🎯 Recommended 3-Leg Parlays")
            suggestions = daily_data.get("parlay_suggestions", [])
            if suggestions:
                for i in range(0, len(suggestions), 2):
                    cols = st.columns(2)
                    for idx, col in enumerate(cols):
                        if i + idx < len(suggestions):
                            sug = suggestions[i + idx]
                            with col:
                                st.markdown(f"#### ⚾ {sug.get('game', 'Unknown Game')}")
                                for j, leg in enumerate(sug.get("legs", []), 1):
                                    st.write(f"**Leg {j}:** {leg.get('player', 'N/A')} {leg.get('prop', '')} ({leg.get('hit_rate', 0)}%)")
                                st.caption("Odds shown in sportsbook")
        except Exception as e:
            st.error(f"Error loading daily data: {e}")
    else:
        st.warning("`daily_k_props.json` not found.")

# ====================== TAB 2: PLAYER STATS ======================
with tab_player:
    with st.sidebar:
        st.header("🎮 Game & Player Selection")
        today_games = get_todays_games()
        if not today_games:
            st.error("No games today")
            st.stop()

        game_options = [g["display"] for g in today_games]
        selected_display = st.selectbox("Select a game", options=game_options, key="game_select")
        selected_game = next((g for g in today_games if g["display"] == selected_display), None)

        if selected_game:
            pf = PARK_FACTORS.get(selected_game["homeAbbrev"], 100)
            pf_color = "#00ff88" if pf > 105 else "#ff5555" if pf < 95 else "#aaa"
            st.markdown(f"🏟️ **Park Factor:** <span style='color:{pf_color}'>{pf}</span> (Runs Index)", unsafe_allow_html=True)
            
            st.subheader("⚾ Starting Pitchers")
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.caption(f"✈️ {selected_game['awayAbbrev']}")
                st.write(f"**{selected_game['awayP']}**")
                st.write(f"ERA: **{selected_game['awayPERA']}**")
            with col_p2:
                st.caption(f"🏠 {selected_game['homeAbbrev']}")
                st.write(f"**{selected_game['homeP']}**")
                st.write(f"ERA: **{selected_game['homePERA']}**")

            st.divider()
            st.subheader("🎯 Player Analysis")
            away_roster = get_team_active_roster(selected_game["awayId"])
            home_roster = get_team_active_roster(selected_game["homeId"])
            
            all_players = []
            for p in away_roster:
                all_players.append({
                    "label": f"{p['fullName']} ({p['position']} - {selected_game['awayAbbrev']})", 
                    "id": p["id"], 
                    "name": p["fullName"], 
                    "posCode": p["posCode"], 
                    "teamAbbrev": selected_game["awayAbbrev"], 
                    "is_away": True
                })
            for p in home_roster:
                all_players.append({
                    "label": f"{p['fullName']} ({p['position']} - {selected_game['homeAbbrev']})", 
                    "id": p["id"], 
                    "name": p["fullName"], 
                    "posCode": p["posCode"], 
                    "teamAbbrev": selected_game["homeAbbrev"], 
                    "is_away": False
                })
            
            all_players = sorted(all_players, key=lambda x: x["name"])
            selected_label = st.selectbox("Select Player", options=["— Choose player —"] + [p["label"] for p in all_players])
            selected_player = next((p for p in all_players if p["label"] == selected_label), None)

            if selected_player:
                is_pitcher = selected_player["posCode"] == "1"
                opp_starter = selected_game["homeP"] if selected_player["is_away"] else selected_game["awayP"]
                opp_era = selected_game["homePERA"] if selected_player["is_away"] else selected_game["awayPERA"]
                opp_pid = selected_game["homePID"] if selected_player["is_away"] else selected_game["awayPID"]
                
                st.info(f"**Facing:** {opp_starter} ({opp_era} ERA)")

                col_stat, col_thresh = st.columns(2)
                with col_stat:
                    stat_options = ["Strikeouts", "Earned Runs", "Outs", "Hits Allowed"] if is_pitcher else ["Hits", "Runs", "RBI", "H+R+RBI", "Strikeouts"]
                    selected_stat = st.selectbox("Stat", options=stat_options, key="stat_select")
                with col_thresh:
                    thresh_opts = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5] if not (is_pitcher and selected_stat == "Outs") else [12.5, 15.5, 17.5, 18.5]
                    threshold = st.selectbox("Threshold", options=thresh_opts, format_func=lambda x: f"{x:.1f}")

    # ====================== MAIN ANALYSIS AREA ======================
    if selected_player and selected_game:
        logs = get_game_log(selected_player["id"], "pitching" if is_pitcher else "hitting")
        
        if logs:
            records = []
            for s in logs:
                stt = s.get("stat", {})
                rec = {"Date": s.get("date"), "Opponent": s.get("opponent", {}).get("name")}
                if is_pitcher:
                    rec.update({
                        "K": int(stt.get("strikeOuts", 0)), 
                        "ER": int(stt.get("earnedRuns", 0)), 
                        "Outs": calculate_outs(stt.get("inningsPitched", "0.0"))
                    })
                else:
                    h, r, rbi = int(stt.get("hits", 0)), int(stt.get("runs", 0)), int(stt.get("rbi", 0))
                    rec.update({
                        "H": h, 
                        "R": r, 
                        "RBI": rbi, 
                        "H+R+RBI": h + r + rbi, 
                        "K": int(stt.get("strikeOuts", 0))
                    })
                records.append(rec)
            
            df = pd.DataFrame(records).sort_values("Date", ascending=False)
            mapping = {
                "Hits": "H", "Runs": "R", "RBI": "RBI", "H+R+RBI": "H+R+RBI",
                "Strikeouts": "K", "Earned Runs": "ER", "Outs": "Outs"
            }
            stat_col = mapping.get(selected_stat)

            if stat_col in df.columns:
                pdata = df.head(10).copy()
                hit_rate = (pdata[stat_col] > threshold).mean() * 100
                
                c1, c2 = st.columns([3, 2])
                with c1:
                    st.subheader(f"🎯 {hit_rate:.0f}% Over {threshold} (Last 10 Games)")
                    fig = px.bar(pdata, x="Date", y=stat_col, text_auto=True, height=400,
                                title=f"{selected_player['name']} - {selected_stat} Trend")
                    fig.add_hline(y=threshold, line_dash="dash", line_color="cyan")
                    st.plotly_chart(fig, use_container_width=True)
                
                with c2:
                    st.write("#### Matchup Quality")
                    st.metric("Park Factor", pf, delta=round(pf-100, 1))
                    st.metric("Opponent Starter ERA", opp_era)
                    
                    # === REAL BVP ===
                    if not is_pitcher and opp_pid:
                        bvp = get_batter_vs_pitcher(selected_player["id"], opp_pid, datetime.datetime.now().year)
                        if bvp and bvp["atBats"] > 0:
                            st.success(f"**BVP vs {opp_starter}**")
                            st.write(f"{bvp['hits']}/{bvp['atBats']}  •  **AVG:** {bvp['avg']}  •  HR: {bvp['homeRuns']}")
                        else:
                            st.info("No significant BVP history this season vs this pitcher.")

            st.dataframe(df.head(15), use_container_width=True, hide_index=True)
        else:
            st.info("No game logs found for this season.")
    elif selected_game:
        st.info("👈 Select a player and stat in the sidebar to view detailed analytics.")
