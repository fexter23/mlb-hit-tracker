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


# ====================== PARLAY LOGIC ======================
PROP_COLUMNS = [
    ("over_1.5_H",   "Over 1.5 Hits"),
    ("over_0.5_H",   "Over 0.5 Hits"),
    ("over_1.5_K",   "Over 1.5 Strikeouts"),
    ("over_0.5_K",   "Over 0.5 Strikeouts"),
    ("over_1.5_HRR", "Over 1.5 H+R+RBI"),
]

def compute_batter_stats(player_id: int, player_name: str, team_abbrev: str):
    """Returns a batter stat dict or None if insufficient data."""
    splits = get_game_log(player_id)
    if len(splits) < 5:
        return None

    records = []
    for split in splits:
        stat = split.get("stat", {})
        hits = int(stat.get("hits", 0))
        runs = int(stat.get("runs", 0))
        rbi  = int(stat.get("rbi", 0))
        ks   = int(stat.get("strikeOuts", 0))
        records.append({"H": hits, "K": ks, "HRR": hits + runs + rbi})

    df = pd.DataFrame(records).head(10)
    n = len(df)
    if n < 5:
        return None

    return {
        "player":        f"{player_name} ({team_abbrev})",
        "player_id":     player_id,
        "games_considered": n,
        "over_0.5_H":   round((df["H"] > 0.5).sum() / n * 100, 1),
        "over_1.5_H":   round((df["H"] > 1.5).sum() / n * 100, 1),
        "over_0.5_K":   round((df["K"] > 0.5).sum() / n * 100, 1),
        "over_1.5_K":   round((df["K"] > 1.5).sum() / n * 100, 1),
        "over_1.5_HRR": round((df["HRR"] > 1.5).sum() / n * 100, 1),
    }

@st.cache_data(ttl=1800)
def build_game_parlay(game_pk: int, away_id: int, home_id: int, away_abbrev: str, home_abbrev: str):
    """Fetches all batter stats for a game and returns the 3-leg parlay suggestion."""
    all_stats = []

    for team_id, abbrev in [(away_id, away_abbrev), (home_id, home_abbrev)]:
        for batter in get_team_active_roster(team_id):
            stats = compute_batter_stats(batter["id"], batter["fullName"], abbrev)
            if stats:
                all_stats.append(stats)

    if not all_stats:
        return None, []

    # Build candidates: every (player x prop) combo
    candidates = []
    for s in all_stats:
        for prop_key, prop_label in PROP_COLUMNS:
            rate = s.get(prop_key, 0)
            if rate > 0:
                candidates.append({
                    "player":    s["player"],
                    "prop_label": prop_label,
                    "hit_rate":  rate,
                    "games_considered": s["games_considered"],
                })

    candidates.sort(key=lambda c: (
        -c["hit_rate"],
        [pk for pk, _ in PROP_COLUMNS].index(
            next(pk for pk, pl in PROP_COLUMNS if pl == c["prop_label"])
        )
    ))

    # Greedy pick 3 unique-player legs
    selected, used = [], set()
    for c in candidates:
        if len(selected) == 3:
            break
        if c["player"] not in used:
            selected.append(c)
            used.add(c["player"])

    # Fallback: allow repeats if not enough unique players
    if len(selected) < 3:
        for c in candidates:
            if len(selected) == 3:
                break
            if c not in selected:
                selected.append(c)

    avg_rate = round(sum(l["hit_rate"] for l in selected) / len(selected), 1) if selected else 0
    return avg_rate, selected


# ====================== STREAMLIT APP ======================
st.set_page_config(page_title="MLB Batter Stats", page_icon="⚾", layout="wide")
st.title("⚾ MLB Active Batter Recent Game Stats")

today_games = get_todays_games()
if not today_games:
    st.error("No games found for today.")
    st.stop()

# ====================== TABS ======================
tab_player, tab_parlays = st.tabs(["📊 Player Stats", "🎯 Today's Parlay Suggestions"])


