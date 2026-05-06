import streamlit as st
import requests
import pandas as pd
import datetime
import plotly.express as px
import json
import os

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
st.title("⚾ MLB Active Player Recent Game Stats")

# ====================== TABS ======================
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
            
            # ====================== H+R+RBI HOT LIST ======================
            st.markdown("### 🔥 H+R+RBI Hot List — All Games Today")
            hrr_list = daily_data.get("hrr_qualifiers", [])
            
            if hrr_list:
                df_hrr = pd.DataFrame(hrr_list)
                if "over_1.5_HRR" in df_hrr.columns:
                    df_hrr = df_hrr.sort_values("over_1.5_HRR", ascending=False).reset_index(drop=True)
                
                display_cols = ["player", "over_1.5_HRR"]
                extra_cols = [col for col in ["last_10_avg", "games", "recent_form"] if col in df_hrr.columns]
                display_cols.extend(extra_cols)
                
                st.dataframe(
                    df_hrr[display_cols],
                    use_container_width=True,
                    hide_index=True
                )
                
                st.success(f"✅ **{len(df_hrr)} players** across all today's games meet the H+R+RBI hot list criteria")
            else:
                st.info("No H+R+RBI qualifiers found.")
            
            st.divider()
            
            # ====================== RECOMMENDED 3-LEG PARLAYS (2 per row) ======================
            st.subheader("🎯 Recommended 3-Leg Parlays")
            suggestions = daily_data.get("parlay_suggestions", [])
            
            if suggestions:
                for i in range(0, len(suggestions), 2):
                    cols = st.columns(2)
                    
                    # First suggestion
                    with cols[0]:
                        sug = suggestions[i]
                        st.markdown(f"#### ⚾ {sug.get('game', 'Unknown Game')}")
                        for j, leg in enumerate(sug.get("legs", []), 1):
                            st.write(f"**Leg {j}:** {leg.get('player', 'N/A')} {leg.get('prop', '')} "
                                    f"({leg.get('hit_rate', 0)}% hit rate)")
                        st.caption("Odds would appear here if available")
                    
                    # Second suggestion (if exists)
                    if i + 1 < len(suggestions):
                        with cols[1]:
                            sug = suggestions[i + 1]
                            st.markdown(f"#### ⚾ {sug.get('game', 'Unknown Game')}")
                            for j, leg in enumerate(sug.get("legs", []), 1):
                                st.write(f"**Leg {j}:** {leg.get('player', 'N/A')} {leg.get('prop', '')} "
                                        f"({leg.get('hit_rate', 0)}% hit rate)")
                            st.caption("Odds would appear here if available")
            else:
                st.info("No parlay suggestions available in the data file yet.")
                
        except Exception as e:
            st.error(f"Error loading daily data: {e}")
    else:
        st.warning("`daily_k_props.json` not found. Please run your compute script first.")

