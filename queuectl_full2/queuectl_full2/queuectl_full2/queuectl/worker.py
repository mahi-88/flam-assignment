
# at top of file
from __future__ import annotations

import os, signal, time, json, subprocess, sys
from typing import Optional
from pathlib import Path

# ADD:
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0




import os, signal, time, json, subprocess, sys
from typing import Optional
from pathlib import Path
from .db import connect
from .repo import acquire_next_job, complete_job, fail_job, log_execution
from .exec import run_command
from .config import get_int
from .utils import utc_now, to_iso

PID_DIR = Path(".queuectl")
PID_FILE = PID_DIR / "controller.pid"
CHILDREN_FILE = PID_DIR / "children.json"

stop_flag = False

def _signal_handler(signum, frame):
    global stop_flag
    stop_flag = True

def worker_loop(db_path: Optional[str]=None):
    global stop_flag
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    conn = connect(db_path)
    worker_id = f"pid-{os.getpid()}"
    poll_ms = get_int(conn, "poll_interval_ms")
    timeout = get_int(conn, "timeout_seconds")
    while not stop_flag:
        job = acquire_next_job(conn, worker_id)
        if not job:
            time.sleep(poll_ms/1000.0)
            continue
        exit_code, out, err = run_command(job["command"], timeout)
        log_execution(conn, job["id"], exit_code, out, err)
        if exit_code == 0:
            complete_job(conn, job["id"])
        else:
            last_error = (err or f"exit {exit_code}")[:512]
            fail_job(conn, job, last_error=last_error)

def _spawn_child(count: int, db_path: Optional[str]):
    args = [sys.executable, "-m", "queuectl.worker", "run"]
    if db_path:
        args.extend(["--db", db_path])
    procs = []
    for _ in range(count):
        if os.name == "nt":
            p = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NEW_PROCESS_GROUP,  # <-- important on Windows
            )
        else:
            p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        procs.append(p.pid)
    return procs


def start_controller(count: int, db_path: Optional[str]=None):
    PID_DIR.mkdir(exist_ok=True)
    if PID_FILE.exists():
        raise RuntimeError("Workers already running (pid file exists).")
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    children = _spawn_child(count, db_path)
    with open(CHILDREN_FILE, "w") as f:
        json.dump(children, f)
    print(f"Started {len(children)} workers: {children}")

def stop_controller():
    if not PID_FILE.exists():
        print("No controller pid file; nothing to stop.")
        return
    children = []
    if CHILDREN_FILE.exists():
        try:
            children = json.loads(CHILDREN_FILE.read_text())
        except Exception:
            children = []

    # Send termination to each child
    for pid in children:
        try:
            if os.name == "nt":
                # Try gentle console break first
                try:
                    os.kill(pid, signal.CTRL_BREAK_EVENT)
                except Exception:
                    # Fallback to taskkill /T /F to kill the process tree
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except PermissionError:
            # As a final fallback on Windows, force kill
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Cleanup pid files
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass
    try:
        CHILDREN_FILE.unlink()
    except FileNotFoundError:
        pass
    print("Sent stop signal to workers and cleaned up pid files.")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    runp = sub.add_parser("run")
    runp.add_argument("--db", default=None)
    args = ap.parse_args()
    if args.cmd == "run":
        worker_loop(args.db)
    else:
        ap.print_help()
