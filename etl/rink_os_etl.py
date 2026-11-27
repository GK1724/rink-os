"""
RINK-OS NHL Data Ingestion & Normalization Pipeline
---------------------------------------------------
Pulls official NHL standings, Toronto Maple Leafs (TOR) regular-season schedule,
play-by-play shot coordinates, and shift chart intervals into structured datasets.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

WEB_API_BASE = "https://api-web.nhle.com/v1"
STATS_API_BASE = "https://api.nhle.com/stats/rest/en"

TEAM_ABBREV = "TOR"
SEASON_ID = "20262027"
REGULAR_SEASON_GAME_TYPE = 2
SHOT_EVENT_KEYS = {"goal", "shot-on-goal", "missed-shot", "blocked-shot"}

OUTPUT_DIR = Path("./rink_os_data")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("rink_os_etl")


@dataclass
class ShotEvent:
    game_id: int
    game_date: str
    event_id: int
    period: int
    period_type: str
    time_in_period: str
    period_seconds: int
    situation_code: str
    strength_state: str
    event_type: str
    is_goal: bool
    is_fenwick: bool
    is_corsi: bool
    event_owner_team_id: int
    is_tor_event: bool
    shooter_id: int | None
    goalie_id: int | None
    shot_type: str | None
    raw_x: float | None
    raw_y: float | None
    norm_x: float | None
    norm_y: float | None
    shot_distance_ft: float | None
    shot_angle_deg: float | None
    tor_skaters_on_ice: list[int]
    opp_skaters_on_ice: list[int]


@dataclass
class ShiftRecord:
    game_id: int
    shift_id: int
    player_id: int
    player_name: str
    team_id: int
    team_abbrev: str
    period: int
    shift_number: int
    start_time: str
    end_time: str
    duration_str: str
    start_seconds: int
    end_seconds: int
    duration_seconds: int


def build_http_session(retries: int = 3, backoff_factor: float = 0.6) -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": "RINK-OS-Analytics-Pipeline/1.0",
            "Accept": "application/json",
        }
    )
    return session


def mmss_to_seconds(clock_str: str | None) -> int:
    if not clock_str or ":" not in clock_str:
        return 0
    try:
        mins, secs = clock_str.split(":", 1)
        return int(mins) * 60 + int(secs)
    except ValueError:
        return 0


def parse_situation_code(code: str | None, is_home_team: bool) -> str:
    if not code or len(code) != 4 or not code.isdigit():
        return "UNK"
    away_g, away_s, home_s, home_g = int(code[0]), int(code[1]), int(code[2]), int(code[3])
    team_s, opp_s = (home_s, away_s) if is_home_team else (away_s, home_s)
    team_g, opp_g = (home_g, away_g) if is_home_team else (away_g, home_g)

    if team_g == 0 or opp_g == 0:
        return "EN"
    if team_s == opp_s:
        return f"{team_s}v{opp_s}"
    return "PP" if team_s > opp_s else "SH"


def normalize_shot_coordinates(
    raw_x: float | None,
    raw_y: float | None,
    is_home_event: bool,
    home_defending_side: str | None,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Orient coordinates so every shot attacks toward +X (goal line at x = +89.0 ft)."""
    if raw_x is None or raw_y is None:
        return None, None, None, None

    norm_x, norm_y = float(raw_x), float(raw_y)

    if home_defending_side in {"left", "right"}:
        attacks_right = (home_defending_side == "left") if is_home_event else (home_defending_side == "right")
        if not attacks_right:
            norm_x = -norm_x
            norm_y = -norm_y
    else:
        if norm_x < 0:
            norm_x = -norm_x
            norm_y = -norm_y

    dx = 89.0 - norm_x
    dy = norm_y
    distance = round(math.hypot(dx, dy), 2)
    angle = round(math.degrees(math.atan2(abs(dy), max(dx, 0.01))), 2)
    return norm_x, norm_y, distance, angle


