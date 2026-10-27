# качает данные с ETS и Каспий и кладёт в postgres
# если такая сделка уже есть - не добавляет второй раз

import hashlib
import io
import re
from datetime import datetime
from urllib.parse import urljoin

import psycopg2
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook

from db_config import DB

HEADERS = {"User-Agent": "Mozilla/5.0"}
ETS_URL = "https://ets.kz/documents/trading-results/"
KASPI_URL = "https://ccx.kz/trading-and-analytics/trading-results?lang=ru"


def soedinit_s_postgres():
    # сначала к системной базе, чтобы можно было создать нашу
    conn = psycopg2.connect(
        host=DB["host"],
        port=DB["port"],
        user=DB["user"],
        password=DB["password"],
        dbname="postgres",
    )
    return conn


def sozdat_bazu_esli_net():
    conn = soedinit_s_postgres()
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s",
        (DB["dbname"],),
    )
    est = cur.fetchone()

    if est is None:
        imya = DB["dbname"]
        cur.execute('CREATE DATABASE "' + imya + '"')
        print("создал базу:", imya)

    cur.close()
    conn.close()


def soedinit_s_trades():
    sozdat_bazu_esli_net()

    conn = psycopg2.connect(
        host=DB["host"],
        port=DB["port"],
        user=DB["user"],
        password=DB["password"],
        dbname=DB["dbname"],
    )
    cur = conn.cursor()

    # таблица сделок
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (
            id SERIAL PRIMARY KEY,
            exchange TEXT NOT NULL,
            trade_date DATE NOT NULL,
            product_name TEXT,
            tnved TEXT,
            product_code TEXT,
            buyer_name TEXT,
            buyer_bin TEXT,
            buyer_broker TEXT,
            seller_name TEXT,
            seller_bin TEXT,
            seller_broker TEXT,
            deals_count INTEGER,
            price_avg NUMERIC,
            amount NUMERIC,
            delivery TEXT,
            uniq_key TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_trades_exchange ON trades(exchange)"
    )

    # таблица журнала (когда запускали парсер)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_log (
            id SERIAL PRIMARY KEY,
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            exchange TEXT NOT NULL,
            fetched INTEGER DEFAULT 0,
            added INTEGER DEFAULT 0,
            status TEXT NOT NULL,
            error_text TEXT
        )
        """
    )

    conn.commit()
    cur.close()
    return conn


def data_dlya_bd(data_tekst):
    # сайт даёт 20.10.2026, в бд удобнее 2026-10-20
    data_tekst = str(data_tekst).strip()
    chasti = data_tekst.split(".")

    if len(chasti) != 3:
        return data_tekst

    den = chasti[0]
    mesyac = chasti[1]
    god = chasti[2]
    return god + "-" + mesyac + "-" + den


def ochistit_tekst(znachenie):
    if znachenie is None:
        return None

    tekst = str(znachenie)
    tekst = tekst.replace("\n", " ")
    tekst = tekst.replace("\t", " ")

    # убрать лишние пробелы
    while "  " in tekst:
        tekst = tekst.replace("  ", " ")

    tekst = tekst.strip()

    if tekst == "":
        return None

    return tekst


def ochistit_chislo(znachenie):
    if znachenie is None:
        return None

    if znachenie == "":
        return None

    if znachenie == "-":
        return None

    # если уже число
    if type(znachenie) == int or type(znachenie) == float:
        return float(znachenie)

    tekst = str(znachenie)
    tekst = tekst.replace(" ", "")
    tekst = tekst.replace("\xa0", "")
    tekst = tekst.replace(",", ".")

    try:
        return float(tekst)
    except ValueError:
        return None


def razdelit_imya_i_bin(tekst):
    # иногда приходит: ТОО Санас 090240015942
    tekst = ochistit_tekst(tekst)

    if tekst is None:
        return None, None

    chasti = tekst.split(" ")
    if len(chasti) < 2:
        return tekst, None

    poslednee = chasti[-1]

    # бин обычно 12 цифр
    if len(poslednee) == 12 and poslednee.isdigit():
        imya = " ".join(chasti[:-1])
        return imya, poslednee

    return tekst, None


def sdelat_klyuch(stroka):
    # ключ чтобы понять что сделка уже есть в базе
    def kusok(imya):
        znachenie = stroka.get(imya)
        if znachenie is None:
            return ""
        return str(znachenie)

    kuski = []
    kuski.append(kusok("exchange"))
    kuski.append(kusok("trade_date"))
    kuski.append(kusok("product_name"))
    kuski.append(kusok("product_code"))
    kuski.append(kusok("buyer_name"))
    kuski.append(kusok("buyer_bin"))
    kuski.append(kusok("seller_name"))
    kuski.append(kusok("seller_bin"))
    kuski.append(kusok("price_avg"))
    kuski.append(kusok("amount"))
    kuski.append(kusok("delivery"))

    raw = "|".join(kuski)
    raw = raw.lower()

    hesh = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return hesh


def sohranit_v_bd(conn, spisok):
    sql = """
        INSERT INTO trades (
            exchange, trade_date, product_name, tnved, product_code,
            buyer_name, buyer_bin, buyer_broker,
            seller_name, seller_bin, seller_broker,
            deals_count, price_avg, amount, delivery, uniq_key
        ) VALUES (
            %(exchange)s, %(trade_date)s, %(product_name)s, %(tnved)s, %(product_code)s,
            %(buyer_name)s, %(buyer_bin)s, %(buyer_broker)s,
            %(seller_name)s, %(seller_bin)s, %(seller_broker)s,
            %(deals_count)s, %(price_avg)s, %(amount)s, %(delivery)s, %(uniq_key)s
        )
        ON CONFLICT (uniq_key) DO NOTHING
    """

    dobavleno = 0
    cur = conn.cursor()

    for odna in spisok:
        odna["uniq_key"] = sdelat_klyuch(odna)
        cur.execute(sql, odna)
        dobavleno = dobavleno + cur.rowcount

    conn.commit()
    cur.close()
    return dobavleno


def poluchit_html(url):
    otvet = requests.get(url, headers=HEADERS, timeout=30)
    otvet.raise_for_status()
    html = BeautifulSoup(otvet.text, "lxml")
    return html


def nayti_ssylku_na_god(soup):
    year_url = None
    ssylki = soup.find_all("a", href=True)

    for a in ssylki:
        tekst = a.get_text(" ", strip=True)
        # пример: Итоги торгов 2026 год
        if "Итоги торгов" in tekst and "год" in tekst:
            # без названия месяца
            if "январ" in tekst.lower():
                continue
            if "феврал" in tekst.lower():
                continue
            if "март" in tekst.lower():
                continue
            if "апрел" in tekst.lower():
                continue
            if "май" in tekst.lower() or "мая" in tekst.lower():
                continue
            if "июн" in tekst.lower():
                continue
            if "июл" in tekst.lower():
                continue
            if "август" in tekst.lower():
                continue
            if "сентябр" in tekst.lower():
                continue
            if "октябр" in tekst.lower():
                continue
            if "ноябр" in tekst.lower():
                continue
            if "декабр" in tekst.lower():
                continue

            year_url = urljoin(ETS_URL, a["href"])

    return year_url


def nayti_mesyacy(soup, year_url):
    mesyacy = []
    ssylki = soup.find_all("a", href=True)

    for a in ssylki:
        tekst = a.get_text(" ", strip=True)
        if "Итоги торгов" not in tekst:
            continue

        # ищем месяц в конце: ... 2026 год Октябрь
        chasti = tekst.split(" ")
        if len(chasti) < 5:
            continue

        # если это просто "Итоги торгов 2026 год" без месяца - пропуск
        if tekst.strip().endswith("год"):
            continue

        mesyac_imya = chasti[-1]
        ssylka = urljoin(year_url, a["href"])
        mesyacy.append([mesyac_imya, ssylka])

    return mesyacy


def nayti_excel_fayly(soup, month_url):
    fayly = []
    uzhe_byl = []
    ssylki = soup.find_all("a", href=True)

    for a in ssylki:
        href = a["href"]
        href_niz = href.lower()

        if ".xls" not in href_niz:
            continue

        polnaya = urljoin(month_url, href)

        if polnaya in uzhe_byl:
            continue

        uzhe_byl.append(polnaya)

        # дата часто написана рядом с ссылкой
        roditel = a.find_parent("li")
        if roditel is None:
            roditel = a.find_parent("div")
        if roditel is None:
            roditel = a.find_parent("p")

        if roditel is not None:
            podpis = roditel.get_text(" ", strip=True)
        else:
            podpis = ""

        data = "?"
        naydeno = re.search(r"(\d{2}\.\d{2}\.\d{4})", podpis)
        if naydeno:
            data = naydeno.group(1)

        fayly.append([data, polnaya])

    return fayly


def skachat_ets():
    print("ETS: открываю сайт...")
    soup = poluchit_html(ETS_URL)

    year_url = nayti_ssylku_na_god(soup)
    print("ETS год:", year_url)

    soup = poluchit_html(year_url)
    mesyacy = nayti_mesyacy(soup, year_url)

    if len(mesyacy) == 0:
        print("ETS: месяцы не нашёл")
        return []

    # берём последний месяц в списке
    posledniy = mesyacy[len(mesyacy) - 1]
    month_name = posledniy[0]
    month_url = posledniy[1]
    print("ETS месяц:", month_name, month_url)

    soup = poluchit_html(month_url)
    fayly = nayti_excel_fayly(soup, month_url)

    if len(fayly) == 0:
        print("ETS: excel не нашёл")
        return []

    posledniy_fayl = fayly[len(fayly) - 1]
    data = posledniy_fayl[0]
    file_url = posledniy_fayl[1]
    print("ETS файл:", data, file_url)

    otvet = requests.get(file_url, headers=HEADERS, timeout=60)
    fayl_v_pamyati = io.BytesIO(otvet.content)
    kniga = load_workbook(fayl_v_pamyati, data_only=True)
    list_excel = kniga.active

    rezultat = []

    for row in list_excel.iter_rows(min_row=5, values_only=True):
        pokupatel = row[1]
        bin_pokupatelya = row[2]
        broker_pokupatelya = row[3]
        prodavec = row[4]
        bin_prodavca = row[5]
        broker_prodavca = row[6]
        tovar = row[7]
        tnved = row[8]
        kod_tovara = row[9]
        kolichestvo_sdelok = row[10]
        cena = row[15]
        summa = row[16]

        if tovar is None:
            continue

        if str(tovar).strip().lower() == "итого":
            continue

        kolvo = None
        if kolichestvo_sdelok is not None:
            kolvo = int(kolichestvo_sdelok)

        odna = {}
        odna["exchange"] = "ETS"
        odna["trade_date"] = data_dlya_bd(data)
        odna["product_name"] = ochistit_tekst(tovar)
        odna["tnved"] = ochistit_tekst(tnved)
        odna["product_code"] = ochistit_tekst(kod_tovara)
        odna["buyer_name"] = ochistit_tekst(pokupatel)
        odna["buyer_bin"] = ochistit_tekst(bin_pokupatelya)
        odna["buyer_broker"] = ochistit_tekst(broker_pokupatelya)
        odna["seller_name"] = ochistit_tekst(prodavec)
        odna["seller_bin"] = ochistit_tekst(bin_prodavca)
        odna["seller_broker"] = ochistit_tekst(broker_prodavca)
        odna["deals_count"] = kolvo
        odna["price_avg"] = ochistit_chislo(cena)
        odna["amount"] = ochistit_chislo(summa)
        odna["delivery"] = None

        rezultat.append(odna)

    return rezultat


def skachat_kaspi():
    print("Каспий: открываю сайт...")
    otvet = requests.get(KASPI_URL, headers=HEADERS, timeout=30)
    otvet.raise_for_status()

    soup = BeautifulSoup(otvet.text, "lxml")
    tablica = soup.find("table")

    if tablica is None:
        print("Каспий: таблицы нет")
        return []

    rezultat = []
    stroki = tablica.find_all("tr")

    # 0 строка - заголовок, начинаем с 1
    nomer = 0
    for tr in stroki:
        nomer = nomer + 1
        if nomer == 1:
            continue

        yacheyki = tr.find_all("td")
        if len(yacheyki) < 16:
            continue

        cols = []
        for td in yacheyki:
            cols.append(td.get_text(" ", strip=True))

        data = cols[0]
        tnved = cols[2]
        tovar = cols[3]
        cena = cols[8]
        summa = cols[9]
        broker_pokupatelya = cols[10]
        pokupatel = cols[11]
        broker_prodavca = cols[12]
        prodavec = cols[13]
        kolvo_tekst = cols[14]
        postavka = cols[15]

        if "итого" in tovar.lower():
            continue

        imya_pok, bin_pok = razdelit_imya_i_bin(pokupatel)
        imya_prod, bin_prod = razdelit_imya_i_bin(prodavec)

        if tnved == "-":
            tnved = None

        if postavka == "-":
            postavka = None

        kolvo = ochistit_chislo(kolvo_tekst)
        if kolvo is not None:
            kolvo = int(kolvo)

        odna = {}
        odna["exchange"] = "Каспий"
        odna["trade_date"] = data_dlya_bd(data)
        odna["product_name"] = ochistit_tekst(tovar)
        odna["tnved"] = ochistit_tekst(tnved)
        odna["product_code"] = None
        odna["buyer_name"] = imya_pok
        odna["buyer_bin"] = bin_pok
        odna["buyer_broker"] = ochistit_tekst(broker_pokupatelya)
        odna["seller_name"] = imya_prod
        odna["seller_bin"] = bin_prod
        odna["seller_broker"] = ochistit_tekst(broker_prodavca)
        odna["deals_count"] = kolvo
        odna["price_avg"] = ochistit_chislo(cena)
        odna["amount"] = ochistit_chislo(summa)
        odna["delivery"] = ochistit_tekst(postavka)

        rezultat.append(odna)

    return rezultat


def zapisat_v_zhurnal_ok(conn, birzha, nachalo, skolko_poluchili, skolko_dobavili):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sync_log (
            started_at, finished_at, exchange, fetched, added, status, error_text
        ) VALUES (%s, NOW(), %s, %s, %s, 'ok', NULL)
        """,
        (nachalo, birzha, skolko_poluchili, skolko_dobavili),
    )
    conn.commit()
    cur.close()


