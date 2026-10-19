"""Validate a sourced DraftKings Showdown salary slate before publication.

Usage: python validate_slate.py data/slates/<game_id>.json
This tool does NOT obtain salary data or certify its source.
"""
import datetime as dt
import json
import pathlib
import sys

POSITIONS = {"QB", "RB", "WR", "TE", "K", "DST"}
ALLOWED_STATUSES = {"available", "questionable", "out", "unknown"}

def validate(path):
    doc = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    errors = []
    def fail(msg):
        errors.append(msg)
    if not isinstance(doc, dict):
        raise ValueError("Slate must be a JSON object")
    game_id = str(doc.get("game_id", ""))
    if not game_id or pathlib.Path(path).stem != game_id:
        fail("game_id must match the JSON filename")
    if doc.get("source_type") != "authorized_draftkings_salaries":
        fail("source_type must identify authorized DraftKings salary data")
    if not str(doc.get("source_url", "")).startswith("https://"):
        fail("source_url must document an HTTPS source")
    for key in ("updated_utc", "availability_verified_utc"):
        value = doc.get(key)
        if not isinstance(value, str):
            fail(key + " must be a UTC timestamp")
            continue
        try:
            stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.utcoffset() != dt.timedelta(0):
                fail(key + " must be UTC")
        except ValueError:
            fail(key + " is not a valid ISO timestamp")
    players = doc.get("players")
    if not isinstance(players, list) or len(players) < 6:
        fail("players must contain at least six entries")
        players = []
    seen = set()
    teams = set()
    for i, p in enumerate(players):
        if not isinstance(p, dict):
            fail(f"players[{i}] must be an object")
            continue
        name, team, pos = p.get("name"), p.get("team"), p.get("position")
        if not all(isinstance(v, str) and v.strip() for v in (name, team, pos)):
            fail(f"players[{i}] missing name/team/position")
            continue
        if pos not in POSITIONS:
            fail(f"{name}: invalid position")
        if not isinstance(p.get("salary"), int) or isinstance(p.get("salary"), bool) or p["salary"] <= 0:
            fail(f"{name}: salary must be a positive integer (FLEX/base salary)")
        if p.get("status") not in ALLOWED_STATUSES:
            fail(f"{name}: invalid status")
        for field in ("projection", "ceiling"):
            v = p.get(field)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v < 200:
                fail(f"{name}: invalid {field}")
        if isinstance(p.get("projection"), (int, float)) and isinstance(p.get("ceiling"), (int, float)) and p["ceiling"] < p["projection"]:
            fail(f"{name}: ceiling below projection")
        key = (name.casefold().strip(), team.upper().strip())
        if key in seen:
            fail(f"{name}: duplicate player")
        seen.add(key)
        teams.add(team.upper().strip())
    if len(teams) != 2:
        fail("Showdown slate must contain exactly two teams")
    return errors

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python validate_slate.py data/slates/<game_id>.json")
        sys.exit(2)
    try:
        issues = validate(sys.argv[1])
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        issues = [str(exc)]
    if issues:
        for issue in issues:
            print("ERROR:", issue)
        sys.exit(1)
    print("PASS: slate schema and basic salary fields validated; provenance and live accuracy still require independent verification.")