# ====================== TAB 2: PLAYER STATS ======================
with tab_player:
    # Sidebar and Player Stats code remains unchanged (same as previous version)
    with st.sidebar:
        st.header("🎮 Game & Player Selection")

        today_games = get_todays_games()
        if not today_games:
            st.error("No games today")
            st.stop()

        game_options = [g["display"] for g in today_games]
        selected_display = st.selectbox("Select a game", options=game_options, key="game_select")
        selected_game = next((g for g in today_games if g["display"] == selected_display), None)

        st.subheader("⚾ Starting Pitchers")
        selected_away_pitcher_id = selected_away_pitcher_name = None
        selected_home_pitcher_id = selected_home_pitcher_name = None

        if selected_game:
            col_p1, col_p2 = st.columns(2)
            away_roster = get_team_active_roster(selected_game["awayId"])
            home_roster = get_team_active_roster(selected_game["homeId"])

            away_pitchers = sorted([p for p in away_roster if p.get("posCode") == "1"], key=lambda x: x["fullName"])
            home_pitchers = sorted([p for p in home_roster if p.get("posCode") == "1"], key=lambda x: x["fullName"])

            game_pk = selected_game["gamePk"]

            with col_p1:
                away_options = [f"{p['fullName']} ({p.get('position', '?')})" for p in away_pitchers] or ["No pitchers found"]
                selected_away_label = st.selectbox(f"Away — {selected_game['awayAbbrev']}", options=away_options, key=f"away_starter_{game_pk}")
                away_map = {f"{p['fullName']} ({p.get('position', '?')})": (p["id"], p["fullName"]) for p in away_pitchers}
                if selected_away_label in away_map:
                    selected_away_pitcher_id, selected_away_pitcher_name = away_map[selected_away_label]

            with col_p2:
                home_options = [f"{p['fullName']} ({p.get('position', '?')})" for p in home_pitchers] or ["No pitchers found"]
                selected_home_label = st.selectbox(f"Home — {selected_game['homeAbbrev']}", options=home_options, key=f"home_starter_{game_pk}")
                home_map = {f"{p['fullName']} ({p.get('position', '?')})": (p["id"], p["fullName"]) for p in home_pitchers}
                if selected_home_label in home_map:
                    selected_home_pitcher_id, selected_home_pitcher_name = home_map[selected_home_label]

        st.divider()
        st.subheader("🎯 Player Analysis")

        all_players = []
        if selected_game:
            away_roster = get_team_active_roster(selected_game["awayId"])
            home_roster = get_team_active_roster(selected_game["homeId"])
            for p in away_roster:
                label = f"{p['fullName']} ({p['position']} - {selected_game['awayAbbrev']})"
                all_players.append({"label": label, "id": p["id"], "name": p["fullName"], "posCode": p["posCode"], "teamAbbrev": selected_game["awayAbbrev"]})
            for p in home_roster:
                label = f"{p['fullName']} ({p['position']} - {selected_game['homeAbbrev']})"
                all_players.append({"label": label, "id": p["id"], "name": p["fullName"], "posCode": p["posCode"], "teamAbbrev": selected_game["homeAbbrev"]})
            all_players = sorted(all_players, key=lambda x: x["name"])

        selected_label = st.selectbox("Select Player", options=["— Choose player —"] + [p["label"] for p in all_players])
        selected_player = next((p for p in all_players if p["label"] == selected_label), None)

        selected_stat = None
        threshold = 1.5

        if selected_player:
            is_pitcher = selected_player["posCode"] == "1"
            
            col_stat, col_thresh = st.columns(2)
            with col_stat:
                if is_pitcher:
                    stat_options = ["Strikeouts", "Earned Runs", "Outs", "Hits Allowed", "Walks Issued"]
                else:
                    stat_options = ["Hits", "Runs", "RBI", "H+R+RBI", "Strikeouts"]
                selected_stat = st.selectbox("Stat", options=stat_options, key="stat_select")

            with col_thresh:
                if is_pitcher and selected_stat == "Outs":
                    thresh_options = [12.5,13.5,14.5,15.5,16.5,17.5,18.5]
                elif is_pitcher and selected_stat == "Strikeouts":
                    thresh_options = [1.5,2.5,3.5,4.5,5.5,6.5,7.5,8.5]
                else:
                    thresh_options = [0.5,1.5,2.5,3.5,4.5,5.5]
                threshold = st.selectbox("Threshold", options=thresh_options, format_func=lambda x: f"{x:.1f}", key="threshold_select")

    # Main Player Stats Content (unchanged)
    if selected_game:
        st.subheader("🔥 Today's Prop Hot Lists (≥80% Hit Rate - Last 10 Games)")
        daily_file = "daily_k_props.json"
        if os.path.exists(daily_file):
            try:
                with open(daily_file, "r", encoding="utf-8") as f:
                    daily_data = json.load(f)
                if daily_data.get("date") == datetime.date.today().strftime("%Y-%m-%d"):
                    away_abbrev = selected_game["awayAbbrev"]
                    home_abbrev = selected_game["homeAbbrev"]
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        with st.expander("Hits Hot List", expanded=True):
                            hits_list = daily_data.get("hits_qualifiers", [])
                            df_h = pd.DataFrame(hits_list)
                            if not df_h.empty:
                                df_h = df_h[df_h["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                                if not df_h.empty:
                                    df_display = df_h[["player", "over_0.5_H", "over_1.5_H"]].copy()
                                    df_display["avg_rate"] = ((df_display["over_0.5_H"] + df_display["over_1.5_H"]) / 2).round(1)
                                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                    with col2:
                        with st.expander("Strikeouts Hot List", expanded=True):
                            k_list = daily_data.get("strikeouts_qualifiers", [])
                            df_k = pd.DataFrame(k_list)
                            if not df_k.empty:
                                df_k = df_k[df_k["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                                if not df_k.empty:
                                    df_display = df_k[["player", "over_0.5_K", "over_1.5_K"]].copy()
                                    df_display["avg_rate"] = ((df_display["over_0.5_K"] + df_display["over_1.5_K"]) / 2).round(1)
                                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                    with col3:
                        with st.expander("H + R + RBI Hot List", expanded=True):
                            hrr_list = daily_data.get("hrr_qualifiers", [])
                            df_hrr = pd.DataFrame(hrr_list)
                            if not df_hrr.empty:
                                df_hrr = df_hrr[df_hrr["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                                if not df_hrr.empty:
                                    st.dataframe(df_hrr[["player", "over_1.5_HRR"]], use_container_width=True, hide_index=True)
                    st.caption(f"✅ Filtered for **{away_abbrev} @ {home_abbrev}**")
            except Exception as e:
                st.error(f"Could not load hot lists: {e}")

        st.divider()

    if selected_player and selected_stat is not None and selected_game:
        # ... (Player analysis code remains the same as in previous version)
        player_id = selected_player["id"]
        is_pitcher = selected_player["posCode"] == "1"
        group = "pitching" if is_pitcher else "hitting"
        game_splits = get_game_log(player_id, group)

        if game_splits:
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
            
            pitch_map = {"Strikeouts": "K", "Earned Runs": "ER", "Outs": "Outs", "Hits Allowed": "H_Allowed", "Walks Issued": "BB"}
            hit_map = {"Hits": "H", "Runs": "R", "RBI": "RBI", "H+R+RBI": "H+R+RBI", "Strikeouts": "K"}
            stat_col = pitch_map.get(selected_stat) if is_pitcher else hit_map.get(selected_stat)

            n_games = min(10, len(df))
            pdata = df.head(n_games).copy()
            over_pct = (pdata[stat_col] > threshold).sum() / n_games * 100 if n_games > 0 else 0

            st.subheader(f"🎯 {selected_stat} > {threshold:.1f} — Last {n_games} Games")
            
            col_left, col_right = st.columns([3, 2])

            with col_left:
                c1, c2 = st.columns(2)
                c1.metric("OVER Rate", f"{over_pct:.0f}%")
                c2.metric("UNDER Rate", f"{100-over_pct:.0f}%")

                fig = px.bar(pdata, x="Date", y=stat_col, title=f"{selected_stat} History", text_auto=True, height=400)
                fig.add_hline(y=threshold, line_dash="dash", line_color="cyan")
                st.plotly_chart(fig, use_container_width=True)

            with col_right:
                if not is_pitcher and selected_away_pitcher_id and selected_home_pitcher_id:
                    opp_id = selected_home_pitcher_id if selected_player["teamAbbrev"] == selected_game["awayAbbrev"] else selected_away_pitcher_id
                    opp_name = selected_home_pitcher_name if selected_player["teamAbbrev"] == selected_game["awayAbbrev"] else selected_away_pitcher_name
                    last_year = datetime.datetime.now().year - 1
                    bvp = get_batter_vs_pitcher(selected_player["id"], opp_id, last_year)
                    st.subheader(f"📊 vs {opp_name} ({last_year})")
                    if bvp and bvp.get("atBats", 0) > 0:
                        c1, c2 = st.columns(2)
                        with c1:
                            st.metric("AB", bvp["atBats"])
                            st.metric("H", bvp["hits"])
                            st.metric("AVG", bvp["avg"])
                        with c2:
                            st.metric("HR", bvp["homeRuns"])
                            st.metric("RBI", bvp["rbi"])
                            st.metric("K", bvp["strikeOuts"])
                        st.metric("OPS", bvp["ops"])
                    else:
                        st.info("No BVP data available.")
                else:
                    st.info("Select opposing starter ↑ to see BVP")

            st.dataframe(df.head(20), use_container_width=True, hide_index=True)
        else:
            st.info("No game logs found for this player this season.")
    elif selected_game:
        st.info("👈 Select a **player**, **stat**, and **threshold** from the sidebar.")
