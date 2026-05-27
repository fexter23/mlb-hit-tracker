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


@st.cache_data(ttl=1800)
def get_todays_games():
    today = datetime.date.today().strftime("%Y-%m-%d")
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={today}&hydrate=team,probablePitcher"
    
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        games = []

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


@st.cache_data(ttl=3600)
def get_batter_vs_pitcher_career(batter_id: int, pitcher_id: int):
    if not pitcher_id:
        return None
    url = f"https://statsapi.mlb.com/api/v1/people/{batter_id}/stats?stats=vsPlayer&group=hitting&opposingPlayerId={pitcher_id}"
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


@st.cache_data(ttl=3600)
def get_batter_platoon_splits(player_id: int):
    year = datetime.datetime.now().year
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=statSplits&group=hitting&season={year}&sitCodes=vl,vr"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
        result = {}
        for s in splits:
            code = s.get("split", {}).get("code", "")
            st_data = s.get("stat", {})
            if code in ("vl", "vr"):
                result[code] = {
                    "avg":       st_data.get("avg", ".000"),
                    "ops":       st_data.get("ops", ".000"),
                    "atBats":    st_data.get("atBats", 0),
                    "hits":      st_data.get("hits", 0),
                    "homeRuns":  st_data.get("homeRuns", 0),
                    "strikeOuts":st_data.get("strikeOuts", 0),
                    "obp":       st_data.get("obp", ".000"),
                    "slg":       st_data.get("slg", ".000"),
                }
        return result
    except Exception:
        return {}


@st.cache_data(ttl=3600)
def get_pitcher_hand(pitcher_id: int) -> str:
    if not pitcher_id:
        return ""
    try:
        url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}"
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        people = resp.json().get("people", [])
        if people:
            return people[0].get("pitchHand", {}).get("code", "")
        return ""
    except Exception:
        return ""


@st.cache_data(ttl=3600)
def get_pitcher_recent_form(pitcher_id: int, num_starts: int = 4):
    if not pitcher_id:
        return []
    year = datetime.datetime.now().year
    url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=gameLog&group=pitching&season={year}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        splits = resp.json().get("stats", [{}])[0].get("splits", [])
        splits_sorted = sorted(splits, key=lambda x: x.get("date", ""), reverse=True)
        records = []
        for s in splits_sorted[:num_starts]:
            st_data = s.get("stat", {})
            ip = st_data.get("inningsPitched", "0.0")
            records.append({
                "Date":     s.get("date", ""),
                "Opp":      s.get("opponent", {}).get("abbreviation", "?"),
                "IP":       ip,
                "H":        int(st_data.get("hits", 0)),
                "ER":       int(st_data.get("earnedRuns", 0)),
                "K":        int(st_data.get("strikeOuts", 0)),
                "BB":       int(st_data.get("baseOnBalls", 0)),
                "ERA":      st_data.get("era", "?.??"),
            })
        return records
    except Exception:
        return []


def calculate_outs(ip_str):
    try:
        if "." in ip_str:
            innings, partial = ip_str.split(".")
            return (int(innings) * 3) + int(partial)
        return int(ip_str) * 3
    except:
        return 0


# ====================== LIVE PROP SCORING ======================

def score_batter_props(player_id: int, player_name: str, team_abbrev: str,
                       opp_era: str, park_factor: int) -> dict | None:
    """Score a batter's H, H+R+RBI props over last 10 games."""
    logs = get_game_log(player_id, "hitting")
    if not logs or len(logs) < 5:
        return None
    records = []
    for s in logs:
        stt = s.get("stat", {})
        h = int(stt.get("hits", 0))
        r = int(stt.get("runs", 0))
        rbi = int(stt.get("rbi", 0))
        records.append({"H": h, "R": r, "RBI": rbi, "HRR": h + r + rbi})
    df = pd.DataFrame(records).head(10)

    h_rate    = (df["H"]   > 0.5).mean() * 100
    h15_rate  = (df["H"]   > 1.5).mean() * 100
    hrr_rate  = (df["HRR"] > 1.5).mean() * 100

    return {
        "player": f"{player_name} ({team_abbrev})",
        "over_0.5_H":   round(h_rate, 1),
        "over_1.5_H":   round(h15_rate, 1),
        "over_1.5_HRR": round(hrr_rate, 1),
        "games":        len(df),
    }


