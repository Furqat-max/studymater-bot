"""
StudyMate — Talabaga yordamchi Telegram bot
============================================
Talabalar uchun: dars jadvali, vazifalar, eslatmalar, GPA kalkulyator,
foydali havolalar, e'lonlar va admin bilan bog'lanish.

Admin panel: statistika, xabar tarqatish (broadcast), jadval/vazifa/e'lon
qo'shish, talaba xabarlariga javob berish, foydalanuvchini bloklash.

Ishga tushirish:
    1) pip install -r requirements.txt
    2) .env faylga BOT_TOKEN va ADMIN_IDS ni yozing (.env.example ga qarang)
    3) python bot.py
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta

import aiosqlite
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Sozlamalar
# --------------------------------------------------------------------------- #

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
}
DB_PATH = os.getenv("DB_PATH", "studymate.db")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("studymate")

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN topilmadi. .env faylni tekshiring (.env.example ga qarang).")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

user_router = Router()
admin_router = Router()
dp.include_router(admin_router)
dp.include_router(user_router)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# --------------------------------------------------------------------------- #
# Ma'lumotlar bazasi
# --------------------------------------------------------------------------- #

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                full_name   TEXT,
                username    TEXT,
                joined_at   TEXT,
                is_banned   INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS schedule (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                day     TEXT,
                text    TEXT
            );

            CREATE TABLE IF NOT EXISTS homework (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                subject      TEXT,
                description  TEXT,
                deadline     TEXT,
                created_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS announcements (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                text        TEXT,
                created_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS reminders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                text        TEXT,
                remind_at   TEXT,
                sent        INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS admin_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                full_name   TEXT,
                text        TEXT,
                created_at  TEXT,
                answered    INTEGER DEFAULT 0
            );
            """
        )
        await db.commit()


