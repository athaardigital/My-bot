import os
import time
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv

import telebot
from telebot import types
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# =====================================
# تحميل المتغيرات
# =====================================

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.environ.get("MONGO_URI")

if not BOT_TOKEN:
    raise Exception("TOKEN NOT FOUND")
if not MONGO_URI:
    raise Exception("MONGO_URI NOT FOUND")

bot = telebot.TeleBot(BOT_TOKEN)

# =====================================
# الاتصال بقاعدة البيانات السحابية (MongoDB)
# =====================================

client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
db = client["AthaarDB"]
groups_col = db["groups"]

# =====================================
# Flask & Webhook
# =====================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running on Cloud Database!", 200

@app.route("/" + BOT_TOKEN, methods=["POST"])
def receive_update():
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

# =====================================
# بيانات المجموعة السحابية
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
    chat_id = str(chat_id)
    doc = groups_col.find_one({"chat_id": chat_id})
    if not doc:
        group = default_group()
        groups_col.insert_one({"chat_id": chat_id, "group": group})
        return group
    return doc["group"]

def save_group(chat_id, group):
    groups_col.update_one(
        {"chat_id": str(chat_id)}, 
        {"$set": {"group": group}}, 
        upsert=True
    )

# =====================================
# الأدمن
# =====================================

def is_admin(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
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
    group = get_group(chat_id)
    today = datetime.now().strftime("%Y/%m/%d")

    state = "🟢 مفتوحة" if group["list_open"] else "🔴 مغلقة"

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
        for i, member in enumerate(group["readers"], start=1):
            done = " ✅" if str(member["id"]) in group["completed"] else ""
            text += f"{i}. {mention(member['id'], member['name'])}{done}\n"

    text += "\n"

    # المستمعات
    text += "━━━━━━━━━━━━━━━\n"
    text += f"🎧 <b>المستمعات</b> ({len(group['listeners'])})\n\n"

    if not group["listeners"]:
        text += "لا يوجد.\n"
    else:
        for i, member in enumerate(group["listeners"], start=1):
            text += f"{i}. {mention(member['id'], member['name'])}\n"

    text += "\n"

    # المعتذرات
    text += "━━━━━━━━━━━━━━━\n"
    text += f"🌿 <b>المعتذرات</b> ({len(group['excused'])})\n\n"

    if not group["excused"]:
        text += "لا يوجد.\n"
    else:
        for i, member in enumerate(group["excused"], start=1):
            text += f"{i}. {mention(member['id'], member['name'])}\n"

    text += "\n━━━━━━━━━━━━━━━\n"
    text += f"🔒 <b>حالة القائمة:</b> {state}"

    return text

# =====================================
# الأزرار
# =====================================

def main_keyboard(chat_id, user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📝 تسجيل اسمي", callback_data="reader"),
        types.InlineKeyboardButton("🎧 مستمعة", callback_data="listener")
    )
    keyboard.add(
        types.InlineKeyboardButton("🌿 معتذرة", callback_data="excused"),
        types.InlineKeyboardButton("🗑️ حذف اسمي", callback_data="delete")
    )
    keyboard.add(
        types.InlineKeyboardButton("✅ تم الفراغ من القراءة", callback_data="done")
    )

    if is_admin(user_id, chat_id):
        keyboard.add(
            types.InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")
        )

    return keyboard

# =====================================
# الإعدادات
# =====================================

def settings_keyboard(chat_id):
    group = get_group(chat_id)
    state_button = "🔒 إغلاق القائمة" if group["list_open"] else "🔓 فتح القائمة"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(state_button, callback_data="toggle"))
    keyboard.add(types.InlineKeyboardButton("📖 تحديث القائمة", callback_data="refresh"))
    keyboard.add(types.InlineKeyboardButton("📢 المناداة", callback_data="call"))
    keyboard.add(types.InlineKeyboardButton("🔄 إعادة ضبط القائمة", callback_data="reset"))

    return keyboard

