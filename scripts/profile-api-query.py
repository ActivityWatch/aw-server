"""Profile queries against a disposable Peewee database.

Run from the repository root with its environment activated:
    python scripts/profile-api-query.py --baseline-ref master
    python scripts/profile-api-query.py --cache

The optional baseline loads aw_server/api.py from that git revision. Both runs
use the same installed aw-core dependency, isolating server/query-path changes.
No ActivityWatch user data is read or modified.
"""

import argparse
import cProfile
import logging
import pstats
import statistics
import subprocess
import tempfile
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from aw_core.models import Event
from aw_datastore import Datastore
from aw_datastore.storages.peewee import PeeweeStorage
from aw_server.api import ServerAPI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--events", type=int, default=10000)
    parser.add_argument("--queries", type=int, default=10)
    args = parser.parse_args()
    if args.events < 1 or args.queries < 1:
        parser.error("events and queries must be positive")
    api_class = ServerAPI
    if args.baseline_ref:
        module = types.ModuleType("aw_server._profile_baseline")
        module.__package__ = "aw_server"
        source = subprocess.check_output(
            ["git", "show", f"{args.baseline_ref}:aw_server/api.py"]
        )
        exec(compile(source, "baseline/aw_server/api.py", "exec"), module.__dict__)
        api_class = module.ServerAPI
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix="aw-query-profile-") as tmp:
        with patch(
            "aw_datastore.storages.peewee.get_data_dir", return_value=tmp
        ), patch("aw_server.settings.get_config_dir", return_value=tmp):
            db = Datastore(
                PeeweeStorage, testing=True, filepath=str(Path(tmp) / "test.db")
            )
            api = api_class(db, testing=True)
        try:
            bucket = db.create_bucket(
                "test", type="test", client="test", hostname="test"
            )
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            bucket.insert(
                [
                    Event(
                        timestamp=start + timedelta(seconds=i),
                        duration=1,
                        data={"app": "test"},
                    )
                    for i in range(args.events)
                ]
            )
            period = (
                start.isoformat()
                + "/"
                + (start + timedelta(seconds=args.events + 1)).isoformat()
            )
            query = ['RETURN = sum_durations(query_bucket("test"));']

            def execute():
                result = api.query2("profile", query, [period], args.cache)
                assert result == [timedelta(seconds=args.events)]

            execute()  # warm filesystem/page cache and optional result cache
            timings = []
            for _ in range(args.queries):
                begin = time.perf_counter()
                execute()
                timings.append(time.perf_counter() - begin)
            print(
                f"revision={args.baseline_ref or 'working-tree'}, cache={args.cache}, events={args.events}"
            )
            print(f"Median query: {1000 * statistics.median(timings):.3f} ms")
            profiler = cProfile.Profile()
            profiler.enable()
            for _ in range(args.queries):
                execute()
            profiler.disable()
            pstats.Stats(profiler).strip_dirs().sort_stats("cumulative").print_stats(18)
        finally:
            db.storage_strategy.db.close()


if __name__ == "__main__":
    main()
