#!/usr/bin/env python
import datetime
import sys
import logging

logging.basicConfig(level=logging.INFO)

try:
    with open("/tmp/teslamate-comed-last-update", "r") as f:
        last_update = datetime.datetime.fromisoformat(f.read())

    last_update_threshold = datetime.datetime.utcnow() - datetime.timedelta(hours=2)

    if last_update < last_update_threshold:
        sys.exit(1)

    sys.exit(0)
except SystemExit:
    pass
except:
    logging.exception("Error during health check")
    sys.exit(1)
