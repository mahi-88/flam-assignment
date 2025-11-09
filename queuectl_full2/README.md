# queuectl

A minimal, production-grade background job queue with a command-line interface. Built on SQLite for simplicity and reliability.

## Features

- **Persistent Storage**: SQLite-backed job queue with WAL mode for concurrent access
- **Multiple Workers**: Spawn multiple worker processes for parallel job execution
- **Retry Logic**: Exponential backoff retry mechanism with configurable parameters
- **Dead Letter Queue**: Automatic handling of jobs that exhaust retry attempts
- **CLI-First Design**: Clean, user-friendly command-line interface
- **Configurable**: Runtime configuration without code changes

## Quick Start

### Installation

```bash
git clone <your-repository-url>
cd queuectl
pip install -e .
```

Verify installation:

```bash
python -m queuectl.cli version
# Output: queuectl v0.1
```

### Basic Usage

Start workers:
```bash
python -m queuectl.cli worker-start --count 2
```

Enqueue a job:
```bash
python -m queuectl.cli enqueue --command "ping 127.0.0.1 -n 2 >NUL"
```

Check status:
```bash
python -m queuectl.cli status
```

Stop workers:
```bash
python -m queuectl.cli worker-stop
```

## Architecture

### System Overview

```
┌─────────────────────┐ poll/lease ┌────────────────────────┐
│   queuectl CLI      │────────────▶│  SQLite (queue.db)     │
│ (Typer + Rich UI)   │             │ jobs / logs / config   │
└──────────┬──────────┘             └───────────┬────────────┘
           │                                     │
           │ Enqueue/Status/List/DLQ/Config      │
           │                                     │
           │                          acquire/lock│
           ▼                                     ▼
┌──────────────────────┐ exec + capture ┌─────────────────────┐
│  Worker Controller   │──── spawn N ───▶│  Worker Process(es) │
│ (spawns children)    │    processes    │  (subprocess jobs)  │
└──────────────────────┘                 └─────────────────────┘
           ▲                                     │
           └─────── stop/cleanup (signals) ──────┘
```

### Job Lifecycle

```
pending ──(worker picks + leases)──▶ processing ──(exit=0)──▶ completed
                                           │
                                           └──(exit≠0)──▶ failed ──▶ backoff ──▶ retry
                                                                         │
                                                                    (exhausted)
                                                                         │
                                                                         ▼
                                                                       dead (DLQ)
```

**Backoff Formula**: `delay_seconds = base ^ attempts` (e.g., base=2 → 2s, 4s, 8s…)

### Data Model

#### `jobs` table
- `id`: Unique job identifier (UUID)
- `command`: Shell command to execute
- `state`: Job state (pending|processing|completed|failed|dead)
- `attempts`: Number of execution attempts
- `max_retries`: Maximum retry attempts before moving to DLQ
- `created_at`, `updated_at`, `run_at`: Timestamps
- `priority`: Job priority (lower = higher priority)
- `worker_id`, `locked_until`: Lease management
- `last_error`: Last error message

#### `job_logs` table
- `job_id`: Reference to job
- `created_at`: Log timestamp
- `exit_code`: Process exit code
- `stdout`, `stderr`: Captured output

#### `config` table
- `key`, `value`: Configuration key-value pairs
  - `backoff_base`: Exponential backoff base
  - `lease_seconds`: Job lease duration
  - `poll_interval_ms`: Worker polling interval
  - `timeout_seconds`: Job execution timeout

## Command Reference

### Worker Management

Start workers:
```bash
python -m queuectl.cli worker-start --count <N>
```

Stop workers:
```bash
python -m queuectl.cli worker-stop
```

### Job Management

Enqueue a job:
```bash
python -m queuectl.cli enqueue --command "<command>" [OPTIONS]

Options:
  --max-retries <N>      Maximum retry attempts (default: 3)
  --run-at <ISO8601>     Schedule job for future execution
  --priority <N>         Job priority (default: 0)
```

List jobs by state:
```bash
python -m queuectl.cli list --state <pending|processing|completed|failed>
```

View system status:
```bash
python -m queuectl.cli status
```

### Dead Letter Queue (DLQ)

List dead jobs:
```bash
python -m queuectl.cli dlq-list-cmd
```

Retry a dead job:
```bash
python -m queuectl.cli dlq-retry-cmd <job-id>
```

### Configuration

Set configuration value:
```bash
python -m queuectl.cli config set <key> <value>

Example:
python -m queuectl.cli config set backoff_base 2
```

## Usage Examples

### Example 1: Basic Happy Path

