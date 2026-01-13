# Balatro AI (built-in bot)

This repo includes a playable bot in `src/balatro_ai/` that connects to the BalatroBot JSON-RPC API and makes decisions for the full game loop (blinds, hands, shop, packs).

It is **not a neural network**. "Training" here means **tuning parameters** (reserve thresholds, rerolls, rollout depth, etc.) by running many seeded games and picking the best-performing configuration.

## Quickstart

1. Start BalatroBot (Terminal 1):

```bash
uvx balatrobot --fast --headless
```

2. Run the AI bot (Terminal 2):

```bash
uv run python -m balatro_ai.bot --deck RED --stake WHITE --seed TEST-0001 --auto-start --no-pause-at-menu
```

## One-command learning (easiest)

This starts BalatroBot if needed, generates seed sets, runs a learning session (default: ASHA), and writes results to `logs/learn/.../best.json`:

```bash
uv run python -m balatro_ai.learn --deck RED --stake WHITE
```

By default, `learn` runs in `--auto` mode:

- Applies a sensible preset (`--profile balanced`) unless you override flags explicitly
- Automatically warm-starts from the most recent `logs/learn/.../best.json` for that deck/stake when available

Use a different preset:

```bash
uv run python -m balatro_ai.learn --deck RED --stake WHITE --profile fast
uv run python -m balatro_ai.learn --deck RED --stake WHITE --profile strong
```

Run multiple back-to-back learning runs (autopilot), chaining the previous `best.json` as the next baseline:

```bash
uv run python -m balatro_ai.learn --deck RED --stake WHITE --runs 5
```

### Learning with unwinnable seeds (more robust)

Some seed sets include a few runs that are effectively unwinnable. You can make tuning focus on overall performance by using a robust objective:

```bash
# Ignore the worst 10% of seeds when comparing configs
uv run python -m balatro_ai.learn --deck RED --stake WHITE --objective trimmed_mean_score --trim-bottom-pct 0.1
```

### Continue learning (warm start)

You can warm-start learning from a previous `best.json`:

```bash
uv run python -m balatro_ai.learn --deck RED --stake WHITE --baseline-json logs/learn/<run>/best.json
```

### Learn across many decks/stakes (matrix)

If you want separate tuned parameters per deck/stake (recommended as stakes get harder), run:

```bash
# Runs sequentially (single-instance friendly). Skips locked decks/stakes by default.
uv run python -m balatro_ai.learn --matrix --all-decks --all-stakes
```

Results are written under a single run directory like `logs/learn/matrix-.../`, with one `best.json` per combo plus a `index.json` summary.

## Run the bot

Common flags:

- `--host/--port`: where BalatroBot is running (default `127.0.0.1:12346`)
- `--deck/--stake/--seed`: run configuration
- `--decision-log logs/run.jsonl`: write decisions/results/errors as JSONL
- `--hand-rollout/--shop-rollout/--pack-rollout`: enable save/load lookahead (slower, often stronger)
- `--determinism-check`: auto-disables rollouts if save/load looks unsafe
- `--intent-trials`: intent evaluation quality vs speed (higher = stronger, slower)
- `--params-auto/--no-params-auto`: auto-load latest `logs/learn/.../best.json` for `--deck/--stake` (default: enabled)
- `--params-auto-root`: where to search for learned `best.json` (default: `logs/learn`)
- `--params-json`: explicitly load tuned parameters from a specific `best.json` produced by `learn`/`autotune`

## Benchmark the bot (generate data)

Run many fixed seeds and save results:

```bash
uv run python -m balatro_ai.benchmark --deck RED --stake WHITE --count 50 --seed-prefix BENCH --out logs/bench.json --decision-log logs/bench.jsonl
```

## View decision logs

Summary stats:

```bash
uv run python -m balatro_ai.replay_viewer --log logs/bench.jsonl --stats
```

Filter for shop decisions:

```bash
uv run python -m balatro_ai.replay_viewer --log logs/bench.jsonl --event decision --state SHOP
```

## Tune (random search)

```bash
uv run python -m balatro_ai.tune --deck RED --stake WHITE --count 50 --seed-prefix TUNE --trials 200 --out logs/tune.json
```

## Autotune (hands-free improvement loop)

```bash
uv run python -m balatro_ai.autotune --deck RED --stake WHITE --train-count 20 --eval-count 10 --generations 3 --trials 10 --out logs/autotune/best.json
```

Open `logs/autotune/best.json` and use `best.bot_flags` to run the bot with the best-found parameters.

## Continuous "best" runner

If you run `autotune` in one terminal, you can run a second process that continuously plays new seeds using the latest best parameters:

```bash
uv run python -m balatro_ai.supervise --best logs/autotune/best.json --seed-prefix PLAY --out logs/autotune/play.jsonl
```

## Testing

Unit tests (no Balatro install required):

```bash
uv run pytest -m "not integration"
```

Integration tests (starts Balatro instances and requires a working game install):

```bash
uv run pytest -m integration
```
