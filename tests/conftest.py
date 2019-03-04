import pytest

import aw_server


@pytest.fixture
def app():
    return aw_server.create_app()
