import logging
import random
import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from dotenv import load_dotenv
from questions import questions

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")
RESULT_RECIPIENTS = [int(uid) for uid in os.getenv("RESULT_RECIPIENTS").split(",")]

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
logging.basicConfig(level=logging.INFO)

user_data = {}

@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id] = {}  # Сбрасываем все старые данные, включая имя
    await message.answer("Пожалуйста, введите ваше имя перед началом теста:")

@dp.message_handler(lambda message: message.from_user.id in user_data and "name" not in user_data[message.from_user.id])
async def receive_name(message: types.Message):
    user_id = message.from_user.id
    name = message.text.strip()
    user_data[user_id]["name"] = name
    await message.answer(f"Спасибо, {name}! Начинаем тест.")
    await begin_test(user_id, message)

async def begin_test(user_id, message):
    selected_questions = random.sample(questions, 10)
    user_data[user_id].update({
        "questions": selected_questions,
        "current": 0,
        "score": 0
    })

    await message.answer("У вас есть 5 минут на прохождение теста.")
    asyncio.create_task(start_timer(user_id, 5 * 60))
    await send_question(user_id)

async def send_question(user_id):
    data = user_data.get(user_id)
    if data is None:
        return

    if data["current"] >= len(data["questions"]):
        return await finish_test(user_id)

    q = data["questions"][data["current"]].copy()
    progress = f"Вопрос {data['current'] + 1} из {len(data['questions'])}"

    options = q["options"].copy()
    random.shuffle(options)
    buttons = [[InlineKeyboardButton(text=opt, callback_data=opt)] for opt in options]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    q["shuffled_options"] = options
    q["original_correct"] = q["correct"]
    q["correct"] = q["correct"]
    data["questions"][data["current"]] = q

    try:
        if len(q["images"]) == 1:
            with open(q["images"][0], "rb") as f:
                await bot.send_photo(chat_id=user_id, photo=f, caption=f"{progress}\n{q['question']}", reply_markup=markup)
        elif len(q["images"]) > 1:
            media = [InputMediaPhoto(open(img, "rb")) for img in q["images"]]
            await bot.send_media_group(chat_id=user_id, media=media)
            await bot.send_message(chat_id=user_id, text=f"{progress}\n{q['question']}", reply_markup=markup)
        else:
            await bot.send_message(chat_id=user_id, text=f"{progress}\n{q['question']}", reply_markup=markup)
    except Exception as e:
        await bot.send_message(chat_id=user_id, text=f"Ошибка при загрузке изображений: {e}")
        return

@dp.callback_query_handler()
async def handle_answer(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = user_data.get(user_id)
    if not data or data["current"] >= len(data["questions"]):
        return

    q = data["questions"][data["current"]]
    selected = callback.data

    await callback.message.edit_reply_markup(reply_markup=None)

    if selected == q["correct"]:
        data["score"] += 1
        feedback = f"✅ Верно! Это был {q['correct']}"
    else:
        feedback = f"❌ Неверно. Правильный ответ: {q['correct']}"

    await callback.answer()
    await bot.send_message(user_id, feedback)
    data["current"] += 1

    await asyncio.sleep(1.5)
    await send_question(user_id)

async def finish_test(user_id):
    data = user_data.get(user_id)
    if not data:
        return

    name = data.get("name", f"ID {user_id}")
    score = data["score"]
    result_text = f"{name} завершил тест: {score}/10"

    if score == 10:
        grade = "Отлично! 💯"
    elif score >= 8:
        grade = "Очень хорошо ✅"
    elif score >= 6:
        grade = "Хорошо 👍"
    elif score >= 4:
        grade = "Удовлетворительно ☑️"
    else:
        grade = "Плохо ❌"

    final_text = f"{result_text}\n{grade}"
    await bot.send_message(chat_id=user_id, text=final_text, reply_markup=InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔁 Пройти тест снова", callback_data="restart")]]
    ))

    for uid in RESULT_RECIPIENTS:
        await bot.send_message(uid, result_text)

@dp.callback_query_handler(lambda c: c.data == "restart")
async def handle_restart(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data[user_id] = {}  # сбрасываем всё
    await callback.message.delete()
    await bot.send_message(user_id, "Пожалуйста, введите ваше имя перед повторным прохождением теста:")

async def start_timer(user_id, timeout):
    await asyncio.sleep(timeout)
    if user_id in user_data and user_data[user_id].get("current", 0) < len(user_data[user_id]["questions"]):
        await bot.send_message(user_id, "⏰ Время вышло! Завершаем тест.")
        await finish_test(user_id)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
