import logging
import unittest
from datetime import datetime

from aw_client import ActivityWatchClient
from aw_core.models import Event

from aw_datastore import Datastore

logging.basicConfig(level=logging.WARN)

class ClientTest(unittest.TestCase):
    def setUp(self):
        self.client = ActivityWatchClient("unittest", testing=True)

    def test_send_event(self):
        self.client.send_event(Event(timestamp=datetime.now(), label="test"))

    def test_send_events(self):
        self.client.send_events([
            Event(timestamp=datetime.now(), label="test"),
            Event(timestamp=datetime.now(), label="test2"),
        ])

if __name__ == "__main__":
    unittest.main()
