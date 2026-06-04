import os
import json
import html
import threading
from datetime import datetime

from flask import Flask
from dotenv import load_dotenv

import telebot
from telebot import types

# =====================================
# تحميل المتغيرات والبيانات
# =====================================

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise Exception("TELEGRAM_BOT_TOKEN NOT FOUND IN ENVIRONMENT VARIABLES")

bot = telebot.TeleBot(BOT_TOKEN)

# حل مشكلة التعارض (Conflict 409): إزالة الويب هوك القديم لتفعيل الـ Polling بنجاح
try:
    bot.remove_webhook()
except Exception as webhook_error:
    print(f"Warning: Could not remove webhook: {webhook_error}")

DATA_FILE = "groups_data.json"
file_lock = threading.Lock()  # قفل أمني لمنع تداخل العمليات وتلف ملف البيانات

# =====================================
# Flask Configuration
# =====================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running perfectly!", 200

# =====================================
# إدارة البيانات (JSON I/O)
# =====================================

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with file_lock:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_data(data):
    try:
        with file_lock:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        print(f"Error saving data: {e}")

# =====================================
# هيكلية بيانات المجموعات
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
# التحقق من الصلاحيات
# =====================================

def is_admin(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

# =====================================
# إنشاء المنشن الآمن
# =====================================

def mention(user_id, name):
    safe_name = html.escape(name)
    return f"<a href='tg://user?id={user_id}'>{safe_name}</a>"

# =====================================
# بناء لوحة العرض الرئيسية
# =====================================

def make_board(chat_id):
    _, group = get_group(chat_id)
    today = datetime.now().strftime("%Y/%m/%d")
    state = "🟢 مفتوحة" if group["list_open"] else "🔴 مغلقة"

    text = (
        f"📅 <b>التاريخ:</b> {today}\n\n"
        "اعلمي رعاكِ الله أنَّ حضوركِ لمجالس العلم هو محضُ انتقاءٍ "
        "وتوفيقٍ من الله، فأحسني رعاية هذه النعمة واحمدي الله عليها.\n\n"
    )

    # قسم القارئات
    text += "━━━━━━━━━━━━━━━\n"
    text += f"📖 <b>القارئات</b> ({len(group['readers'])})\n\n"
    if not group["readers"]:
        text += "لا يوجد.\n"
    else:
        for i, member in enumerate(group["readers"], start=1):
            done = " ✅" if str(member["id"]) in group["completed"] else ""
            text += f"{i}. {mention(member['id'], member['name'])}{done}\n"

    text += "\n"

    # قسم المستمعات
    text += "━━━━━━━━━━━━━━━\n"
    text += f"🎧 <b>المستمعات</b> ({len(group['listeners'])})\n\n"
    if not group["listeners"]:
        text += "لا يوجد.\n"
    else:
        for i, member in enumerate(group["listeners"], start=1):
            text += f"{i}. {mention(member['id'], member['name'])}\n"

    text += "\n"

    # قسم المعتذرات
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
# صناعة لوحات الأزرار
# =====================================

def main_keyboard():
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
    keyboard.add(
        types.InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")
    )
    return keyboard

def settings_keyboard(chat_id):
    _, group = get_group(chat_id)
    state_button = "🔒 إغلاق القائمة" if group["list_open"] else "🔓 فتح القائمة"

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(types.InlineKeyboardButton(state_button, callback_data="toggle"))
    keyboard.add(types.InlineKeyboardButton("📖 تحديث اللوحة", callback_data="refresh"))
    keyboard.add(types.InlineKeyboardButton("📢 المناداة", callback_data="call"))
    keyboard.add(types.InlineKeyboardButton("🔄 إعادة الضبط", callback_data="reset"))
    keyboard.add(types.InlineKeyboardButton("🔙 عودة للوحة الرئيسية", callback_data="back_to_main"))
    return keyboard

# =====================================
# تحديث اللوحة في المجموعات
# =====================================

def update_board(chat_id):
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
            reply_markup=main_keyboard()
        )
    except Exception as e:
        print(f"Error updating board: {e}")

# =====================================
# تنظيف العضوة من القوائم
# =====================================

def remove_member(group, user_id):
    uid = str(user_id)
    group["readers"] = [x for x in group["readers"] if str(x["id"]) != uid]
    group["listeners"] = [x for x in group["listeners"] if str(x["id"]) != uid]
    group["excused"] = [x for x in group["excused"] if str(x["id"]) != uid]

# =====================================
# استجابة الأمر /start
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    if message.chat.type == "private":
        bot.send_message(
            message.chat.id,
            "السلام عليكم ورحمة الله وبركاته\n\n"
            "حيَّاكِ الله.\n\n"
            "انشري البوت فضلًا فهو صدقةٌ عنِّي وعن والديَّ ومقرأتنا وكل المسلمين والمسلمات الأحياء منهم والأموات."
        )
        return

    data, group = get_group(message.chat.id)
    chat_id_str = str(message.chat.id)

    data[chat_id_str] = default_group()
    
    sent = bot.send_message(
        message.chat.id,
        make_board(message.chat.id),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=main_keyboard()
    )

    data[chat_id_str]["message_id"] = sent.message_id
    save_data(data)

