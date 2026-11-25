import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row


def connect() -> psycopg.Connection:
    """A new connection; the caller closes it. Most code wants `database()` instead."""
    return psycopg.connect(host=os.getenv('DB_HOST', 'postgres'), dbname=os.getenv('DB_NAME', 'zebra'),
                           user=os.getenv('DB_USER', 'zebra'), password=os.environ['POSTGRES_PASSWORD'],
                           connect_timeout=1, options='-c statement_timeout=1500 -c lock_timeout=500',
                           row_factory=dict_row)


@contextmanager
def database():
    with connect() as conn:
        yield conn


@contextmanager
def readonly():
    """A connection whose transaction refuses every write: the AI data layer reads through this only."""
    with database() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        yield conn
