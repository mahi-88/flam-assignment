
import os, time, subprocess, sys, json, signal

def run_cli(args):
    cmd = [sys.executable, "-m", "queuectl.cli"] + args
    return subprocess.run(cmd, capture_output=True, text=True)

def test_persistence(tmp_path):
    db = tmp_path/"t.db"
    run_cli(["config","set","lease_seconds","1","--db",str(db)])
    run_cli(["enqueue","--command","python -c \"import time; time.sleep(2)\"","--db",str(db)])
    p = subprocess.Popen([sys.executable, "-m", "queuectl.worker", "run", "--db", str(db)])
    time.sleep(0.5)
    p.kill(); p.wait(timeout=5)
    p2 = subprocess.Popen([sys.executable, "-m", "queuectl.worker", "run", "--db", str(db)])
    time.sleep(3)
    p2.send_signal(signal.SIGTERM); p2.wait(timeout=5)
    r = run_cli(["status","--db",str(db), "--json"])
    data = json.loads(r.stdout.strip())
    assert data["states"]["completed"] == 1
