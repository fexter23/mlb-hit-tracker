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

tab_player, tab_parlays = st.tabs(["📊 Player Stats", "🎯 Today's Parlay Suggestions"])

# ====================== TAB 1: PLAYER STATS ======================
with tab_player:
    st.subheader("🔥 Today's Prop Hot Lists (≥80% Hit Rate - Last 10 Games)")

    today_games = get_todays_games()
    if not today_games:
        st.error("No games found for today.")
        st.stop()

    # Game selector
    game_options = [g["display"] for g in today_games]
    selected_display = st.selectbox("Select a game", options=game_options, key="game_select")
    selected_game = next((g for g in today_games if g["display"] == selected_display), None)

    if selected_game:
        away_abbrev = selected_game["awayAbbrev"]
        home_abbrev = selected_game["homeAbbrev"]

        # === LIVE HOT LISTS ===
        with st.spinner("Computing live hot lists for this game..."):
            away_batters = get_team_active_roster(selected_game["awayId"])
            home_batters = get_team_active_roster(selected_game["homeId"])

            batter_list = []
            for b in away_batters:
                batter_list.append((b["id"], b["fullName"], away_abbrev))
            for b in home_batters:
                batter_list.append((b["id"], b["fullName"], home_abbrev))

            hits_qualifiers = []
            strikeouts_qualifiers = []
            hrr_qualifiers = []

            for player_id, full_name, team_abbrev in batter_list:
                game_splits = get_game_log(player_id)
                if len(game_splits) < 5:
                    continue

                records = []
                for split in game_splits:
                    stat = split.get("stat", {})
                    hits = int(stat.get("hits", 0))
                    runs = int(stat.get("runs", 0))
                    rbi = int(stat.get("rbi", 0))
                    strikeouts = int(stat.get("strikeOuts", 0))
                    combined = hits + runs + rbi

                    records.append({"H": hits, "K": strikeouts, "HRR": combined})

                if not records:
                    continue

                df_player = pd.DataFrame(records)
                pdata = df_player.head(10).copy()
                n_games = len(pdata)

                if n_games < 5:
                    continue

                over_05_h = (pdata["H"] > 0.5).sum() / n_games * 100
                over_15_h = (pdata["H"] > 1.5).sum() / n_games * 100
                over_05_k = (pdata["K"] > 0.5).sum() / n_games * 100
                over_15_k = (pdata["K"] > 1.5).sum() / n_games * 100
                over_15_hrr = (pdata["HRR"] > 1.5).sum() / n_games * 100

                batter_stats = {
                    "player": f"{full_name} ({team_abbrev})",
                    "over_0.5_H": round(over_05_h, 1),
                    "over_1.5_H": round(over_15_h, 1),
                    "over_0.5_K": round(over_05_k, 1),
                    "over_1.5_K": round(over_15_k, 1),
                    "over_1.5_HRR": round(over_15_hrr, 1),
                    "games_considered": n_games
                }

                if over_05_h >= 80 or over_15_h >= 80:
                    hits_qualifiers.append(batter_stats)
                if over_05_k >= 80 or over_15_k >= 80:
                    strikeouts_qualifiers.append(batter_stats)
                if over_15_hrr >= 80:
                    hrr_qualifiers.append(batter_stats)

        # Display the live hot lists
        col1, col2, col3 = st.columns(3)

        with col1:
            with st.expander("Hits Hot List", expanded=True):
                df = pd.DataFrame(hits_qualifiers)
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
            with st.expander("Strikeouts Hot List", expanded=True):
                df = pd.DataFrame(strikeouts_qualifiers)
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
            with st.expander("H + R + RBI Hot List", expanded=True):
                df = pd.DataFrame(hrr_qualifiers)
                if not df.empty:
                    df = df[df["player"].str.contains(f"\\({away_abbrev}\\)|\\({home_abbrev}\\)", regex=True)]
                    if not df.empty:
                        st.dataframe(df[["player", "over_1.5_HRR"]], use_container_width=True, hide_index=True,
                            column_config={
                                "player": st.column_config.TextColumn("Player"),
                                "over_1.5_HRR": st.column_config.NumberColumn("% >1.5 HRR", format="%.1f%%"),
                            })

        st.caption(f"✅ Live calculation for **{away_abbrev} @ {home_abbrev}** • Last 10 games per player")
    else:
        st.info("Select a game above to see live hot lists.")

    st.divider()

    # ====================== INDIVIDUAL PLAYER ANALYSIS ======================
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

                # Prop Hit Rate + Bar Chart
                if selected_stat and threshold is not None:
                    n_games = min(10, len(df))
                    pdata = df.head(n_games).copy()

                    stat_col_map = {
                        "Hits": "H", "Runs": "R", "RBI": "RBI",
                        "H+R+RBI": "H+R+RBI", "Strikeouts": "K"
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
                        st.markdown(
                            f"<div style='text-align:center;'>"
                            f"<div style='font-size:2.8em; font-weight:bold; color:{over_color};'>{over_pct:.0f}%</div>"
                            f"<div style='color:#aaa; font-size:0.9em;'>OVER</div></div>",
                            unsafe_allow_html=True
                        )
                    with col_u:
                        st.markdown(
                            f"<div style='text-align:center;'>"
                            f"<div style='font-size:2.8em; font-weight:bold; color:{under_color};'>{under_pct:.0f}%</div>"
                            f"<div style='color:#aaa; font-size:0.9em;'>UNDER</div></div>",
                            unsafe_allow_html=True
                        )

                    # Streak
                    results_list = (pdata[stat_col] > threshold).tolist()
                    if results_list:
                        streak_type = "O" if results_list[0] else "U"
                        streak_count = 0
                        for r in results_list:
                            if (r and streak_type == "O") or (not r and streak_type == "U"):
                                streak_count += 1
                            else:
                                break
                        st.markdown(f"**Current streak:** {streak_type}{streak_count}")

                    # Bar Chart
                    fig_prop = px.bar(
                        pdata, x="Date", y=stat_col,
                        title=f"{selected_stat} — Last {n_games} Games",
                        text_auto=True
                    )
                    fig_prop.update_traces(textposition='inside')
                    fig_prop.add_hline(
                        y=threshold, line_dash="dash", line_color="#00ffff",
                        annotation_text=f"Threshold = {threshold:.1f}",
                        annotation_position="top right"
                    )
                    fig_prop.update_layout(height=380, margin=dict(t=60, b=30),
                                           yaxis_title=None, xaxis_title=None)
                    fig_prop.update_xaxes(type='category')
                    st.plotly_chart(fig_prop, use_container_width=True)

                # Game Log
                st.subheader(f"Recent Games — Hitting Stats ({len(df)} games this season)")

                totals_row = pd.DataFrame([{
                    "Date": "TOTAL", "Opponent": "", "Home/Away": "",
                    "AB": int(df["AB"].sum()), "R": df["R"].sum(), "H": df["H"].sum(),
                    "HR": int(df["HR"].sum()), "RBI": df["RBI"].sum(),
                    "K": int(df["K"].sum()), "H+R+RBI": df["H+R+RBI"].sum(),
                    "AVG": "", "OBP": "", "SLG": "",
                }])

                df_display = pd.concat([df.head(20), totals_row], ignore_index=True)

                st.dataframe(df_display, use_container_width=True, hide_index=True,
                             column_config={
                                 "H+R+RBI": st.column_config.NumberColumn("H + R + RBI", format="%d"),
                                 "K": st.column_config.NumberColumn("Strikeouts", format="%d")
                             })

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
    st.caption("Active batters only • Current season • Official MLB Stats API")

# ====================== TAB 2: PARLAY SUGGESTIONS ======================
with tab_parlays:
    st.subheader("🎯 Today's 3-Leg Parlay Suggestions")

    daily_file = "daily_k_props.json"

    if os.path.exists(daily_file):
        try:
            with open(daily_file, "r", encoding="utf-8") as f:
                daily_data = json.load(f)

            parlay_suggestions = daily_data.get("parlay_suggestions", [])

            if parlay_suggestions:
                for suggestion in parlay_suggestions:
                    st.markdown(f"#### ⚾ {suggestion.get('game', 'Unknown Game')}")

                    if not suggestion.get("legs"):
                        st.warning(suggestion.get("note", "No legs available."))
                    else:
                        avg_rate = suggestion.get("avg_leg_hit_rate", 0)
                        badge_color = "#00ff88" if avg_rate >= 80 else "#ffcc00" if avg_rate >= 65 else "#ff5555"
                        st.markdown(
                            f"<span style='background:{badge_color}; color:#111; font-weight:700; "
                            f"padding:4px 12px; border-radius:12px;'>Avg hit rate: {avg_rate}%</span>",
                            unsafe_allow_html=True
                        )

                        for i, leg in enumerate(suggestion.get("legs", []), 1):
                            rate = leg.get("hit_rate", 0)
                            rate_color = "#00ff88" if rate >= 80 else "#ffcc00" if rate >= 65 else "#ff5555"
                            st.markdown(
                                f"**Leg {i}** — {leg['player']} — {leg['prop']} "
                                f"<span style='color:{rate_color}; font-weight:700;'>{rate}%</span> "
                                f"({leg.get('games_considered', '?')} games)",
                                unsafe_allow_html=True
                            )
                    st.divider()
            else:
                st.info("No parlay suggestions available yet. Run `python compute_daily_k_props.py`")
        except Exception as e:
            st.error(f"Could not load parlay suggestions: {e}")
    else:
        st.info("Run `python compute_daily_k_props.py` to generate parlay suggestions.")

st.divider()
st.caption("Active batters only • Current season • Official MLB Stats API")
