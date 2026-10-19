# Gridiron Lab V8.2 — Automation starter

**What works:** A GitHub Actions workflow can refresh the NFL schedule and historical player PPR baselines every six hours, committing them to the repository. The UI includes **Load game automatically**, which fetches a verified, current matchup slate if available. No user uploads are required to use that button.

**Critical limitation:** No automatic DraftKings salary, official inactive, or ownership provider is connected. Consequently the one-tap button **fails closed** instead of making up salaries, declaring unknown players active, or recommending an unverified lineup. This is an infrastructure milestone, **not** a working fully automatic lineup product. The old manual import workflow remains available for research.

**Next integration:** obtain authorized DK salary/contest feed and a timestamped verified inactive feed. Publish one `data/slates/<game_id>.json` per matchup with `source_type=authorized_draftkings_salaries`, `game_id`, `updated_utc`, `availability_verified_utc`, and `players` array with `name,team,position,salary,status,projection,ceiling`. Game ID must match the published schedule ID. These values must come from legitimate verified sources, never fabricated. Avoid committing paid credentials.

**Deployment:** Add the files to a *separate branch* for testing. If using GitHub Pages branch deployment, publishing updates requires a Pages configuration pointed to the branch; if using Actions deployment, ensure a deployment workflow publishes generated files. Workflow commits require repository Actions write permissions. Scheduled runs may be delayed.

**No claim of validated profitability.** Historical baselines do not imply reliable projections, and ownership, role correlations and out-of-sample validation are not yet solved.
