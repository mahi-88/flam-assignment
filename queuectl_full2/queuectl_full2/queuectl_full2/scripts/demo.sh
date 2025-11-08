
#!/usr/bin/env bash
set -euo pipefail
DB="${1:-queue.db}"

python -m queuectl.cli worker-start --count 2 --db "$DB"

python -m queuectl.cli enqueue --command "echo Hello" --db "$DB"
python -m queuectl.cli enqueue --command "bash -c 'exit 1'" --max-retries 1 --db "$DB"
python -m queuectl.cli enqueue --command "python -c 'import time; time.sleep(2)'" --db "$DB"

python -m queuectl.cli status --db "$DB"
sleep 5
python -m queuectl.cli status --db "$DB"
python -m queuectl.cli dlq-list-cmd --db "$DB"

python -m queuectl.cli worker-stop