def zapisat_v_zhurnal_oshibka(conn, birzha, nachalo, tekst_oshibki):
    if tekst_oshibki is None:
        tekst_oshibki = ""

    # чтоб не писать огромный текст
    if len(tekst_oshibki) > 2000:
        tekst_oshibki = tekst_oshibki[0:2000]

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sync_log (
            started_at, finished_at, exchange, fetched, added, status, error_text
        ) VALUES (%s, NOW(), %s, 0, 0, 'error', %s)
        """,
        (nachalo, birzha, tekst_oshibki),
    )
    conn.commit()
    cur.close()


def main():
    conn = soedinit_s_trades()
    print("база:", DB["host"], DB["dbname"])

    # ----- ETS -----
    nachalo = datetime.now()
    ets_spisok = []
    ets_novyh = 0

    try:
        ets_spisok = skachat_ets()
        ets_novyh = sohranit_v_bd(conn, ets_spisok)
        zapisat_v_zhurnal_ok(conn, "ETS", nachalo, len(ets_spisok), ets_novyh)
    except Exception as oshibka:
        print("ETS ошибка:", oshibka)
        zapisat_v_zhurnal_oshibka(conn, "ETS", nachalo, str(oshibka))

    # ----- Каспий -----
    nachalo = datetime.now()
    kaspi_spisok = []
    kaspi_novyh = 0

    try:
        kaspi_spisok = skachat_kaspi()
        kaspi_novyh = sohranit_v_bd(conn, kaspi_spisok)
        zapisat_v_zhurnal_ok(
            conn, "Каспий", nachalo, len(kaspi_spisok), kaspi_novyh
        )
    except Exception as oshibka:
        print("Каспий ошибка:", oshibka)
        zapisat_v_zhurnal_oshibka(conn, "Каспий", nachalo, str(oshibka))

    # сколько всего сейчас в базе
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM trades")
    vsego = cur.fetchone()[0]

    cur.execute("SELECT exchange, COUNT(*) FROM trades GROUP BY exchange")
    po_birzham = cur.fetchall()
    cur.close()
    conn.close()

    print()
    print("ETS получено:", len(ets_spisok), "новых:", ets_novyh)
    print("Каспий получено:", len(kaspi_spisok), "новых:", kaspi_novyh)
    print("всего в базе:", vsego)
    print("по биржам:", po_birzham)


if __name__ == "__main__":
    main()
