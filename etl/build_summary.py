"""
RINK-OS Dashboard Summary Builder
---------------------------------
Builds rink_os_data/rink_os_summary.json — the compact feed the GitHub Pages
dashboard loads at runtime. Contains only official, verifiable team facts
pulled live from the NHL APIs (standings + team summary reports):

  * record, points, points %, pace, division place, L10, streak
  * goals for / against, GA per game, league GA rank
  * power play % and penalty kill %

Model outputs (xG, GSAx, chemistry) are intentionally NOT included here;
they belong to rink_os_metrics.json.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

WEB_API_BASE = "https://api-web.nhle.com/v1"
STATS_API_BASE = "https://api.nhle.com/stats/rest/en"
TEAM_ABBREV = "TOR"
TEAM_ID = 10
SEASON_ID = "20262027"
OUTPUT_PATH = Path("./rink_os_data/rink_os_summary.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rink_os_summary")


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def get_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_summary() -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "RINK-OS summary builder"})

    standings = get_json(session, f"{WEB_API_BASE}/standings/now").get("standings", [])
    tor = next(s for s in standings if s.get("teamAbbrev", {}).get("default") == TEAM_ABBREV)

    gp = tor.get("gamesPlayed", 0)
    ga = tor.get("goalAgainst", 0)
    ga_rank = 1 + sum(1 for s in standings if s.get("goalAgainst", 0) < ga)

    summary_report = get_json(
        session,
        f"{STATS_API_BASE}/team/summary",
        params={"limit": -1, "cayenneExp": f"seasonId={SEASON_ID} and gameTypeId=2"},
    ).get("data", [])
    tor_stats = next(t for t in summary_report if t.get("teamId") == TEAM_ID)

    pts_pct = tor.get("pointPctg", 0.0)
    div_seq = tor.get("divisionSequence", 0)

    return {
        "meta": {
            "team": TEAM_ABBREV,
            "season": SEASON_ID,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "NHL standings/now + stats team summary",
        },
        "gp": gp,
        "wins": tor.get("wins", 0),
        "losses": tor.get("losses", 0),
        "ot_losses": tor.get("otLosses", 0),
        "record": f"{tor.get('wins', 0)}-{tor.get('losses', 0)}-{tor.get('otLosses', 0)}",
        "points": tor.get("points", 0),
        "pts_pct": round(pts_pct, 4),
        "pts_pct_display": f".{round(pts_pct * 1000):03d}",
        "points_pace_82": round((tor.get("points", 0) / gp) * 82, 1) if gp else 0.0,
        "games_remaining": 82 - gp,
        "division": tor.get("divisionName"),
        "division_seq": div_seq,
        "division_ordinal": ordinal(div_seq),
        "goals_for": tor.get("goalFor", 0),
        "goals_against": ga,
        "ga_per_game": round(ga / gp, 2) if gp else 0.0,
        "ga_rank_nhl": ga_rank,
        "ga_rank_ordinal": ordinal(ga_rank),
        "l10_record": f"{tor.get('l10Wins', 0)}-{tor.get('l10Losses', 0)}-{tor.get('l10OtLosses', 0)}",
        "streak": f"{tor.get('streakCode', '')}{tor.get('streakCount', '')}",
        "pp_pct": round(100 * (tor_stats.get("powerPlayPct") or 0), 2),
        "pk_pct": round(100 * (tor_stats.get("penaltyKillPct") or 0), 2),
    }


def main() -> None:
    summary = build_summary()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    logger.info("Saved dashboard summary to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