async def upsert_user(user_id: int, full_name: str, username: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, full_name, username, joined_at, is_banned)
            VALUES (?, ?, ?, ?, 0)
            ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, username=excluded.username
            """,
            (user_id, full_name, username, datetime.now().isoformat()),
        )
        await db.commit()


async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row and row[0])


# --------------------------------------------------------------------------- #
# Klaviaturalar
# --------------------------------------------------------------------------- #

def main_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📅 Dars jadvali"), KeyboardButton(text="📚 Vazifalar")],
        [KeyboardButton(text="⏰ Eslatma qo'yish"), KeyboardButton(text="🧮 GPA kalkulyator")],
        [KeyboardButton(text="📖 Foydali havolalar"), KeyboardButton(text="📢 E'lonlar")],
        [KeyboardButton(text="📞 Admin bilan bog'lanish"), KeyboardButton(text="❓ Yordam")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📊 Statistika", callback_data="adm_stats")],
        [InlineKeyboardButton(text="📢 Xabar tarqatish", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📅 Jadval qo'shish", callback_data="adm_schedule")],
        [InlineKeyboardButton(text="📚 Vazifa qo'shish", callback_data="adm_homework")],
        [InlineKeyboardButton(text="📝 E'lon joylash", callback_data="adm_announce")],
        [InlineKeyboardButton(text="💬 Talaba xabarlari", callback_data="adm_inbox")],
        [InlineKeyboardButton(text="🚫 Bloklash / ochish", callback_data="adm_ban")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


WEEKDAYS = ["Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba", "Yakshanba"]


def weekday_kb(prefix: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=d, callback_data=f"{prefix}:{d}")] for d in WEEKDAYS]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# --------------------------------------------------------------------------- #
# FSM holatlari
# --------------------------------------------------------------------------- #

class Broadcast(StatesGroup):
    text = State()


class ScheduleAdd(StatesGroup):
    day = State()
    text = State()


class HomeworkAdd(StatesGroup):
    subject = State()
    description = State()
    deadline = State()


class AnnounceAdd(StatesGroup):
    text = State()


class ReminderAdd(StatesGroup):
    text = State()
    minutes = State()


class ContactAdmin(StatesGroup):
    text = State()


class GPACalc(StatesGroup):
    data = State()


class BanUser(StatesGroup):
    user_id = State()


class ReplyToUser(StatesGroup):
    text = State()


# --------------------------------------------------------------------------- #
# Foydalanuvchi: /start va asosiy menyu
# --------------------------------------------------------------------------- #

@user_router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await upsert_user(message.from_user.id, message.from_user.full_name, message.from_user.username or "")
    await message.answer(
        "👋 Assalomu alaykum, <b>{}</b>!\n\n"
        "StudyMate — talabalar uchun yordamchi botga xush kelibsiz.\n"
        "Quyidagi menyudan kerakli bo'limni tanlang 👇".format(message.from_user.full_name),
        reply_markup=main_menu_kb(),
    )


@user_router.message(Command("help"))
@user_router.message(F.text == "❓ Yordam")
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>StudyMate bot imkoniyatlari:</b>\n\n"
        "📅 <b>Dars jadvali</b> — hafta kunlari bo'yicha darslar\n"
        "📚 <b>Vazifalar</b> — topshiriqlar va muddatlari\n"
        "⏰ <b>Eslatma</b> — shaxsiy eslatma qo'yish\n"
        "🧮 <b>GPA kalkulyator</b> — o'rtacha bahoni hisoblash\n"
        "📖 <b>Foydali havolalar</b> — kutubxona/kurslar\n"
        "📢 <b>E'lonlar</b> — so'nggi e'lonlar\n"
        "📞 <b>Admin bilan bog'lanish</b> — savolingizni yozing\n"
    )


# --------------------------------------------------------------------------- #
# Dars jadvali
# --------------------------------------------------------------------------- #

@user_router.message(F.text == "📅 Dars jadvali")
async def show_schedule_days(message: Message) -> None:
    await message.answer("Qaysi kun jadvalini ko'rmoqchisiz?", reply_markup=weekday_kb("day"))


@user_router.callback_query(F.data.startswith("day:"))
async def show_schedule_for_day(call: CallbackQuery) -> None:
    day = call.data.split(":", 1)[1]
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT text FROM schedule WHERE day=? ORDER BY id", (day,))
        rows = await cur.fetchall()
    if not rows:
        text = f"📅 <b>{day}</b> uchun hali jadval kiritilmagan."
    else:
        lines = "\n".join(f"• {r[0]}" for r in rows)
        text = f"📅 <b>{day}</b> jadvali:\n\n{lines}"
    await call.message.edit_text(text)
    await call.answer()


# --------------------------------------------------------------------------- #
# Vazifalar
# --------------------------------------------------------------------------- #

@user_router.message(F.text == "📚 Vazifalar")
async def show_homework(message: Message) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT subject, description, deadline FROM homework ORDER BY id DESC LIMIT 15"
        )
        rows = await cur.fetchall()
    if not rows:
        await message.answer("📚 Hozircha vazifalar yo'q.")
        return
    lines = []
    for subject, desc, deadline in rows:
        lines.append(f"📘 <b>{subject}</b>\n{desc}\n🗓 Muddat: {deadline}\n")
    await message.answer("\n".join(lines))


# --------------------------------------------------------------------------- #
# Shaxsiy eslatma
# --------------------------------------------------------------------------- #

@user_router.message(F.text == "⏰ Eslatma qo'yish")
async def reminder_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ReminderAdd.text)
    await message.answer("Eslatma matnini yozing (masalan: \"Kutubxonaga kitob topshirish\"):")


@user_router.message(ReminderAdd.text)
async def reminder_text(message: Message, state: FSMContext) -> None:
    await state.update_data(text=message.text)
    await state.set_state(ReminderAdd.minutes)
    await message.answer("Necha daqiqadan keyin eslataman? (faqat son kiriting, masalan: 60)")


@user_router.message(ReminderAdd.minutes)
async def reminder_minutes(message: Message, state: FSMContext) -> None:
    if not message.text.isdigit():
        await message.answer("Iltimos, faqat son kiriting (masalan: 30).")
        return
    minutes = int(message.text)
    data = await state.get_data()
    remind_at = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO reminders (user_id, text, remind_at, sent) VALUES (?, ?, ?, 0)",
            (message.from_user.id, data["text"], remind_at),
        )
        await db.commit()
    await state.clear()
    await message.answer(f"✅ Eslatma o'rnatildi. {minutes} daqiqadan so'ng eslataman.", reply_markup=main_menu_kb())


async def reminder_worker() -> None:
    """Har 30 soniyada muddati kelgan eslatmalarni yuboradi."""
    while True:
        try:
            now = datetime.now().isoformat()
            async with aiosqlite.connect(DB_PATH) as db:
                cur = await db.execute(
                    "SELECT id, user_id, text FROM reminders WHERE sent=0 AND remind_at<=?", (now,)
                )
                due = await cur.fetchall()
                for rid, user_id, text in due:
                    try:
                        await bot.send_message(user_id, f"⏰ <b>Eslatma:</b> {text}")
                    except Exception as e:  # noqa: BLE001
                        log.warning("Eslatma yuborilmadi user=%s: %s", user_id, e)
                    await db.execute("UPDATE reminders SET sent=1 WHERE id=?", (rid,))
                await db.commit()
        except Exception as e:  # noqa: BLE001
            log.exception("reminder_worker xato: %s", e)
        await asyncio.sleep(30)


# --------------------------------------------------------------------------- #
# GPA kalkulyator
# --------------------------------------------------------------------------- #

@user_router.message(F.text == "🧮 GPA kalkulyator")
async def gpa_start(message: Message, state: FSMContext) -> None:
    await state.set_state(GPACalc.data)
    await message.answer(
        "Har bir fanni <b>kredit-baho</b> shaklida, har birini yangi qatorda yuboring.\n\n"
        "Masalan:\n<code>3-5\n2-4\n4-3\n2-5</code>\n\n"
        "(baholar 2 dan 5 gacha bo'lishi kerak)"
    )


@user_router.message(GPACalc.data)
async def gpa_calculate(message: Message, state: FSMContext) -> None:
    lines = [ln.strip() for ln in message.text.strip().splitlines() if ln.strip()]
    total_credit = 0.0
    total_points = 0.0
    errors = []
    for ln in lines:
        parts = ln.replace(" ", "").split("-")
        if len(parts) != 2:
            errors.append(ln)
            continue
        try:
            credit = float(parts[0])
            grade = float(parts[1])
        except ValueError:
            errors.append(ln)
            continue
        if not (2 <= grade <= 5) or credit <= 0:
            errors.append(ln)
            continue
        total_credit += credit
        total_points += credit * grade

    if total_credit == 0:
        await message.answer(
            "❌ To'g'ri ma'lumot topilmadi. Format: <code>kredit-baho</code>, masalan <code>3-5</code>.\n"
            "Qaytadan urinib ko'ring yoki /start bosing."
        )
        return

    avg5 = total_points / total_credit
    gpa4 = ((avg5 - 2) / 3) * 4  # 2..5 oralig'ini 0..4 ga proporsional o'giradi (taxminiy)
    gpa4 = max(0.0, min(4.0, gpa4))

    text = (
        f"📊 <b>Natija:</b>\n\n"
        f"O'rtacha ball (5 balllik): <b>{avg5:.2f}</b>\n"
        f"Taxminiy GPA (4.0 tizimida): <b>{gpa4:.2f}</b>\n"
        f"Jami kredit: {total_credit:.0f}"
    )
    if errors:
        text += "\n\n⚠️ Quyidagi qatorlar hisobga olinmadi:\n" + "\n".join(errors)

    await state.clear()
    await message.answer(text, reply_markup=main_menu_kb())


# --------------------------------------------------------------------------- #
# Foydali havolalar / E'lonlar
# --------------------------------------------------------------------------- #

@user_router.message(F.text == "📖 Foydali havolalar")
async def useful_links(message: Message) -> None:
    await message.answer(
        "📖 <b>Foydali havolalar:</b>\n\n"
        "• 📚 Milliy elektron kutubxona: ziyonet.uz\n"
        "• 🎓 Coursera (bepul kurslar): coursera.org\n"
        "• 🧠 Khan Academy: khanacademy.org\n"
        "• 📝 Grammarly (matn tekshirish): grammarly.com\n\n"
        "<i>Admin bu ro'yxatni kengaytirishi mumkin.</i>"
    )


@user_router.message(F.text == "📢 E'lonlar")
async def show_announcements(message: Message) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT text, created_at FROM announcements ORDER BY id DESC LIMIT 5"
        )
        rows = await cur.fetchall()
    if not rows:
        await message.answer("📢 Hozircha e'lonlar yo'q.")
        return
    lines = []
    for text, created_at in rows:
        date_str = created_at.split("T")[0]
        lines.append(f"🗓 {date_str}\n{text}")
    await message.answer("\n\n".join(lines))


# --------------------------------------------------------------------------- #
# Admin bilan bog'lanish
# --------------------------------------------------------------------------- #

@user_router.message(F.text == "📞 Admin bilan bog'lanish")
async def contact_admin_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ContactAdmin.text)
    await message.answer("Xabaringizni yozing, adminga yuboraman:")


@user_router.message(ContactAdmin.text)
async def contact_admin_send(message: Message, state: FSMContext) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO admin_messages (user_id, full_name, text, created_at, answered) VALUES (?, ?, ?, ?, 0)",
            (message.from_user.id, message.from_user.full_name, message.text, datetime.now().isoformat()),
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ Xabaringiz adminga yuborildi. Tez orada javob olasiz.", reply_markup=main_menu_kb())

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📨 <b>Yangi xabar</b>\nFoydalanuvchi: {message.from_user.full_name} (id: {message.from_user.id})\n\n{message.text}",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Adminga yuborilmadi: %s", e)


# --------------------------------------------------------------------------- #
# ADMIN PANEL
# --------------------------------------------------------------------------- #

@admin_router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_menu_kb())


@admin_router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        total = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
        banned = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM admin_messages WHERE answered=0")
        pending = (await cur.fetchone())[0]
    await call.message.answer(
        f"📊 <b>Statistika</b>\n\nJami foydalanuvchilar: {total}\nBloklangan: {banned}\nJavobsiz xabarlar: {pending}"
    )
    await call.answer()


@admin_router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(Broadcast.text)
    await call.message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni kiriting:")
    await call.answer()


@admin_router.message(Broadcast.text)
async def adm_broadcast_send(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE is_banned=0")
        users = await cur.fetchall()
    sent, failed = 0, 0
    for (user_id,) in users:
        try:
            await bot.send_message(user_id, f"📢 {message.text}")
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
        await asyncio.sleep(0.05)  # Telegram limitidan saqlanish
    await message.answer(f"✅ Yuborildi: {sent} ta\n❌ Xato: {failed} ta")


@admin_router.callback_query(F.data == "adm_schedule")
async def adm_schedule_day(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(ScheduleAdd.day)
    await call.message.answer("Qaysi kunga jadval qo'shmoqchisiz?", reply_markup=weekday_kb("admday"))
    await call.answer()


@admin_router.callback_query(F.data.startswith("admday:"))
async def adm_schedule_day_chosen(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    day = call.data.split(":", 1)[1]
    await state.update_data(day=day)
    await state.set_state(ScheduleAdd.text)
    await call.message.answer(f"<b>{day}</b> uchun darsni kiriting (masalan: \"09:00 — Matematika, 214-xona\"):")
    await call.answer()


@admin_router.message(ScheduleAdd.text)
async def adm_schedule_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO schedule (day, text) VALUES (?, ?)", (data["day"], message.text))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ {data['day']} jadvaliga qo'shildi.")


@admin_router.callback_query(F.data == "adm_homework")
async def adm_homework_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(HomeworkAdd.subject)
    await call.message.answer("Fan nomini kiriting:")
    await call.answer()


@admin_router.message(HomeworkAdd.subject)
async def adm_homework_subject(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.update_data(subject=message.text)
    await state.set_state(HomeworkAdd.description)
    await message.answer("Topshiriq tavsifini kiriting:")


@admin_router.message(HomeworkAdd.description)
async def adm_homework_desc(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.update_data(description=message.text)
    await state.set_state(HomeworkAdd.deadline)
    await message.answer("Muddatini kiriting (masalan: 2026-10-05):")


@admin_router.message(HomeworkAdd.deadline)
async def adm_homework_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO homework (subject, description, deadline, created_at) VALUES (?, ?, ?, ?)",
            (data["subject"], data["description"], message.text, datetime.now().isoformat()),
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ Vazifa qo'shildi.")


@admin_router.callback_query(F.data == "adm_announce")
async def adm_announce_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(AnnounceAdd.text)
    await call.message.answer("E'lon matnini kiriting:")
    await call.answer()


@admin_router.message(AnnounceAdd.text)
async def adm_announce_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO announcements (text, created_at) VALUES (?, ?)",
            (message.text, datetime.now().isoformat()),
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ E'lon joylandi. (Foydalanuvchilar \"📢 E'lonlar\" bo'limida ko'radi)")


@admin_router.callback_query(F.data == "adm_inbox")
async def adm_inbox(call: CallbackQuery) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, user_id, full_name, text FROM admin_messages WHERE answered=0 ORDER BY id DESC LIMIT 10"
        )
        rows = await cur.fetchall()
    if not rows:
        await call.message.answer("📭 Javobsiz xabarlar yo'q.")
        return await call.answer()
    for mid, user_id, full_name, text in rows:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"reply:{user_id}:{mid}")]]
        )
        await call.message.answer(f"👤 {full_name} (id: {user_id}):\n{text}", reply_markup=kb)
    await call.answer()


@admin_router.callback_query(F.data.startswith("reply:"))
async def adm_reply_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, user_id, mid = call.data.split(":")
    await state.set_state(ReplyToUser.text)
    await state.update_data(user_id=int(user_id), mid=int(mid))
    await call.message.answer("Javobingizni yozing:")
    await call.answer()


@admin_router.message(ReplyToUser.text)
async def adm_reply_send(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    try:
        await bot.send_message(data["user_id"], f"💬 <b>Admin javobi:</b>\n{message.text}")
        ok = True
    except Exception:  # noqa: BLE001
        ok = False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE admin_messages SET answered=1 WHERE id=?", (data["mid"],))
        await db.commit()
    await state.clear()
    await message.answer("✅ Javob yuborildi." if ok else "❌ Yuborib bo'lmadi (foydalanuvchi botni bloklagan bo'lishi mumkin).")


@admin_router.callback_query(F.data == "adm_ban")
async def adm_ban_start(call: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(call.from_user.id):
        return await call.answer()
    await state.set_state(BanUser.user_id)
    await call.message.answer(
        "Bloklash/ochish uchun foydalanuvchi ID sini yuboring.\n"
        "Bloklash: <code>ban 123456</code>\nOchish: <code>unban 123456</code>"
    )
    await call.answer()


@admin_router.message(BanUser.user_id)
async def adm_ban_apply(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = message.text.strip().split()
    if len(parts) != 2 or parts[0] not in ("ban", "unban") or not parts[1].isdigit():
        await message.answer("Format xato. Masalan: <code>ban 123456</code>")
        return
    action, uid = parts[0], int(parts[1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=? WHERE user_id=?", (1 if action == "ban" else 0, uid))
        await db.commit()
    await state.clear()
    await message.answer(f"✅ Foydalanuvchi {uid} {'bloklandi' if action == 'ban' else 'blokdan chiqarildi'}.")


# --------------------------------------------------------------------------- #
# Bloklangan foydalanuvchilarni filtrlash (barcha handlerlardan oldin)
# --------------------------------------------------------------------------- #

@dp.message.outer_middleware()
async def ban_filter_middleware(handler, event: Message, data):
    if event.from_user and await is_banned(event.from_user.id) and not is_admin(event.from_user.id):
        await event.answer("🚫 Siz botdan foydalanish huquqidan mahrum qilingansiz.")
        return
    return await handler(event, data)


# --------------------------------------------------------------------------- #
# Ishga tushirish
# --------------------------------------------------------------------------- #

async def main() -> None:
    await init_db()
    asyncio.create_task(reminder_worker())
    log.info("Bot ishga tushdi.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
