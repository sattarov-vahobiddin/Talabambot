import os
import io
import shutil
import asyncio
import uuid
from pathlib import Path
from typing import List

from PIL import Image, ImageOps
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.filters import CommandStart

BOT_TOKEN = "8627695155:AAH9bbugKITYKIUD4goKiRylgoq9wbrIk5o"

BASE_DIR = Path("data")
UPLOADS_DIR = BASE_DIR / "uploads"
PDF_DIR = BASE_DIR / "pdfs"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
PDF_DIR.mkdir(parents=True, exist_ok=True)

bot = Bot(token="8627695155:AAH9bbugKITYKIUD4goKiRylgoq9wbrIk5o")
dp = Dispatcher()

user_images = {}
user_locks = {}

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📄 PDF qilish")],
        [KeyboardButton(text="🗑 Tozalash")],
    ],
    resize_keyboard=True
)


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


@dp.message(CommandStart())
async def start_handler(message: Message):
    user_id = message.from_user.id
    if user_id not in user_images:
        user_images[user_id] = []

    await message.answer(
        "Salom.\n"
        "Rasmlar yuboring, keyin 📄 PDF qilish tugmasini bosing.",
        reply_markup=main_keyboard
    )


@dp.message(F.text == "🗑 Tozalash")
async def clear_handler(message: Message):
    user_id = message.from_user.id
    cleanup_user_files(user_id)
    await message.answer("Barcha rasmlar tozalandi.", reply_markup=main_keyboard)


@dp.message(F.photo)
async def photo_handler(message: Message):
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


@dp.message()
async def other_handler(message: Message):
    await message.answer(
        "Menga rasm yuboring yoki 📄 PDF qilish tugmasini bosing.",
        reply_markup=main_keyboard
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())