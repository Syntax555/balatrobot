# Balatro AI (built-in bot)

This repo includes a playable bot in `src/balatro_ai/` that connects to the BalatroBot JSON-RPC API and makes decisions for the full game loop (blinds, hands, shop, packs).

It is **not a neural network**. “Training” here means **tuning parameters** (reserve thresholds, rerolls, rollout depth, etc.) by running many seeded games and picking the best-performing configuration.

## Prerequisites

1. Install and run BalatroBot (this repo’s main CLI).
1. Start Balatro with the API server running (recommended for automation):

```bash
uvx balatrobot --fast --headless
```

Verify the API:

```bash
curl -X POST http://127.0.0.1:12346 ^
  -H "Content-Type: application/json" ^
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"health\",\"id\":1}"
```

## Run the bot

Recommended invocation:

```bash
uv run python -m balatro_ai.bot --deck RED --stake WHITE --seed TEST-0001 --auto-start --no-pause-at-menu
```

Common flags:

- `--host/--port`: where BalatroBot is running (default `127.0.0.1:12346`)
- `--deck/--stake/--seed`: run configuration
- `--max-steps`: safety cap (default `1000`)
- `--decision-log logs/run.jsonl`: write decisions/results/errors as JSONL
- `--hand-rollout/--shop-rollout/--pack-rollout`: enable save/load lookahead (slower, often stronger)
- `--determinism-check`: auto-disables rollouts if save/load looks unsafe
- `--intent-trials`: intent evaluation quality vs speed (higher = stronger, slower)

## Benchmark the bot (generate “data”)

Run many fixed seeds and save results:

```bash
uv run python -m balatro_ai.benchmark --deck RED --stake WHITE --count 50 --seed-prefix BENCH --out logs/bench.json --decision-log logs/bench.jsonl
```

The `--decision-log` JSONL is useful for debugging why choices were made.

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

This tries many bot parameter settings against a seed set and returns the best.

```bash
uv run python -m balatro_ai.tune --deck RED --stake WHITE --count 50 --seed-prefix TUNE --trials 200 --out logs/tune.json
```

Then run the bot using the best params (copy values from `logs/tune.json`):

```bash
uv run python -m balatro_ai.bot --deck RED --stake WHITE --seed YOURSEED --auto-start --no-pause-at-menu ^
  --reserve-early 10 --reserve-mid 20 --reserve-late 25 --max-rerolls-per-shop 1 --rollout-k 30 --discard-m 12
```

## Autotune (hands-free improvement loop)

`balatro_ai.autotune` repeatedly:

1. Generates a train seed set (and optional eval seed set)
1. Samples/mutates parameters
1. Runs all train seeds
1. Keeps the best and writes it to disk (including ready-to-copy `bot_flags`)

Example (fast sanity run):

```bash
uv run python -m balatro_ai.autotune --deck RED --stake WHITE --train-count 20 --eval-count 10 --generations 3 --trials 10 --out logs/autotune/best.json
```

Open `logs/autotune/best.json` and use `best.bot_flags` to run the bot with the best-found parameters.

## Continuous “best” runner

If you run `autotune` in one terminal, you can run a second process that continuously plays new seeds using the latest best parameters:

```bash
uv run python -m balatro_ai.supervise --best logs/autotune/best.json --seed-prefix PLAY --out logs/autotune/play.jsonl
```

This will keep reloading `best.json` and apply improvements automatically as the tuner finds better configs.

## Testing

Unit tests (no Balatro install required):

```bash
uv run pytest -m "not integration"
```

Integration tests (starts Balatro instances and requires a working game install):

```bash
uv run pytest -m integration
```
