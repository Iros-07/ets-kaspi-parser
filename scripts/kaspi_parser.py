import requests
from bs4 import BeautifulSoup
from tabulate import tabulate

URL = "https://ccx.kz/trading-and-analytics/trading-results?lang=ru"
HEADERS = {"User-Agent": "Mozilla/5.0"}

r = requests.get(URL, headers=HEADERS, timeout=30)
r.raise_for_status()
soup = BeautifulSoup(r.text, "lxml")

table = soup.find("table")
if not table:
    print("таблица не найдена")
    raise SystemExit(1)

rows = []
for tr in table.find_all("tr")[1:]:
    cols = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
    if len(cols) < 16:
        continue

    date = cols[0]
    product = cols[3]
    price = cols[8]
    amount = cols[9]
    buyer = cols[11]
    seller = cols[13]

    if "итого" in product.lower():
        continue

    if len(product) > 45:
        product = product[:44] + "..."
    if len(buyer) > 28:
        buyer = buyer[:27] + "..."
    if len(seller) > 28:
        seller = seller[:27] + "..."

    price = price.replace(" ", "")
    amount = amount.replace(" ", "")

    rows.append([date, product, buyer, seller, price, amount])

print(f"страница: {URL}")
print()
print("=== Каспий (CCX) ===")
print()
print(tabulate(
    rows,
    headers=["Дата", "Товар", "Покупатель", "Продавец", "Цена ср.", "Сумма"],
    tablefmt="github",
))
print(f"\nСтрок: {len(rows)}")
