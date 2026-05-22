import os
import json
import threading
from datetime import datetime

from flask import Flask, request
from dotenv import load_dotenv

import telebot
from telebot import types

# =========================
# تحميل المتغيرات البيئية
# =========================

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("لم يتم العثور على TELEGRAM_BOT_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# =========================
# الملفات
# =========================

DATA_FILE = "groups_data.json"

# =========================
# العبارات الثابتة
# =========================

REMINDER_TEXT = (
    "اعلمي رعاكِ الله أنَّ حضوركِ لمجالسِ العلمِ هو محضُ انتقاءٍ "
    "وتوفيقٍ من الله، فأحسني رعايةَ هذه النعمةِ واحمدي الله عليها."
)

PRIVATE_START_TEXT = (
    "السلام عليكم ورحمة الله وبركاته\n\n"
    "حيَّاكِ الله.\n\n"
    "انشري البوت فضلًا، فهو صدقةٌ عنِّي وعن والديَّ ومقرأتِنا "
    "وكلِّ المسلمين والمسلمات والمؤمنين والمؤمنات الأحياء منهم والأموات."
)

CALL_TEXT = "هلمُّوا لمجلسٍ تحفُّه الملائكة 🌿"

# =========================
# أدوات البيانات
# =========================

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_today_dates():
    now = datetime.now()

    gregorian = now.strftime("%Y/%m/%d")
    time_now = now.strftime("%I:%M %p")

    return gregorian, time_now

def default_group_data():
    gregorian, _ = get_today_dates()

    return {
        "message_id": None,
        "list_open": False,
        "created_date": gregorian,
        "readers": [],
        "listeners": [],
        "excused": [],
        "completed": []
    }

def get_group_data(chat_id):
    data = load_data()

    chat_id = str(chat_id)

    if chat_id not in data:
        data[chat_id] = default_group_data()
        save_data(data)

    return data, data[chat_id]

# =========================
# التحقق من الإشراف
# =========================

def is_admin(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

# =========================
# إنشاء الأزرار
# =========================

def build_keyboard(chat_id, user_id):
    _, group = get_group_data(chat_id)

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        types.InlineKeyboardButton(
            "📝 تسجيل اسمي",
            callback_data="register"
        ),
        types.InlineKeyboardButton(
            "🗑️ حذف اسمي",
            callback_data="delete"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "✅ تم الفراغ من القراءة",
            callback_data="done"
        )
    )

    if is_admin(user_id, chat_id):
        keyboard.add(
            types.InlineKeyboardButton(
                "⚙️ الإعدادات",
                callback_data="settings"
            )
        )

    return keyboard

def build_settings_keyboard(chat_id, user_id):
    _, group = get_group_data(chat_id)

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    status_text = (
        "🔒 إغلاق القائمة"
        if group["list_open"]
        else "🔓 فتح القائمة"
    )

    keyboard.add(
        types.InlineKeyboardButton(
            status_text,
            callback_data="toggle"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📖 تحديث القائمة",
            callback_data="refresh"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "📢 المناداة",
            callback_data="call_members"
        )
    )

    keyboard.add(
        types.InlineKeyboardButton(
            "🔄 إعادة ضبط القائمة",
            callback_data="reset"
        )
    )

    return keyboard

# =========================
# تنسيق القائمة
# =========================

def make_clickable_name(user_id, name):
    return f"[{name}](tg://user?id={user_id})"

def format_section(title, items, completed):
    text = f"━━━━━━━━━━━━━━━\n"
    text += f"*{title}* ({len(items)})\n\n"

    if not items:
        text += "لا يوجد.\n"
        return text

    for idx, member in enumerate(items, start=1):
        done_mark = " ✅" if str(member["id"]) in completed else ""

        text += (
            f"{idx}. "
            f"{make_clickable_name(member['id'], member['name'])}"
            f"{done_mark}\n"
        )

    return text

def generate_board(chat_id):
    _, group = get_group_data(chat_id)

    gregorian, time_now = get_today_dates()

    state = (
        "🟢 القائمة مفتوحة"
        if group["list_open"]
        else "🔴 القائمة مغلقة"
    )

    text = (
        f"📅 *التاريخ:* {gregorian}\n"
        f"🕓 *الوقت:* {time_now}\n\n"
        f"{REMINDER_TEXT}\n\n"
    )

    text += format_section(
        "📖 القارئات",
        group["readers"],
        group["completed"]
    )

    text += "\n"

    text += format_section(
        "🎧 المستمعات",
        group["listeners"],
        group["completed"]
    )

    text += "\n"

    text += format_section(
        "🌿 المعتذرات",
        group["excused"],
        group["completed"]
    )

    text += "\n━━━━━━━━━━━━━━━\n"
    text += f"{state}"

    return text

# =========================
# تحديث الرسالة الرئيسية
# =========================

def update_main_message(chat_id, user_id):
    _, group = get_group_data(chat_id)

    if not group["message_id"]:
        return

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=group["message_id"],
            text=generate_board(chat_id),
            parse_mode="Markdown",
            reply_markup=build_keyboard(chat_id, user_id),
            disable_web_page_preview=True
        )
    except Exception as e:
        print(e)

# =========================
# البحث عن العضوة
# =========================

def user_exists(all_lists, user_id):
    for item in all_lists:
        if str(item["id"]) == str(user_id):
            return True
    return False

