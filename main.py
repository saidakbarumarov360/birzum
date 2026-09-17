import sqlite3
import threading
from datetime import datetime, timezone

import telebot
from telebot import types

from config import BOT_TOKEN, ADMINS, DB_PATH

USERS_PAGE_LIMIT = 5

ADMIN_MENU_BUTTONS = {
    "👥 Mijozlar", "📊 Statistika", "📢 Xabar yuborish",
    "➕ Admin qo'shish", "➖ Adminni o'chirish"
}


# ======================================================================
# DATABASE
# ======================================================================

class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()
        self._seed_admins()

    # ---------- INIT ----------

    def _init_db(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    first_name TEXT,
                    last_name TEXT,
                    username TEXT,
                    phone TEXT,
                    registered_at TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    added_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    admin_id INTEGER,
                    message_type TEXT NOT NULL,
                    message_id INTEGER,
                    direction TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            self.conn.commit()

    def _seed_admins(self):
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cur = self.conn.cursor()
            for tid in ADMINS:
                cur.execute(
                    "INSERT OR IGNORE INTO admins (telegram_id, added_at) VALUES (?, ?)",
                    (tid, now)
                )
            self.conn.commit()

    # ---------- USERS ----------

    def user_exists(self, telegram_id):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
            return cur.fetchone() is not None

    def add_user(self, telegram_id, first_name, last_name, username, phone):
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO users
                (telegram_id, first_name, last_name, username, phone, registered_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (telegram_id, first_name, last_name, username, phone, now))
            self.conn.commit()

    def get_user_by_telegram_id(self, telegram_id):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def set_user_active(self, telegram_id, is_active):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "UPDATE users SET is_active = ? WHERE telegram_id = ?",
                (1 if is_active else 0, telegram_id)
            )
            self.conn.commit()

    def get_users_page(self, offset, limit):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT * FROM users ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            return [dict(r) for r in cur.fetchall()]

    def get_users_count(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) as c FROM users")
            return cur.fetchone()["c"]

    def get_active_users_count(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) as c FROM users WHERE is_active = 1")
            return cur.fetchone()["c"]

    def get_blocked_users_count(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) as c FROM users WHERE is_active = 0")
            return cur.fetchone()["c"]

    def get_today_registered_count(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT COUNT(*) as c FROM users WHERE registered_at LIKE ?",
                (f"{today}%",)
            )
            return cur.fetchone()["c"]

    def get_month_registered_count(self):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT COUNT(*) as c FROM users WHERE registered_at LIKE ?",
                (f"{month}%",)
            )
            return cur.fetchone()["c"]

    def get_all_active_users(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT telegram_id FROM users WHERE is_active = 1")
            return [r["telegram_id"] for r in cur.fetchall()]

    # ---------- ADMINS ----------

    def is_admin(self, telegram_id):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT id FROM admins WHERE telegram_id = ?", (telegram_id,))
            return cur.fetchone() is not None

    def add_admin(self, telegram_id):
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO admins (telegram_id, added_at) VALUES (?, ?)",
                (telegram_id, now)
            )
            self.conn.commit()
            return cur.rowcount > 0

    def remove_admin(self, telegram_id):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM admins WHERE telegram_id = ?", (telegram_id,))
            self.conn.commit()
            return cur.rowcount > 0

    def get_admins(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT telegram_id FROM admins")
            return [r["telegram_id"] for r in cur.fetchall()]

    # ---------- MESSAGES ----------

    def log_message(self, user_id, admin_id, message_type, message_id, direction):
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO messages (user_id, admin_id, message_type, message_id, direction, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, admin_id, message_type, message_id, direction, now))
            self.conn.commit()

    def get_user_incoming_message_count(self, user_id):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT COUNT(*) as c FROM messages WHERE user_id = ? AND direction = 'in'",
                (user_id,)
            )
            return cur.fetchone()["c"]

    def get_messages_count(self):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) as c FROM messages")
            return cur.fetchone()["c"]

    def get_direction_count(self, direction):
        with self.lock:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) as c FROM messages WHERE direction = ?", (direction,))
            return cur.fetchone()["c"]


# ======================================================================
# KEYBOARDS
# ======================================================================

def phone_request_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True))
    return kb


def admin_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("👥 Mijozlar", "📊 Statistika")
    kb.row("📢 Xabar yuborish")
    kb.row("➕ Admin qo'shish", "➖ Adminni o'chirish")
    return kb


def reply_inline_keyboard(user_telegram_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("↩️ Javob berish", callback_data=f"reply:{user_telegram_id}"))
    return kb


