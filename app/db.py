import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from db_config import DB


def get_conn():
    return psycopg2.connect(**DB)


def fetch_all(sql, params=None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def fetch_one(sql, params=None):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None
