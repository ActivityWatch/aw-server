"""
Useful for turning JSON logs into human-readable logs.

Usage:
    aw-server --log-json 2>&1 | python3 process_logs.py

"""

import json

while True:
    msg = json.loads(input())
    print("{asctime} [{levelname}] {message}".format(**msg))

