import io
import re
import requests
from bs4 import BeautifulSoup
from openpyxl import load_workbook
from tabulate import tabulate
from urllib.parse import urljoin

URL = "https://ets.kz/documents/trading-results/"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def get_html(url):
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


# страница итогов -> ссылка на год
soup = get_html(URL)
year_url = None
for a in soup.find_all("a", href=True):
    t = a.get_text(" ", strip=True)
    if re.search(r"Итоги торгов\s+\d{4}\s+год", t, re.I):
        year_url = urljoin(URL, a["href"])
print("год:", year_url)

# год -> месяцы
soup = get_html(year_url)
months = []
for a in soup.find_all("a", href=True):
    t = a.get_text(" ", strip=True)
    m = re.search(r"Итоги торгов\s+\d{4}\s+год\s+(\S+)", t, re.I)
    if m:
        months.append((m.group(1), urljoin(year_url, a["href"])))
month_name, month_url = months[-1]  
print("месяц:", month_name, month_url)

# месяц -> xlsx файлы
soup = get_html(month_url)
files = []
for a in soup.find_all("a", href=True):
    href = a["href"]
    if ".xls" not in href.lower():
        continue
    parent = a.find_parent(["li", "div", "p", "td"])
    text = parent.get_text(" ", strip=True) if parent else ""
    m = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
    date = m.group(1) if m else "?"
    files.append((date, urljoin(month_url, href)))

# убрать дубли
uniq = []
seen = set()
for date, link in files:
    if link not in seen:
        seen.add(link)
        uniq.append((date, link))
files = uniq

date, file_url = files[-1]
print("файл:", date, file_url)

# скачать excel
r = requests.get(file_url, headers=HEADERS, timeout=60)
wb = load_workbook(io.BytesIO(r.content), data_only=True)
ws = wb.active

# терминал
rows = []
for row in ws.iter_rows(min_row=5, values_only=True):
    buyer = row[1]
    seller = row[4]
    product = row[7]
    price = row[15]
    amount = row[16]

    if product is None:
        continue
    if str(product).strip().lower() == "итого":
        continue

    p = str(product)
    if len(p) > 48:
        p = p[:40] + "..."
    b = str(buyer or "")
    if len(b) > 28:
        b = b[:20] + "..."
    s = str(seller or "")
    if len(s) > 48:
        s = s[:40] + "..."

    rows.append([date, p, b, s, price, amount])

print()
print(f"=== ETS {date} ===")
print()
print(tabulate(
    rows,
    headers=["Дата", "Товар", "Покупатель", "Продавец", "Цена ср.", "Сумма"],
    tablefmt="github",
))
print(f"\nСтрок: {len(rows)}")