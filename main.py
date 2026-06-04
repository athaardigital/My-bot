import os
import json
import html
import threading
from datetime import datetime
from flask import Flask
from dotenv import load_dotenv
import telebot
from telebot import types

load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)
DATA_FILE = "groups_data.json"
file_lock = threading.Lock()
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running perfectly!", 200

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

def default_group():
    return {
        "message_id": None,
        "list_open": True, # يفضل أن تكون مفتوحة افتراضياً عند الإنشاء
        "extra_roles_open": False,
        "readers": [], 
        "listeners": [],
        "excused": []
    }

def get_group(chat_id):
    data = load_data()
    chat_id = str(chat_id)
    if chat_id not in data:
        data[chat_id] = default_group()
        save_data(data)
    return data, data[chat_id]

def is_admin(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

def mention(user_id, name):
    return f"<a href='tg://user?id={user_id}'>{html.escape(name)}</a>"

def get_arabic_date():
    ar_days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    ar_months = ["جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان", "جويلية", "أوت", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    now = datetime.now()
    return f"{ar_days[now.weekday()]} {now.day} {ar_months[now.month - 1]} {now.year} م"

def make_board(chat_id):
    _, group = get_group(chat_id)
    text = f"📅 {get_arabic_date()}\n\n📊 إحصاء المجلس الحالي:\n⏳ ---------------------------------- ⏳\n\n"
    text += "<blockquote>❝ اعلموا رعاكم الله أن حضوركم مجالس العلم النافع هو محض اصطفاء من ربكم فاحمدوه على هذه النعمة وأحسنوا رعايتها ❞</blockquote>\n\n"
    text += "⏳ ---------------------------------- ⏳\n\n✨ قَائِمَةُ تِلَاوَةِ الْقُرْآنِ الْكَرِيمِ ✨\n\n"
    
    text += f"📖 الْقَارِئُونَ/ات: {len(group['readers'])}\n"
    for i, r in enumerate(group['readers'], 1):
        text += f"{i}. {mention(r['id'], r['name'])}{' ✅' if r.get('done') else ''}\n"
    
    text += f"\n🎧 الْمُسْتَمِعُونَ/ات: {len(group['listeners'])}\n"
    for i, l in enumerate(group['listeners'], 1):
        text += f"{i}. {mention(l['id'], l['name'])}\n"
        
    text += f"\n❌ الْمُعْتَذِرُونَ/ات: {len(group['excused'])}\n"
    for i, e in enumerate(group['excused'], 1):
        text += f"{i}. {mention(e['id'], e['name'])}\n"
    
    text += f"\nحالة القائمة: {'🟢 مفتوحة' if group.get('list_open', True) else '🔴 مغلقة'}"
    return text

def main_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("حذف آخر دور 🗑️", callback_data="delete_last"), types.InlineKeyboardButton("تسجيل اسمي 📝", callback_data="reader"))
    keyboard.row(types.InlineKeyboardButton("❌ معتذر/ة", callback_data="excused"), types.InlineKeyboardButton("🎧 مستمع/ة", callback_data="listener"))
    keyboard.row(types.InlineKeyboardButton("✅ تم الفراغ من القراءة", callback_data="done"))
    keyboard.row(types.InlineKeyboardButton("⚙️ إعدادات المشرفين", callback_data="settings"))
    return keyboard

def settings_keyboard(chat_id):
    _, group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("تبديل الأدوار 🔓/🔒", callback_data="toggle_extra"), types.InlineKeyboardButton("فتح/إغلاق القائمة 🔓/🔒", callback_data="toggle_list"))
    keyboard.row(types.InlineKeyboardButton("الإحصاء النهائي 📊", callback_data="final_stats"), types.InlineKeyboardButton("زر المناداة 📢", callback_data="call"))
    keyboard.row(types.InlineKeyboardButton("تحديث 🔄", callback_data="resend"), types.InlineKeyboardButton("تصفير القائمة 🔄", callback_data="reset"))
    keyboard.row(types.InlineKeyboardButton("عودة للمجلس ↩️", callback_data="back_to_main"))
    return keyboard

@bot.message_handler(commands=["start"])
def start(message):
    data, group = get_group(message.chat.id)
    sent = bot.send_message(message.chat.id, make_board(message.chat.id), parse_mode="HTML", reply_markup=main_keyboard())
    group["message_id"] = sent.message_id
    save_data(data)

# دالة مساعدة لتنظيف المستخدم من القوائم الأخرى عند اختياره دوراً جديداً
def remove_user_from_all(user_id, group):
    for lst in ["readers", "listeners", "excused"]:
        group[lst] = [u for u in group[lst] if u["id"] != user_id]

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    data, group = get_group(chat_id)
    
    # التحقق من صلاحيات المشرفين لزر الإعدادات
    if call.data in ["settings", "toggle_extra", "toggle_list", "final_stats", "call", "resend", "reset"]:
        if not is_admin(user_id, chat_id):
            bot.answer_callback_query(call.id, "❌ عذراً، هذا الزر مخصص للمشرفين فقط.", show_alert=True)
            return

    # منطق التسجيل في القوائم
    if call.data == "reader":
        if not group.get("list_open", True):
            bot.answer_callback_query(call.id, "القائمة مغلقة حالياً 🔴", show_alert=True)
            return
        remove_user_from_all(user_id, group)
        group["readers"].append({"id": user_id, "name": user_name, "done": False})
        bot.answer_callback_query(call.id, "تم تسجيلك كقارئ ✅")

    elif call.data == "listener":
        remove_user_from_all(user_id, group)
        group["listeners"].append({"id": user_id, "name": user_name})
        bot.answer_callback_query(call.id, "تم تسجيلك كمستمع 🎧")

    elif call.data == "excused":
        remove_user_from_all(user_id, group)
        group["excused"].append({"id": user_id, "name": user_name})
        bot.answer_callback_query(call.id, "تم تسجيل اعتذارك ❌")

    elif call.data == "done":
        found = False
        for r in group["readers"]:
            if r["id"] == user_id:
                r["done"] = True
                found = True
                break
        if found:
            bot.answer_callback_query(call.id, "تم تأكيد فراغك من القراءة تقبل الله ✅")
        else:
            bot.answer_callback_query(call.id, "يجب أن تسجل كقارئ أولاً ⚠️", show_alert=True)

    # حفظ البيانات بعد أي تغيير
    save_data(data)
    
    # تحديث الرسالة وتجاهل الخطأ في حال لم تتغير البيانات لتجنب تعطل البوت
    try:
        markup = settings_keyboard(chat_id) if call.data in ["settings", "toggle_extra", "toggle_list"] else main_keyboard()
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=group["message_id"], 
            text=make_board(chat_id), 
            parse_mode="HTML", 
            reply_markup=markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        # إذا كان الخطأ أن الرسالة متطابقة، نتجاهله
        if "message is not modified" not in str(e).lower():
            pass 

    bot.answer_callback_query(call.id)

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    print("Bot is running...")
    bot.infinity_polling()

