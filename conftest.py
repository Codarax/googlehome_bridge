import pytest
import threading
import time
import os

from ha_stub import app as ha_app


@pytest.fixture(scope='session', autouse=True)
def ha_stub_server():
    """Start the HA stub server in a background thread for the test session."""
    port = int(os.getenv('HA_STUB_PORT', '8123'))

    def run():
        ha_app.run(host='127.0.0.1', port=port)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    # give it a moment to start
    time.sleep(0.2)
    yield
    # thread is daemon; it will exit with process
