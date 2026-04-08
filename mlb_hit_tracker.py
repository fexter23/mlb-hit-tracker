import streamlit as st
import requests
import pandas as pd
import datetime
import plotly.express as px

# ===============================================================
# PAGE CONFIG (must be first Streamlit call)
# ===============================================================
st.set_page_config(
    page_title="MLB Batter Analytics",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)

CURRENT_SEASON = datetime.datetime.now().year
API_BASE = "https://statsapi.mlb.com/api/v1"

# ===============================================================
# GENERIC API HELPER
# ===============================================================
def mlb_api_get(url: str):
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()

# ===============================================================
# SCHEDULE & GAME DATA
# ===============================================================
@st.cache_data(ttl=1800)
def get_todays_games():
    today = datetime.date.today().strftime("%Y-%m-%d")
    url = f"{API_BASE}/schedule?sportId=1&date={today}&hydrate=team"
    data = mlb_api_get(url)

    games = []
    for d in data.get("dates", []):
        for g in d.get("games", []):
            games.append({
                "gamePk": g["gamePk"],
                "homeId": g["teams"]["home"]["team"]["id"],
                "awayId": g["teams"]["away"]["team"]["id"],
                "display": f"{g['teams']['away']['team']['abbreviation']} @ "
                           f"{g['teams']['home']['team']['abbreviation']} "
                           f"({g['status']['detailedState']})"
            })
    return games

# ===============================================================
# ROSTERS
# ===============================================================
@st.cache_data(ttl=1800)
def get_team_active_batters(team_id: int):
    url = f"{API_BASE}/teams/{team_id}/roster?rosterType=active"
    data = mlb_api_get(url)

    batters = []
    for r in data.get("roster", []):
        if r["position"]["code"] != "P":
            batters.append({
                "id": r["person"]["id"],
                "name": r["person"]["fullName"]
            })
    return batters

# ===============================================================
# PLAYER DETAILS
# ===============================================================
@st.cache_data(ttl=3600)
def get_player_info(player_id: int):
    url = f"{API_BASE}/people/{player_id}"
    data = mlb_api_get(url)
    return data["people"][0]

# ===============================================================
# GAME LOG + SPLITS (ITEM 2)
# ===============================================================
@st.cache_data(ttl=3600)
def get_batter_game_log(player_id: int):
    url = (
        f"{API_BASE}/people/{player_id}/stats"
        f"?stats=gameLog&group=hitting&season={CURRENT_SEASON}"
    )
    data = mlb_api_get(url)
    splits = data.get("stats", [])[0].get("splits", [])

    return pd.DataFrame([
        {
            "date": s["date"],
            "hits": int(s["stat"]["hits"]),
            "homeAway": s["homeAway"],
            "dayNight": s["dayNight"]
        }
        for s in splits
    ])

def hit_rate(df: pd.DataFrame, n=10):
    return (df.head(n)["hits"] > 0).mean() if not df.empty else None

# ===============================================================
# PITCHER CONTEXT (ITEM 1)
# ===============================================================
@st.cache_data(ttl=1800)
def get_probable_pitchers(game_pk: int):
    url = f"{API_BASE}/game/{game_pk}/feed/live"
    data = mlb_api_get(url)
    return data["gameData"].get("probablePitchers", {})

@st.cache_data(ttl=3600)
def get_pitcher_season_stats(pitcher_id: int):
    url = (
        f"{API_BASE}/people/{pitcher_id}/stats"
        f"?stats=season&group=pitching&season={CURRENT_SEASON}"
    )
    data = mlb_api_get(url)
    splits = data.get("stats", [])[0].get("splits", [])
    return splits[0]["stat"] if splits else {}

# ===============================================================
# LINEUP CONTEXT (ITEM 3)
# ===============================================================
@st.cache_data(ttl=900)
def get_lineups(game_pk: int):
    url = f"{API_BASE}/game/{game_pk}/feed/live"
    data = mlb_api_get(url)

    lineups = {}
    for side in ["home", "away"]:
        lineup = []
        ids = data["liveData"]["boxscore"]["teams"][side].get("batters", [])
        players = data["gameData"]["players"]

        for i, pid in enumerate(ids):
            p = players.get(f"ID{pid}")
            lineup.append({
                "id": pid,
                "name": p["fullName"],
                "spot": i + 1
            })
        lineups[side] = lineup

    return lineups

def lineup_context(lineup, batter_id):
    for i, p in enumerate(lineup):
        if p["id"] == batter_id:
            return {
                "spot": p["spot"],
                "ahead": lineup[i - 1]["name"] if i > 0 else None,
                "behind": lineup[i + 1]["name"] if i < len(lineup) - 1 else None
            }
    return None

# ===============================================================
# STREAMLIT UI
# ===============================================================
st.title("⚾ MLB Batter Analytics (Stats‑Only)")

games = get_todays_games()
if not games:
    st.warning("No games found today.")
    st.stop()

game = st.selectbox(
    "Select a game",
    games,
    format_func=lambda g: g["display"]
)

batters = (
    get_team_active_batters(game["homeId"]) +
    get_team_active_batters(game["awayId"])
)

batter = st.selectbox(
    "Select a batter",
    batters,
    format_func=lambda b: b["name"]
)

# ===============================================================
# DATA LOAD
# ===============================================================
player = get_player_info(batter["id"])
game_log = get_batter_game_log(batter["id"])
probables = get_probable_pitchers(game["gamePk"])
lineups = get_lineups(game["gamePk"])

# ===============================================================
# DISPLAY: PITCHER CONTEXT
# ===============================================================
st.subheader("🧤 Pitcher Context")

opponent_side = "home" if batter in get_team_active_batters(game["awayId"]) else "away"
pitcher = probables.get(opponent_side)

if pitcher:
    p_stats = get_pitcher_season_stats(pitcher["id"])
    st.write(
        f"**Probable Pitcher:** {pitcher['fullName']} "
        f"(Throws {pitcher['handedness']['throws']})"
    )
    st.write(f"ERA: {p_stats.get('era', '—')} • "
             f"AVG Against: {p_stats.get('avg', '—')}")
else:
    st.info("Probable pitcher not yet announced.")

# ===============================================================
# DISPLAY: BATTER SPLITS
# ===============================================================
st.subheader("📊 Recent Performance & Splits")

if not game_log.empty:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Last 10 Games", f"{hit_rate(game_log,10):.0%}")
    c2.metric("Home Games", f"{hit_rate(game_log[game_log.homeAway=='H'],10):.0%}")
    c3.metric("Away Games", f"{hit_rate(game_log[game_log.homeAway=='A'],10):.0%}")
    c4.metric("Night Games", f"{hit_rate(game_log[game_log.dayNight=='N'],10):.0%}")

    fig = px.line(
        game_log.head(15),
        x="date",
        y="hits",
        title="Hits per Game (Recent)"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No recent game data available.")

# ===============================================================
# DISPLAY: LINEUP CONTEXT
# ===============================================================
st.subheader("📋 Lineup Context")

home_ctx = lineup_context(lineups["home"], batter["id"])
away_ctx = lineup_context(lineups["away"], batter["id"])
ctx = home_ctx or away_ctx

if ctx:
    st.write(f"Batting **{ctx['spot']}**")
    if ctx["ahead"]:
        st.write(f"Ahead: {ctx['ahead']}")
    if ctx["behind"]:
        st.write(f"Behind: {ctx['behind']}")
else:
    st.info("Lineup not yet confirmed.")