# =====================================
# معالجة الأزرار التفاعلية
# =====================================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    user = call.from_user
    user_id_str = str(user.id)
    
    data, group = get_group(chat_id)

    full_name = user.first_name or "مستخدمة"
    if user.last_name:
        full_name += f" {user.last_name}"

    member = {"id": user_id_str, "name": full_name}

    admin_actions = ["settings", "toggle", "reset", "call"]

    if call.data in admin_actions:
        if not is_admin(user.id, chat_id):
            bot.answer_callback_query(call.id, "❌ عذرًا، هذا الإجراء متاح للمشرفات فقط.", show_alert=True)
            return

    # 1. تسجيل قارئة
    if call.data == "reader":
        if not group["list_open"]:
            bot.answer_callback_query(call.id, "⚠️ القائمة مغلقة حاليًا من قِبل الإدارة.", show_alert=True)
            return
        remove_member(group, user.id)
        group["readers"].append(member)
        bot.answer_callback_query(call.id, "✅ تم تسجيلكِ كقارئة.")

    # 2. تسجيل مستمعة
    elif call.data == "listener":
        remove_member(group, user.id)
        group["listeners"].append(member)
        bot.answer_callback_query(call.id, "🎧 تم تسجيلكِ كمستمعة.")

    # 3. تسجيل معتذرة
    elif call.data == "excused":
        remove_member(group, user.id)
        group["excused"].append(member)
        bot.answer_callback_query(call.id, "🌿 تم تسجيل اعتذاركِ.")

    # 4. حذف الاسم
    elif call.data == "delete":
        remove_member(group, user.id)
        group["completed"] = [x for x in group["completed"] if str(x) != user_id_str]
        bot.answer_callback_query(call.id, "🗑️ تم حذف اسمكِ من القائمة.")

    # 5. تم الفراغ من القراءة
    elif call.data == "done":
        is_reader = any(str(x["id"]) == user_id_str for x in group["readers"])
        if not is_reader:
            bot.answer_callback_query(call.id, "⚠️ يجب تسجيل اسمكِ كقارئة أولًا لإنهاء القراءة!", show_alert=True)
            return
        if user_id_str not in group["completed"]:
            group["completed"].append(user_id_str)
            bot.answer_callback_query(call.id, "🎉 تقبل الله منكِ وطهر قلبكِ.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "أنتِ مسجلة بالفعل كمكتملة.")

    # 6. فتح قائمة الإعدادات للمشرفين
    elif call.data == "settings":
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=settings_keyboard(chat_id)
        )
        bot.answer_callback_query(call.id, "⚙️ تم فتح لوحة التحكم.")
        return

    # 7. التبديل بين فتح وإغلاق القائمة
    elif call.data == "toggle":
        group["list_open"] = not group["list_open"]
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=settings_keyboard(chat_id)
        )
        status_txt = "مفتوحة الآن" if group["list_open"] else "مغلقة الآن"
        bot.answer_callback_query(call.id, f"⚙️ القائمة {status_txt}.")
        return

    # 8. تحديث لوحة العرض يدوياً
    elif call.data == "refresh":
        bot.answer_callback_query(call.id, "🔄 جاري التحديث...")

    # 9. إعادة ضبط القائمة وتصفير الأسماء
    elif call.data == "reset":
        old_message = group["message_id"]
        data[str(chat_id)] = default_group()
        data[str(chat_id)]["message_id"] = old_message
        bot.answer_callback_query(call.id, "🔄 تم إعادة ضبط القائمة وتصفيرها بالكامل.", show_alert=True)

    # 10. زر العودة للوحة الرئيسية من الإعدادات
    elif call.data == "back_to_main":
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=main_keyboard()
        )
        bot.answer_callback_query(call.id, "🔙 عدتِ للوحة الرئيسية.")
        return

    # 11. نداء العضوات المقيدات في الخاص لتنبيههن
    elif call.data == "call":
        all_members = group["readers"] + group["listeners"] + group["excused"]
        bot.answer_callback_query(call.id, "📢 جاري إرسال التنبيهات في الخاص...")
        for member in all_members:
            try:
                bot.send_message(int(member["id"]), "هلمُّوا لمجلسٍ تحفُّه الملائكة 🌿")
            except Exception:
                pass
        return

    save_data(data)
    update_board(chat_id)

# =====================================
# تشغيل خادم Flask
# =====================================

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# =====================================
# بداية تشغيل النظام الهجين
# =====================================

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    bot.infinity_polling(skip_pending=True)
