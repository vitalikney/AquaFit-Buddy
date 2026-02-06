import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN_FILE = os.getenv("TELEGRAM_BOT_TOKEN_FILE", "bot_token.txt")


def read_token_from_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            token = handle.read().strip()
            return token or None
    except OSError:
        return None


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or read_token_from_file(TOKEN_FILE)
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

SET_WEIGHT, SET_HEIGHT, SET_AGE, SET_ACTIVITY, SET_CITY, SET_CAL_GOAL = range(6)
FOOD_GRAMS = 10


@dataclass
class PendingFood:
    name: str
    kcal_per_100g: float


users: Dict[int, dict] = {}


def get_user(user_id: int) -> dict:
    return users.setdefault(
        user_id,
        {
            "weight": None,
            "height": None,
            "age": None,
            "activity": None,
            "city": None,
            "water_goal": None,
            "calorie_goal": None,
            "logged_water": 0.0,
            "logged_calories": 0.0,
            "burned_calories": 0.0,
            "pending_food": None,
        },
    )


def parse_float(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def get_temperature_c(city: str) -> Optional[float]:
    if not OPENWEATHER_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data["main"]["temp"])
    except Exception as exc:  # noqa: BLE001 - keep simple for homework
        logger.warning("Weather fetch failed: %s", exc)
        return None