class RinkOSCollector:
    def __init__(self, team_abbrev: str = TEAM_ABBREV, season: str = SEASON_ID, request_delay: float = 0.25):
        self.team_abbrev = team_abbrev.upper()
        self.season = season
        self.request_delay = request_delay
        self.session = build_http_session()

    def _get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        time.sleep(self.request_delay)
        return resp.json()

    def fetch_standings(self) -> list[dict[str, Any]]:
        logger.info("Fetching live NHL standings...")
        data = self._get_json(f"{WEB_API_BASE}/standings/now")
        rows: list[dict[str, Any]] = []

        for entry in data.get("standings", []):
            abbrev = entry.get("teamAbbrev", {}).get("default")
            gp = entry.get("gamesPlayed", 0)
            pts = entry.get("points", 0)
            rows.append(
                {
                    "team_abbrev": abbrev,
                    "team_name": entry.get("teamName", {}).get("default"),
                    "conference": entry.get("conferenceName"),
                    "division": entry.get("divisionName"),
                    "division_seq": entry.get("divisionSequence"),
                    "league_seq": entry.get("leagueSequence"),
                    "gp": gp,
                    "wins": entry.get("wins", 0),
                    "losses": entry.get("losses", 0),
                    "ot_losses": entry.get("otLosses", 0),
                    "points": pts,
                    "pts_pct": round(entry.get("pointPctg", 0.0), 4),
                    "points_pace_82": round((pts / gp) * 82, 1) if gp else 0.0,
                    "goals_for": entry.get("goalFor", 0),
                    "goals_against": entry.get("goalAgainst", 0),
                    "goal_diff": entry.get("goalDifferential", 0),
                    "ga_per_game": round(entry.get("goalAgainst", 0) / gp, 2) if gp else 0.0,
                    "l10_record": f"{entry.get('l10Wins', 0)}-{entry.get('l10Losses', 0)}-{entry.get('l10OtLosses', 0)}",
                    "streak": f"{entry.get('streakCode', '')}{entry.get('streakCount', '')}",
                }
            )
        return rows

    def fetch_completed_games(self) -> list[dict[str, Any]]:
        logger.info("Fetching %s schedule for season %s...", self.team_abbrev, self.season)
        data = self._get_json(f"{WEB_API_BASE}/club-schedule-season/{self.team_abbrev}/{self.season}")
        completed = []
        for g in data.get("games", []):
            if g.get("gameType") == REGULAR_SEASON_GAME_TYPE and g.get("gameState") in {"OFF", "FINAL"}:
                completed.append(
                    {
                        "game_id": g["id"],
                        "game_date": g["gameDate"],
                        "home_team": g["homeTeam"]["abbrev"],
                        "away_team": g["awayTeam"]["abbrev"],
                        "home_score": g["homeTeam"].get("score", 0),
                        "away_score": g["awayTeam"].get("score", 0),
                    }
                )
        logger.info("Found %d completed regular-season games.", len(completed))
        return completed

    def fetch_game_shifts(self, game_id: int) -> list[ShiftRecord]:
        url = f"{STATS_API_BASE}/shiftcharts"
        data = self._get_json(url, params={"cayenneExp": f"gameId={game_id}"})
        shifts: list[ShiftRecord] = []

        for row in data.get("data", []):
            if row.get("detailCode", 0) != 0:
                continue

            start_sec = mmss_to_seconds(row.get("startTime"))
            end_sec = mmss_to_seconds(row.get("endTime"))
            dur_sec = mmss_to_seconds(row.get("duration")) or max(0, end_sec - start_sec)

            first = row.get("firstName", "")
            last = row.get("lastName", "")
            shifts.append(
                ShiftRecord(
                    game_id=game_id,
                    shift_id=row["id"],
                    player_id=row["playerId"],
                    player_name=f"{first} {last}".strip(),
                    team_id=row["teamId"],
                    team_abbrev=row.get("teamAbbrev", ""),
                    period=row.get("period", 1),
                    shift_number=row.get("shiftNumber", 0),
                    start_time=row.get("startTime", "00:00"),
                    end_time=row.get("endTime", "00:00"),
                    duration_str=row.get("duration", "00:00"),
                    start_seconds=start_sec,
                    end_seconds=end_sec,
                    duration_seconds=dur_sec,
                )
            )
        return shifts

    def fetch_game_shots(
        self,
        game_meta: dict[str, Any],
        shifts: list[ShiftRecord],
    ) -> tuple[list[ShotEvent], list[dict[str, Any]]]:
        game_id = game_meta["game_id"]
        pbp = self._get_json(f"{WEB_API_BASE}/gamecenter/{game_id}/play-by-play")

        home_team_id = pbp["homeTeam"]["id"]
        away_team_id = pbp["awayTeam"]["id"]
        is_tor_home = pbp["homeTeam"]["abbrev"] == self.team_abbrev
        tor_team_id = home_team_id if is_tor_home else away_team_id

        roster_spots = [
            {
                "player_id": p["playerId"],
                "team_id": p["teamId"],
                "sweater_number": p.get("sweaterNumber"),
                "first_name": p.get("firstName", {}).get("default"),
                "last_name": p.get("lastName", {}).get("default"),
                "position_code": p.get("positionCode"),
            }
            for p in pbp.get("rosterSpots", [])
        ]

        shifts_by_period: dict[int, list[ShiftRecord]] = {}
        for s in shifts:
            shifts_by_period.setdefault(s.period, []).append(s)

        shot_events: list[ShotEvent] = []
        for play in pbp.get("plays", []):
            event_type = play.get("typeDescKey", "")
            if event_type not in SHOT_EVENT_KEYS:
                continue

            details = play.get("details", {})
            owner_team_id = details.get("eventOwnerTeamId")
            if owner_team_id is None:
                continue

            period_desc = play.get("periodDescriptor", {})
            period = period_desc.get("number", 1)
            period_type = period_desc.get("periodType", "REG")
            time_in_period = play.get("timeInPeriod", "00:00")
            p_sec = mmss_to_seconds(time_in_period)

            is_home_event = owner_team_id == home_team_id
            sit_code = str(play.get("situationCode", ""))
            strength = parse_situation_code(sit_code, is_home_event)

            norm_x, norm_y, dist_ft, angle_deg = normalize_shot_coordinates(
                raw_x=details.get("xCoord"),
                raw_y=details.get("yCoord"),
                is_home_event=is_home_event,
                home_defending_side=play.get("homeTeamDefendingSide"),
            )

            tor_on_ice: list[int] = []
            opp_on_ice: list[int] = []
            for s in shifts_by_period.get(period, []):
                if s.start_seconds <= p_sec < s.end_seconds:
                    if s.team_id == tor_team_id:
                        tor_on_ice.append(s.player_id)
                    elif s.team_id in {home_team_id, away_team_id}:
                        opp_on_ice.append(s.player_id)

            shooter_id = details.get("scoringPlayerId") or details.get("shootingPlayerId")
            shot_events.append(
                ShotEvent(
                    game_id=game_id,
                    game_date=game_meta["game_date"],
                    event_id=play["eventId"],
                    period=period,
                    period_type=period_type,
                    time_in_period=time_in_period,
                    period_seconds=p_sec,
                    situation_code=sit_code,
                    strength_state=strength,
                    event_type=event_type,
                    is_goal=(event_type == "goal"),
                    is_fenwick=(event_type in {"goal", "shot-on-goal", "missed-shot"}),
                    is_corsi=True,
                    event_owner_team_id=owner_team_id,
                    is_tor_event=(owner_team_id == tor_team_id),
                    shooter_id=shooter_id,
                    goalie_id=details.get("goalieInNetId"),
                    shot_type=details.get("shotType"),
                    raw_x=details.get("xCoord"),
                    raw_y=details.get("yCoord"),
                    norm_x=norm_x,
                    norm_y=norm_y,
                    shot_distance_ft=dist_ft,
                    shot_angle_deg=angle_deg,
                    tor_skaters_on_ice=sorted(set(tor_on_ice)),
                    opp_skaters_on_ice=sorted(set(opp_on_ice)),
                )
            )

        return shot_events, roster_spots

    def run_pipeline(self, max_games: int | None = None, output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
        output_dir.mkdir(parents=True, exist_ok=True)

        standings = self.fetch_standings()
        games = self.fetch_completed_games()
        if max_games is not None:
            games = games[-max_games:]

        all_shots: list[dict[str, Any]] = []
        all_shifts: list[dict[str, Any]] = []
        roster_map: dict[int, dict[str, Any]] = {}

        for idx, game in enumerate(games, start=1):
            gid = game["game_id"]
            logger.info("[%d/%d] Ingesting game %s (%s vs %s)...", idx, len(games), gid, game["away_team"], game["home_team"])
            shifts = self.fetch_game_shifts(gid)
            shots, roster_spots = self.fetch_game_shots(game, shifts)

            all_shifts.extend(asdict(s) for s in shifts)
            all_shots.extend(asdict(e) for e in shots)
            for player in roster_spots:
                roster_map[player["player_id"]] = player

        df_standings = pd.DataFrame(standings)
        df_shots = pd.DataFrame(all_shots)
        df_shifts = pd.DataFrame(all_shifts)
        df_players = pd.DataFrame(list(roster_map.values()))

        df_standings.to_parquet(output_dir / "standings.parquet", index=False)
        df_shots.to_parquet(output_dir / "shot_events.parquet", index=False)
        df_shifts.to_parquet(output_dir / "shifts.parquet", index=False)
        df_players.to_parquet(output_dir / "players.parquet", index=False)

        tor_standing = next((r for r in standings if r["team_abbrev"] == self.team_abbrev), {})
        atlantic_standings = [r for r in standings if r.get("division") == "Atlantic"]

        rink_os_payload = {
            "meta": {
                "team": self.team_abbrev,
                "season": self.season,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "games_ingested": len(games),
                "total_shot_events": len(all_shots),
                "total_shift_records": len(all_shifts),
            },
            "club_snapshot": tor_standing,
            "atlantic_standings": atlantic_standings,
            "players": list(roster_map.values()),
            "shot_events": all_shots,
            "shifts": all_shifts,
        }

        json_path = output_dir / "rink_os_feed.json"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(rink_os_payload, f, indent=2)

        logger.info("Pipeline complete. Saved JSON payload to %s", json_path)
        return rink_os_payload


if __name__ == "__main__":
    collector = RinkOSCollector(team_abbrev="TOR", season="20262027", request_delay=0.25)
    collector.run_pipeline(max_games=None)