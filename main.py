import os
import json
import threading
from datetime import datetime

from flask import Flask
from dotenv import load_dotenv

import telebot
from telebot import types

# =====================================
# تحميل المتغيرات
# =====================================

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise Exception("TOKEN NOT FOUND")

bot = telebot.TeleBot(BOT_TOKEN)

DATA_FILE = "groups_data.json"

# =====================================
# Flask
# =====================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running", 200

# =====================================
# البيانات
# =====================================

def load_data():

    if os.path.exists(DATA_FILE):

        try:

            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)

        except:
            return {}

    return {}

def save_data(data):

    with open(DATA_FILE, "w", encoding="utf-8") as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

# =====================================
# بيانات المجموعة
# =====================================

def default_group():

    return {

        "message_id": None,

        "list_open": False,

        "readers": [],

        "listeners": [],

        "excused": [],

        "completed": []
    }

def get_group(chat_id):

    data = load_data()

    chat_id = str(chat_id)

    if chat_id not in data:

        data[chat_id] = default_group()

        save_data(data)

    return data, data[chat_id]

# =====================================
# الأدمن
# =====================================

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

# =====================================
# المنشن
# =====================================

def mention(user_id, name):

    safe_name = name.replace("<", "").replace(">", "")

    return f"<a href='tg://user?id={user_id}'>{safe_name}</a>"

# =====================================
# اللوحة
# =====================================

def make_board(chat_id):

    _, group = get_group(chat_id)

    today = datetime.now().strftime("%Y/%m/%d")

    state = (
        "🟢 مفتوحة"
        if group["list_open"]
        else "🔴 مغلقة"
    )

    text = (
        f"📅 <b>التاريخ:</b> {today}\n\n"

        "اعلمي رعاكِ الله أنَّ حضوركِ "
        "لمجالس العلم هو محضُ انتقاءٍ "
        "وتوفيقٍ من الله "
        "فأحسني رعاية هذه النعمة "
        "واحمدي الله عليها.\n\n"
    )

    # القارئات

    text += "━━━━━━━━━━━━━━━\n"
    text += f"📖 <b>القارئات</b> ({len(group['readers'])})\n\n"

    if not group["readers"]:

        text += "لا يوجد.\n"

    else:

        for i, member in enumerate(
            group["readers"],
            start=1
        ):

            done = (
                " ✅"
                if str(member["id"]) in group["completed"]
                else ""
            )

            text += (
                f"{i}. "
                f"{mention(member['id'], member['name'])}"
                f"{done}\n"
            )

    text += "\n"

    # المستمعات

    text += "━━━━━━━━━━━━━━━\n"
    text += f"🎧 <b>المستمعات</b> ({len(group['listeners'])})\n\n"

    if not group["listeners"]:

        text += "لا يوجد.\n"

    else:

        for i, member in enumerate(
            group["listeners"],
            start=1
        ):

            text += (
                f"{i}. "
                f"{mention(member['id'], member['name'])}\n"
            )

    text += "\n"

    # المعتذرات

    text += "━━━━━━━━━━━━━━━\n"
    text += f"🌿 <b>المعتذرات</b> ({len(group['excused'])})\n\n"

    if not group["excused"]:

        text += "لا يوجد.\n"

    else:

        for i, member in enumerate(
            group["excused"],
            start=1
        ):

            text += (
                f"{i}. "
                f"{mention(member['id'], member['name'])}\n"
            )

    text += "\n━━━━━━━━━━━━━━━\n"
    text += f"🔒 <b>حالة القائمة:</b> {state}"

    return text

# =====================================
# الأزرار
# =====================================

def main_keyboard(chat_id, user_id):

    keyboard = types.InlineKeyboardMarkup(
        row_width=2
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "📝 تسجيل اسمي",
            callback_data="reader"
        ),

        types.InlineKeyboardButton(
            "🎧 مستمعة",
            callback_data="listener"
        )
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "🌿 معتذرة",
            callback_data="excused"
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

# =====================================
# الإعدادات
# =====================================

def settings_keyboard(chat_id):

    _, group = get_group(chat_id)

    state_button = (
        "🔒 إغلاق القائمة"
        if group["list_open"]
        else "🔓 فتح القائمة"
    )

    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(

        types.InlineKeyboardButton(
            state_button,
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
            callback_data="call"
        )
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "🔄 إعادة ضبط القائمة",
            callback_data="reset"
        )
    )

    return keyboard

