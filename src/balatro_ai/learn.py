from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from balatro_ai.autotune import main as autotune_main
from balatro_ai.logging_utils import configure_logging
from balatro_ai.rpc import BalatroRPC


@dataclass(frozen=True)
class _ServerProcess:
    process: subprocess.Popen
    base_url: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "One-command workflow: ensure BalatroBot is running, generate seed sets, "
            "run autotune, and write outputs to a fresh run directory."
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


def _start_server(*, host: str, port: int, fast: bool, headless: bool) -> _ServerProcess:
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(args.log_level)

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    _prune_runs(out_root, keep_last=args.keep_last)

    run_dir = out_root / f"{args.deck}-{args.stake}-{_timestamp()}"
    run_dir.mkdir(parents=True, exist_ok=True)

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

    train_prefix = f"LEARN-TRAIN-{_timestamp()}"
    eval_prefix = f"LEARN-EVAL-{_timestamp()}"
    best_path = run_dir / "best.json"

    try:
        autotune_args = [
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--deck",
            args.deck,
            "--stake",
            args.stake,
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
            "--out",
            str(best_path),
        ]
        return autotune_main(autotune_args)
    finally:
        if server is not None and os.environ.get("BALATRO_AI_LEARN_KEEP_SERVER") != "1":
            _stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())

