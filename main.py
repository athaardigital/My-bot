import os
import json
from datetime import datetime

from flask import Flask, request
from dotenv import load_dotenv

import telebot
from telebot import types

# ======================================
# تحميل المتغيرات
# ======================================

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not BOT_TOKEN:
    raise Exception("BOT TOKEN NOT FOUND")

if not WEBHOOK_URL:
    raise Exception("WEBHOOK URL NOT FOUND")

bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

DATA_FILE = "groups_data.json"

# ======================================
# تحميل البيانات
# ======================================

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

# ======================================
# بيانات المجموعة
# ======================================

def default_group():

    return {

        "message_id": None,

        "list_open": False,

        "created_date": datetime.now().strftime("%Y/%m/%d"),

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

# ======================================
# التحقق من الإشراف
# ======================================

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

# ======================================
# منشن آمن
# ======================================

def mention(user_id, name):

    safe_name = name.replace("[", "").replace("]", "")

    return f"<a href='tg://user?id={user_id}'>{safe_name}</a>"

# ======================================
# إنشاء اللوحة
# ======================================

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

        "اعلمي رعاكِ الله أنَّ حضوركِ لمجالس العلم "
        "هو محضُ انتقاءٍ وتوفيقٍ من الله، "
        "فأحسني رعاية هذه النعمة واحمدي الله عليها.\n\n"
    )

    # ==================================
    # القارئات
    # ==================================

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

    # ==================================
    # المستمعات
    # ==================================

    text += "━━━━━━━━━━━━━━━\n"
    text += f"🎧 <b>المستمعات</b> ({len(group['listeners'])})\n\n"

    if not group["listeners"]:

        text += "لا يوجد.\n"

    else:

        for i, member in enumerate(
            group["listeners"],
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

    # ==================================
    # المعتذرات
    # ==================================

    text += "━━━━━━━━━━━━━━━\n"
    text += f"🌿 <b>المعتذرات</b> ({len(group['excused'])})\n\n"

    if not group["excused"]:

        text += "لا يوجد.\n"

    else:

        for i, member in enumerate(
            group["excused"],
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

    text += "\n━━━━━━━━━━━━━━━\n"
    text += f"🔒 <b>حالة القائمة:</b> {state}"

    return text

# ======================================
# الأزرار الأساسية
# ======================================

def main_keyboard(chat_id, user_id):

    keyboard = types.InlineKeyboardMarkup(
        row_width=2
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "📝 تسجيل اسمي",
            callback_data="register_reader"
        ),

        types.InlineKeyboardButton(
            "🎧 تسجيل مستمعة",
            callback_data="register_listener"
        )
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "🌿 تسجيل معتذرة",
            callback_data="register_excused"
        ),

        types.InlineKeyboardButton(
            "🗑️ حذف اسمي",
            callback_data="delete_name"
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

# ======================================
# أزرار الإعدادات
# ======================================

def settings_keyboard(chat_id):

    _, group = get_group(chat_id)

    state_button = (
        "🔒 إغلاق القائمة"
        if group["list_open"]
        else "🔓 فتح القائمة"
    )

    keyboard = types.InlineKeyboardMarkup(
        row_width=1
    )

    keyboard.add(

        types.InlineKeyboardButton(
            state_button,
            callback_data="toggle_list"
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
            callback_data="call_all"
        )
    )

    keyboard.add(

        types.InlineKeyboardButton(
            "🔄 إعادة ضبط القائمة",
            callback_data="reset"
        )
    )

    return keyboard

# ======================================
# تحديث اللوحة
# ======================================

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

# ======================================
# إزالة العضوة
# ======================================

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

# ======================================
# /start
# ======================================

@bot.message_handler(commands=["start"])
def start(message):

    # ==============================
    # الخاص
    # ==============================

    if message.chat.type == "private":

        bot.send_message(

            message.chat.id,

            "السلام عليكم ورحمة الله وبركاته\n\n"

            "حيَّاكِ الله.\n\n"

            "انشري البوت فضلًا، "
            "فهو صدقةٌ عنِّي وعن والديَّ "
            "ومقرأتِنا وكلِّ المسلمين والمسلمات "
            "والمؤمنين والمؤمنات الأحياء منهم والأموات."
        )

        return

    # ==============================
    # المجموعة
    # ==============================

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

# ======================================
# جميع الأزرار
# ======================================

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

    # ==================================
    # تسجيل قارئة
    # ==================================

    if call.data == "register_reader":

        if not group["list_open"]:

            bot.answer_callback_query(
                call.id,
                "القائمة مغلقة حالياً."
            )

            return

        remove_member(group, user.id)

        group["readers"].append(member)

        save_data(data)

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم تسجيلكِ قارئة."
        )

    # ==================================
    # تسجيل مستمعة
    # ==================================

    elif call.data == "register_listener":

        if not group["list_open"]:

            bot.answer_callback_query(
                call.id,
                "القائمة مغلقة حالياً."
            )

            return

        remove_member(group, user.id)

        group["listeners"].append(member)

        save_data(data)

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم تسجيلكِ مستمعة."
        )

    # ==================================
    # تسجيل معتذرة
    # ==================================

    elif call.data == "register_excused":

        remove_member(group, user.id)

        group["excused"].append(member)

        save_data(data)

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم تسجيلكِ معتذرة."
        )

    # ==================================
    # حذف الاسم
    # ==================================

    elif call.data == "delete_name":

        remove_member(group, user.id)

        group["completed"] = [

            x for x in group["completed"]

            if str(x) != str(user.id)
        ]

        save_data(data)

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم حذف اسمكِ."
        )

    # ==================================
    # تم الفراغ
    # ==================================

    elif call.data == "done":

        exists = any(

            str(x["id"]) == str(user.id)

            for x in (
                group["readers"] +
                group["listeners"]
            )
        )

        if not exists:

            bot.answer_callback_query(
                call.id,
                "سجلي اسمكِ أولاً."
            )

            return

        if str(user.id) not in group["completed"]:

            group["completed"].append(
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

    # ==================================
    # الإعدادات
    # ==================================

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

    # ==================================
    # فتح وإغلاق
    # ==================================

    elif call.data == "toggle_list":

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
            "تم تحديث حالة القائمة."
        )

    # ==================================
    # تحديث
    # ==================================

    elif call.data == "refresh":

        update_board(
            call.message.chat.id,
            user.id
        )

        bot.answer_callback_query(
            call.id,
            "تم تحديث القائمة."
        )

    # ==================================
    # إعادة ضبط
    # ==================================

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
            "تمت إعادة ضبط القائمة."
        )

    # ==================================
    # المناداة
    # ==================================

    elif call.data == "call_all":

        if not is_admin(
            user.id,
            call.message.chat.id
        ):
            return

        sent_count = 0

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

                sent_count += 1

            except:
                pass

        bot.answer_callback_query(
            call.id,
            f"تم إرسال {sent_count}"
        )

# ======================================
# Flask
# ======================================

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

# ======================================
# تشغيل البوت
# ======================================

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
