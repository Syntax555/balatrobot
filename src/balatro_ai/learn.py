from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from balatro_ai.asha_tune import main as asha_tune_main
from balatro_ai.autotune import main as autotune_main
from balatro_ai.logging_utils import configure_logging
from balatro_ai.rpc import BalatroRPC, BalatroRPCError


@dataclass(frozen=True)
class _ServerProcess:
    process: subprocess.Popen
    base_url: str


_VALID_STAKES: tuple[str, ...] = (
    "WHITE",
    "RED",
    "GREEN",
    "BLACK",
    "BLUE",
    "PURPLE",
    "ORANGE",
    "GOLD",
)

_VALID_DECKS: tuple[str, ...] = (
    "RED",
    "BLUE",
    "YELLOW",
    "GREEN",
    "BLACK",
    "MAGIC",
    "NEBULA",
    "GHOST",
    "ABANDONED",
    "CHECKERED",
    "ZODIAC",
    "PAINTED",
    "ANAGLYPH",
    "PLASMA",
    "ERRATIC",
)

_AUTO_PROFILES: dict[str, dict[str, Any]] = {
    # "Hands-free" presets for typical users. Advanced users can override any knob explicitly.
    "fast": {
        "strategy": "asha",
        "train_count": 30,
        "eval_count": 10,
        "asha_candidates": 30,
        "asha_rungs": 3,
        "asha_min_seeds": 6,
        "asha_max_seeds": 0,
        "objective": "trimmed_mean_score",
        "trim_bottom_pct": 0.1,
        "mutations": 10,
    },
    "balanced": {
        "strategy": "asha",
        "train_count": 60,
        "eval_count": 20,
        "asha_candidates": 50,
        "asha_rungs": 4,
        "asha_min_seeds": 8,
        "asha_max_seeds": 0,
        "objective": "trimmed_mean_score",
        "trim_bottom_pct": 0.1,
        "mutations": 15,
    },
    "strong": {
        "strategy": "asha",
        "train_count": 120,
        "eval_count": 40,
        "asha_candidates": 80,
        "asha_rungs": 5,
        "asha_min_seeds": 10,
        "asha_max_seeds": 0,
        "objective": "trimmed_mean_score",
        "trim_bottom_pct": 0.1,
        "mutations": 25,
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "One-command workflow: ensure BalatroBot is running, generate seed sets, "
            "run learning, and write outputs to a fresh run directory."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=12346)
    parser.add_argument("--deck", default="RED")
    parser.add_argument("--stake", default="WHITE")
    parser.add_argument("--log-level", default="INFO")

    parser.add_argument(
        "--start-server",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If enabled, start `uvx balatrobot` automatically when not already running.",
    )
    parser.add_argument(
        "--server-fast",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If enabled, start server with --fast.",
    )
    parser.add_argument(
        "--server-headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If enabled, start server with --headless.",
    )

    parser.add_argument(
        "--out-dir",
        default="logs/learn",
        help="Root output directory (a timestamped subdir will be created).",
    )
    parser.add_argument(
        "--keep-last",
        type=int,
        default=5,
        help="Keep only N most recent run dirs under --out-dir (0 disables pruning).",
    )

    parser.add_argument("--train-count", type=int, default=30)
    parser.add_argument("--eval-count", type=int, default=15)
    parser.add_argument("--generations", type=int, default=5)
    parser.add_argument("--trials", type=int, default=25)
    parser.add_argument(
        "--strategy",
        choices=("asha", "autotune"),
        default="asha",
        help="Learning strategy: asha is single-instance friendly; autotune is random search.",
    )
    parser.add_argument("--asha-candidates", type=int, default=40)
    parser.add_argument("--asha-eta", type=int, default=3)
    parser.add_argument("--asha-rungs", type=int, default=4)
    parser.add_argument("--asha-min-seeds", type=int, default=6)
    parser.add_argument("--asha-max-seeds", type=int, default=0)
    parser.add_argument(
        "--baseline-json",
        default="",
        help=(
            "Optional params JSON to warm-start learning (e.g. logs/learn/.../best.json). "
            "Useful when continuing improvement or switching decks/stakes."
        ),
    )
    parser.add_argument(
        "--mutations",
        type=int,
        default=10,
        help="When using --baseline-json with strategy=asha, include N mutated candidates.",
    )
    parser.add_argument(
        "--objective",
        default="wins_then_ante",
        choices=("wins_then_ante", "mean_score", "trimmed_mean_score"),
        help=(
            "Objective function for learning. wins_then_ante matches historical behavior; "
            "mean_score / trimmed_mean_score are more robust when some seeds are unwinnable."
        ),
    )
    parser.add_argument(
        "--trim-bottom-pct",
        type=float,
        default=0.0,
        help=(
            "For trimmed_mean_score: drop the bottom fraction of per-seed scores before averaging "
            "(e.g. 0.1 ignores the hardest 10%%)."
        ),
    )
    parser.add_argument(
        "--auto",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "If enabled, apply sensible defaults (profile + baseline auto-detection) unless explicitly overridden. "
            "Disable for fully manual control."
        ),
    )
    parser.add_argument(
        "--profile",
        choices=tuple(_AUTO_PROFILES),
        default="balanced",
        help="Auto profile when --auto is enabled (fast/balanced/strong).",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help=(
            "Optional autopilot: run N learning runs back-to-back, using the previous best.json as baseline "
            "for the next run (single deck/stake only; ignored for --matrix)."
        ),
    )

    parser.add_argument(
        "--matrix",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "If enabled, learn sequentially for many deck/stake combinations and write one best.json per combo. "
            "This is single-instance friendly (runs one combo at a time)."
        ),
    )
    parser.add_argument(
        "--all-decks",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If enabled, include all known decks for --matrix.",
    )
    parser.add_argument(
        "--all-stakes",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If enabled, include all known stakes for --matrix.",
    )
    parser.add_argument(
        "--decks",
        default="",
        help='Comma-separated decks for --matrix (e.g. "RED,BLUE,CHECKERED"). Overrides --deck.',
    )
    parser.add_argument(
        "--stakes",
        default="",
        help='Comma-separated stakes for --matrix (e.g. "WHITE,RED"). Overrides --stake.',
    )
    parser.add_argument(
        "--skip-locked",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "If enabled, preflight each deck/stake by calling RPC start and skip combos that fail "
            "(useful when decks/stakes are not unlocked)."
        ),
    )
    parser.add_argument(
        "--matrix-max",
        type=int,
        default=0,
        help="Optional cap for number of deck/stake combos to run (0 disables).",
    )
    parser.add_argument("--rng-seed", default="learn")
    parser.add_argument("--max-steps", type=int, default=1500)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _wait_for_health(*, base_url: str, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + max(1.0, float(timeout_s))
    rpc = BalatroRPC(base_url=base_url, timeout=5.0)
    try:
        while time.time() < deadline:
            try:
                value = rpc.health()
                if isinstance(value, dict) and value.get("status") == "ok":
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False
    finally:
        rpc.close()


def _start_server(
    *, host: str, port: int, fast: bool, headless: bool
) -> _ServerProcess:
    cmd: list[str] = ["uvx", "balatrobot", "--host", host, "--port", str(port)]
    if fast:
        cmd.append("--fast")
    if headless:
        cmd.append("--headless")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return _ServerProcess(process=proc, base_url=_base_url(host, port))


def _stop_server(server: _ServerProcess) -> None:
    proc = server.process
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _prune_runs(root: Path, *, keep_last: int) -> None:
    keep_last = int(keep_last)
    if keep_last <= 0:
        return
    if not root.exists():
        return
    dirs = [p for p in root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in dirs[keep_last:]:
        shutil.rmtree(old, ignore_errors=True)


def _split_csv(value: str) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return [p.upper() for p in parts if p]


def _has_flag(argv: list[str], flag: str) -> bool:
    for token in argv:
        if token == flag:
            return True
        if isinstance(token, str) and token.startswith(flag + "="):
            return True
    return False


def _apply_auto_defaults(args: argparse.Namespace, argv: list[str]) -> None:
    if not bool(getattr(args, "auto", True)):
        return
    profile = str(getattr(args, "profile", "balanced") or "balanced").lower()
    defaults = _AUTO_PROFILES.get(profile, _AUTO_PROFILES["balanced"])

    def set_if_missing(flag: str, attr: str) -> None:
        if _has_flag(argv, flag):
            return
        if attr in defaults:
            setattr(args, attr, defaults[attr])

    set_if_missing("--strategy", "strategy")
    set_if_missing("--train-count", "train_count")
    set_if_missing("--eval-count", "eval_count")
    set_if_missing("--asha-candidates", "asha_candidates")
    set_if_missing("--asha-rungs", "asha_rungs")
    set_if_missing("--asha-min-seeds", "asha_min_seeds")
    set_if_missing("--asha-max-seeds", "asha_max_seeds")
    set_if_missing("--objective", "objective")
    set_if_missing("--trim-bottom-pct", "trim_bottom_pct")
    set_if_missing("--mutations", "mutations")


def _find_latest_best_json(out_root: Path, *, deck: str, stake: str) -> Path | None:
    """Find the most recent best.json for deck/stake under logs/learn."""
    deck = (deck or "").upper()
    stake = (stake or "").upper()
    if not deck or not stake or not out_root.exists():
        return None

    candidates: list[Path] = []
    # Single-run layout: logs/learn/RED-WHITE-<timestamp>/best.json
    candidates.extend(out_root.glob(f"{deck}-{stake}-*/best.json"))
    # Matrix layout: logs/learn/matrix-<timestamp>/RED-WHITE/best.json
    candidates.extend(out_root.glob(f"matrix-*/{deck}-{stake}/best.json"))

    latest: Path | None = None
    latest_mtime = -1.0
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > latest_mtime:
            latest = path
            latest_mtime = mtime
    return latest


def _matrix_decks(args: argparse.Namespace) -> list[str]:
    if args.all_decks:
        return list(_VALID_DECKS)
    decks = _split_csv(getattr(args, "decks", ""))
    if decks:
        return decks
    return [str(args.deck).upper()]


def _matrix_stakes(args: argparse.Namespace) -> list[str]:
    if args.all_stakes:
        return list(_VALID_STAKES)
    stakes = _split_csv(getattr(args, "stakes", ""))
    if stakes:
        return stakes
    return [str(args.stake).upper()]


def _preflight_start(
    *,
    base_url: str,
    deck: str,
    stake: str,
    timeout_s: float,
) -> tuple[bool, str]:
    rpc = BalatroRPC(base_url=base_url, timeout=max(1.0, float(timeout_s)))
    try:
        rpc.menu()
        rpc.start(deck=deck, stake=stake, seed="LEARN-PREFLIGHT")
        rpc.menu()
        return True, ""
    except BalatroRPCError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        rpc.close()


def _run_learn_for_combo(
    args: argparse.Namespace,
    *,
    deck: str,
    stake: str,
    run_dir: Path,
    baseline_json: str = "",
) -> int:
    train_prefix = f"LEARN-TRAIN-{deck}-{stake}-{_timestamp()}"
    eval_prefix = f"LEARN-EVAL-{deck}-{stake}-{_timestamp()}"
    best_path = run_dir / "best.json"

    if args.strategy == "autotune":
        autotune_args = [
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--deck",
            deck,
            "--stake",
            stake,
            "--train-count",
            str(args.train_count),
            "--eval-count",
            str(args.eval_count),
            "--train-prefix",
            train_prefix,
            "--eval-prefix",
            eval_prefix,
            "--generations",
            str(args.generations),
            "--trials",
            str(args.trials),
            "--rng-seed",
            str(args.rng_seed),
            "--max-steps",
            str(args.max_steps),
            "--timeout",
            str(args.timeout),
            "--log-level",
            args.log_level,
            "--baseline-json",
            str(baseline_json or args.baseline_json or ""),
            "--objective",
            str(args.objective),
            "--trim-bottom-pct",
            str(args.trim_bottom_pct),
            "--out",
            str(best_path),
        ]
        return autotune_main(autotune_args)

    max_seeds = int(args.asha_max_seeds)
    if max_seeds <= 0:
        max_seeds = int(args.train_count)
    asha_args = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--deck",
        deck,
        "--stake",
        stake,
        "--seed-prefix",
        train_prefix,
        "--count",
        str(args.train_count),
        "--candidates",
        str(args.asha_candidates),
        "--eta",
        str(args.asha_eta),
        "--rungs",
        str(args.asha_rungs),
        "--min-seeds",
        str(args.asha_min_seeds),
        "--max-seeds",
        str(max_seeds),
        "--baseline-json",
        str(baseline_json or args.baseline_json or ""),
        "--mutations",
        str(int(args.mutations)),
        "--eval-count",
        str(int(args.eval_count)),
        "--eval-prefix",
        eval_prefix,
        "--rng-seed",
        str(args.rng_seed),
        "--max-steps",
        str(args.max_steps),
        "--timeout",
        str(args.timeout),
        "--log-level",
        args.log_level,
        "--objective",
        str(args.objective),
        "--trim-bottom-pct",
        str(args.trim_bottom_pct),
        "--out",
        str(best_path),
    ]
    return asha_tune_main(asha_args)


def main(argv: list[str] | None = None) -> int:
    argv_list = list(argv) if argv is not None else sys.argv[1:]
    args = build_parser().parse_args(argv_list)
    _apply_auto_defaults(args, argv_list)
    configure_logging(args.log_level)

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    _prune_runs(out_root, keep_last=args.keep_last)

    base_url = _base_url(args.host, args.port)
    server: _ServerProcess | None = None

    if not _wait_for_health(base_url=base_url, timeout_s=2.0):
        if not args.start_server:
            print(
                f"BalatroBot not reachable at {base_url}. Start it first or use --start-server.",
                file=sys.stderr,
            )
            return 2
        server = _start_server(
            host=args.host,
            port=int(args.port),
            fast=bool(args.server_fast),
            headless=bool(args.server_headless),
        )
        if not _wait_for_health(base_url=server.base_url, timeout_s=60.0):
            print("Failed to start BalatroBot (health check timeout).", file=sys.stderr)
            _stop_server(server)
            return 2

    try:
        runs = max(1, int(getattr(args, "runs", 1) or 1))
        if bool(getattr(args, "matrix", False)):
            runs = 1

        if not args.matrix:
            deck = str(args.deck).upper()
            stake = str(args.stake).upper()
            baseline = str(getattr(args, "baseline_json", "") or "").strip()
            if not baseline and bool(getattr(args, "auto", True)):
                found = _find_latest_best_json(out_root, deck=deck, stake=stake)
                if found is not None:
                    baseline = str(found)

            exit_code = 0
            current_baseline = baseline
            for run_index in range(1, runs + 1):
                suffix = f"-r{run_index:02d}" if runs > 1 else ""
                run_dir = out_root / f"{deck}-{stake}-{_timestamp()}{suffix}"
                run_dir.mkdir(parents=True, exist_ok=True)
                exit_code = _run_learn_for_combo(
                    args,
                    deck=deck,
                    stake=stake,
                    run_dir=run_dir,
                    baseline_json=current_baseline,
                )
                if exit_code != 0:
                    return exit_code
                current_baseline = str(run_dir / "best.json")
            return exit_code

        run_dir = out_root / f"matrix-{_timestamp()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        combos: list[tuple[str, str]] = []
        for deck in _matrix_decks(args):
            for stake in _matrix_stakes(args):
                combos.append((deck, stake))
        max_combos = int(args.matrix_max)
        if max_combos > 0:
            combos = combos[:max_combos]

        combos_summary: list[dict[str, Any]] = []
        summary: dict[str, Any] = {
            "host": args.host,
            "port": int(args.port),
            "strategy": args.strategy,
            "train_count": int(args.train_count),
            "eval_count": int(args.eval_count),
            "combos": combos_summary,
        }
        for deck, stake in combos:
            combo_key = f"{deck}-{stake}"
            combo_dir = run_dir / combo_key
            combo_dir.mkdir(parents=True, exist_ok=True)

            baseline = str(getattr(args, "baseline_json", "") or "").strip()
            if not baseline and bool(getattr(args, "auto", True)):
                found = _find_latest_best_json(out_root, deck=deck, stake=stake)
                if found is not None:
                    baseline = str(found)

            if args.skip_locked:
                ok, reason = _preflight_start(
                    base_url=base_url, deck=deck, stake=stake, timeout_s=5.0
                )
                if not ok:
                    (combo_dir / "skipped.json").write_text(
                        json.dumps(
                            {
                                "deck": deck,
                                "stake": stake,
                                "skipped": True,
                                "reason": reason,
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    combos_summary.append(
                        {
                            "deck": deck,
                            "stake": stake,
                            "status": "skipped",
                            "reason": reason,
                        }
                    )
                    continue

            exit_code = _run_learn_for_combo(
                args,
                deck=deck,
                stake=stake,
                run_dir=combo_dir,
                baseline_json=baseline,
            )
            combos_summary.append(
                {
                    "deck": deck,
                    "stake": stake,
                    "status": "ok" if exit_code == 0 else "error",
                    "exit_code": int(exit_code),
                    "best_json": str((combo_dir / "best.json").as_posix()),
                }
            )

        (run_dir / "index.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        return 0
    finally:
        if server is not None and os.environ.get("BALATRO_AI_LEARN_KEEP_SERVER") != "1":
            _stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
