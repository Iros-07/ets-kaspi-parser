# простые функции для запросов к postgres
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

# db_config лежит в папке scripts
put_k_scripts = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(put_k_scripts))

from db_config import DB


def podkluchitsya():
    conn = psycopg2.connect(
        host=DB["host"],
        port=DB["port"],
        user=DB["user"],
        password=DB["password"],
        dbname=DB["dbname"],
    )
    return conn


def vzyat_vse(sql, params=None):
    if params is None:
        params = ()

    conn = podkluchitsya()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def vzyat_odnu(sql, params=None):
    rows = vzyat_vse(sql, params)

    if len(rows) == 0:
        return None

    return rows[0]
