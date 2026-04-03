# ====================== compute_daily_k_props.py ======================
# Save this as a new file in the same folder as mlb.py
# Run manually: python compute_daily_k_props.py
# It runs every morning (schedule it with cron, Task Scheduler, or GitHub Actions)

import requests
import pandas as pd
import datetime
import json

# ====================== API FUNCTIONS (copied from mlb.py) ======================
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


# ====================== MAIN COMPUTE FUNCTION ======================
def compute_daily_k_props():
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"🚀 Computing strikeout prop hit rates for {today_str} games...")

    today_games = get_todays_games()
    if not today_games:
        print("❌ No games found for today.")
        return

    results = []
    for game in today_games:
        away_batters = get_team_active_roster(game["awayId"])
        home_batters = get_team_active_roster(game["homeId"])

        batter_list = []
        for b in away_batters:
            batter_list.append((b["id"], b["fullName"], game["awayAbbrev"]))
        for b in home_batters:
            batter_list.append((b["id"], b["fullName"], game["homeAbbrev"]))

        for player_id, full_name, team_abbrev in batter_list:
            game_splits = get_game_log(player_id)
            if not game_splits:
                continue

            records = []
            for split in game_splits:
                stat = split.get("stat", {})
                k = int(stat.get("strikeOuts", 0))
                date_str = split.get("date", "N/A")
                records.append({"Date": date_str, "K": k})

            if not records:
                continue

            df = pd.DataFrame(records)
            df = df.sort_values("Date", ascending=False)
            pdata = df.head(10).copy()
            n_games = len(pdata)

            if n_games == 0:
                continue

            over_05_pct = (pdata["K"] > 0.5).sum() / n_games * 100
            over_15_pct = (pdata["K"] > 1.5).sum() / n_games * 100
            avg_k = pdata["K"].mean()

            label = f"{full_name} ({team_abbrev})"

            results.append({
                "player": label,
                "over_0.5_K": round(over_05_pct, 1),
                "over_1.5_K": round(over_15_pct, 1),
                "avg_K_last10": round(avg_k, 2),
                "games_considered": n_games,
                "player_id": player_id
            })

    if not results:
        print("❌ No batter data found.")
        return

    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values("over_1.5_K", ascending=False)

    print("\n=== TODAY'S STRIKEOUT PROP HIT RATES (Last 10 Games) ===")
    print(df_results[["player", "over_0.5_K", "over_1.5_K", "avg_K_last10", "games_considered"]].to_string(index=False))

    # Save to JSON for the Streamlit app
    data = {
        "date": today_str,
        "generated_at": datetime.datetime.now().isoformat(),
        "total_batters_processed": len(results),
        "batters": df_results.to_dict("records")
    }

    with open("daily_k_props.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(results)} batters to daily_k_props.json")
    print("   → Your mlb.py app will now display this table automatically!")


if __name__ == "__main__":
    compute_daily_k_props()