def calc_water_goal(weight: float, activity_min: float, temp_c: Optional[float]) -> float:
    base = weight * 30.0
    activity_bonus = 500.0 * (activity_min // 30)
    heat_bonus = 0.0
    if temp_c is not None:
        if temp_c > 30:
            heat_bonus = 1000.0
        elif temp_c > 25:
            heat_bonus = 500.0
    return base + activity_bonus + heat_bonus


def calc_calorie_goal(weight: float, height: float, age: float, activity_min: float) -> float:
    base = 10 * weight + 6.25 * height - 5 * age
    if activity_min <= 30:
        activity_bonus = 200
    elif activity_min <= 60:
        activity_bonus = 300
    else:
        activity_bonus = 400
    return base + activity_bonus


def calc_workout_burned(workout_type: str, minutes: float, weight: float) -> float:
    per_min = {
        "run": 10,
        "running": 10,
        "jog": 8,
        "walk": 4,
        "walking": 4,
        "bike": 8,
        "cycling": 8,
        "swim": 9,
        "gym": 6,
        "hiit": 12,
        "yoga": 3,
    }.get(workout_type.lower(), 5)
    return minutes * per_min * (weight / 70.0)


def search_food_kcal(food_name: str) -> Optional[PendingFood]:
    try:
        resp = requests.get(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": food_name,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        products = data.get("products", [])
        if not products:
            return None
        product = products[0]
        name = product.get("product_name") or food_name
        nutriments = product.get("nutriments", {})
        kcal = nutriments.get("energy-kcal_100g")
        if kcal is None:
            energy_kj = nutriments.get("energy_100g")
            if energy_kj is not None:
                kcal = float(energy_kj) * 0.239006
        if kcal is None:
            return None
        return PendingFood(name=name, kcal_per_100g=float(kcal))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Food fetch failed: %s", exc)
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! Я помогу рассчитать норму воды и калорий, "
        "а также вести трекинг.\n\n"
        "Команды:\n"
        "/set_profile - настроить профиль\n"
        "/log_water <мл> - добавить воду\n"
        "/log_food <продукт> - добавить еду\n"
        "/log_workout <тип> <мин> - добавить тренировку\n"
        "/check_progress - прогресс"
    )
    await update.message.reply_text(text)


async def set_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Введите ваш вес (в кг):")
    return SET_WEIGHT


async def set_weight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = parse_float(update.message.text)
    if value is None or value <= 0:
        await update.message.reply_text("Нужно число > 0. Повторите ввод веса.")
        return SET_WEIGHT
    context.user_data["weight"] = value
    await update.message.reply_text("Введите ваш рост (в см):")
    return SET_HEIGHT


async def set_height(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = parse_float(update.message.text)
    if value is None or value <= 0:
        await update.message.reply_text("Нужно число > 0. Повторите ввод роста.")
        return SET_HEIGHT
    context.user_data["height"] = value
    await update.message.reply_text("Введите ваш возраст:")
    return SET_AGE


async def set_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = parse_float(update.message.text)
    if value is None or value <= 0:
        await update.message.reply_text("Нужно число > 0. Повторите ввод возраста.")
        return SET_AGE
    context.user_data["age"] = value
    await update.message.reply_text("Сколько минут активности у вас в день?")
    return SET_ACTIVITY


async def set_activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = parse_float(update.message.text)
    if value is None or value < 0:
        await update.message.reply_text("Нужно число >= 0. Повторите ввод активности.")
        return SET_ACTIVITY
    context.user_data["activity"] = value
    await update.message.reply_text("В каком городе вы находитесь?")
    return SET_CITY


async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    city = update.message.text.strip()
    if not city:
        await update.message.reply_text("Введите название города текстом.")
        return SET_CITY
    context.user_data["city"] = city
    await update.message.reply_text(
        "Если хотите задать цель по калориям вручную, отправьте число. "
        "Иначе отправьте 0 для автоподбора."
    )
    return SET_CAL_GOAL


async def set_cal_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    data = get_user(user_id)

    weight = context.user_data["weight"]
    height = context.user_data["height"]
    age = context.user_data["age"]
    activity = context.user_data["activity"]
    city = context.user_data["city"]

    manual_goal = parse_float(update.message.text)
    if manual_goal is None or manual_goal < 0:
        await update.message.reply_text("Нужно число >= 0. Повторите ввод цели.")
        return SET_CAL_GOAL

    temp_c = get_temperature_c(city)
    water_goal = calc_water_goal(weight, activity, temp_c)
    calorie_goal = manual_goal if manual_goal > 0 else calc_calorie_goal(weight, height, age, activity)

    data.update(
        {
            "weight": weight,
            "height": height,
            "age": age,
            "activity": activity,
            "city": city,
            "water_goal": water_goal,
            "calorie_goal": calorie_goal,
        }
    )

    weather_note = (
        f"Температура в городе {city}: {temp_c:.1f}°C. "
        if temp_c is not None
        else "Температура не определена (нет ключа или ошибка API). "
    )

    await update.message.reply_text(
        "Профиль сохранен!\n"
        f"{weather_note}"
        f"Норма воды: {water_goal:.0f} мл.\n"
        f"Норма калорий: {calorie_goal:.0f} ккал."
    )
    context.user_data.clear()
    return ConversationHandler.END


async def log_water(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    data = get_user(user_id)
    if data["weight"] is None:
        await update.message.reply_text("Сначала настройте профиль: /set_profile")
        return

    if not context.args:
        await update.message.reply_text("Использование: /log_water <мл>")
        return

    amount = parse_float(context.args[0])
    if amount is None or amount <= 0:
        await update.message.reply_text("Введите количество воды в мл (число > 0).")
        return

    data["logged_water"] += amount
    remaining = max(data["water_goal"] - data["logged_water"], 0)
    await update.message.reply_text(
        f"Записано: {amount:.0f} мл. Осталось: {remaining:.0f} мл до нормы."
    )


async def log_food(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    data = get_user(user_id)
    if data["weight"] is None:
        await update.message.reply_text("Сначала настройте профиль: /set_profile")
        return ConversationHandler.END

    if not context.args:
        await update.message.reply_text("Использование: /log_food <название продукта>")
        return ConversationHandler.END

    food_name = " ".join(context.args).strip()
    pending = search_food_kcal(food_name)
    if pending is None:
        await update.message.reply_text("Не нашел продукт или калорийность. Попробуйте другой запрос.")
        return ConversationHandler.END

    data["pending_food"] = pending
    await update.message.reply_text(
        f"{pending.name} — {pending.kcal_per_100g:.0f} ккал на 100 г. Сколько грамм вы съели?"
    )
    return FOOD_GRAMS


async def log_food_grams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    data = get_user(user_id)
    pending: Optional[PendingFood] = data.get("pending_food")
    if pending is None:
        await update.message.reply_text("Нет активного продукта. Введите /log_food <продукт>.")
        return ConversationHandler.END

    grams = parse_float(update.message.text)
    if grams is None or grams <= 0:
        await update.message.reply_text("Введите граммы числом > 0.")
        return FOOD_GRAMS

    kcal = pending.kcal_per_100g * grams / 100.0
    data["logged_calories"] += kcal
    data["pending_food"] = None
    await update.message.reply_text(f"Записано: {kcal:.1f} ккал.")
    return ConversationHandler.END


async def log_workout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    data = get_user(user_id)
    if data["weight"] is None:
        await update.message.reply_text("Сначала настройте профиль: /set_profile")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Использование: /log_workout <тип> <мин>")
        return

    workout_type = context.args[0]
    minutes = parse_float(context.args[1])
    if minutes is None or minutes <= 0:
        await update.message.reply_text("Минуты должны быть числом > 0.")
        return

    burned = calc_workout_burned(workout_type, minutes, data["weight"])
    data["burned_calories"] += burned

    extra_water = 200 * (minutes // 30)
    await update.message.reply_text(
        f"Тренировка: {workout_type} {minutes:.0f} мин — {burned:.0f} ккал. "
        f"Дополнительно: выпейте {extra_water:.0f} мл воды."
    )


async def check_progress(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    data = get_user(user_id)
    if data["weight"] is None:
        await update.message.reply_text("Сначала настройте профиль: /set_profile")
        return

    water_goal = data["water_goal"]
    water_left = max(water_goal - data["logged_water"], 0)

    calorie_goal = data["calorie_goal"]
    consumed = data["logged_calories"]
    burned = data["burned_calories"]
    net = consumed - burned
    remaining = max(calorie_goal - net, 0)

    text = (
        "📊 Прогресс:\n"
        "Вода:\n"
        f"- Выпито: {data['logged_water']:.0f} мл из {water_goal:.0f} мл.\n"
        f"- Осталось: {water_left:.0f} мл.\n\n"
        "Калории:\n"
        f"- Потреблено: {consumed:.0f} ккал из {calorie_goal:.0f} ккал.\n"
        f"- Сожжено: {burned:.0f} ккал.\n"
        f"- Баланс: {net:.0f} ккал.\n"
        f"- Осталось до цели: {remaining:.0f} ккал."
    )
    await update.message.reply_text(text)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN env var")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    profile_conv = ConversationHandler(
        entry_points=[CommandHandler("set_profile", set_profile)],
        states={
            SET_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_weight)],
            SET_HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_height)],
            SET_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_age)],
            SET_ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_activity)],
            SET_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_city)],
            SET_CAL_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_cal_goal)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    food_conv = ConversationHandler(
        entry_points=[CommandHandler("log_food", log_food)],
        states={
            FOOD_GRAMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_food_grams)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(profile_conv)
    app.add_handler(CommandHandler("log_water", log_water))
    app.add_handler(food_conv)
    app.add_handler(CommandHandler("log_workout", log_workout))
    app.add_handler(CommandHandler("check_progress", check_progress))

    app.run_polling()


if __name__ == "__main__":
    main()
