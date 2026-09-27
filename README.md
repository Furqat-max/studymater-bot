# StudyMate — Talabaga yordamchi bot

Telegram bot: talabalar uchun dars jadvali, vazifalar, eslatmalar, GPA
kalkulyator, e'lonlar va admin bilan bog'lanish + to'liq admin panel.

## 1. O'zingizning Telegram ID raqamingizni oling

Admin panelidan foydalanish uchun sizning Telegram ID kerak (token emas).
Telegram'da **@userinfobot** ga `/start` yozing — u sizga ID raqamingizni beradi.

## 2. `.env` faylni to'ldiring

`.env` fayli allaqachon tokeningiz bilan tayyor. Faqat `ADMIN_IDS` qatoriga
o'z ID raqamingizni yozing (bir nechta admin bo'lsa, vergul bilan ajrating):

```
BOT_TOKEN=8663831975:AAFZ55taMgDQYogNurvDBrZQDqfM5oNzW_8
ADMIN_IDS=123456789
DB_PATH=studymate.db
```

**Muhim:** Tokeningizni bu suhbatda ochiq yubordingiz. Xavfsizlik uchun
Telegram'da **@BotFather** ga o'ting → botingizni tanlang → *API Token* →
*Revoke current token* qilib, yangi token oling, so'ng uni `.env` fayliga
qo'ying.

## 3. Kompyuterda ishga tushirish

```bash
# 1) Python 3.10+ o'rnatilgan bo'lishi kerak
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2) Kutubxonalarni o'rnatish
pip install -r requirements.txt

# 3) Botni ishga tushirish
python bot.py
```

Bot ishga tushgach, Telegram'da botingizga `/start` yozing. Admin panelni
ochish uchun `/admin` yozing (faqat `ADMIN_IDS` da ko'rsatilgan ID uchun
ishlaydi).

## 4. Doim ishlab turishi uchun (24/7) — bepul xosting

Kompyuteringizni o'chirsangiz ham bot ishlashda davom etishi uchun uni
serverga joylashtiring. Eng oson bepul variantlar:

### Railway.app (tavsiya etiladi, eng oson)
1. https://railway.app ga GitHub hisobingiz bilan kiring.
2. Ushbu papkani GitHub repo qilib yuklang.
3. Railway'da "New Project" → "Deploy from GitHub repo" tanlang.
4. "Variables" bo'limida `BOT_TOKEN` va `ADMIN_IDS` ni qo'shing.
5. Start command: `python bot.py`

### Render.com
1. https://render.com da "New Background Worker" yarating.
2. Repo'ni ulang, build command: `pip install -r requirements.txt`,
   start command: `python bot.py`.
3. Environment Variables bo'limiga `BOT_TOKEN` va `ADMIN_IDS` ni qo'shing.

### O'z VPS serveringizda (systemd bilan doimiy ishlash)
```bash
sudo apt update && sudo apt install python3-venv -y
git clone <repo> studymate_bot && cd studymate_bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```
So'ng `systemd` service yarating, u orqali server qayta yonganda ham bot
avtomatik ishga tushadi (kerak bo'lsa, buni ham keyinroq sozlab beraman).

## Fayllar tuzilishi

```
studymate_bot/
├── bot.py              # Asosiy bot kodi
├── requirements.txt    # Python kutubxonalari
├── .env                # Sozlamalar (token, admin ID)
├── .env.example        # Namuna fayl
├── studymate.db        # SQLite baza (birinchi ishga tushganda avtomatik yaraladi)
└── README.md           # Shu fayl
```

## Kengaytirish g'oyalari

- Guruh/kurs bo'yicha alohida jadval va vazifalar
- Fayl (PDF, rasm) yuborish orqali vazifa biriktirish
- Talabalar reytingi yoki faollik statistikasi
- Inline qidiruv orqali fanlarni tezkor topish
- Ko'p tilli interfeys (o'zbek/rus/ingliz)

Har qanday qo'shimcha funksiya kerak bo'lsa — ayting, qo'shib beraman.
