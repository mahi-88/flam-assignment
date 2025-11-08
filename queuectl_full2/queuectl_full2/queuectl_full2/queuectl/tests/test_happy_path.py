
import os, time, subprocess, sys, json, signal

def run_cli(args, env=None):
    cmd = [sys.executable, "-m", "queuectl.cli"] + args
    return subprocess.run(cmd, capture_output=True, text=True, env=env or os.environ.copy())

def test_happy_path(tmp_path):
    db = tmp_path/"t.db"
    r = run_cli(["enqueue", "--command", "python -c \"print('hi')\"", "--db", str(db)])
    assert r.returncode == 0
    p = subprocess.Popen([sys.executable, "-m", "queuectl.worker", "run", "--db", str(db)])
    time.sleep(1.5)
    p.send_signal(signal.SIGTERM); p.wait(timeout=5)
    r = run_cli(["list", "--state", "completed", "--db", str(db), "--json"])
    assert r.returncode == 0
    data = json.loads(r.stdout.strip())
    assert len(data) == 1
