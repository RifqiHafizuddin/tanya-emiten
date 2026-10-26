"""Retries for transient network failures (dropped connections, DNS blips, read timeouts)."""
import time

import psycopg
import requests

TRANSIENT = (requests.ConnectionError, requests.Timeout, psycopg.OperationalError)


def retry(fn, tries: int = 5, wait: float = 5.0):
    """Call fn(); on a transient error wait 5, 10, 20, 40 s and try again, then re-raise."""
    for i in range(tries):
        try:
            return fn()
        except TRANSIENT as e:
            if i == tries - 1:
                raise
            print(f"  network: {type(e).__name__}, retrying in {wait * 2**i:.0f}s")
            time.sleep(wait * 2**i)
