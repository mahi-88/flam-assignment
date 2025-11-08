
import os, time, subprocess, sys, json, signal

def run_cli(args):
    cmd = [sys.executable, "-m", "queuectl.cli"] + args
    return subprocess.run(cmd, capture_output=True, text=True)

def test_retry_dlq(tmp_path):
    db = tmp_path/"t.db"
    run_cli(["config","set","backoff_base","2","--db",str(db)])
    run_cli(["enqueue","--command","bash -c 'exit 1'","--max-retries","1","--db",str(db)])
    p = subprocess.Popen([sys.executable, "-m", "queuectl.worker", "run", "--db", str(db)])
    time.sleep(4)
    p.send_signal(signal.SIGTERM); p.wait(timeout=5)
    dlq = run_cli(["dlq-list-cmd","--db",str(db), "--json"])
    assert dlq.returncode == 0
    data = json.loads(dlq.stdout.strip())
    assert len(data) == 1
    job_id = data[0]["id"]
    r = run_cli(["dlq-retry-cmd", job_id, "--db", str(db)])
    assert r.returncode == 0