def score_pitcher_k_props(pitcher_id: int, pitcher_name: str, team_abbrev: str) -> dict | None:
    """Score a pitcher's strikeout props over last 5 starts."""
    if not pitcher_id:
        return None
    logs = get_game_log(pitcher_id, "pitching")
    if not logs or len(logs) < 3:
        return None

    records = []
    for s in sorted(logs, key=lambda x: x.get("date", ""), reverse=True)[:5]:
        stt = s.get("stat", {})
        ip_str = stt.get("inningsPitched", "0.0")
        outs = calculate_outs(ip_str)
        ks = int(stt.get("strikeOuts", 0))
        records.append({"K": ks, "outs": outs, "ip_str": ip_str})

    df = pd.DataFrame(records)
    total_outs = df["outs"].sum()
    total_ks   = df["K"].sum()
    k9 = round((total_ks / total_outs * 27) if total_outs > 0 else 0, 2)

    k35_rate = (df["K"] > 3.5).mean() * 100
    k45_rate = (df["K"] > 4.5).mean() * 100
    k55_rate = (df["K"] > 5.5).mean() * 100
    avg_k    = round(df["K"].mean(), 1)

    return {
        "pitcher": f"{pitcher_name} ({team_abbrev})",
        "K/9":          k9,
        "avg_K":        avg_k,
        "over_3.5_K":   round(k35_rate, 1),
        "over_4.5_K":   round(k45_rate, 1),
        "over_5.5_K":   round(k55_rate, 1),
        "starts":       len(df),
    }


