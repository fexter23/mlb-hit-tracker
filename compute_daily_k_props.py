import requests
import pandas as pd
import datetime
import json
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ====================== CONFIG ======================
RECIPIENT_EMAIL = "your@email.com"       # <-- hardcode recipient here
SENDER_EMAIL    = os.environ["GMAIL_USER"]        # set in GitHub Actions secrets
SENDER_PASSWORD = os.environ["GMAIL_APP_PASSWORD"] # set in GitHub Actions secrets


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


# ====================== PARLAY BUILDER ======================
def get_best_prop(row):
    """Return the single strongest prop label + pct for a qualifier row."""
    options = [
        ("Over 0.5 Hits",        row["over_0.5_H"]),
        ("Over 1.5 Hits",        row["over_1.5_H"]),
        ("Over 0.5 Strikeouts",  row["over_0.5_K"]),
        ("Over 1.5 Strikeouts",  row["over_1.5_K"]),
        ("Over 1.5 H+R+RBI",     row["over_1.5_HRR"]),
    ]
    return max(options, key=lambda x: x[1])

def build_parlays(df, n_parlays=3):
    """
    Greedily pick up to n_parlays non-overlapping 3-leg parlays.
    Each player appears in at most one parlay.
    """
    players = df.to_dict("records")
    parlays = []
    used = set()

    for i in range(len(players)):
        if i in used:
            continue
        legs = [players[i]]
        used.add(i)
        for j in range(len(players)):
            if j in used:
                continue
            legs.append(players[j])
            used.add(j)
            if len(legs) == 3:
                break
        if len(legs) == 3:
            parlays.append(legs)
        if len(parlays) == n_parlays:
            break

    return parlays


# ====================== EMAIL ======================
def build_html_email(parlays, today_str):
    if not parlays:
        return f"""
        <html><body style="font-family:sans-serif;color:#222;max-width:600px;margin:auto;padding:24px;">
          <h2>MLB Prop Parlays — {today_str}</h2>
          <p>No qualifying prop bets found for today. Check back tomorrow!</p>
        </body></html>
        """

    parlay_html = ""
    for idx, legs in enumerate(parlays, 1):
        legs_html = ""
        for li, leg in enumerate(legs, 1):
            prop_label, prop_pct = get_best_prop(leg)
            legs_html += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;">
                <span style="font-size:11px;background:#e8f4fd;color:#1a6fa8;
                             padding:2px 8px;border-radius:999px;">Leg {li}</span>
              </td>
              <td style="padding:8px 12px;border-bottom:1px solid #f0f0f0;">
                <strong>{leg['player']}</strong><br>
                <span style="font-size:12px;color:#666;">{prop_label} &mdash; {prop_pct:.0f}% in last {leg['games_considered']} games</span>
              </td>
            </tr>
            """
        parlay_html += f"""
        <div style="margin-bottom:20px;border:1px solid #e5e5e5;border-radius:8px;overflow:hidden;">
          <div style="background:#f8f8f8;padding:10px 16px;font-size:13px;
                      font-weight:600;color:#555;letter-spacing:.04em;">
            PARLAY {idx}
          </div>
          <table style="width:100%;border-collapse:collapse;">
            {legs_html}
          </table>
        </div>
        """

    return f"""
    <html><body style="font-family:sans-serif;color:#222;max-width:600px;margin:auto;padding:24px;">
      <h2 style="margin-bottom:4px;">Today's 3-Leg Parlay Suggestions</h2>
      <p style="color:#888;font-size:13px;margin-bottom:24px;">{today_str} &mdash; based on last 10 games, &ge;80% threshold</p>
      {parlay_html}
      <p style="font-size:11px;color:#aaa;margin-top:24px;">
        Past performance does not guarantee future results. Bet responsibly.
      </p>
    </body></html>
    """

def send_email(subject, html_body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
    print(f"✅ Email sent to {RECIPIENT_EMAIL}")


# ====================== MAIN ======================
def compute_daily_k_props():
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"🚀 Computing daily prop hot lists for {today_str}...")

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
                hits        = int(stat.get("hits", 0))
                runs        = int(stat.get("runs", 0))
                rbi         = int(stat.get("rbi", 0))
                strikeouts  = int(stat.get("strikeOuts", 0))
                combined    = hits + runs + rbi
                records.append({"H": hits, "K": strikeouts, "HRR": combined})

            if not records:
                continue

            df   = pd.DataFrame(records)
            pdata = df.head(10).copy()
            n_games = len(pdata)
            if n_games < 5:
                continue

            over_05_h   = (pdata["H"]   > 0.5).sum() / n_games * 100
            over_15_h   = (pdata["H"]   > 1.5).sum() / n_games * 100
            over_05_k   = (pdata["K"]   > 0.5).sum() / n_games * 100
            over_15_k   = (pdata["K"]   > 1.5).sum() / n_games * 100
            over_15_hrr = (pdata["HRR"] > 1.5).sum() / n_games * 100

            if (over_05_h >= 80 or over_15_h >= 80 or
                over_05_k >= 80 or over_15_k >= 80 or
                over_15_hrr >= 80):

                results.append({
                    "player":           f"{full_name} ({team_abbrev})",
                    "over_0.5_H":       round(over_05_h,   1),
                    "over_1.5_H":       round(over_15_h,   1),
                    "over_0.5_K":       round(over_05_k,   1),
                    "over_1.5_K":       round(over_15_k,   1),
                    "over_1.5_HRR":     round(over_15_hrr, 1),
                    "games_considered": n_games,
                    "player_id":        player_id,
                })

    if not results:
        print("❌ No batters met the ≥80% threshold on any prop today.")
        parlays = []
    else:
        df_results = pd.DataFrame(results).sort_values(
            ["over_1.5_H", "over_1.5_K", "over_1.5_HRR"], ascending=False
        )
        print(f"\n=== TODAY'S PROP QUALIFIERS ===")
        print(f"Found {len(results)} qualifying batters")
        parlays = build_parlays(df_results)
        print(f"Built {len(parlays)} 3-leg parlay(s)")

        # Save JSON
        data = {
            "date": today_str,
            "generated_at": datetime.datetime.now().isoformat(),
            "total_qualifiers": len(results),
            "batters": df_results.to_dict("records"),
            "parlays": [
                [{"player": leg["player"], "prop": get_best_prop(leg)[0], "pct": get_best_prop(leg)[1]} for leg in p]
                for p in parlays
            ]
        }
        with open("daily_k_props.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # Send email regardless (even if empty)
    subject   = f"MLB Prop Parlays — {today_str}"
    html_body = build_html_email(parlays, today_str)
    send_email(subject, html_body)


if __name__ == "__main__":
    compute_daily_k_props()
