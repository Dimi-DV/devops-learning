#!/usr/bin/env python3
"""Writes a timestamp to a log file every 10 seconds."""
import time
import datetime
import os

LOG_FILE = "/tmp/timestamp_service.log"

def main():
    print(f"Timestamp logger starting, writing to {LOG_FILE}")
    while True:
        now = datetime.datetime.now().isoformat()
        with open(LOG_FILE, "a") as f:
            f.write(f"{now} - Service is running (PID: {os.getpid()})\n")
        time.sleep(10)

if __name__ == "__main__":
    main()