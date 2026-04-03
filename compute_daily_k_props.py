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


# ====================== PARLAY SUGGESTION FUNCTION ======================
def suggest_game_parlays(game_batter_stats: list, game_label: str) -> dict:
    """
    Given a list of batter stat dicts for one game, pick the 3 best prop legs
    based on highest hit rate. Each candidate is a (player, prop_label, hit_rate) tuple.

    Priority order for prop selection:
      1. Avoid duplicate players across the 3 legs (prefer variety)
      2. Rank by hit rate descending
      3. Prefer higher-threshold props (1.5) when hit rate is the same
    """
    PROP_COLUMNS = [
        ("over_1.5_H",   "Over 1.5 Hits"),
        ("over_0.5_H",   "Over 0.5 Hits"),
        ("over_1.5_K",   "Over 1.5 Strikeouts"),
        ("over_0.5_K",   "Over 0.5 Strikeouts"),
        ("over_1.5_HRR", "Over 1.5 H+R+RBI"),
    ]

    # Build a flat list of all (player, prop_key, prop_label, hit_rate) candidates
    candidates = []
    for batter in game_batter_stats:
        for prop_key, prop_label in PROP_COLUMNS:
            rate = batter.get(prop_key, 0)
            if rate > 0:
                candidates.append({
                    "player":     batter["player"],
                    "player_id":  batter["player_id"],
                    "prop_key":   prop_key,
                    "prop_label": prop_label,
                    "hit_rate":   rate,
                    "games_considered": batter["games_considered"],
                })

    # Sort: highest hit rate first; for ties, prefer 1.5-threshold props (they appear earlier in PROP_COLUMNS)
    candidates.sort(key=lambda c: (-c["hit_rate"], PROP_COLUMNS.index((c["prop_key"], c["prop_label"]))))

    # Greedily pick 3 legs, preferring unique players
    selected = []
    used_players = set()

    # Pass 1: unique players only
    for c in candidates:
        if len(selected) == 3:
            break
        if c["player"] not in used_players:
            selected.append(c)
            used_players.add(c["player"])

    # Pass 2: if we still need legs, allow repeat players (edge case with thin rosters)
    if len(selected) < 3:
        for c in candidates:
            if len(selected) == 3:
                break
            if c not in selected:
                selected.append(c)

    if not selected:
        return {
            "game": game_label,
            "note": "Insufficient data to suggest a parlay for this game.",
            "legs": []
        }

    combined_confidence = round(
        sum(leg["hit_rate"] for leg in selected) / len(selected), 1
    )

    return {
        "game": game_label,
        "avg_leg_hit_rate": combined_confidence,
        "legs": [
            {
                "player":    leg["player"],
                "prop":      leg["prop_label"],
                "hit_rate":  leg["hit_rate"],
                "games_considered": leg["games_considered"],
            }
            for leg in selected
        ]
    }


# ====================== MAIN COMPUTE FUNCTION ======================
def compute_daily_k_props():
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"🚀 Computing daily prop hot lists for {today_str}...")

    today_games = get_todays_games()
    if not today_games:
        print("❌ No games found for today.")
        return

    results = []
    # Map gamePk -> list of qualifying batter stat dicts (for parlay builder)
    game_batter_map: dict[int, dict] = {}

    for game in today_games:
        away_batters = get_team_active_roster(game["awayId"])
        home_batters = get_team_active_roster(game["homeId"])

        batter_list = []
        for b in away_batters:
            batter_list.append((b["id"], b["fullName"], game["awayAbbrev"]))
        for b in home_batters:
            batter_list.append((b["id"], b["fullName"], game["homeAbbrev"]))

        game_key = game["gamePk"]
        game_label = f"{game['awayTeam']} @ {game['homeTeam']}"
        game_batter_map[game_key] = {"label": game_label, "batters": []}

        for player_id, full_name, team_abbrev in batter_list:
            game_splits = get_game_log(player_id)
            if len(game_splits) < 5:   # Require at least 5 games
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
                    "HRR": combined
                })

            if not records:
                continue

            df = pd.DataFrame(records)
            pdata = df.head(10).copy()   # Last 10 games
            n_games = len(pdata)

            if n_games < 5:
                continue

            # Calculate percentages
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
                "games_considered": n_games,
                "player_id": player_id
            }

            # Always store for parlay builder (all batters with enough games)
            game_batter_map[game_key]["batters"].append(batter_stats)

            # === KEY FILTER: Only include in main results if ≥80% on AT LEAST ONE threshold ===
            if (over_05_h >= 80 or over_15_h >= 80 or
                over_05_k >= 80 or over_15_k >= 80 or
                over_15_hrr >= 80):
                results.append(batter_stats)

    # ====================== PARLAY SUGGESTIONS ======================
    parlay_suggestions = []
    print(f"\n=== TODAY'S 3-LEG PARLAY SUGGESTIONS (per game) ===")
    for game_key, gdata in game_batter_map.items():
        if not gdata["batters"]:
            continue
        suggestion = suggest_game_parlays(gdata["batters"], gdata["label"])
        parlay_suggestions.append(suggestion)

        print(f"\n🎯 {suggestion['game']}")
        if not suggestion["legs"]:
            print(f"   ⚠️  {suggestion.get('note', 'No legs available.')}")
        else:
            print(f"   Avg leg hit rate: {suggestion['avg_leg_hit_rate']}%")
            for i, leg in enumerate(suggestion["legs"], 1):
                print(f"   Leg {i}: {leg['player']} — {leg['prop']}  ({leg['hit_rate']}% in last {leg['games_considered']} games)")

    # ====================== MAIN RESULTS OUTPUT ======================
    if not results:
        print("\n❌ No batters met the ≥80% threshold on any prop today.")
        data = {
            "date": today_str,
            "generated_at": datetime.datetime.now().isoformat(),
            "total_qualifiers": 0,
            "batters": [],
            "parlay_suggestions": parlay_suggestions
        }
    else:
        df_results = pd.DataFrame(results)
        df_results = df_results.sort_values(["over_1.5_H", "over_1.5_K", "over_1.5_HRR"], ascending=False)

        print(f"\n=== TODAY'S PROP QUALIFIERS (>=80% on at least one threshold) ===")
        print(f"Found {len(results)} qualifying batters")
        print(df_results[["player",
                          "over_0.5_H", "over_1.5_H",
                          "over_0.5_K", "over_1.5_K",
                          "over_1.5_HRR",
                          "games_considered"]].to_string(index=False))

        data = {
            "date": today_str,
            "generated_at": datetime.datetime.now().isoformat(),
            "total_qualifiers": len(results),
            "batters": df_results.to_dict("records"),
            "parlay_suggestions": parlay_suggestions
        }

    # Save JSON
    with open("daily_k_props.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(results)} qualifying batters + {len(parlay_suggestions)} parlay suggestions to daily_k_props.json")


if __name__ == "__main__":
    compute_daily_k_props()
