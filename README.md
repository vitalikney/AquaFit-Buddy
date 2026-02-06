# Telegram Bot: Water, Calories, Activity Tracker

Учебный проект: Telegram-бот для расчета нормы воды и калорий, логирования воды/еды/тренировок и просмотра прогресса.

## Возможности

- Настройка профиля: вес, рост, возраст, активность, город, цель калорий.
- Расчет нормы воды с учетом активности и температуры (OpenWeather).
- Расчет нормы калорий по формуле (Mifflin-St Jeor + бонус активности).
- Логирование воды, еды (через OpenFoodFacts), тренировок.
- Просмотр прогресса по воде и калориям.

## Требования

- Python 3.10+
- Telegram Bot Token
- (опционально) OpenWeather API key

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Переменные окружения

```bash
export TELEGRAM_BOT_TOKEN="ВАШ_ТОКЕН"
# опционально для погоды
export OPENWEATHER_API_KEY="ВАШ_КЛЮЧ"
```

## Запуск

```bash
python bot.py
```

## Команды бота

- `/start` — справка
- `/set_profile` — настройка профиля
- `/log_water <мл>` — добавить воду
- `/log_food <продукт>` — добавить еду
- `/log_workout <тип> <мин>` — добавить тренировку
- `/check_progress` — посмотреть прогресс
- `/cancel` — отмена текущего диалога

## Пример сценария

```
/set_profile
80
184
26
45
Moscow
0

/log_water 500
/log_food банан
150
/log_workout бег 30
/check_progress
```

## Структура проекта

- `bot.py` — логика Telegram-бота
- `requirements.txt` — зависимости
- `README.md` — описание проекта

## Примечания

- Данные пользователей хранятся в памяти (без БД).
- Ключи и токены не храните в репозитории.