# =====================================
# تحديث اللوحة
# =====================================

def update_board(chat_id, user_id):
    group = get_group(chat_id)
    if not group["message_id"]:
        return

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=group["message_id"],
            text=make_board(chat_id),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=main_keyboard(chat_id, user_id)
        )
    except Exception as e:
        print(f"Update Board Error: {e}")

# =====================================
# حذف العضوة
# =====================================

def remove_member(group, user_id):
    group["readers"] = [x for x in group["readers"] if str(x["id"]) != str(user_id)]
    group["listeners"] = [x for x in group["listeners"] if str(x["id"]) != str(user_id)]
    group["excused"] = [x for x in group["excused"] if str(x["id"]) != str(user_id)]

# =====================================
# start
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    if message.chat.type == "private":
        bot.send_message(
            message.chat.id,
            "السلام عليكم ورحمة الله وبركاته\n\nحيَّاكِ الله.\n\n"
            "انشري البوت فضلًا فهو صدقةٌ عنِّي وعن والديَّ "
            "ومقرأتنا وكل المسلمين والمسلمات والمؤمنين والمؤمنات "
            "الأحياء منهم والأموات."
        )
        return

    chat_id = str(message.chat.id)
    group = default_group()

    sent = bot.send_message(
        message.chat.id,
        make_board(chat_id),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=main_keyboard(message.chat.id, message.from_user.id)
    )

    group["message_id"] = sent.message_id
    save_group(chat_id, group)

# =====================================
# الأزرار
# =====================================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    group = get_group(chat_id)
    user = call.from_user

    full_name = user.first_name or "مستخدمة"
    if user.last_name:
        full_name += f" {user.last_name}"

    member = {"id": str(user.id), "name": full_name}

    if call.data == "reader":
        if not group["list_open"]:
            bot.answer_callback_query(call.id, "القائمة مغلقة.")
            return
        remove_member(group, user.id)
        group["readers"].append(member)

    elif call.data == "listener":
        remove_member(group, user.id)
        group["listeners"].append(member)

    elif call.data == "excused":
        remove_member(group, user.id)
        group["excused"].append(member)

    elif call.data == "delete":
        remove_member(group, user.id)
        group["completed"] = [x for x in group["completed"] if str(x) != str(user.id)]

    elif call.data == "done":
        if str(user.id) not in group["completed"]:
            group["completed"].append(str(user.id))

    elif call.data == "settings":
        if not is_admin(user.id, chat_id):
            return
        bot.edit_message_reply_markup(
            chat_id,
            call.message.message_id,
            reply_markup=settings_keyboard(chat_id)
        )
        return

    elif call.data == "toggle":
        if not is_admin(user.id, chat_id):
            return
        group["list_open"] = not group["list_open"]

    elif call.data == "refresh":
        pass

    elif call.data == "reset":
        old_message = group["message_id"]
        group = default_group()
        group["message_id"] = old_message

    elif call.data == "call":
        all_members = group["readers"] + group["listeners"] + group["excused"]
        for mem in all_members:
            try:
                bot.send_message(int(mem["id"]), "هلمُّوا لمجلسٍ تحفُّه الملائكة 🌿")
            except:
                pass

    # حفظ البيانات في السحابة بعد أي تعديل
    save_group(chat_id, group)
    update_board(chat_id, user.id)
    
    try:
        bot.answer_callback_query(call.id, "تم.")
    except:
        pass

# =====================================
# التشغيل مع Webhook
# =====================================

if __name__ == "__main__":
    # مسح أي Webhook قديم لتجنب التعارض
    bot.remove_webhook()
    time.sleep(1)
    
    # إعداد الـ Webhook الخاص بخوادم Render
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
    if RENDER_URL:
        bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
        print(f"Webhook set to {RENDER_URL}/{BOT_TOKEN}")
    else:
        print("⚠️ لم يتم العثور على RENDER_EXTERNAL_URL في البيئة.")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
