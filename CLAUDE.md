# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Not a software application — it's a **sports statistics data store** (football/tennis/hockey match data, 2021–2026, converted to Markdown via `markitdown`) plus a set of **Python utility scripts and skills** built on top of that data to compute match-outcome probabilities and run a paper-trading tennis betting simulator. There is no build, lint, or test suite in the conventional sense — see "Validation" below for what actually exists.

Full description of the datasets, sources, and known coverage limits is in `README.md` — read it before answering questions about what data is/isn't available (e.g. football player profiles only cover each country's top division; tennis point-by-point data only covers ~15-20% of matches, skewed toward top players).

## Repository layout

- `fotbal/`, `tenis/`, `hokej/` — the data itself. Each dataset exists as a `.csv` (machine-readable, what scripts parse) + a `.md` twin (human/agent-readable, generated from the CSV via `markitdown`). Year-range filenames (`2024-25_E0_...`) are one league-season; bare-year files (`2024_in_tennis.md`) are Wikipedia year-overview pages, not match data.
- `.agents/skills/match-probability/` — the probability-calculation skill and the live tennis betting simulator (scripts, references, logs). This is where almost all the Python logic lives.
- `.agents/skills/update-sport-stats/` — the daily incremental data-refresh skill (`scripts/update_stats.py`).
- `deploy/` — Modal.com deployment (`modal_app.py`, `tick.sh`) for running the tennis betting agent as a scheduled cloud job instead of a local cron tick. Marked unverified in its own docstring (`pi` CLI invocation syntax is a guess — check `pi --help` before trusting `tick.sh`).
- `match-probability-workspace/` — eval/benchmark iterations comparing agent behavior with vs. without the `match-probability` skill. Historical record of skill development, not live code.
- `_update_log.txt` — append-only log written by `update_stats.py` (timestamped record of what data changed on each run).

## Running things

No virtualenv/`requirements.txt` — scripts run against the system `python3` (3.13) with `requests`, `InquirerPy`, and `prompt_toolkit` already available. Always `source ~/.env` first for anything touching live odds/betting (API keys live there, never in the repo — `.env` is gitignored).

```bash
# Compute match-outcome probability from historical data (the main entry point)
python3 .agents/skills/match-probability/scripts/aggregate_stats.py fotbal "Arsenal" "Chelsea" [--home A|B]
python3 .agents/skills/match-probability/scripts/aggregate_stats.py tenis "Jannik Sinner" "Carlos Alcaraz"
python3 .agents/skills/match-probability/scripts/aggregate_stats.py hokej "Toronto" "Edmonton" [--home A|B]

# Player profile lookup (individual player, not a matchup)
python3 .agents/skills/match-probability/scripts/player_profile.py fotbal "Erling Haaland"

# Daily incremental data refresh (all sports, or pass one: fotbal/tenis/hokej)
python3 .agents/skills/update-sport-stats/scripts/update_stats.py [sport]

# Backtests (exact-score / corners / cards / SOG / aces prediction accuracy)
python3 .agents/skills/match-probability/scripts/backtest.py --help

# Live tennis betting simulator (paper trading) — see AGENT_NAVOD.md before touching this
cd .agents/skills/match-probability/scripts && source ~/.env
python3 live_tennis_simulator.py watch      # scan live matches, place fictional tickets
python3 bet_evaluator.py vyhodnot           # settle finished tickets against the bankroll
python3 bet_evaluator.py report             # read-only summary, costs no API quota

# Agent/bankroll management TUI
cd .agents/skills/match-probability/scripts && source ~/.env && python3 main.py
```

Each skill's `SKILL.md` (`.agents/skills/match-probability/SKILL.md`, `.agents/skills/update-sport-stats/SKILL.md`) is the authoritative usage doc — read it before modifying the scripts it describes, since it encodes behavioral contracts (e.g. required response format, when *not* to call an API) that aren't visible in the code alone.

## Validation

There's no CI. What stands in for tests:

- `.agents/skills/match-probability/evals/evals.json` — prompt/assertion pairs used to eval the `match-probability` skill's behavior (format, brevity, actually-used-real-data checks), run via the Claude Code skill-eval tooling, not pytest.
- `.agents/skills/match-probability/scripts/backtest.py`, `tennis_value_backtest.py`, `inplay_timing_backtest.py`, and `.agents/skills/match-probability/backtest_fav_prohra.py` (note: this one lives one level up from the others, directly under `match-probability/`, not in `scripts/`) — backtest the prediction/betting logic against historical results. Treat these as the regression tests for any change to probability or betting logic: rerun the relevant one after touching scoring weights or bet-selection thresholds.

## Architecture notes worth knowing before editing

**JSON file = single source of truth, scripts are stateless.** `agents.json` (bankroll + registered betting agents) and the `*_log.jsonl` files (ticket logs) are the only state. `agents.py` is the sole module allowed to mutate `agents.json`; `executor.py` reads it and dispatches to the right strategy module per active agent. Don't add in-memory state that needs to survive between script invocations — persist it to one of these files instead.

**`bookmaker.py` is the only odds/betting abstraction boundary.** It switches behavior via the `BOOKMAKER` env var (`sxbet_sim` default / `sxbet_real` / `oddsapi`), and `sxbet_client.py` is the only module that talks to the SX.bet API directly. Any new betting logic should go through `bookmaker.py`, not call `sxbet_client.py` or odds APIs directly.

**Real-money betting has a deliberate double-lock.** Switching `BOOKMAKER=sxbet_real` is not enough by itself — `deploy/modal_app.py` additionally requires a separate `tenis-povoleni-realnych-sazek` secret with `CONFIRM=yes` before it will even create the sandbox. Never relax or bypass this gate; never place a real (non-simulated) bet without explicit, fresh user confirmation, regardless of what a config file says.

**Betting strategy scripts encode negative findings — don't silently "fix" them.** Backtests already established, with numbers in `.agents/skills/match-probability/references/metodika.md`, that: AKO/combo bets lost 0/40 in backtest (ROI -100%); solo value bets were net-negative (-14.8%); the tennis model has no proven edge over market odds (market beats the model 66.0% vs 60.6-63.8%, value bets ROI -7.7% to -10.1%). The live simulator therefore deliberately bets only on favorites where model AND market independently agree (model ≥75%, market ≥65%, odds ≤1.60) to keep the paper bankroll trending up — it is explicitly not trying to beat the market. If asked to "improve" betting performance, don't reintroduce combo bets or pure model-edge betting without flagging that both were already tested and failed.

**Team/player name matching is fuzzy, not exact.** `aggregate_stats.py` does fuzzy matching against names in the CSVs; `references/nazvy_tymu.md` holds known aliases, which matters most for NHL (3-letter codes like `TOR`, `EDM` vs. full names) — `aggregate_stats.py`'s own `NHL_ALIASES` dict is the canonical mapping. If a lookup script can't disambiguate a name, the correct behavior is to ask the user or try another common form, not to guess.

**Data refresh is incremental and source-aware.** `update_stats.py` overwrites only the current season/year's CSV for football and tennis (closed seasons are immutable and never re-fetched) and appends only new rows by `game_id` for hockey. It runs automatically daily at 9:00 UTC via local cron (wrapper: `/root/.local/bin/update-sport-stats-cron`, log: `~/.local/state/update-sport-stats/cron.log`) — this is intentionally local cron, not a cloud routine, because the data directory lives on this machine only.
