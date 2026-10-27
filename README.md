# ets-kaspi-parser

Парсинг итогов торгов ETS и Каспий (CCX) в PostgreSQL + простой сайт.

## Нужно

- Python 3.10+
- PostgreSQL

## Установка

```bash
git clone https://github.com/Iros-07/ets-kaspi-parser.git
cd ets-kaspi-parser
py -3 -m pip install -r requirements.txt
```

В `scripts/db_config.py` указать хост, пользователя, пароль и имя БД.

PostgreSQL должен быть запущен. База `trades` создаётся сама при первом sync.

## Загрузка данных

```bash
cd scripts
py -3 sync_db.py
```

Отдельно в терминал (без БД):

```bash
py -3 ets_parser.py
py -3 kaspi_parser.py
```

## Сайт

```bash
cd app
py -3 main.py
```

Открыть http://127.0.0.1:8000

- `/` — сделки  
- `/journal` — журнал запусков  
- `/status` — статус  
- кнопка «Обновить» — повторный `sync_db.py`
