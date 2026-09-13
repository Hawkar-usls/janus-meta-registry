from __future__ import annotations
import argparse, datetime as dt, hashlib, json, subprocess, time
from pathlib import Path

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", required=True)
    ap.add_argument("--raw-log-dir", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--command", required=True)
    ap.add_argument("--source-head", default="")
    ap.add_argument("--authority-head", default="")
    args = ap.parse_args()

    journal = Path(args.journal)
    raw_dir = Path(args.raw_log_dir)
    journal.parent.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    started = dt.datetime.now(dt.timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%S.%fZ")
    t0 = time.perf_counter()
    proc = subprocess.run(
        args.command,
        cwd=args.cwd,
        shell=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    duration_ms = int((time.perf_counter() - t0) * 1000)

    stdout_path = raw_dir / f"{run_id}.stdout.log"
    stderr_path = raw_dir / f"{run_id}.stderr.log"
    stdout_path.write_text(proc.stdout, encoding="utf-8", newline="\n")
    stderr_path.write_text(proc.stderr, encoding="utf-8", newline="\n")

    event = {
        "schema": "JANUS_LOCAL_FIRST_RUN_EVENT_V1",
        "run_id": run_id,
        "utc_started": started.isoformat().replace("+00:00", "Z"),
        "project": args.project,
        "gate": args.gate,
        "source_head": args.source_head or None,
        "authority_head": args.authority_head or None,
        "cwd_role": "isolated_local_worktree",
        "command": args.command,
        "command_sha256": sha256_text(args.command),
        "exit_code": proc.returncode,
        "duration_ms": duration_ms,
        "stdout_sha256": sha256_text(proc.stdout),
        "stderr_sha256": sha256_text(proc.stderr),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "result": "PASS" if proc.returncode == 0 else "FAIL",
        "firewalls": [
            "LOCAL_EXECUTION_DOES_NOT_CHANGE_SCIENTIFIC_STATUS",
            "FAILURES_AND_MISMATCHES_ARE_APPEND_ONLY",
            "NO_SECRETS_OR_TOKENS_IN_JOURNAL",
        ],
    }
    with journal.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n")
    print("JANUS_RUN_EVENT=" + json.dumps(event, ensure_ascii=False, sort_keys=True))
    return proc.returncode

if __name__ == "__main__":
    raise SystemExit(main())
