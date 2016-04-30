import logging
import unittest
from datetime import datetime

from aw.client import awclient
from aw.core.models import Activity, Event

logging.basicConfig(level=logging.DEBUG)

class ClientTest(unittest.TestCase):
    def setUp(self):
        self.client = awclient("unittest", testing=True)

    def test_session(self):
        with self.client:
            self.client.send_event(Activity(timestamp=(datetime.now(), datetime.now())))

    def test_send_event(self):
        self.client.send_event(Event(timestamp=datetime.now(), label="test"))
