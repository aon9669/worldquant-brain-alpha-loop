# WorldQuant BRAIN alpha loop

An automated loop that designs WorldQuant BRAIN alphas with an LLM, checks them locally, then runs simulate, check and submit through the BRAIN API. Python code makes every submit decision; the LLM only writes candidate files.

> **No credentials are included in this repository.** BRAIN login details come only from environment variables (see `.env.example`). Run outputs, logs, state files, alpha results and account data are left out on purpose (see `.gitignore`).

## How it runs (MacBook Air M1)

- **launchd** keeps the supervisor alive: `com.aon.wqloop` runs `caffeinate -is bash wq_loop/loop.sh` (templates are in `launchd/`).
- `wq_loop/loop.sh` loads `${WQ_ENV_FILE:-~/.wq_env}`, refuses to start without `WQB_EMAIL`/`WQB_PASSWORD`, then runs `wq_loop/engine.py` about every 5 minutes. It waits 30 min after a usage-limit exit (code 30) and 30 s after exit code 75.
- `wq_loop/engine.py` runs one cycle: build context, generate candidates, run a local syntax/operator precheck (`wq_harness/precheck.py`, `wq_loop/research.py precheck`), then simulate, check and submit through `tool/worldquant_brain_cli.py`, and log the results.

## LLM generation via `llm-queue`

- `llm-queue/` is a small file-based job queue (`dispatcher.py` runs as launchd `com.aon.llmqueue`, and `q` is the CLI). It runs at most 2 jobs at a time.
- **Primary:** Antigravity (`agy`) with model **`gemini-3.8-flash-high`**. Effort is part of the model id, so the loop doesn't use `--effort` or `--mode plan`.
- **Fallback:** if the agy job fails, times out (840 s) or writes no valid candidates, that cycle uses **`claude-sonnet-5-5`** (`claude -p`). An agy quota or limit error pauses agy for 30 minutes.
- **Revert switch:** `export WQ_LLM_BACKEND=claude` (for example in `loop.sh`) uses Sonnet only. `WQ_LLM_QUEUE=0` skips the queue and calls Claude directly.
- The generation process is defined by `llm-alpha-generation-guide.md` (Silver-to-Gold spec), with `silver-to-gold-generation-skill.md` alongside it. The prompt tells the model to read the guide end to end.

### agy permission allowlist (`AGY_SETTINGS` in `engine.py`)

- allow: `command(python3 wq_loop/research.py)`, `read_file(<repo>/)`, `write_file(<repo>/wq_loop/cycles/)`
- deny: writes to `.git/`, `wq_loop/engine.py`, `wq_loop/loop.sh`, `wq_loop/test_engine.py` and `venv/`; reading the credentials file (`~/.wq_env`) and `~/antigravity-work/`; and `mcp(*)`, `read_url(*)`, `execute_url(*)`
- Claude, the fallback, gets only `Read, Write, Edit, Bash(python3 wq_loop/research.py *)`. The BRAIN credentials and `ANTHROPIC_API_KEY` are removed from the LLM's environment.

## BRAIN API flow

1. **Simulate** each prechecked candidate one at a time. Rate or concurrency rejections back off exponentially, and a POST that timed out is never blindly repeated.
2. **Check** the alpha's official BRAIN checks. All of them must PASS, along with metric gates such as Sharpe, fitness, turnover and self-correlation.
3. **Submit** only when everything passes, and read the alpha back before and after.
4. **Daily limit:** if BRAIN reports the daily submission limit, submissions pause until **09:00 Asia/Bangkok the next day** (`paused_until` in `submit_state.json`) while generation and simulation continue.

## Setup

```bash
git clone https://github.com/aon9669/worldquant-brain-alpha-loop.git
cd worldquant-brain-alpha-loop
python3 -m venv venv && venv/bin/pip install -r tool/requirements.txt
cp .env.example ~/.wq_env && chmod 600 ~/.wq_env   # then fill in WQB_EMAIL / WQB_PASSWORD
# LLM CLIs: install and sign in to `agy` (Antigravity) and `claude` (Claude Code) yourself
cp -r llm-queue ~/llm-queue                          # or set LLMQ_HOME
# launchd: fill in the placeholders and load the agents
sed -e "s#__REPO_DIR__#$PWD#g" -e "s#__HOME__#$HOME#g" -e "s#__PYTHON3__#$(command -v python3)#g" \
    launchd/com.aon.wqloop.plist.template > ~/Library/LaunchAgents/com.aon.wqloop.plist
sed -e "s#__REPO_DIR__/llm-queue#$HOME/llm-queue#g" -e "s#__REPO_DIR__#$PWD#g" -e "s#__HOME__#$HOME#g" -e "s#__PYTHON3__#$(command -v python3)#g" \
    launchd/com.aon.llmqueue.plist.template > ~/Library/LaunchAgents/com.aon.llmqueue.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.aon.llmqueue.plist
bash wq_loop/start.sh
```

Run only **one** copy of the loop at a time, on one machine.

Tests: `python3 wq_loop/test_engine.py`

## Layout

- `wq_loop/`: engine, supervisor, research helper, tests and `catalog.json` (BRAIN data-field metadata, with no account data)
- `wq_harness/`: `operators.json`, `fields_cache/`, `precheck.py` and simulation helper scripts
- `tool/`: BRAIN API CLI and research agent, vendored from [zeron-G/worldquant-alpha-research-agent](https://github.com/zeron-G/worldquant-alpha-research-agent) (MIT, see `tool/LICENSE`)
- `llm-queue/`: the queue dispatcher, the `q` CLI and its README
- `launchd/`: plist templates
- `diagrams/`: platform and operation diagrams
- Root `*.py`: early candidate-generation and proxy-backtest experiments

Not included: submitted alpha expressions and results, the alpha memory (`wq_harness/memory.jsonl`), run logs and cycle outputs. Add them yourself if you want them versioned.
