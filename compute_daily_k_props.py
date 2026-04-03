import requests
import pandas as pd
import datetime
import json

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
    except Exception as e:
        print(f"Error fetching games: {e}")
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
    print(f"🚀 Computing daily prop hit rates (Hits + K + H+R+RBI) for {today_str}...")

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

                records.append({
                    "H": hits,
                    "K": strikeouts,
                    "HRR": combined   # H + R + RBI
                })

            if not records:
                continue

            df = pd.DataFrame(records)
            pdata = df.head(10).copy()   # Last 10 games
            n_games = len(pdata)

            if n_games < 5:
                continue

            # Calculate hit rates
            over_05_h = (pdata["H"] > 0.5).sum() / n_games * 100
            over_15_h = (pdata["H"] > 1.5).sum() / n_games * 100
            over_05_k = (pdata["K"] > 0.5).sum() / n_games * 100
            over_15_k = (pdata["K"] > 1.5).sum() / n_games * 100
            over_15_hrr = (pdata["HRR"] > 1.5).sum() / n_games * 100   # Only 1.5 as requested

            avg_h = pdata["H"].mean()
            avg_k = pdata["K"].mean()
            avg_hrr = pdata["HRR"].mean()

            # Include player if ≥ 80% on ANY of the props
            if (over_05_h >= 80 or over_15_h >= 80 or 
                over_05_k >= 80 or over_15_k >= 80 or 
                over_15_hrr >= 80):
                
                label = f"{full_name} ({team_abbrev})"

                results.append({
                    "player": label,
                    "over_0.5_H": round(over_05_h, 1),
                    "over_1.5_H": round(over_15_h, 1),
                    "over_0.5_K": round(over_05_k, 1),
                    "over_1.5_K": round(over_15_k, 1),
                    "over_1.5_HRR": round(over_15_hrr, 1),   # H+R+RBI > 1.5
                    "avg_H_last10": round(avg_h, 2),
                    "avg_K_last10": round(avg_k, 2),
                    "avg_HRR_last10": round(avg_hrr, 2),
                    "games_considered": n_games,
                    "player_id": player_id
                })

    if not results:
        print("❌ No batters met the ≥80% hit rate threshold today.")
        data = {
            "date": today_str,
            "generated_at": datetime.datetime.now().isoformat(),
            "total_qualifiers": 0,
            "batters": []
        }
    else:
        df_results = pd.DataFrame(results)
        # Sort by strongest props first
        df_results = df_results.sort_values(["over_1.5_H", "over_1.5_K", "over_1.5_HRR"], ascending=False)

        print(f"\n=== TODAY'S PROP QUALIFIERS (≥80% hit rate) ===")
        print(f"Found {len(results)} qualifying batters")
        print(df_results[["player", 
                          "over_0.5_H", "over_1.5_H", 
                          "over_0.5_K", "over_1.5_K", 
                          "over_1.5_HRR", 
                          "avg_H_last10", "avg_K_last10", "avg_HRR_last10", 
                          "games_considered"]].to_string(index=False))

        data = {
            "date": today_str,
            "generated_at": datetime.datetime.now().isoformat(),
            "total_qualifiers": len(results),
            "batters": df_results.to_dict("records")
        }

    # Save to JSON
    with open("daily_k_props.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(results)} qualifying batters to daily_k_props.json")
    print("File ready for Streamlit app!")


if __name__ == "__main__":
    compute_daily_k_props()
