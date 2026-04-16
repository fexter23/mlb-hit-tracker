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
    print(f"🚀 Computing daily prop hot lists + parlay suggestions for {today_str}...")

    today_games = get_todays_games()
    if not today_games:
        print("❌ No games found for today.")
        return

    hits_qualifiers = []
    strikeouts_qualifiers = []
    hrr_qualifiers = []
    parlay_suggestions = []

    for game in today_games:
        away_batters = get_team_active_roster(game["awayId"])
        home_batters = get_team_active_roster(game["homeId"])

        batter_list = []
        for b in away_batters:
            batter_list.append((b["id"], b["fullName"], game["awayAbbrev"]))
        for b in home_batters:
            batter_list.append((b["id"], b["fullName"], game["homeAbbrev"]))

        game_batter_stats = []
        game_label = f"{game['awayTeam']} @ {game['homeTeam']}"

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

            df = pd.DataFrame(records)
            pdata = df.head(10).copy()
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
                "games_considered": n_games,
                "player_id": player_id
            }

            game_batter_stats.append(batter_stats)

            # Add to correct hot list(s)
            if over_05_h >= 80 or over_15_h >= 80:
                hits_qualifiers.append(batter_stats)
            if over_05_k >= 80 or over_15_k >= 80:
                strikeouts_qualifiers.append(batter_stats)
            if over_15_hrr >= 80:
                hrr_qualifiers.append(batter_stats)

        # Build parlay suggestion for this game
        if game_batter_stats:
            suggestion = suggest_game_parlays(game_batter_stats, game_label)
            parlay_suggestions.append(suggestion)

    # Sort parlay suggestions by average hit rate (descending)
    parlay_suggestions.sort(key=lambda x: x.get("avg_leg_hit_rate", 0), reverse=True)

    # ====================== SAVE TO JSON ======================
    data = {
        "date": today_str,
        "generated_at": datetime.datetime.now().isoformat(),
        "hits_qualifiers": hits_qualifiers,
        "strikeouts_qualifiers": strikeouts_qualifiers,
        "hrr_qualifiers": hrr_qualifiers,
        "parlay_suggestions": parlay_suggestions
    }

    with open("daily_k_props.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved:")
    print(f"   • Hits qualifiers:        {len(hits_qualifiers)}")
    print(f"   • Strikeouts qualifiers:  {len(strikeouts_qualifiers)}")
    print(f"   • H+R+RBI qualifiers:     {len(hrr_qualifiers)}")
    print(f"   • Parlay suggestions:     {len(parlay_suggestions)}")
    print(f"\nFile daily_k_props.json is ready!")


# ====================== PARLAY HELPER ======================
def suggest_game_parlays(game_batter_stats: list, game_label: str) -> dict:
    PROP_COLUMNS = [
        ("over_1.5_H",   "Over 1.5 Hits"),
        ("over_0.5_H",   "Over 0.5 Hits"),
        ("over_1.5_K",   "Over 1.5 Strikeouts"),
        ("over_0.5_K",   "Over 0.5 Strikeouts"),
        ("over_1.5_HRR", "Over 1.5 H+R+RBI"),
    ]

    candidates = []
    for batter in game_batter_stats:
        for prop_key, prop_label in PROP_COLUMNS:
            rate = batter.get(prop_key, 0)
            if rate > 0:
                candidates.append({
                    "player": batter["player"],
                    "prop_key": prop_key,
                    "prop_label": prop_label,
                    "hit_rate": rate,
                    "games_considered": batter["games_considered"],
                })

    candidates.sort(key=lambda c: (-c["hit_rate"], 
                                   [pk for pk, _ in PROP_COLUMNS].index(next(pk for pk, pl in PROP_COLUMNS if pl == c["prop_label"]))))

    selected, used = [], set()
    for c in candidates:
        if len(selected) == 4:          # Changed to 4 legs
            break
        if c["player"] not in used:
            selected.append(c)
            used.add(c["player"])

    # Fill remaining legs if needed
    if len(selected) < 4:
        for c in candidates:
            if len(selected) == 4:
                break
            if c not in selected:
                selected.append(c)

    if not selected:
        return {"game": game_label, "note": "Insufficient data", "legs": []}

    combined_confidence = round(sum(leg["hit_rate"] for leg in selected) / len(selected), 1)

    return {
        "game": game_label,
        "avg_leg_hit_rate": combined_confidence,
        "legs": [
            {
                "player": leg["player"],
                "prop": leg["prop_label"],
                "hit_rate": leg["hit_rate"],
                "games_considered": leg["games_considered"],
            }
            for leg in selected
        ]
    }


if __name__ == "__main__":
    compute_daily_k_props()
