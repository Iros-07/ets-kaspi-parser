# сайт: сделки, журнал, статус
# запуск: py -3 main.py
import subprocess
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import vzyat_odnu, vzyat_vse

papka_scripts = Path(__file__).resolve().parent.parent / "scripts"
papka_app = Path(__file__).parent

app = FastAPI()
templates = Jinja2Templates(directory=str(papka_app / "templates"))


@app.get("/", response_class=HTMLResponse)
def stranica_sdelki(request: Request):
    # сколько всего строк
    stroka_count = vzyat_odnu("SELECT COUNT(*) AS n FROM trades")
    if stroka_count is None:
        total = 0
    else:
        total = stroka_count["n"]

    # все сделки
    rows = vzyat_vse(
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
            "rows": rows,
            "total": total,
        },
    )


@app.get("/journal", response_class=HTMLResponse)
def stranica_zhurnal(request: Request):
    try:
        rows = vzyat_vse(
            """
            SELECT id, started_at, finished_at, exchange, fetched, added,
                   status, error_text
            FROM sync_log
            ORDER BY id DESC
            LIMIT 100
            """
        )
    except Exception:
        # если таблицы ещё нет
        rows = []

    return templates.TemplateResponse(
        request=request,
        name="journal.html",
        context={
            "rows": rows,
        },
    )


@app.get("/status", response_class=HTMLResponse)
def stranica_status(request: Request):
    stroka_count = vzyat_odnu("SELECT COUNT(*) AS n FROM trades")
    if stroka_count is None:
        total = 0
    else:
        total = stroka_count["n"]

    by_ex = vzyat_vse(
        """
        SELECT exchange, COUNT(*) AS n
        FROM trades
        GROUP BY exchange
        ORDER BY exchange
        """
    )

    last_dates = vzyat_vse(
        """
        SELECT exchange, MAX(trade_date) AS last_date
        FROM trades
        GROUP BY exchange
        ORDER BY exchange
        """
    )

    # последние запуски: просто берём журнал и оставляем по 1 на биржу
    last_runs = []
    try:
        vse_zapuski = vzyat_vse(
            """
            SELECT exchange, finished_at, added, status, error_text
            FROM sync_log
            ORDER BY id DESC
            """
        )

        uzhe_est = []
        for zapusk in vse_zapuski:
            birzha = zapusk["exchange"]
            if birzha in uzhe_est:
                continue
            uzhe_est.append(birzha)
            last_runs.append(zapusk)
    except Exception:
        last_runs = []

    return templates.TemplateResponse(
        request=request,
        name="status.html",
        context={
            "total": total,
            "by_ex": by_ex,
            "last_dates": last_dates,
            "last_runs": last_runs,
        },
    )


@app.post("/sync")
def knopka_obnovit():
    # запускаем sync_db.py как отдельную программу
    put_k_failu = papka_scripts / "sync_db.py"
    subprocess.run(
        [sys.executable, str(put_k_failu)],
        cwd=str(papka_scripts),
        check=False,
    )
    return RedirectResponse(url="/journal", status_code=303)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
