# парсер Каспий - просто печатает таблицу в терминал
import requests
from bs4 import BeautifulSoup
from tabulate import tabulate

URL = "https://ccx.kz/trading-and-analytics/trading-results?lang=ru"
HEADERS = {"User-Agent": "Mozilla/5.0"}

otvet = requests.get(URL, headers=HEADERS, timeout=30)
otvet.raise_for_status()

soup = BeautifulSoup(otvet.text, "lxml")
tablica = soup.find("table")

if tablica is None:
    print("таблица не найдена")
    raise SystemExit(1)

rows = []
stroki = tablica.find_all("tr")

nomer = 0
for tr in stroki:
    nomer = nomer + 1
    if nomer == 1:
        # заголовок пропускаем
        continue

    yacheyki = tr.find_all("td")
    if len(yacheyki) < 16:
        continue

    cols = []
    for td in yacheyki:
        cols.append(td.get_text(" ", strip=True))

    data = cols[0]
    tovar = cols[3]
    cena = cols[8]
    summa = cols[9]
    pokupatel = cols[11]
    prodavec = cols[13]

    if "итого" in tovar.lower():
        continue

    if len(tovar) > 45:
        tovar = tovar[0:44] + "..."

    if len(pokupatel) > 28:
        pokupatel = pokupatel[0:27] + "..."

    if len(prodavec) > 28:
        prodavec = prodavec[0:27] + "..."

    cena = cena.replace(" ", "")
    summa = summa.replace(" ", "")

    rows.append([data, tovar, pokupatel, prodavec, cena, summa])

print("страница:", URL)
print()
print("=== Каспий ===")
print()
print(
    tabulate(
        rows,
        headers=["Дата", "Товар", "Покупатель", "Продавец", "Цена ср.", "Сумма"],
        tablefmt="github",
    )
)
print()
print("Строк:", len(rows))
