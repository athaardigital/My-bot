import os
import json
from datetime import datetime

from flask import Flask, request
from dotenv import load_dotenv

import telebot
from telebot import types

# =========================
# تحميل المتغيرات
# =========================

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not BOT_TOKEN:
    raise Exception("BOT TOKEN NOT FOUND")

if not WEBHOOK_URL:
    raise Exception("WEBHOOK URL NOT FOUND")

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="Markdown"
)

app = Flask(__name__)

DATA_FILE = "groups_data.json"

# =========================
# البيانات
# =========================

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass

    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

def default_group():
    return {
        "message_id": None,
        "list_open": False,
        "members": [],
        "read": []
    }

def get_group(chat_id):
    data = load_data()

    chat_id = str(chat_id)

    if chat_id not in data:
        data[chat_id] = default_group()
        save_data(data)

    return data, data[chat_id]

# =========================
# الأدمن
# =========================

def is_admin(user_id, chat_id):
    try:
        member = bot.get_chat_member(
            chat_id,
            user_id
        )

        return member.status in [
            "administrator",
            "creator"
        ]
    except:
        return False

# =========================
# التاريخ
# =========================

def get_date():
    now = datetime.now()

    return now.strftime("%Y/%m/%d")

# =========================
# اللوحة
# =========================

def mention(user_id, name):
    return f"[{name}](tg://user?id={user_id})"

def make_text(chat_id):

    _, group = get_group(chat_id)

    state = (
        "🟢 مفتوحة"
        if group["list_open"]
        else "🔴 مغلقة"
    )

    text = (
        f"📅 *التاريخ:* {get_date()}\n\n"
        "اعلمي رعاكِ الله أنَّ حضوركِ لمجالس العلم "
        "هو محضُ انتقاءٍ وتوفيقٍ من الله "
        "فأحسني رعاية هذه النعمة واحمدي الله عليها.\n\n"
    )

    text += "━━━━━━━━━━━━━━━\n"
    text += f"📖 *القارئات* ({len(group['members'])})\n\n"

    if not group["members"]:
        text += "لا يوجد.\n"

    else:
        for i, member in enumerate(
            group["members"],
            start=1
        ):

            done = (
                " ✅"
                if member["id"] in group["read"]
                else ""
            )

            text += (
                f"{i}. "
                f"{mention(member['id'], member['name'])}"
                f"{done}\n"
            )

    text += "\n━━━━━━━━━━━━━━━\n"
    text += f"🔒 *حالة القائمة:* {state}"

    return text

# =========================
# الأزرار
# =========================

def keyboard(chat_id, user_id):

    markup = types.InlineKeyboardMarkup(
        row_width=2
    )

    markup.add(
        types.InlineKeyboardButton(
            "📝 تسجيل اسمي",
            callback_data="register"
        ),

        types.InlineKeyboardButton(
            "🗑️ حذف اسمي",
            callback_data="delete"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "✅ تم الفراغ من القراءة",
            callback_data="done"
        )
    )

    if is_admin(user_id, chat_id):

        markup.add(
            types.InlineKeyboardButton(
                "⚙️ الإعدادات",
                callback_data="settings"
            )
        )

    return markup

def settings_keyboard(chat_id):

    _, group = get_group(chat_id)

    state_button = (
        "🔒 إغلاق القائمة"
        if group["list_open"]
        else "🔓 فتح القائمة"
    )

    markup = types.InlineKeyboardMarkup(
        row_width=1
    )

    markup.add(
        types.InlineKeyboardButton(
            state_button,
            callback_data="toggle"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "📖 تحديث القائمة",
            callback_data="refresh"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "🔄 إعادة ضبط القائمة",
            callback_data="reset"
        )
    )

    markup.add(
        types.InlineKeyboardButton(
            "📢 المناداة",
            callback_data="call"
        )
    )

    return markup

# =========================
# تحديث الرسالة
# =========================

def update_board(chat_id, user_id):

    _, group = get_group(chat_id)

    if not group["message_id"]:
        return

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=group["message_id"],
            text=make_text(chat_id),
            parse_mode="Markdown",
            reply_markup=keyboard(
                chat_id,
                user_id
            ),
            disable_web_page_preview=True
        )
    except Exception as e:
        print(e)

# =========================
# start
# =========================