```bash
# Clean slate
Remove-Item queue.db -ErrorAction Ignore

# Start workers
python -m queuectl.cli worker-start --count 2

# Enqueue a simple job
python -m queuectl.cli enqueue --command "ping 127.0.0.1 -n 2 >NUL"

# Wait for completion
Start-Sleep -Seconds 3

# Check results
python -m queuectl.cli status
python -m queuectl.cli list --state completed

# Cleanup
python -m queuectl.cli worker-stop
```

### Example 2: Scheduled Job

```bash
# Schedule a job for the future
python -m queuectl.cli enqueue \
  --command "ping 127.0.0.1 -n 2 >NUL" \
  --run-at "2099-01-01T00:00:00Z"

# Verify it's pending
python -m queuectl.cli list --state pending
```

### Example 3: Retry with Backoff

```bash
# Configure backoff
python -m queuectl.cli config set backoff_base 2

# Enqueue a failing job
python -m queuectl.cli enqueue \
  --command "cmd /c exit /b 1" \
  --max-retries 3

# Watch retries
Start-Sleep -Seconds 2
python -m queuectl.cli list --state failed
```

### Example 4: Dead Letter Queue

```bash
# Enqueue job with limited retries
python -m queuectl.cli enqueue \
  --command "cmd /c exit /b 1" \
  --max-retries 1

# Wait for exhaustion
Start-Sleep -Seconds 5

# View dead jobs
python -m queuectl.cli dlq-list-cmd
```

## Testing

Run the test suite:

```bash
# Happy path test
python -m pytest tests/test_happy_path.py

# Retry and DLQ test
python -m pytest tests/test_retry_dlq.py

# Multi-worker test
python -m pytest tests/test_multiworkers.py

# Persistence test
python -m pytest tests/test_persistence.py
```

## Project Structure

```
queuectl/
├── queuectl/
│   ├── __init__.py
│   ├── cli.py           # Typer CLI entrypoint
│   ├── db.py            # SQLite engine + pragmas + migrations
│   ├── models.py        # Constants and data models
│   ├── repo.py          # CRUD + acquisition + DLQ + logs
│   ├── worker.py        # Controller + worker loop
│   ├── scheduler.py     # Backoff helpers
│   ├── config.py        # Configuration management
│   ├── exec.py          # Subprocess execution (timeout-safe)
│   └── utils.py         # Utilities (IDs, timestamps, etc.)
├── tests/
│   ├── test_happy_path.py
│   ├── test_retry_dlq.py
│   ├── test_multiworkers.py
│   └── test_persistence.py
├── scripts/
│   └── demo.sh          # Quick e2e demo
├── pyproject.toml
└── README.md
```

## Design Decisions

### Assumptions

- **Single-node deployment**: Workers run on the same machine
- **SQLite with WAL mode**: Simple and durable for local concurrency
- **Shell commands**: Support for simple shell strings (cmd /c, ping, python -c)
- **Lease-based locking**: Time-boxed leases prevent duplicate processing after crashes
- **CLI-first interface**: No web UI for simplicity

### Trade-offs

- **Not distributed**: No support for multi-machine deployments
- **Limited scalability**: Suitable for single-machine workloads
- **Shell execution**: Security considerations for command injection
- **No UI**: All interactions through CLI

## Troubleshooting

### Windows-Specific Issues

**Command quoting**: Use double quotes for PowerShell:
```powershell
python -m queuectl.cli enqueue --command "python -c \"print('Hello')\""
```

**Worker won't stop**: Manually kill workers:
```powershell
if (Test-Path ".queuectl\children.json") {
  $pids = Get-Content ".queuectl\children.json" | ConvertFrom-Json
  foreach ($pid in $pids) { 
    try { taskkill /PID $pid /T /F | Out-Null } catch {} 
  }
}
Remove-Item ".queuectl" -Recurse -Force -ErrorAction Ignore
```

**Installation fails**: Ensure you're in the directory containing `pyproject.toml`:
```bash
cd queuectl
pip install -e .
```

### Common Issues

**Jobs stuck in processing**: Check if workers are running and lease hasn't expired
```bash
python -m queuectl.cli status
```

**Database locked**: Ensure only one process is modifying the database at a time

**Worker crashes**: Check job logs for errors
```bash
python -m queuectl.cli list --state failed
```

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request
   
### Video Link
https://drive.google.com/file/d/1GdFvMz_RvzY8bHdf1R0EkSHPGUUTy-tZ/view?usp=sharing

## Acknowledgments

Built with:
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [SQLite](https://www.sqlite.org/) - Database engine