def users_pagination_keyboard(offset, limit, total):
    kb = types.InlineKeyboardMarkup()
    buttons = []
    if offset > 0:
        buttons.append(
            types.InlineKeyboardButton("◀️ Oldingi", callback_data=f"users_page:{max(0, offset - limit)}")
        )
    if offset + limit < total:
        buttons.append(
            types.InlineKeyboardButton("Keyingi ▶️", callback_data=f"users_page:{offset + limit}")
        )
    if buttons:
        kb.row(*buttons)
    return kb


# ======================================================================
# XABAR YUBORISH YORDAMCHI FUNKSIYALARI
# ======================================================================

def format_customer_header(user, title):
    first_name = user.get("first_name") or "-"
    last_name = user.get("last_name") or "-"
    username = f"@{user['username']}" if user.get("username") else "-"
    phone = user.get("phone") or "-"
    telegram_id = user["telegram_id"]
    return (
        f"{title}\n\n"
        f"Ism: {first_name}\n"
        f"Familiya: {last_name}\n"
        f"Telefon: {phone}\n"
        f"Username: {username}\n"
        f"Telegram ID: {telegram_id}"
    )


def send_customer_message_to_admins(bot, db, user, message):
    """Mijozdan kelgan xabarni barcha adminlarga yuboradi va log qiladi."""
    admin_ids = db.get_admins()

    is_first = db.get_user_incoming_message_count(user["id"]) == 0
    title = "👤 Yangi mijoz" if is_first else "👤 Mijozdan yangi xabar"
    header = format_customer_header(user, title)
    kb = reply_inline_keyboard(user["telegram_id"])

    for admin_id in admin_ids:
        try:
            if message.content_type == "text":
                text = f"{header}\n\n💬 Mijoz xabari:\n\n{message.text}"
                bot.send_message(admin_id, text, reply_markup=kb)
            else:
                bot.send_message(admin_id, header)
                copied = bot.copy_message(admin_id, message.chat.id, message.message_id)
                try:
                    bot.edit_message_reply_markup(
                        chat_id=admin_id, message_id=copied.message_id, reply_markup=kb
                    )
                except Exception:
                    bot.send_message(
                        admin_id,
                        "Yuqoridagi xabarga javob berish uchun bosing:",
                        reply_markup=kb
                    )
        except Exception:
            # Admin botni bloklagan bo'lishi mumkin - keyingi adminga o'tamiz
            continue

    db.log_message(user["id"], None, message.content_type, message.message_id, "in")


def deliver_admin_reply(bot, db, target_user, admin_message, admin_telegram_id):
    """Admin javobini mijozga yetkazadi. Muvaffaqiyatli bo'lsa True qaytaradi."""
    chat_id = target_user["telegram_id"]
    try:
        if admin_message.content_type == "text":
            bot.send_message(chat_id, f"👨‍💼 Admin javobi:\n\n{admin_message.text}")
        else:
            bot.send_message(chat_id, "👨‍💼 Admin javobi:")
            bot.copy_message(chat_id, admin_message.chat.id, admin_message.message_id)

        db.log_message(
            target_user["id"], admin_telegram_id,
            admin_message.content_type, admin_message.message_id, "out"
        )
        return True
    except Exception:
        db.set_user_active(chat_id, False)
        return False


# ======================================================================
# ADMIN HANDLERLAR
# ======================================================================