# ====================== TAB 1: PLAYER STATS ======================
with tab_player:
    with st.sidebar:
        st.header("🎮 Filters")

        game_options = [g["display"] for g in today_games]
        selected_display = st.selectbox("Select a game", options=game_options)
        selected_game = next((g for g in today_games if g["display"] == selected_display), None)

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

        player_id = None
        selected_stat = None
        threshold = None

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
                    rbi  = int(stat.get("rbi", 0))
                    strikeouts = int(stat.get("strikeOuts", 0))
                    combined = hits + runs + rbi

                    records.append({
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
                    })

                df = pd.DataFrame(records)
                df = df.sort_values("Date", ascending=False)

                if selected_stat and threshold is not None:
                    n_games = min(10, len(df))
                    pdata = df.head(n_games).copy()

                    stat_col_map = {
                        "Hits": "H", "Runs": "R", "RBI": "RBI",
                        "H+R+RBI": "H+R+RBI", "Strikeouts": "K"
                    }
                    stat_col = stat_col_map[selected_stat]

                    over_count  = (pdata[stat_col] > threshold).sum()
                    under_count = (pdata[stat_col] <= threshold).sum()
                    over_pct    = (over_count / n_games) * 100 if n_games > 0 else 0
                    under_pct   = (under_count / n_games) * 100 if n_games > 0 else 0

                    over_color  = '#00ff88' if over_pct  > 73 else '#ffcc00' if over_pct  >= 60 else '#ff5555'
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

                    results_list = (pdata[stat_col] > threshold).tolist()
                    if results_list:
                        streak_type  = "O" if results_list[0] else "U"
                        streak_count = 0
                        for r in results_list:
                            if (r and streak_type == "O") or (not r and streak_type == "U"):
                                streak_count += 1
                            else:
                                break
                        st.markdown(f"**Current streak:** {streak_type}{streak_count}")

                    fig_prop = px.bar(pdata, x="Date", y=stat_col,
                                      title=f"{selected_stat} — Last {n_games} Games", text_auto=True)
                    fig_prop.update_traces(textposition='inside')
                    fig_prop.add_hline(y=threshold, line_dash="dash", line_color="#00ffff",
                                       annotation_text=f"Threshold = {threshold:.1f}",
                                       annotation_position="top right")
                    fig_prop.update_layout(height=380, margin=dict(t=60, b=30),
                                           yaxis_title=None, xaxis_title=None)
                    fig_prop.update_xaxes(type='category')
                    st.plotly_chart(fig_prop, use_container_width=True)

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
    st.caption("Active batters only • Current season • Official MLB Stats API • Strikeouts added")


# ====================== TAB 2: PARLAY SUGGESTIONS ======================
with tab_parlays:
    st.subheader("🎯 Today's 3-Leg Parlay Suggestions")
    st.caption("Best 3 props per game ranked by hit rate over last 10 games (min. 5 games). One leg per player preferred.")

    # Game selector inside the tab
    game_options_parlay = [f"{g['awayAbbrev']} @ {g['homeAbbrev']}" for g in today_games]
    selected_parlay_game_label = st.selectbox(
        "Select game",
        options=["— All games —"] + game_options_parlay,
        key="parlay_game_select"
    )

    games_to_show = today_games
    if selected_parlay_game_label != "— All games —":
        games_to_show = [
            g for g in today_games
            if f"{g['awayAbbrev']} @ {g['homeAbbrev']}" == selected_parlay_game_label
        ]

    # Fetch all parlays first so we can sort by avg hit rate
    with st.spinner("Loading parlay data for all games..."):
        parlay_data = []
        for game in games_to_show:
            avg_rate, legs = build_game_parlay(
                game["gamePk"],
                game["awayId"], game["homeId"],
                game["awayAbbrev"], game["homeAbbrev"]
            )
            parlay_data.append((game, avg_rate, legs))

    parlay_data.sort(key=lambda x: x[1] if x[1] is not None else 0, reverse=True)

    for game, avg_rate, legs in parlay_data:
        game_label = f"{game['awayTeam']} @ {game['homeTeam']}"

        with st.expander(f"⚾ {game_label}", expanded=(len(games_to_show) == 1)):
            if not legs:
                st.warning("Not enough data to suggest a parlay for this game.")
                continue

            # Confidence badge colour
            badge_color = "#00ff88" if avg_rate >= 80 else "#ffcc00" if avg_rate >= 65 else "#ff5555"
            st.markdown(
                f"<div style='margin-bottom:12px;'>"
                f"<span style='background:{badge_color}; color:#111; font-weight:700; "
                f"padding:3px 10px; border-radius:12px; font-size:0.85em;'>"
                f"Avg hit rate: {avg_rate}%</span></div>",
                unsafe_allow_html=True
            )

            for i, leg in enumerate(legs, 1):
                rate = leg["hit_rate"]
                rate_color = "#00ff88" if rate >= 80 else "#ffcc00" if rate >= 65 else "#ff5555"
                st.markdown(
                    f"**Leg {i}** &nbsp; {leg['player']} — {leg['prop_label']} &nbsp; "
                    f"<span style='color:{rate_color}; font-weight:700;'>{rate:.0f}%</span> "
                    f"<span style='color:#888; font-size:0.85em;'>({leg['games_considered']} games)</span>",
                    unsafe_allow_html=True
                )

            st.divider()
