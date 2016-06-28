import logging
import unittest
from datetime import datetime

from aw.client import ActivityWatchClient
from aw.core.models import Event

from aw.server import datastore
from aw.server.datastore import Datastore

logging.basicConfig(level=logging.DEBUG)

class ClientTest(unittest.TestCase):
    def setUp(self):
        self.client = ActivityWatchClient("unittest", testing=True)

    def test_session(self):
        with self.client:
            self.client.send_event(Event(timestamp=(datetime.now(), datetime.now())))

    def test_send_event(self):
        self.client.send_event(Event(timestamp=datetime.now(), label="test"))

if __name__ == "__main__":
    unittest.main()
