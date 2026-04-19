import shutil
import asyncio
import uuid
import sqlite3
from pathlib import Path
from typing import List

from PIL import Image, ImageOps
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.filters import CommandStart, Command

BOT_TOKEN = "8627695155:AAH9bbugKITYKIUD4goKiRylgoq9wbrIk5o"
ADMIN_ID = 5471487688  # Admin Telegram ID

BASE_DIR = Path("data")
UPLOADS_DIR = BASE_DIR / "uploads"
PDF_DIR = BASE_DIR / "pdfs"
DB_PATH = BASE_DIR / "bot.db"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_images = {}
user_locks = {}
admin_states = {}  # admin_id -> state


# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def add_user(user_id: int, username: str = "", full_name: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, username, full_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            full_name=excluded.full_name
    """, (user_id, username or "", full_name or ""))
    conn.commit()
    conn.close()


def get_all_users() -> List[int]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_total_users_count() -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    return count


# ---------------- KEYBOARDS ----------------
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📄 PDF qilish")],
        [KeyboardButton(text="🗑 Tozalash")],
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="👥 Foydalanuvchilar soni")],
        [KeyboardButton(text="📢 Hammaga xabar"), KeyboardButton(text="📎 Fayl yuborish")],
        [KeyboardButton(text="📣 Reklama/Post tashlash")],
        [KeyboardButton(text="❌ Admin panelni yopish")],
    ],
    resize_keyboard=True
)


# ---------------- HELPERS ----------------
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def get_user_dir(user_id: int) -> Path:
    user_dir = UPLOADS_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]


def cleanup_user_files(user_id: int) -> None:
    user_dir = UPLOADS_DIR / str(user_id)
    if user_dir.exists():
        shutil.rmtree(user_dir, ignore_errors=True)
    user_dir.mkdir(parents=True, exist_ok=True)
    user_images[user_id] = []


def prepare_image_for_pdf(img: Image.Image, max_dim: int = 2000) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    max_side = max(w, h)

    if max_side > max_dim:
        ratio = max_dim / max_side
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    return img


def make_pdf(image_paths: List[Path], pdf_path: Path) -> int:
    images = []

    for path in image_paths:
        with Image.open(path) as img:
            ready = prepare_image_for_pdf(img)
            images.append(ready.copy())

    if not images:
        raise ValueError("Rasm topilmadi")

    first = images[0]
    rest = images[1:]

    first.save(
        pdf_path,
        "PDF",
        save_all=True,
        append_images=rest,
        resolution=100.0,
    )

    return pdf_path.stat().st_size


def active_users_count() -> int:
    return sum(1 for imgs in user_images.values() if imgs)


async def send_to_all_users_text(text: str):
    users = get_all_users()
    ok_count = 0
    fail_count = 0

    for user_id in users:
        try:
            await bot.send_message(user_id, text)
            ok_count += 1
        except Exception:
            fail_count += 1

    return ok_count, fail_count


async def copy_to_all_users(from_chat_id: int, message_id: int):
    users = get_all_users()
    ok_count = 0
    fail_count = 0

    for user_id in users:
        try:
            await bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id)
            ok_count += 1
        except Exception:
            fail_count += 1

    return ok_count, fail_count


# ---------------- USER HANDLERS ----------------
@dp.message(CommandStart())
async def start_handler(message: Message):
    add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or ""
    )

    user_id = message.from_user.id
    if user_id not in user_images:
        user_images[user_id] = []

    await message.answer(
        "Assalamu alaykum. \nRasmlar yuboring, keyin 📄 PDF qilish tugmasini bosing.",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "🗑 Tozalash")
async def clear_handler(message: Message):
    add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or ""
    )

    user_id = message.from_user.id
    if user_id not in user_images:
        user_images[user_id] = []

    cleanup_user_files(user_id)
    await message.answer("Barcha rasmlar tozalandi.", reply_markup=main_keyboard)


@dp.message(F.photo)
async def photo_handler(message: Message):
    add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or ""
    )

    # ADMIN STATE: agar admin reklama/post yoki fayl yuborish rejimida bo'lsa,
    # rasmni oddiy user rasmi sifatida emas, broadcast sifatida yuboramiz
    if is_admin(message.from_user.id):
        state = admin_states.get(message.from_user.id)

        if state == "broadcast_file":
            ok_count, fail_count = await copy_to_all_users(message.chat.id, message.message_id)
            admin_states[message.from_user.id] = None
            await message.answer(
                f"✅ Fayl yuborildi.\n"
                f"Yetib bordi: {ok_count}\n"
                f"Xato: {fail_count}",
                reply_markup=admin_keyboard
            )
            return

        elif state == "broadcast_post":
            ok_count, fail_count = await copy_to_all_users(message.chat.id, message.message_id)
            admin_states[message.from_user.id] = None
            await message.answer(
                f"✅ Reklama/Post yuborildi.\n"
                f"Yetib bordi: {ok_count}\n"
                f"Xato: {fail_count}",
                reply_markup=admin_keyboard
            )
            return

    user_id = message.from_user.id

    if user_id not in user_images:
        user_images[user_id] = []

    lock = get_user_lock(user_id)

    async with lock:
        user_dir = get_user_dir(user_id)
        photo = message.photo[-1]

        unique_name = f"{len(user_images[user_id]) + 1:04d}_{photo.file_unique_id}_{uuid.uuid4().hex[:8]}.jpg"
        save_path = user_dir / unique_name

        file = await bot.get_file(photo.file_id)
        await bot.download_file(file.file_path, destination=save_path)

        user_images[user_id].append(str(save_path))

        await message.answer(
            f"Rasm saqlandi: {len(user_images[user_id])} ta",
            reply_markup=main_keyboard
)

@dp.message(F.text == "📄 PDF qilish")
async def pdf_handler(message: Message):
    add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or ""
    )

    user_id = message.from_user.id

    if user_id not in user_images or not user_images[user_id]:
        await message.answer("Siz hali rasm yubormadingiz.", reply_markup=main_keyboard)
        return

    lock = get_user_lock(user_id)

    async with lock:
        image_paths = [Path(p) for p in user_images[user_id] if Path(p).exists()]
        image_paths.sort()

        if not image_paths:
            await message.answer("Rasmlar topilmadi.")
            return

        pdf_path = PDF_DIR / f"{user_id}_images.pdf"

        try:
            await message.answer("PDF tayyorlanmoqda...")
            pdf_size = make_pdf(image_paths, pdf_path)

            await message.answer_document(
                document=FSInputFile(pdf_path),
                caption=f"Tayyor PDF. Hajmi: {round(pdf_size / (1024 * 1024), 2)} MB"
            )
        except Exception as e:
            await message.answer(f"PDF qilishda xatolik: {e}")
        finally:
            cleanup_user_files(user_id)
            if pdf_path.exists():
                pdf_path.unlink(missing_ok=True)


# ---------------- ADMIN HANDLERS ----------------
@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Siz admin emassiz.")
        return

    add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or ""
    )

    admin_states[message.from_user.id] = None
    await message.answer("Admin panel ochildi.", reply_markup=admin_keyboard)


@dp.message(F.text == "📊 Statistika")
async def admin_stats_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "📊 Bot statistikasi:\n"
        f"👥 Jami foydalanuvchilar: {get_total_users_count()} ta\n"
        f"🟢 Aktiv navbatdagi userlar: {active_users_count()} ta",
        reply_markup=admin_keyboard
    )


@dp.message(F.text == "👥 Foydalanuvchilar soni")
async def admin_users_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        f"Botdagi jami foydalanuvchilar soni: {get_total_users_count()} ta",
        reply_markup=admin_keyboard
    )


@dp.message(F.text == "📢 Hammaga xabar")
async def broadcast_text_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    admin_states[message.from_user.id] = "broadcast_text"
    await message.answer("Yubormoqchi bo'lgan xabaringizni matn ko'rinishida yuboring.")


@dp.message(F.text == "📎 Fayl yuborish")
async def broadcast_file_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    admin_states[message.from_user.id] = "broadcast_file"
    await message.answer("Hammaga yubormoqchi bo'lgan faylni yuboring.")


@dp.message(F.text == "📣 Reklama/Post tashlash")
async def broadcast_post_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    admin_states[message.from_user.id] = "broadcast_post"
    await message.answer("Reklama/postni yuboring. Matn, rasm, video, fayl - hammasi bo'ladi.")


@dp.message(F.text == "❌ Admin panelni yopish")
async def close_admin_handler(message: Message):
    if not is_admin(message.from_user.id):
        return

    admin_states[message.from_user.id] = None
    await message.answer("Admin panel yopildi.", reply_markup=main_keyboard)


@dp.message()
async def other_handler(message: Message):
    add_user(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        full_name=message.from_user.full_name or ""
    )

    if is_admin(message.from_user.id):
        state = admin_states.get(message.from_user.id)

        if state == "broadcast_text":
            text = message.text or ""
            if not text.strip():
                await message.answer("Matn yuboring.")
                return

            ok_count, fail_count = await send_to_all_users_text(text)
            admin_states[message.from_user.id] = None
            await message.answer(
                f"✅ Xabar yuborildi.\n"
                f"Yetib bordi: {ok_count}\n"
                f"Xato: {fail_count}",
                reply_markup=admin_keyboard
            )
            return

        elif state == "broadcast_file":
            ok_count, fail_count = await copy_to_all_users(message.chat.id, message.message_id)
            admin_states[message.from_user.id] = None
            await message.answer(
                f"✅ Fayl yuborildi.\n"
                f"Yetib bordi: {ok_count}\n"
                f"Xato: {fail_count}",
                reply_markup=admin_keyboard
            )
            return

        elif state == "broadcast_post":
            ok_count, fail_count = await copy_to_all_users(message.chat.id, message.message_id)
            admin_states[message.from_user.id] = None
            await message.answer(
                f"✅ Reklama/Post yuborildi.\n"
                f"Yetib bordi: {ok_count}\n"
                f"Xato: {fail_count}",
                reply_markup=admin_keyboard
            )
            return

    await message.answer(
        "Menga rasm yuboring yoki 📄 PDF qilish tugmasini bosing.",
        reply_markup=main_keyboard
    )


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())