"""Summarize user-reported DFS results without fitting weights to hindsight.

Run: python evaluate_contests.py
This is a descriptive baseline, NOT a profitability or out-of-sample test.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "historical_contests.json"

def summarize(data):
    contests = data["contests"]
    if not contests:
        raise ValueError("No contests available")
    known_winners = [c for c in contests if c.get("winner_points") is not None]
    known_payouts = [c for c in contests if c.get("payout_usd") is not None]
    complete_roi = [c for c in contests if c.get("entry_fee_usd") is not None and c.get("payout_usd") is not None]
    print(f"Recorded contests: {len(contests)}")
    print(f"Mean reported lineup score: {sum(c['lineup_points'] for c in contests)/len(contests):.2f}")
    if known_winners:
        gaps = [c["winner_points"] - c["lineup_points"] for c in known_winners]
        print(f"Mean gap to reported winning score ({len(gaps)} contests): {sum(gaps)/len(gaps):.2f}")
    print(f"Known payouts: {len(known_payouts)} of {len(contests)}; missing values are NOT treated as $0")
    if complete_roi:
        paid = sum(c["payout_usd"] for c in complete_roi)
        cost = sum(c["entry_fee_usd"] for c in complete_roi)
        print(f"ROI on {len(complete_roi)} contests with both fees and payouts: {(paid-cost)/cost*100:.1f}%" if cost else "ROI unavailable: zero recorded fees")
    else:
        print("ROI unavailable: no contests with both fee and payout")
    print("Caution: no saved pre-kickoff predictions or full opponent field. Do not tune or claim improved predictive accuracy from these scores alone.")

if __name__ == "__main__":
    summarize(json.loads(DATA.read_text(encoding="utf-8")))