def generate_live_props(games: list, progress_bar=None) -> dict:
    """
    Fetch and score all batters + starting pitchers for today's games.
    Returns dict with keys: hits_qualifiers, hrr_qualifiers, k_qualifiers, parlay_suggestions.
    """
    hits_results = []
    hrr_results  = []
    k_results    = []
    total_steps  = len(games) * 2  # away + home roster per game, plus pitchers
    step = 0

    for game in games:
        for side in ("away", "home"):
            team_id    = game["awayId"]    if side == "away" else game["homeId"]
            team_abbrev= game["awayAbbrev"]if side == "away" else game["homeAbbrev"]
            opp_era    = game["homePERA"]  if side == "away" else game["awayPERA"]
            pf         = PARK_FACTORS.get(game["homeAbbrev"], 100)

            roster = get_team_active_roster(team_id)
            for player in roster:
                if player["posCode"] == "1":   # pitchers handled separately
                    continue
                result = score_batter_props(
                    player["id"], player["fullName"], team_abbrev, opp_era, pf
                )
                if result:
                    hits_results.append(result)
                    hrr_results.append(result)

            step += 1
            if progress_bar:
                progress_bar.progress(min(step / total_steps, 0.9))

        # Score both probable starters
        for pid, pname, tabbrev in [
            (game["awayPID"], game["awayP"], game["awayAbbrev"]),
            (game["homePID"], game["homeP"], game["homeAbbrev"]),
        ]:
            if pid:
                result = score_pitcher_k_props(pid, pname, tabbrev)
                if result:
                    k_results.append(result)

    # Sort & filter
    hits_q = sorted(
        [r for r in hits_results if r["over_0.5_H"] >= 80],
        key=lambda x: x["over_0.5_H"], reverse=True
    )
    hrr_q = sorted(
        [r for r in hrr_results if r["over_1.5_HRR"] >= 80],
        key=lambda x: x["over_1.5_HRR"], reverse=True
    )
    k_q = sorted(k_results, key=lambda x: x["over_4.5_K"], reverse=True)

    # Build simple 3-leg parlay suggestions from top hits + hrr + k prop
    parlay_suggestions = []
    top_hits = [r for r in hits_q if r["over_0.5_H"] >= 80][:6]
    top_k    = [r for r in k_q    if r["over_4.5_K"] >= 60][:4]

    for i in range(0, min(len(top_hits), 6), 3):
        legs_pool = top_hits[i:i+3]
        if len(legs_pool) < 2:
            break
        legs = [{"player": r["player"], "prop": "Over 0.5 Hits", "hit_rate": r["over_0.5_H"]} for r in legs_pool]
        if top_k:
            k_leg = top_k[i // 3] if (i // 3) < len(top_k) else top_k[0]
            legs[-1] = {"player": k_leg["pitcher"], "prop": "Over 4.5 Ks", "hit_rate": k_leg["over_4.5_K"]}
        parlay_suggestions.append({
            "game": "Today's Games",
            "legs": legs,
        })

    if progress_bar:
        progress_bar.progress(1.0)

    return {
        "date": datetime.date.today().strftime("%Y-%m-%d"),
        "hits_qualifiers": hits_q,
        "hrr_qualifiers":  hrr_q,
        "k_qualifiers":    k_q,
        "parlay_suggestions": parlay_suggestions,
    }


# ====================== ANALYTICS HELPERS ======================

def compute_weighted_hit_rate(pdata: pd.DataFrame, stat_col: str, threshold: float) -> float:
    n = len(pdata)
    if n == 0:
        return 0.0
    decay = 0.1
    weights = [1.0 / (1.0 + decay * i) for i in range(n)]
    total_weight = sum(weights)
    hits = sum(w for i, w in enumerate(weights) if pdata.iloc[i][stat_col] > threshold)
    return (hits / total_weight) * 100


def detect_streak_slump(pdata: pd.DataFrame, stat_col: str, threshold: float):
    recent = pdata.head(3)[stat_col].tolist()
    if len(recent) < 3:
        return "Neutral", "➖", "#aaaaaa"
    over = [v > threshold for v in recent]
    if all(over):
        return "🔥 Streak", "🔥", "#00ff88"
    if not any(over):
        return "❄️ Slump", "❄️", "#ff5555"
    return "➖ Neutral", "➖", "#aaaaaa"


def compute_confidence_score(
    hit_rate: float,
    weighted_hit_rate: float,
    park_factor: int,
    opp_era: str,
    bvp_season: dict | None,
    bvp_career: dict | None,
    streak_label: str,
    platoon_split: dict | None = None,
    pitcher_hand: str = "",
) -> tuple[float, dict]:
    scores = {}

    scores["Hit Rate (raw)"] = round(hit_rate * 0.20, 1)
    scores["Hit Rate (weighted)"] = round(weighted_hit_rate * 0.20, 1)

    pf_norm = min(max((park_factor - 85) / 50, 0), 1)
    scores["Park Factor"] = round(pf_norm * 15, 1)

    try:
        era_val = float(opp_era)
        era_norm = min(max((era_val - 2.0) / 5.0, 0), 1)
        scores["Opp. ERA"] = round(era_norm * 15, 1)
    except (ValueError, TypeError):
        scores["Opp. ERA"] = 7.5

    # BvP
    bvp_score = 0.0
    if bvp_season and bvp_season.get("atBats", 0) >= 2:
        try:
            avg = float(bvp_season["avg"])
            ab = bvp_season["atBats"]
            sample_weight = min(ab / 10, 1.0)
            bvp_score = max(bvp_score, avg * 10 / 0.400 * sample_weight)
        except:
            pass
    if bvp_career and bvp_career.get("atBats", 0) >= 3:
        try:
            avg = float(bvp_career["avg"])
            ab = bvp_career["atBats"]
            sample_weight = min(ab / 15, 1.0) * 0.8
            bvp_score = max(bvp_score, avg * 10 / 0.400 * sample_weight)
        except:
            pass
    scores["BvP History"] = round(min(bvp_score, 10), 1)

    streak_bonus = 10.0 if "Streak" in streak_label else (0.0 if "Slump" in streak_label else 5.0)
    scores["Streak/Slump"] = streak_bonus

    # Platoon
    platoon_score = 5.0
    if platoon_split and pitcher_hand in ("L", "R"):
        code = "vl" if pitcher_hand == "L" else "vr"
        split_data = platoon_split.get(code)
        if split_data and split_data.get("atBats", 0) >= 5:
            try:
                ops = float(split_data["ops"])
                platoon_score = min(max((ops - 0.600) / 0.500 * 10, 0), 10)
            except:
                pass
    scores["Platoon Split"] = round(platoon_score, 1)

    total = min(sum(scores.values()), 100)
    return round(total, 1), scores


# ====================== STREAMLIT APP ======================
st.title("⚾ MLB Active Player Stats Pro")

tab_parlays, tab_player = st.tabs(["🎯 Today's Parlay Suggestions", "📊 Player Stats"])

# ====================== TAB 1: PARLAY SUGGESTIONS ======================
with tab_parlays:
    st.subheader("🎯 Today's Parlay Suggestions & Prop Hot Lists")

    # ---- Session state for generated data ----
    if "live_props" not in st.session_state:
        st.session_state.live_props = None
    if "props_date" not in st.session_state:
        st.session_state.props_date = None

    date_today = datetime.date.today().strftime("%Y-%m-%d")
    data_is_stale = st.session_state.props_date != date_today

    col_gen1, col_gen2 = st.columns([3, 1])
    with col_gen1:
        if st.session_state.live_props is None:
            st.info("📡 Click **Generate** to fetch live stats for all of today's games and score props automatically.")
        elif data_is_stale:
            st.warning("⚠️ Data was generated on a previous date. Click **Regenerate** to refresh.")
        else:
            gen_time = st.session_state.get("props_generated_at", "")
            st.success(f"✅ Live data loaded — generated at {gen_time}")
    with col_gen2:
        btn_label = "🔄 Regenerate" if st.session_state.live_props else "⚡ Generate"
        if st.button(btn_label, use_container_width=True):
            today_games_for_gen = get_todays_games()
            if not today_games_for_gen:
                st.error("No games found for today.")
            else:
                prog = st.progress(0, text="Fetching rosters & game logs…")
                with st.spinner("Scoring props across all games — this takes ~30 seconds…"):
                    result = generate_live_props(today_games_for_gen, progress_bar=prog)
                prog.empty()
                st.session_state.live_props = result
                st.session_state.props_date = date_today
                st.session_state.props_generated_at = datetime.datetime.now().strftime("%H:%M")
                st.rerun()

    # ---- Render data if available ----
    daily_data = st.session_state.live_props

    # Fall back to legacy JSON file if it exists and no live data yet
    if daily_data is None:
        daily_file = "daily_k_props.json"
        if os.path.exists(daily_file):
            try:
                with open(daily_file, "r", encoding="utf-8") as f:
                    daily_data = json.load(f)
                if daily_data.get("date") != date_today:
                    st.caption(f"ℹ️ Showing cached file from {daily_data.get('date', '?')}. Generate live data above for today.")
                else:
                    st.caption("ℹ️ Showing data from `daily_k_props.json`. Hit Generate for live data.")
            except Exception:
                daily_data = None

    if daily_data:
        prop_tab_hits, prop_tab_hrr, prop_tab_k, prop_tab_parlay = st.tabs(
            ["🟢 Hits Hot List", "🔥 H+R+RBI Hot List", "⚡ Pitcher K Props", "🎯 Parlay Suggestions"]
        )

        # ---- Hits Hot List ----
        with prop_tab_hits:
            hits_list = daily_data.get("hits_qualifiers", [])
            if hits_list:
                df_h = pd.DataFrame(hits_list)
                avail = [c for c in ["player", "over_0.5_H", "over_1.5_H", "games"] if c in df_h.columns]
                st.dataframe(
                    df_h[avail].sort_values("over_0.5_H", ascending=False).reset_index(drop=True),
                    use_container_width=True, hide_index=True
                )
                st.success(f"✅ **{len(df_h)} batters** with ≥80% hit rate on Over 0.5 H")
            else:
                st.info("No hits data available. Click Generate above.")

        # ---- H+R+RBI Hot List ----
        with prop_tab_hrr:
            hrr_list = daily_data.get("hrr_qualifiers", [])
            if hrr_list:
                df_hrr = pd.DataFrame(hrr_list)
                avail = [c for c in ["player", "over_1.5_HRR", "over_0.5_H", "games"] if c in df_hrr.columns]
                st.dataframe(
                    df_hrr[avail].sort_values("over_1.5_HRR", ascending=False).reset_index(drop=True),
                    use_container_width=True, hide_index=True
                )
                st.success(f"✅ **{len(df_hrr)} batters** with ≥80% hit rate on Over 1.5 H+R+RBI")
            else:
                st.info("No H+R+RBI data available. Click Generate above.")

        # ---- Pitcher K Props ----
        with prop_tab_k:
            st.markdown("#### ⚡ Starting Pitcher Strikeout Props — Last 5 Starts")
            st.caption("Hit rates based on historical game logs. Always verify vs. sportsbook lines.")
            k_list = daily_data.get("k_qualifiers", [])
            if k_list:
                df_k = pd.DataFrame(k_list)

                # Color-code K/9
                def k9_color(val):
                    try:
                        v = float(val)
                        if v >= 10: return "color:#00ff88"
                        if v >= 8:  return "color:#ffcc00"
                        return "color:#ff5555"
                    except:
                        return ""

                def rate_color(val):
                    try:
                        v = float(val)
                        if v >= 70: return "color:#00ff88"
                        if v >= 50: return "color:#ffcc00"
                        return "color:#aaaaaa"
                    except:
                        return ""

                avail = [c for c in ["pitcher", "K/9", "avg_K", "over_3.5_K", "over_4.5_K", "over_5.5_K", "starts"] if c in df_k.columns]
                styled_k = df_k[avail].style \
                    .map(k9_color,   subset=["K/9"]       if "K/9"       in avail else []) \
                    .map(rate_color, subset=["over_3.5_K"] if "over_3.5_K" in avail else []) \
                    .map(rate_color, subset=["over_4.5_K"] if "over_4.5_K" in avail else []) \
                    .map(rate_color, subset=["over_5.5_K"] if "over_5.5_K" in avail else []) \
                    .format(precision=1)

                st.dataframe(styled_k, use_container_width=True, hide_index=True)

                # Highlight top K plays
                top_k_plays = df_k[df_k["over_4.5_K"] >= 60].sort_values("over_4.5_K", ascending=False) if "over_4.5_K" in df_k.columns else pd.DataFrame()
                if not top_k_plays.empty:
                    st.markdown("**🎯 Top K Plays (≥60% on Over 4.5 K):**")
                    for _, row in top_k_plays.head(5).iterrows():
                        k9_val = row.get("K/9", "?")
                        avg_val = row.get("avg_K", "?")
                        rate_val = row.get("over_4.5_K", "?")
                        st.markdown(
                            f"<div style='background:#1e1e2e;border:1px solid #00ff88;border-radius:8px;"
                            f"padding:8px 14px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center'>"
                            f"<span style='font-weight:700'>{row['pitcher']}</span>"
                            f"<span style='color:#aaa;font-size:12px'>K/9: <b style='color:#fff'>{k9_val}</b> &nbsp;|&nbsp; "
                            f"Avg K: <b style='color:#fff'>{avg_val}</b> &nbsp;|&nbsp; "
                            f"Over 4.5: <b style='color:#00ff88'>{rate_val}%</b></span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
            else:
                st.info("No pitcher K data available. Click Generate above.")

        # ---- Parlay Suggestions ----
        with prop_tab_parlay:
            suggestions = daily_data.get("parlay_suggestions", [])
            if suggestions:
                st.markdown("#### 🎯 Suggested 3-Leg Parlays")
                st.caption("Built from top hit-rate batters + best K props. Always verify lines.")
                for i in range(0, len(suggestions), 2):
                    cols = st.columns(2)
                    for idx, col in enumerate(cols):
                        if i + idx < len(suggestions):
                            sug = suggestions[i + idx]
                            with col:
                                st.markdown(
                                    f"<div style='background:#1e1e2e;border:1px solid #444;border-radius:10px;padding:12px 16px;margin-bottom:10px'>",
                                    unsafe_allow_html=True
                                )
                                st.markdown(f"**⚾ {sug.get('game', 'Today')}**")
                                for j, leg in enumerate(sug.get("legs", []), 1):
                                    rate = leg.get("hit_rate", 0)
                                    rate_color = "#00ff88" if rate >= 70 else "#ffcc00" if rate >= 50 else "#aaa"
                                    st.markdown(
                                        f"Leg {j}: **{leg.get('player','?')}** — {leg.get('prop','')} "
                                        f"<span style='color:{rate_color}'>({rate}%)</span>",
                                        unsafe_allow_html=True
                                    )
                                st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.info("No parlay suggestions yet. Click Generate above.")

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
                all_players.append({"label": f"{p['fullName']} ({p['position']} - {selected_game['awayAbbrev']})", 
                                  "id": p["id"], "name": p["fullName"], "posCode": p["posCode"], 
                                  "teamAbbrev": selected_game["awayAbbrev"], "is_away": True})
            for p in home_roster:
                all_players.append({"label": f"{p['fullName']} ({p['position']} - {selected_game['homeAbbrev']})", 
                                  "id": p["id"], "name": p["fullName"], "posCode": p["posCode"], 
                                  "teamAbbrev": selected_game["homeAbbrev"], "is_away": False})
            
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

    # ====================== HOT LISTS ======================
    if selected_game:
        game_daily_data = st.session_state.get("live_props")
        # Fall back to legacy JSON
        if game_daily_data is None:
            daily_file = "daily_k_props.json"
            if os.path.exists(daily_file):
                try:
                    with open(daily_file, "r", encoding="utf-8") as f:
                        game_daily_data = json.load(f)
                except Exception:
                    game_daily_data = None

        if game_daily_data:
            st.subheader("🔥 Today's Prop Hot Lists — This Game")
            st.caption(f"Filtered for **{selected_game['display']}**")

            col1, col2, col3 = st.columns(3)
            search_pattern = f"{selected_game['awayAbbrev']}|{selected_game['homeAbbrev']}"

            with col1:
                st.markdown("**Hits Hot List**")
                hits_list = game_daily_data.get("hits_qualifiers", [])
                if hits_list:
                    df_h2 = pd.DataFrame(hits_list)
                    df_game = df_h2[df_h2["player"].str.contains(search_pattern, na=False, case=False)].copy()
                    if not df_game.empty:
                        hit_cols = [c for c in ["player", "over_0.5_H", "over_1.5_H"] if c in df_game.columns]
                        st.dataframe(df_game[hit_cols].head(10), use_container_width=True, hide_index=True)
                    else:
                        st.info("No hot hitters in this game.")
                else:
                    st.info("Generate props in Tab 1 first.")

            with col2:
                st.markdown("**Pitcher K Props**")
                k_list2 = game_daily_data.get("k_qualifiers", [])
                if k_list2:
                    df_k2 = pd.DataFrame(k_list2)
                    pitcher_col = "pitcher" if "pitcher" in df_k2.columns else "player"
                    df_game_k = df_k2[df_k2[pitcher_col].str.contains(search_pattern, na=False, case=False)].copy()
                    if not df_game_k.empty:
                        k_cols = [c for c in [pitcher_col, "K/9", "avg_K", "over_3.5_K", "over_4.5_K"] if c in df_game_k.columns]
                        st.dataframe(df_game_k[k_cols], use_container_width=True, hide_index=True)
                    else:
                        st.info("No K prop data for pitchers in this game.")
                else:
                    st.info("Generate props in Tab 1 first.")

            with col3:
                st.markdown("**H + R + RBI Hot List**")
                hrr_list2 = game_daily_data.get("hrr_qualifiers", [])
                if hrr_list2:
                    df_hrr2 = pd.DataFrame(hrr_list2)
                    df_game_hrr = df_hrr2[df_hrr2["player"].str.contains(search_pattern, na=False, case=False)].copy()
                    if not df_game_hrr.empty:
                        hrr_cols = [c for c in ["player", "over_1.5_HRR"] if c in df_game_hrr.columns]
                        st.dataframe(df_game_hrr[hrr_cols].head(10), use_container_width=True, hide_index=True)
                    else:
                        st.info("No hot H+R+RBI in this game.")
                else:
                    st.info("Generate props in Tab 1 first.")
        else:
            st.info("💡 Go to **Today's Parlay Suggestions** tab and click **Generate** to load prop hot lists.")

        st.divider()

    # ====================== PLAYER ANALYSIS ======================
    if selected_player and selected_game:
        is_pitcher = selected_player["posCode"] == "1"
        logs = get_game_log(selected_player["id"], "pitching" if is_pitcher else "hitting")
        
        if logs:
            records = []
            for s in logs:
                stt = s.get("stat", {})
                rec = {"Date": s.get("date"), "Opponent": s.get("opponent", {}).get("name")}
                if is_pitcher:
                    rec.update({"K": int(stt.get("strikeOuts", 0)), 
                              "ER": int(stt.get("earnedRuns", 0)), 
                              "Outs": calculate_outs(stt.get("inningsPitched", "0.0"))})
                else:
                    h = int(stt.get("hits", 0))
                    r = int(stt.get("runs", 0))
                    rbi = int(stt.get("rbi", 0))
                    ab = int(stt.get("atBats", 0))
                    rec.update({"AB": ab, "H": h, "R": r, "RBI": rbi, "H+R+RBI": h + r + rbi, 
                              "K": int(stt.get("strikeOuts", 0))})
                records.append(rec)
            
            df = pd.DataFrame(records).sort_values("Date", ascending=False)
            mapping = {"Hits": "H", "Runs": "R", "RBI": "RBI", "H+R+RBI": "H+R+RBI",
                       "Strikeouts": "K", "Earned Runs": "ER", "Outs": "Outs"}
            stat_col = mapping.get(selected_stat)

            if stat_col in df.columns:
                pdata = df.head(10).copy()
                hit_rate = (pdata[stat_col] > threshold).mean() * 100
                weighted_hr = compute_weighted_hit_rate(pdata, stat_col, threshold)
                streak_label, streak_emoji, streak_color = detect_streak_slump(pdata, stat_col, threshold)

                bvp_season, bvp_career = None, None
                platoon_splits, pitcher_hand = {}, ""
                if not is_pitcher and opp_pid:
                    current_year = datetime.datetime.now().year
                    bvp_season = get_batter_vs_pitcher(selected_player["id"], opp_pid, current_year)
                    bvp_career = get_batter_vs_pitcher_career(selected_player["id"], opp_pid)
                    platoon_splits = get_batter_platoon_splits(selected_player["id"])
                    pitcher_hand = get_pitcher_hand(opp_pid)

                confidence, conf_breakdown = compute_confidence_score(
                    hit_rate, weighted_hr, pf, opp_era, bvp_season, bvp_career,
                    streak_label, platoon_splits, pitcher_hand
                )

                # Confidence + Streak Banner
                conf_color = "#00ff88" if confidence >= 70 else "#ffcc00" if confidence >= 50 else "#ff5555"
                conf_label = "High" if confidence >= 70 else "Medium" if confidence >= 50 else "Low"
                st.markdown(
                    f"""<div style="display:flex;gap:12px;align-items:center;margin-bottom:8px;">
                        <div style="background:#1e1e2e;border:1px solid {conf_color};border-radius:10px;padding:8px 18px;text-align:center;">
                            <div style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:1px;">Confidence</div>
                            <div style="font-size:28px;font-weight:700;color:{conf_color};">{confidence}</div>
                            <div style="font-size:12px;color:{conf_color};">{conf_label}</div>
                        </div>
                        <div style="background:#1e1e2e;border:1px solid {streak_color};border-radius:10px;padding:8px 18px;text-align:center;">
                            <div style="font-size:11px;color:#aaa;text-transform:uppercase;letter-spacing:1px;">Last 3 Games</div>
                            <div style="font-size:28px;">{streak_emoji}</div>
                            <div style="font-size:12px;color:{streak_color};">{streak_label}</div>
                        </div>
                    </div>""",
                    unsafe_allow_html=True,
                )

                c1, c2 = st.columns([3, 2])
                with c1:
                    st.subheader(f"🎯 {hit_rate:.0f}% Over {threshold} (Last 10 Games)")
                    chart_data = pdata.sort_values("Date", ascending=False)
                    bar_colors = ["#00ff88" if v > threshold else "#ff5555" for v in chart_data[stat_col]]
                    fig = px.bar(chart_data, x="Date", y=stat_col, text_auto=True, height=380,
                                title=f"{selected_player['name']} - {selected_stat} Trend")
                    fig.update_traces(marker_color=bar_colors)
                    fig.add_hline(y=threshold, line_dash="dash", line_color="cyan",
                                  annotation_text=f"Line {threshold}", annotation_position="top right")
                    st.plotly_chart(fig, use_container_width=True)

                    hr_col1, hr_col2 = st.columns(2)
                    with hr_col1:
                        st.metric("Raw Hit Rate (last 10)", f"{hit_rate:.0f}%")
                    with hr_col2:
                        delta = round(weighted_hr - hit_rate, 1)
                        st.metric("Weighted Hit Rate", f"{weighted_hr:.0f}%",
                                  delta=f"{delta:+.1f}%")

                with c2:
                    st.write("#### Matchup Quality")
                    mq1, mq2 = st.columns(2)
                    with mq1:
                        st.metric("Park Factor", pf, delta=round(pf-100, 1))
                    with mq2:
                        st.metric("Opp. ERA", opp_era)

                    if not is_pitcher and opp_pid:
                        st.caption(f"**vs {opp_starter}**")
                        bvp1, bvp2 = st.columns(2)
                        with bvp1:
                            if bvp_season and bvp_season["atBats"] > 0:
                                st.metric("Season AVG", bvp_season["avg"], help=f"{bvp_season['hits']}/{bvp_season['atBats']} • HR: {bvp_season['homeRuns']}")
                            else:
                                st.metric("Season AVG", "—")
                        with bvp2:
                            if bvp_career and bvp_career["atBats"] > 0:
                                st.metric("Career AVG", bvp_career["avg"], help=f"{bvp_career['hits']}/{bvp_career['atBats']} • HR: {bvp_career['homeRuns']}")
                            else:
                                st.metric("Career AVG", "—")

                        if platoon_splits:
                            hand_label = {"L": "LHP", "R": "RHP"}.get(pitcher_hand, "")
                            st.caption(f"**Platoon Splits** {'— facing ' + hand_label if hand_label else ''}")
                            pl1, pl2 = st.columns(2)
                            for col, code, label in [(pl1, "vr", "vs RHP"), (pl2, "vl", "vs LHP")]:
                                with col:
                                    d = platoon_splits.get(code)
                                    if d and d["atBats"] > 0:
                                        highlight = (pitcher_hand == "R" and code == "vr") or (pitcher_hand == "L" and code == "vl")
                                        border = "border:1px solid #00ff88;" if highlight else ""
                                        st.markdown(
                                            f"<div style='background:#1e1e2e;border-radius:8px;padding:6px 8px;{border}'>"
                                            f"<div style='font-size:10px;color:#aaa'>{label} ({d['atBats']} AB)</div>"
                                            f"<div style='font-size:15px;font-weight:700'>{d['avg']}</div>"
                                            f"<div style='font-size:10px;color:#aaa'>OPS {d['ops']}</div>"
                                            f"</div>",
                                            unsafe_allow_html=True
                                        )

                    # ==== FIXED PITCHER RECENT FORM ====
                    if opp_pid:
                        pitcher_form = get_pitcher_recent_form(opp_pid, num_starts=4)
                        if pitcher_form:
                            st.caption(f"**{opp_starter} — Last {len(pitcher_form)} Starts**")
                            form_df = pd.DataFrame(pitcher_form)
                            
                            def er_color(val):
                                if pd.isna(val):
                                    return ""
                                try:
                                    v = float(val)
                                    if v <= 1: return "color:#00ff88"
                                    if v <= 3: return "color:#ffcc00"
                                    return "color:#ff5555"
                                except:
                                    return ""
                            
                            styled = (form_df.style
                                .map(lambda v: er_color(v), subset=["ER"])
                                .format(precision=0)
                            )
                            
                            st.dataframe(styled, use_container_width=True, hide_index=True)

                            if len(pitcher_form) >= 2:
                                recent_er = sum(r["ER"] for r in pitcher_form[:2])
                                older_er = sum(r["ER"] for r in pitcher_form[2:]) / max(len(pitcher_form) - 2, 1)
                                avg_recent = recent_er / 2
                                if avg_recent < older_er - 0.5:
                                    st.success("📉 Pitcher trending better recently")
                                elif avg_recent > older_er + 0.5:
                                    st.warning("📈 Pitcher trending worse recently")

                    with st.expander("📊 Confidence Breakdown"):
                        max_pts_map = {
                            "Hit Rate (raw)": 20, "Hit Rate (weighted)": 20,
                            "Park Factor": 15, "Opp. ERA": 15,
                            "BvP History": 10, "Streak/Slump": 10, "Platoon Split": 10
                        }
                        for component, pts in conf_breakdown.items():
                            max_pts = max_pts_map.get(component, 10)
                            pct = pts / max_pts
                            bar_w = int(pct * 100)
                            bar_c = "#00ff88" if pct >= 0.7 else "#ffcc00" if pct >= 0.4 else "#ff5555"
                            st.markdown(
                                f"<div style='margin-bottom:6px'>"
                                f"<div style='display:flex;justify-content:space-between;font-size:12px'>"
                                f"<span>{component}</span><span style='color:{bar_c}'>{pts}/{max_pts}</span></div>"
                                f"<div style='background:#333;border-radius:4px;height:6px'>"
                                f"<div style='background:{bar_c};width:{bar_w}%;height:6px;border-radius:4px'></div>"
                                f"</div></div>",
                                unsafe_allow_html=True
                            )

            st.dataframe(df.head(15), use_container_width=True, hide_index=True)
        else:
            st.info("No game logs found for this season.")
    elif selected_game:
        st.info("👈 Select a player from the sidebar to view detailed analytics.")
