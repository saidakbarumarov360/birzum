import os

# Bot tokenni shu yerga yozing yoki BOT_TOKEN environment o'zgaruvchisi orqali bering.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8647782932:AAFHZv3kxVmfTROc9OZn0bj0TIYFjSOS1UA")

# Boshlang'ich adminlar ro'yxati (Telegram ID lar).
# Bot birinchi marta ishga tushganda bu ID lar admins jadvaliga avtomatik qo'shiladi.
ADMINS = [
    5921153725,
    1906154974
]

DB_PATH = "bot.db"