@bot.message_handler(commands=["start"])
def start(message):

    if message.chat.type == "private":

        bot.send_message(
            message.chat.id,
            "السلام عليكم ورحمة الله وبركاته\n\n"
            "حيَّاكِ الله.\n\n"
            "انشري البوت فضلًا فهو صدقة "
            "عنِّي وعن والديَّ ومقرأتنا "
            "وكل المسلمين والمسلمات."
        )

        return

    data = load_data()

    chat_id = str(message.chat.id)

    data[chat_id] = default_group()

    sent = bot.send_message(
        message.chat.id,
        make_text(message.chat.id),
        parse_mode="Markdown",
        reply_markup=keyboard(
            message.chat.id,
            message.from_user.id
        )
    )

    data[chat_id]["message_id"] = sent.message_id

    save_data(data)

# =========================
# الأزرار
# =========================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):

    data, group = get_group(
        call.message.chat.id
    )

    user = call.from_user

    name = user.first_name

    if user.last_name:
        name += f" {user.last_name}"

    # =====================
    # تسجيل
    # =====================

    if call.data == "register":

        if not group["list_open"]:

            bot.answer_callback_query(
                call.id,
                "القائمة مغلقة."
            )

            return

        exists = any(
            str(m["id"]) == str(user.id)
            for m in group["members"]
        )

        if exists:

            bot.answer_callback_query(
                call.id,
                "اسمكِ مسجل مسبقاً."
            )

            return

        group["members"].append({
            "id": str(user.id),
            "name": name
        })

        save_data(data)

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم التسجيل."
        )

    # =====================
    # حذف
    # =====================

    elif call.data == "delete":

        before = len(group["members"])

        group["members"] = [
            m for m in group["members"]
            if str(m["id"]) != str(user.id)
        ]

        group["read"] = [
            r for r in group["read"]
            if str(r) != str(user.id)
        ]

        after = len(group["members"])

        if before == after:

            bot.answer_callback_query(
                call.id,
                "اسمكِ غير موجود."
            )

            return

        save_data(data)

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم الحذف."
        )

    # =====================
    # تم الفراغ
    # =====================

    elif call.data == "done":

        exists = any(
            str(m["id"]) == str(user.id)
            for m in group["members"]
        )

        if not exists:

            bot.answer_callback_query(
                call.id,
                "سجلي اسمكِ أولاً."
            )

            return

        if str(user.id) in group["read"]:

            bot.answer_callback_query(
                call.id,
                "تم التأكيد مسبقاً."
            )

            return

        group["read"].append(
            str(user.id)
        )

        save_data(data)

        update_board(
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

        if not is_admin(
            user.id,
            call.message.chat.id
        ):
            return

        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=settings_keyboard(
                call.message.chat.id
            )
        )

    # =====================
    # فتح وإغلاق
    # =====================

    elif call.data == "toggle":

        if not is_admin(
            user.id,
            call.message.chat.id
        ):
            return

        group["list_open"] = (
            not group["list_open"]
        )

        save_data(data)

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم تحديث الحالة."
        )

    # =====================
    # تحديث
    # =====================

    elif call.data == "refresh":

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم التحديث."
        )

    # =====================
    # إعادة ضبط
    # =====================

    elif call.data == "reset":

        if not is_admin(
            user.id,
            call.message.chat.id
        ):
            return

        old_message = group["message_id"]

        data[str(call.message.chat.id)] = (
            default_group()
        )

        data[str(call.message.chat.id)][
            "message_id"
        ] = old_message

        save_data(data)

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تمت إعادة الضبط."
        )

    # =====================
    # المناداة
    # =====================

    elif call.data == "call":

        if not is_admin(
            user.id,
            call.message.chat.id
        ):
            return

        count = 0

        for member in group["members"]:

            try:

                bot.send_message(
                    int(member["id"]),
                    "هلمُّوا لمجلسٍ تحفُّه الملائكة 🌿"
                )

                count += 1

            except:
                pass

        bot.answer_callback_query(
            call.id,
            f"تم إرسال {count}"
        )

# =========================
# Flask
# =========================

@app.route("/")
def home():
    return "Bot is running", 200

@app.route(
    f"/{BOT_TOKEN}",
    methods=["POST"]
)
def webhook():

    json_str = request.get_data().decode(
        "UTF-8"
    )

    update = telebot.types.Update.de_json(
        json_str
    )

    bot.process_new_updates([update])

    return "OK", 200

# =========================
# تشغيل
# =========================

bot.remove_webhook()

bot.set_webhook(
    url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
)

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
            )
