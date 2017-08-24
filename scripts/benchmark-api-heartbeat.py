from time import sleep
import cProfile
import pstats
from datetime import timezone as tz
from datetime import datetime

from aw_core.models import Event

import aw_datastore
import aw_server


def benchmark():
    ds = aw_datastore.Datastore(aw_datastore.storages.PeeweeStorage, testing=True)
    api = aw_server.api.ServerAPI(ds, testing=True)

    print(api.get_info())

    bucket_id = "test-benchmark"

    try:
        api.create_bucket(bucket_id, "test", "test", "test")
    except Exception as e:
        print(e)

    print("Benchmarking... this will take 30 seconds")
    for i in range(120):
        sleep(0.1)
        api.heartbeat(bucket_id, Event(timestamp=datetime.now(tz=tz.utc), data={"test": str(int(i))}), pulsetime=0.3)

if __name__ == "__main__":
    f_bench = "benchmark.dat"
    cProfile.run('benchmark()', f_bench)
    p = pstats.Stats(f_bench)
    p.strip_dirs()
    # p.sort_stats('tottime')
    p.sort_stats('cumulative')
    p.print_stats(20)
