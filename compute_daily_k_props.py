import requests
import pandas as pd
import datetime
import streamlit as st

# ====================== API FUNCTIONS ======================
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
                })
        return games
    except Exception:
        return []

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

# ====================== DATA PROCESSING ======================
@st.cache_data(ttl=3600)
def fetch_and_compute_props():
    today_games = get_todays_games()
    if not today_games:
        return pd.DataFrame()

    results = []
    for game in today_games:
        away_batters = get_team_active_roster(game["awayId"])
        home_batters = get_team_active_roster(game["homeId"])

        batter_list = []
        for b in away_batters: batter_list.append((b["id"], b["fullName"], game["awayAbbrev"]))
        for b in home_batters: batter_list.append((b["id"], b["fullName"], game["homeAbbrev"]))

        for player_id, full_name, team_abbrev in batter_list:
            game_splits = get_game_log(player_id)
            if len(game_splits) < 5: continue

            records = []
            for split in game_splits:
                stat = split.get("stat", {})
                h, r, rbi, k = int(stat.get("hits", 0)), int(stat.get("runs", 0)), int(stat.get("rbi", 0)), int(stat.get("strikeOuts", 0))
                records.append({"H": h, "K": k, "HRR": h + r + rbi})

            df = pd.DataFrame(records).head(10)
            n = len(df)
            if n < 5: continue

            # Calc percentages
            stats_dict = {
                "player": f"{full_name} ({team_abbrev})",
                "over_0.5_H": round((df["H"] > 0.5).sum() / n * 100, 1),
                "over_1.5_H": round((df["H"] > 1.5).sum() / n * 100, 1),
                "over_0.5_K": round((df["K"] > 0.5).sum() / n * 100, 1),
                "over_1.5_K": round((df["K"] > 1.5).sum() / n * 100, 1),
                "over_1.5_HRR": round((df["HRR"] > 1.5).sum() / n * 100, 1),
                "games_considered": n
            }

            # Filter: 80% threshold on at least one
            if any(v >= 80 for k, v in stats_dict.items() if k.startswith("over_")):
                results.append(stats_dict)

    return pd.DataFrame(results)

# ====================== STREAMLIT UI ======================
def main():
    st.set_page_config(page_title="MLB Prop Lab", layout="wide")
    st.title("⚾ MLB Daily Prop Hot Lists (Last 10 Games)")

    with st.spinner("Crunching player stats..."):
        df = fetch_and_compute_props()

    if df.empty:
        st.error("No qualifiers found for today.")
        return

    # --- HITS SECTION ---
    st.header("🔥 Hits (H)")
    h_cols = ["player", "over_0.5_H", "over_1.5_H", "games_considered"]
    df_h = df[(df["over_0.5_H"] >= 80) | (df["over_1.5_H"] >= 80)][h_cols].sort_values("over_1.5_H", ascending=False)
    
    if not df_h.empty:
        st.bar_chart(df_h.set_index("player")[["over_0.5_H", "over_1.5_H"]])
        st.dataframe(df_h, use_container_width=True, hide_index=True)
    else:
        st.info("No 80%+ qualifiers for Hits.")

    st.divider()

    # --- STRIKEOUTS SECTION ---
    st.header("⚡ Strikeouts (K)")
    k_cols = ["player", "over_0.5_K", "over_1.5_K", "games_considered"]
    df_k = df[(df["over_0.5_K"] >= 80) | (df["over_1.5_K"] >= 80)][k_cols].sort_values("over_1.5_K", ascending=False)

    if not df_k.empty:
        st.bar_chart(df_k.set_index("player")[["over_0.5_K", "over_1.5_K"]])
        st.dataframe(df_k, use_container_width=True, hide_index=True)
    else:
        st.info("No 80%+ qualifiers for Strikeouts.")

    st.divider()

    # --- HRR SECTION ---
    st.header("📊 Hits + Runs + RBI (HRR)")
    hrr_cols = ["player", "over_1.5_HRR", "games_considered"]
    df_hrr = df[df["over_1.5_HRR"] >= 80][hrr_cols].sort_values("over_1.5_HRR", ascending=False)

    if not df_hrr.empty:
        st.bar_chart(df_hrr.set_index("player")["over_1.5_HRR"])
        st.dataframe(df_hrr, use_container_width=True, hide_index=True)
    else:
        st.info("No 80%+ qualifiers for HRR.")

if __name__ == "__main__":
    main()