def remove_user_from_lists(group, user_id):
    group["readers"] = [
        x for x in group["readers"]
        if str(x["id"]) != str(user_id)
    ]

    group["listeners"] = [
        x for x in group["listeners"]
        if str(x["id"]) != str(user_id)
    ]

    group["excused"] = [
        x for x in group["excused"]
        if str(x["id"]) != str(user_id)
    ]

# =========================
# /start
# =========================

@bot.message_handler(commands=["start"])
def start_handler(message):

    if message.chat.type == "private":
        bot.send_message(
            message.chat.id,
            PRIVATE_START_TEXT
        )
        return

    data, group = get_group_data(message.chat.id)

    data[str(message.chat.id)] = default_group_data()

    sent = bot.send_message(
        message.chat.id,
        generate_board(message.chat.id),
        parse_mode="Markdown",
        reply_markup=build_keyboard(
            message.chat.id,
            message.from_user.id
        ),
        disable_web_page_preview=True
    )

    data[str(message.chat.id)]["message_id"] = sent.message_id

    save_data(data)

# =========================
# الأزرار
# =========================

@bot.callback_query_handler(func=lambda c: True)
def callback_handler(call):

    data, group = get_group_data(call.message.chat.id)

    user = call.from_user

    full_name = user.first_name or "مستخدمة"

    if user.last_name:
        full_name += f" {user.last_name}"

    member_data = {
        "id": str(user.id),
        "name": full_name
    }

    # =====================
    # تسجيل
    # =====================

    if call.data == "register":

        if not group["list_open"]:
            bot.answer_callback_query(
                call.id,
                "القائمة مغلقة حالياً."
            )
            return

        all_lists = (
            group["readers"] +
            group["listeners"] +
            group["excused"]
        )

        if user_exists(all_lists, user.id):
            bot.answer_callback_query(
                call.id,
                "اسمكِ مسجل مسبقاً."
            )
            return

        group["readers"].append(member_data)

        save_data(data)

        update_main_message(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم تسجيل اسمكِ بنجاح."
        )

    # =====================
    # حذف
    # =====================

    elif call.data == "delete":

        all_lists_before = (
            len(group["readers"]) +
            len(group["listeners"]) +
            len(group["excused"])
        )

        remove_user_from_lists(group, user.id)

        group["completed"] = [
            x for x in group["completed"]
            if str(x) != str(user.id)
        ]

        all_lists_after = (
            len(group["readers"]) +
            len(group["listeners"]) +
            len(group["excused"])
        )

        if all_lists_before == all_lists_after:
            bot.answer_callback_query(
                call.id,
                "اسمكِ غير موجود."
            )
            return

        save_data(data)

        update_main_message(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم حذف اسمكِ."
        )

    # =====================
    # تم الفراغ
    # =====================

    elif call.data == "done":

        all_lists = (
            group["readers"] +
            group["listeners"] +
            group["excused"]
        )

        if not user_exists(all_lists, user.id):
            bot.answer_callback_query(
                call.id,
                "يجب تسجيل الاسم أولاً."
            )
            return

        if str(user.id) in group["completed"]:
            bot.answer_callback_query(
                call.id,
                "تم توثيق الفراغ مسبقاً."
            )
            return

        group["completed"].append(str(user.id))

        save_data(data)

        update_main_message(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "بارك الله فيكِ."
        )

    # =====================
    # الإعدادات
    # =====================

    elif call.data == "settings":

        if not is_admin(user.id, call.message.chat.id):
            return

        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_settings_keyboard(
                call.message.chat.id,
                user.id
            )
        )

    # =====================
    # فتح وإغلاق
    # =====================

    elif call.data == "toggle":

        if not is_admin(user.id, call.message.chat.id):
            return

        group["list_open"] = not group["list_open"]

        save_data(data)

        update_main_message(
            call.message.chat.id,
            user.id
        )

        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=build_settings_keyboard(
                call.message.chat.id,
                user.id
            )
        )

        bot.answer_callback_query(
            call.id,
            "تم تحديث حالة القائمة."
        )

    # =====================
    # تحديث
    # =====================

    elif call.data == "refresh":

        if not is_admin(user.id, call.message.chat.id):
            return

        update_main_message(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم تحديث القائمة."
        )

    # =====================
    # إعادة ضبط
    # =====================

    elif call.data == "reset":

        if not is_admin(user.id, call.message.chat.id):
            return

        data[str(call.message.chat.id)] = default_group_data()

        data[str(call.message.chat.id)]["message_id"] = (
            call.message.message_id
        )

        save_data(data)

        update_main_message(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تمت إعادة ضبط القائمة."
        )

    # =====================
    # المناداة
    # =====================

    elif call.data == "call_members":

        if not is_admin(user.id, call.message.chat.id):
            return

        all_members = (
            group["readers"] +
            group["listeners"] +
            group["excused"]
        )

        sent_count = 0

        for member in all_members:
            try:
                bot.send_message(
                    int(member["id"]),
                    CALL_TEXT
                )
                sent_count += 1
            except:
                pass

        bot.answer_callback_query(
            call.id,
            f"تمت المناداة لـ {sent_count}"
        )

# =========================
# Flask
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Athaar Bot Running", 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/health")
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )

# =========================
# التشغيل
# =========================

if __name__ == "__main__":

    print("تم تشغيل بوت آثار للتلاوة")

    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    bot.remove_webhook()

    bot.infinity_polling(
        skip_pending=True
            )
