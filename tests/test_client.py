import logging
import unittest
from datetime import datetime, timezone

from aw_client import ActivityWatchClient
from aw_core.models import Event

logging.basicConfig(level=logging.WARN)


# FIXME: This client test needs to use a synchronous version of
#        the ActivityWatchClient in order for errors to propagate.
class ClientTest(unittest.TestCase):
    def setUp(self):
        self.client = ActivityWatchClient("unittest", testing=True)
        self.client.setup_bucket("test", "testevents")
        self.client.connect()

    def test_send_event(self):
        self.client.send_event("test", Event(timestamp=datetime.now(tz=timezone.utc), data={"label": "test"}))

    def test_send_events(self):
        self.client.send_events("test", [
            Event(timestamp=datetime.now(tz=timezone.utc), data={"label": "test"}),
            Event(timestamp=datetime.now(tz=timezone.utc), data={"label": "test2"}),
        ])


if __name__ == "__main__":
    unittest.main()