# =====================================
# تحديث اللوحة
# =====================================

def update_board(chat_id, user_id):

    _, group = get_group(chat_id)

    if not group["message_id"]:
        return

    try:

        bot.edit_message_text(

            chat_id=chat_id,

            message_id=group["message_id"],

            text=make_board(chat_id),

            parse_mode="HTML",

            disable_web_page_preview=True,

            reply_markup=main_keyboard(
                chat_id,
                user_id
            )
        )

    except Exception as e:

        print(e)

# =====================================
# حذف العضوة
# =====================================

def remove_member(group, user_id):

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

# =====================================
# start
# =====================================

@bot.message_handler(commands=["start"])
def start(message):

    # الخاص

    if message.chat.type == "private":

        bot.send_message(

            message.chat.id,

            "السلام عليكم ورحمة الله وبركاته\n\n"

            "حيَّاكِ الله.\n\n"

            "انشري البوت فضلًا "
            "فهو صدقةٌ عنِّي وعن والديَّ "
            "ومقرأتنا وكل المسلمين والمسلمات "
            "والمؤمنين والمؤمنات "
            "الأحياء منهم والأموات."
        )

        return

    # المجموعة

    data = load_data()

    chat_id = str(message.chat.id)

    data[chat_id] = default_group()

    sent = bot.send_message(

        message.chat.id,

        make_board(message.chat.id),

        parse_mode="HTML",

        disable_web_page_preview=True,

        reply_markup=main_keyboard(
            message.chat.id,
            message.from_user.id
        )
    )

    data[chat_id]["message_id"] = sent.message_id

    save_data(data)

# =====================================
# الأزرار
# =====================================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):

    data, group = get_group(
        call.message.chat.id
    )

    user = call.from_user

    full_name = user.first_name or "مستخدمة"

    if user.last_name:
        full_name += f" {user.last_name}"

    member = {
        "id": str(user.id),
        "name": full_name
    }

    # قارئة

    if call.data == "reader":

        if not group["list_open"]:

            bot.answer_callback_query(
                call.id,
                "القائمة مغلقة."
            )

            return

        remove_member(group, user.id)

        group["readers"].append(member)

    # مستمعة

    elif call.data == "listener":

        remove_member(group, user.id)

        group["listeners"].append(member)

    # معتذرة

    elif call.data == "excused":

        remove_member(group, user.id)

        group["excused"].append(member)

    # حذف

    elif call.data == "delete":

        remove_member(group, user.id)

        group["completed"] = [

            x for x in group["completed"]

            if str(x) != str(user.id)
        ]

    # تم الفراغ

    elif call.data == "done":

        if str(user.id) not in group["completed"]:

            group["completed"].append(
                str(user.id)
            )

    # الإعدادات

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

        return

    # فتح وإغلاق

    elif call.data == "toggle":

        if not is_admin(
            user.id,
            call.message.chat.id
        ):
            return

        group["list_open"] = (
            not group["list_open"]
        )

    # تحديث

    elif call.data == "refresh":

        pass

    # إعادة ضبط

    elif call.data == "reset":

        old_message = group["message_id"]

        data[str(call.message.chat.id)] = (
            default_group()
        )

        data[str(call.message.chat.id)][
            "message_id"
        ] = old_message

    # المناداة

    elif call.data == "call":

        all_members = (
            group["readers"] +
            group["listeners"] +
            group["excused"]
        )

        for member in all_members:

            try:

                bot.send_message(
                    int(member["id"]),
                    "هلمُّوا لمجلسٍ تحفُّه الملائكة 🌿"
                )

            except:
                pass

    save_data(data)

    update_board(
        call.message.chat.id,
        user.id
    )

    bot.answer_callback_query(
        call.id,
        "تم."
    )

# =====================================
# تشغيل Flask
# =====================================

def run_flask():

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )

# =====================================
# التشغيل
# =====================================

if __name__ == "__main__":

    flask_thread = threading.Thread(
        target=run_flask
    )

    flask_thread.start()

    bot.infinity_polling(
        skip_pending=True
    )