def register_admin_handlers(bot, db):

    def is_admin(telegram_id):
        return db.is_admin(telegram_id)

    def format_user_block(u):
        username = f"@{u['username']}" if u.get("username") else "-"
        status = "🟢 Faol" if u["is_active"] else "🔴 Bloklangan"
        registered_at = (u.get("registered_at") or "-")[:19]
        return (
            f"Ism: {u.get('first_name') or '-'}\n"
            f"Familiya: {u.get('last_name') or '-'}\n"
            f"Telefon: {u.get('phone') or '-'}\n"
            f"Telegram ID: {u['telegram_id']}\n"
            f"Username: {username}\n"
            f"Ro'yxatdan o'tgan: {registered_at}\n"
            f"Status: {status}"
        )

    def build_users_page_text_and_kb(offset):
        total = db.get_users_count()
        users = db.get_users_page(offset, USERS_PAGE_LIMIT)
        if not users:
            return "Hozircha mijozlar yo'q.", None
        blocks = [format_user_block(u) for u in users]
        text = f"👥 Mijozlar ({total} ta):\n\n" + "\n\n".join(blocks)
        kb = users_pagination_keyboard(offset, USERS_PAGE_LIMIT, total)
        return text, (kb if kb.keyboard else None)

    # ---------- ADMIN PANEL ----------

    @bot.message_handler(commands=["admin"])
    def admin_panel(message):
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "Sizda ushbu buyruqdan foydalanish huquqi yo'q.")
            return
        bot.send_message(message.chat.id, "Admin panel:", reply_markup=admin_menu_keyboard())

    # ---------- MIJOZLAR ----------

    @bot.message_handler(func=lambda m: m.text == "👥 Mijozlar")
    def show_users(message):
        if not is_admin(message.from_user.id):
            return
        text, kb = build_users_page_text_and_kb(0)
        bot.send_message(message.chat.id, text, reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("users_page:"))
    def users_page_callback(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Ruxsat yo'q.")
            return
        offset = int(call.data.split(":")[1])
        text, kb = build_users_page_text_and_kb(offset)
        try:
            bot.edit_message_text(
                text, chat_id=call.message.chat.id, message_id=call.message.message_id,
                reply_markup=kb
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id)

    # ---------- STATISTIKA ----------

    @bot.message_handler(func=lambda m: m.text == "📊 Statistika")
    def show_stats(message):
        if not is_admin(message.from_user.id):
            return
        text = (
            "📊 Statistika\n\n"
            f"👥 Jami mijozlar: {db.get_users_count()}\n"
            f"🟢 Faol mijozlar: {db.get_active_users_count()}\n"
            f"🔴 Botni bloklagan mijozlar: {db.get_blocked_users_count()}\n"
            f"📅 Bugun ro'yxatdan o'tganlar: {db.get_today_registered_count()}\n"
            f"📅 Shu oyda ro'yxatdan o'tganlar: {db.get_month_registered_count()}\n"
            f"💬 Jami kelgan xabarlar: {db.get_direction_count('in')}\n"
            f"📤 Jami yuborilgan javoblar: {db.get_direction_count('out')}"
        )
        bot.send_message(message.chat.id, text)

    # ---------- BROADCAST ----------

    @bot.message_handler(func=lambda m: m.text == "📢 Xabar yuborish")
    def broadcast_start(message):
        if not is_admin(message.from_user.id):
            return
        msg = bot.send_message(
            message.chat.id,
            "Yubormoqchi bo'lgan xabarni yuboring (matn, rasm, video yoki fayl):"
        )
        bot.register_next_step_handler(msg, broadcast_process)

    def broadcast_process(message):
        if not is_admin(message.from_user.id):
            return
        if message.content_type not in ("text", "photo", "video", "document"):
            bot.send_message(
                message.chat.id,
                "Bu turdagi xabarni yuborib bo'lmaydi. Faqat matn, rasm, video yoki fayl."
            )
            return

        user_ids = db.get_all_active_users()
        success = 0
        failed = 0
        for uid in user_ids:
            try:
                bot.copy_message(uid, message.chat.id, message.message_id)
                success += 1
            except Exception:
                failed += 1
                db.set_user_active(uid, False)

        bot.send_message(
            message.chat.id,
            "Xabar yuborildi.\n\n"
            f"Muvaffaqiyatli yuborildi: {success} ta\n"
            f"Yuborilmadi/bloklaganlar: {failed} ta"
        )

    # ---------- ADMIN QO'SHISH ----------

    @bot.message_handler(func=lambda m: m.text == "➕ Admin qo'shish")
    def add_admin_start(message):
        if not is_admin(message.from_user.id):
            return
        msg = bot.send_message(message.chat.id, "Yangi adminning Telegram ID raqamini yuboring:")
        bot.register_next_step_handler(msg, add_admin_process)

    def add_admin_process(message):
        if not is_admin(message.from_user.id):
            return
        text = (message.text or "").strip()
        if not text.isdigit():
            bot.send_message(message.chat.id, "Telegram ID faqat raqamlardan iborat bo'lishi kerak.")
            return
        new_admin_id = int(text)
        added = db.add_admin(new_admin_id)
        if added:
            bot.send_message(message.chat.id, f"Admin qo'shildi: {new_admin_id}")
            try:
                bot.send_message(new_admin_id, "Sizga admin huquqi berildi.")
            except Exception:
                pass
        else:
            bot.send_message(message.chat.id, "Bu foydalanuvchi allaqachon admin.")

    # ---------- ADMINNI O'CHIRISH ----------

    @bot.message_handler(func=lambda m: m.text == "➖ Adminni o'chirish")
    def remove_admin_start(message):
        if not is_admin(message.from_user.id):
            return
        msg = bot.send_message(message.chat.id, "O'chirmoqchi bo'lgan adminning Telegram ID raqamini yuboring:")
        bot.register_next_step_handler(msg, remove_admin_process)

    def remove_admin_process(message):
        if not is_admin(message.from_user.id):
            return
        text = (message.text or "").strip()
        if not text.isdigit():
            bot.send_message(message.chat.id, "Telegram ID faqat raqamlardan iborat bo'lishi kerak.")
            return
        target_id = int(text)
        removed = db.remove_admin(target_id)
        if removed:
            bot.send_message(message.chat.id, f"Admin o'chirildi: {target_id}")
        else:
            bot.send_message(message.chat.id, "Bunday admin topilmadi.")

    # ---------- JAVOB BERISH TIZIMI ----------

    @bot.callback_query_handler(func=lambda c: c.data.startswith("reply:"))
    def reply_callback(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Ruxsat yo'q.")
            return
        target_telegram_id = int(call.data.split(":")[1])
        msg = bot.send_message(call.message.chat.id, "Mijozga yuboriladigan javobni yozing:")
        bot.register_next_step_handler(msg, reply_process, target_telegram_id)
        bot.answer_callback_query(call.id)

    def reply_process(message, target_telegram_id):
        admin_id = message.from_user.id
        if not is_admin(admin_id):
            return
        target_user = db.get_user_by_telegram_id(target_telegram_id)
        if target_user is None:
            bot.send_message(message.chat.id, "Mijoz topilmadi.")
            return
        ok = deliver_admin_reply(bot, db, target_user, message, admin_id)
        if ok:
            bot.send_message(message.chat.id, "Javob mijozga yuborildi.")
        else:
            bot.send_message(
                message.chat.id,
                "Xabarni yuborishda xatolik: mijoz botni bloklagan bo'lishi mumkin."
            )


# ======================================================================
# MIJOZ HANDLERLAR
# ======================================================================

def register_user_handlers(bot, db):

    @bot.message_handler(commands=["start"])
    def start_handler(message):
        telegram_id = message.from_user.id

        if db.is_admin(telegram_id):
            bot.send_message(
                message.chat.id,
                "Assalomu alaykum! Admin panelga xush kelibsiz.",
                reply_markup=admin_menu_keyboard()
            )
            return

        user = db.get_user_by_telegram_id(telegram_id)
        if user is None:
            bot.send_message(
                message.chat.id,
                "Assalomu alaykum! Botdan foydalanish uchun telefon raqamingizni yuboring.",
                reply_markup=phone_request_keyboard()
            )
        else:
            if not user["is_active"]:
                db.set_user_active(telegram_id, True)
            first_name = user.get("first_name") or message.from_user.first_name or ""
            bot.send_message(
                message.chat.id,
                f"Assalomu alaykum, {first_name}!\n\n"
                f"Sizning murojaatingizni yozishingiz mumkin. "
                f"Operatorlarimiz sizga javob berishadi.",
                reply_markup=types.ReplyKeyboardRemove()
            )

    @bot.message_handler(content_types=["contact"])
    def contact_handler(message):
        telegram_id = message.from_user.id

        if message.contact.user_id and message.contact.user_id != telegram_id:
            bot.send_message(message.chat.id, "Iltimos, o'zingizning telefon raqamingizni yuboring.")
            return

        if not db.user_exists(telegram_id):
            db.add_user(
                telegram_id=telegram_id,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                username=message.from_user.username,
                phone=message.contact.phone_number
            )

        first_name = message.from_user.first_name or ""
        bot.send_message(
            message.chat.id,
            f"Rahmat! Ro'yxatdan muvaffaqiyatli o'tdingiz.\n\n"
            f"Assalomu alaykum, {first_name}!\n\n"
            f"Sizning murojaatingizni yozishingiz mumkin. "
            f"Operatorlarimiz sizga javob berishadi.",
            reply_markup=types.ReplyKeyboardRemove()
        )

    @bot.message_handler(
        content_types=["text", "photo", "video", "document", "audio", "voice", "location"]
    )
    def customer_message_handler(message):
        telegram_id = message.from_user.id

        # Adminlarning oddiy xabarlari (admin panel tashqarisida) e'tiborga olinmaydi
        if db.is_admin(telegram_id):
            return

        if message.content_type == "text" and message.text:
            if message.text.startswith("/"):
                return
            if message.text in ADMIN_MENU_BUTTONS:
                return

        user = db.get_user_by_telegram_id(telegram_id)
        if user is None:
            bot.send_message(
                message.chat.id,
                "Iltimos, avval telefon raqamingizni yuboring.",
                reply_markup=phone_request_keyboard()
            )
            return

        if not user["is_active"]:
            db.set_user_active(telegram_id, True)
            user = db.get_user_by_telegram_id(telegram_id)

        send_customer_message_to_admins(bot, db, user, message)


# ======================================================================
# ISHGA TUSHIRISH
# ======================================================================

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
db = Database()

# Admin handlerlar birinchi ro'yxatdan o'tishi kerak, chunki ularning
# matn tugmalari (masalan "👥 Mijozlar") aniqroq filtrga ega.
register_admin_handlers(bot, db)
register_user_handlers(bot, db)

if __name__ == "__main__":
    print("Bot ishga tushdi...")
    bot.infinity_polling(skip_pending=True, timeout=60)
