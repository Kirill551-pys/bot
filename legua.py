import csv
import time
import cloudscraper

# Создаем скрапер с явно заданными параметрами браузера
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True,
    }
)

# Дополнительные заголовки, которые ожидает увидеть SofaScore
scraper.headers.update({
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Origin': 'https://www.sofascore.com',
    'Referer': 'https://www.sofascore.com/',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
})

OUTPUT_FILE = 'champions_league_sofascore.csv'