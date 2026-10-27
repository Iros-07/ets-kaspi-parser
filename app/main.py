import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import fetch_all, fetch_one

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

app = FastAPI()
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

@app.get("/", response_class=HTMLResponse)
def trades(request: Request):
    total_row = fetch_one("SELECT COUNT(*) AS n FROM trades")
    total = total_row["n"] if total_row else 0

    rows = fetch_all(
        """
        SELECT trade_date, exchange, product_name, buyer_name, seller_name,
               price_avg, amount
        FROM trades
        ORDER BY trade_date DESC, id DESC
        """
    )

    return templates.TemplateResponse(
        request=request,
        name="trades.html",
        context={
            "tab": "trades",
            "rows": rows,
            "total": total,
        },
    )


@app.get("/journal", response_class=HTMLResponse)
def journal(request: Request):
    try:
        rows = fetch_all(
            """
            SELECT id, started_at, finished_at, exchange, fetched, added,
                   status, error_text
            FROM sync_log
            ORDER BY id DESC
            LIMIT 100
            """
        )
    except Exception:
        rows = []

    return templates.TemplateResponse(
        request=request,
        name="journal.html",
        context={"tab": "journal", "rows": rows},
    )


@app.get("/status", response_class=HTMLResponse)
def status(request: Request):
    total = fetch_one("SELECT COUNT(*) AS n FROM trades")
    by_ex = fetch_all(
        "SELECT exchange, COUNT(*) AS n FROM trades GROUP BY exchange ORDER BY exchange"
    )
    last_dates = fetch_all(
        """
        SELECT exchange, MAX(trade_date) AS last_date
        FROM trades
        GROUP BY exchange
        ORDER BY exchange
        """
    )
    try:
        last_runs = fetch_all(
            """
            SELECT DISTINCT ON (exchange)
                exchange, finished_at, added, status, error_text
            FROM sync_log
            ORDER BY exchange, id DESC
            """
        )
    except Exception:
        last_runs = []

    return templates.TemplateResponse(
        request=request,
        name="status.html",
        context={
            "tab": "status",
            "total": total["n"] if total else 0,
            "by_ex": by_ex,
            "last_dates": last_dates,
            "last_runs": last_runs,
        },
    )


@app.post("/sync")
def sync():
    subprocess.run(
        [sys.executable, str(SCRIPTS / "sync_db.py")],
        cwd=str(SCRIPTS),
        check=False,
    )
    return RedirectResponse(url="/journal", status_code=303)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
