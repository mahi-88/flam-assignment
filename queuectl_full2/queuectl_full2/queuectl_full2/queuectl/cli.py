
from __future__ import annotations
import json, sys
import typer
from rich.console import Console
from rich.table import Table
from typing import Optional
from .db import connect, DEFAULT_DB_PATH
from .repo import enqueue as repo_enqueue, list_jobs, status as repo_status, dlq_list, dlq_retry, get_logs
from .utils import gen_id, utc_now, to_iso
from .worker import start_controller, stop_controller
from .config import get_config, set_config

app = typer.Typer(add_completion=False)
console = Console()

def _conn(db: Optional[str]):
    return connect(db)

@app.command(help="Add a new job to the queue. Provide JSON or use flags.")
def enqueue(job_json: Optional[str] = typer.Argument(None),
            command: Optional[str] = typer.Option(None, "--command", "-c", help="Command to execute"),
            id: Optional[str] = typer.Option(None, "--id", help="Job ID (defaults to UUID)"),
            max_retries: int = typer.Option(None, "--max-retries"),
            priority: int = typer.Option(0, "--priority"),
            run_at: Optional[str] = typer.Option(None, "--run-at", help="ISO UTC time"),
            db: Optional[str] = typer.Option(None, "--db", help=f"DB path (default: {DEFAULT_DB_PATH})")):
    conn = _conn(db)
    if job_json:
        job = json.loads(job_json)
    else:
        if not command:
            raise typer.BadParameter("Either JOB_JSON or --command required.")
        job = {"command": command}
    job.setdefault("id", id or gen_id())
    if max_retries is not None:
        job["max_retries"] = max_retries
    if run_at is not None:
        job["run_at"] = run_at
    if "run_at" not in job:
        job["run_at"] = to_iso(utc_now())
    job.setdefault("priority", priority)
    repo_enqueue(conn, job)
    console.print(f"[green]Enqueued[/green] {job['id']} : {job['command']}")

@app.command(help="Start worker processes.")
def worker_start(count: int = typer.Option(1, "--count"),
                 db: Optional[str] = typer.Option(None, "--db")):
    try:
        start_controller(count, db)
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

@app.command(help="Stop worker processes gracefully.")
def worker_stop():
    stop_controller()

@app.command(help="Show summary of job states & active workers.")
def status(db: Optional[str] = typer.Option(None, "--db"), json_out: bool = typer.Option(False, "--json")):
    conn = _conn(db)
    st = repo_status(conn)
    if json_out:
        console.print_json(data=st); return
    table = Table(title="queuectl status")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Total", str(st["total"]))
    for k,v in st["states"].items():
        table.add_row(k.capitalize(), str(v))
    table.add_row("Active workers", str(st["active_workers"]))
    table.add_row("DB", str(db or DEFAULT_DB_PATH))
    console.print(table)

@app.command(help="List jobs by state.")
def list(state: Optional[str] = typer.Option(None, "--state"),
         limit: int = typer.Option(50, "--limit"),
         db: Optional[str] = typer.Option(None, "--db"),
         json_out: bool = typer.Option(False, "--json")):
    conn = _conn(db)
    rows = list_jobs(conn, state, limit)
    if json_out:
        console.print_json(data=rows); return
    table = Table(title=f"jobs (state={state or 'any'})")
    cols = ["id","state","attempts","max_retries","run_at","priority","command","last_error"]
    for c in cols:
        table.add_column(c)
    for r in rows:
        table.add_row(*(str(r.get(c,''))[:80] for c in cols))
    console.print(table)

@app.command(help="DLQ: list dead jobs.")
def dlq_list_cmd(db: Optional[str]=typer.Option(None, "--db"), json_out: bool=typer.Option(False, "--json")):
    conn = _conn(db)
    rows = dlq_list(conn)
    if json_out:
        console.print_json(data=rows); return
    table = Table(title="DLQ (dead jobs)")
    cols = ["id","attempts","max_retries","updated_at","command","last_error"]
    for c in cols:
        table.add_column(c)
    for r in rows:
        table.add_row(*(str(r.get(c,''))[:80] for c in cols))
    console.print(table)

@app.command(help="DLQ: retry a dead job by id.")
def dlq_retry_cmd(job_id: str = typer.Argument(...),
                  db: Optional[str]=typer.Option(None, "--db")):
    conn = _conn(db)
    ok = dlq_retry(conn, job_id)
    if not ok:
        console.print(f"[red]Job {job_id} not in DLQ[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Re-enqueued[/green] {job_id}")

@app.command(help="Show recent logs for a job.")
def logs(job_id: str = typer.Argument(...),
         limit: int = typer.Option(5, "--limit"),
         db: Optional[str]=typer.Option(None, "--db"),
         json_out: bool=typer.Option(False, "--json")):
    conn = _conn(db)
    rows = get_logs(conn, job_id, limit)
    if json_out:
        console.print_json(data=rows); return
    table = Table(title=f"logs for {job_id}")
    cols = ["id","created_at","exit_code","stdout","stderr"]
    for c in cols:
        table.add_column(c)
    for r in rows:
        table.add_row(*(str(r.get(c,''))[:80] for c in cols))
    console.print(table)

@app.command(help="Config get or set keys.")
def config(action: str = typer.Argument(..., help="get|set"),
           key: str = typer.Argument(...),
           value: Optional[str] = typer.Argument(None),
           db: Optional[str] = typer.Option(None, "--db")):
    conn = _conn(db)
    if action == "get":
        try:
            v = get_config(conn, key)
        except KeyError:
            console.print(f"[red]Key not found[/red]")
            raise typer.Exit(1)
        console.print(f"{key} = {v}")
    elif action == "set":
        if value is None:
            raise typer.BadParameter("value required for set")
        set_config(conn, key, value)
        console.print(f"Set {key} = {value}")
    else:
        raise typer.BadParameter("action must be 'get' or 'set'")

@app.command()
def version():
    console.print("queuectl v0.1")

def main():
    app()

if __name__ == "__main__":
    main()
