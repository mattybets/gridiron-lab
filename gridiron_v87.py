"""Gridiron Lab v8.7: conservative pre-kickoff player eligibility and lineup validation.
No live availability feed is assumed. Integrate only with verified slate data.
"""
INACTIVE = {"out", "inactive", "ir", "doubtful"}
def eligible(player, confirmed_active=None, opportunity=None):
    status = str(player.get("status", "unknown")).lower()
    if status in INACTIVE:
        return False, "inactive"
    if confirmed_active is None or player.get("key") not in confirmed_active:
        return False, "availability not verified"
    if opportunity is None or opportunity.get(player.get("key"), 0) <= 0:
        return False, "opportunity not verified"
    return True, "eligible"

def validate_showdown(lineup, players, confirmed_active, opportunity, cap=50000):
    roster = lineup.get("players", [])
    if len(roster) != 6 or sum(p.get("slot") == "CPT" for p in roster) != 1:
        return False, "invalid showdown slots"
    if len({p.get("key") for p in roster}) != 6:
        return False, "duplicate player"
    if len({p.get("team") for p in roster}) < 2:
        return False, "both teams required"
    by_key = {p["key"]: p for p in players}
    if any(p.get("key") not in by_key for p in roster):
        return False, "unknown player"
    cost = sum(by_key[p["key"]]["salary"] * (1.5 if p["slot"] == "CPT" else 1) for p in roster)
    if cost > cap:
        return False, "over salary cap"
    for p in roster:
        ok, reason = eligible(by_key[p["key"]], confirmed_active, opportunity)
        if not ok:
            return False, p["name"] + ": " + reason
    return True, "verified"
