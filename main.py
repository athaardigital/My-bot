import os
import json
import html
import threading
from datetime import datetime
from flask import Flask
from dotenv import load_dotenv
import telebot
from telebot import types
from hijri_converter import Gregorian

# إعدادات البوت
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
        "message_id": None, "list_open": True, "extra_roles_open": False,
        "readers": [], "listeners": [], "excused": [], "swap_state": None
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
    except: return False

def mention(user_id, name):
    return f"<a href='tg://user?id={user_id}'>{html.escape(name)}</a>"

def get_dates():
    ar_days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    now = datetime.now()
    # التاريخ الميلادي
    miladi = f"{ar_days[now.weekday()]} {now.day}/{now.month}/{now.year} م"
    # التاريخ الهجري
    h = Gregorian.fromdate(now.date()).to_hijri()
    hijri = f"{h.day} {h.month_name()} {h.year} هـ"
    return f"{hijri} | {miladi}"

def make_board(chat_id):
    _, group = get_group(chat_id)
    text = f"📅 {get_dates()}\n\n📊 إحصاء المجلس الحالي:\n⏳ ---------------------------------- ⏳\n\n"
    text += "<blockquote>❝ اعلموا رعاكم الله أن حضوركم مجالس العلم النافع هو محض اصطفاء من ربكم فاحمدوه على هذه النعمة وأحسنوا رعايتها ❞</blockquote>\n\n"
    text += "⏳ ---------------------------------- ⏳\n\n✨ قَائِمَةُ تِلَاوَةِ الْقُرْآنِ الْكَرِيمِ ✨\n\n"
    
    text += f"📖 الْقَارِئُونَ: {len(group['readers'])}\n"
    for i, r in enumerate(group['readers'], 1):
        text += f"{i}. {mention(r['id'], r['name'])}{' ✅' if r.get('done') else ''}\n"
    
    text += f"\n🎧 الْمُسْتَمِعُونَ: {len(group['listeners'])}\n"
    for i, l in enumerate(group['listeners'], 1):
        text += f"{i}. {mention(l['id'], l['name'])}\n"
        
    text += f"\n❌ الْمُعْتَذِرُونَ: {len(group['excused'])}\n"
    for i, e in enumerate(group['excused'], 1):
        text += f"{i}. {mention(e['id'], e['name'])}\n"
    
    return text

def main_keyboard(chat_id):
    _, group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("حذف آخر دور 🗑️", callback_data="delete_last"), types.InlineKeyboardButton("تسجيل اسمي 📝", callback_data="reader"))
    if group.get("extra_roles_open"): keyboard.row(types.InlineKeyboardButton("دور إضافي ➕", callback_data="extra_role"))
    keyboard.row(types.InlineKeyboardButton("❌ معتذر", callback_data="excused"), types.InlineKeyboardButton("🎧 مستمع", callback_data="listener"))
    keyboard.row(types.InlineKeyboardButton("✅ تم الفراغ", callback_data="done"))
    keyboard.row(types.InlineKeyboardButton("⚙️ إعدادات المشرفين", callback_data="settings"))
    return keyboard

def settings_keyboard(chat_id):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("إدارة وتبديل الأدوار 🔄", callback_data="mr_list"))
    keyboard.row(types.InlineKeyboardButton("القائمة الإضافية 🔓/🔒", callback_data="toggle_extra"), types.InlineKeyboardButton("القائمة الأساسية 🔓/🔒", callback_data="toggle_list"))
    keyboard.row(types.InlineKeyboardButton("الإحصاء النهائي 📊", callback_data="final_stats"), types.InlineKeyboardButton("مناداة 📢", callback_data="call"))
    keyboard.row(types.InlineKeyboardButton("تحديث 🔄", callback_data="resend"), types.InlineKeyboardButton("تصفير 🔄", callback_data="reset"))
    keyboard.row(types.InlineKeyboardButton("عودة للمجلس ↩️", callback_data="back_to_main"))
    return keyboard

def readers_list_keyboard(chat_id):
    _, group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup()
    for i, r in enumerate(group.get("readers", [])):
        text_name = f"{i+1}. {r['name']}"
        if group.get("swap_state") == i: text_name += " (محدد 🔄)"
        keyboard.add(types.InlineKeyboardButton(text_name, callback_data=f"mr_sel_{i}"))
    if group.get("swap_state") is not None: keyboard.add(types.InlineKeyboardButton("إلغاء التبديل ❌", callback_data="mr_cancel_swap"))
    keyboard.add(types.InlineKeyboardButton("رجوع 🔙", callback_data="settings"))
    return keyboard

def reader_action_keyboard(index):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("تقديم ⬆️", callback_data=f"mr_up_{index}"), types.InlineKeyboardButton("تأخير ⬇️", callback_data=f"mr_dn_{index}"))
    keyboard.row(types.InlineKeyboardButton("تبديل 🔄", callback_data=f"mr_sw_{index}"))
    keyboard.add(types.InlineKeyboardButton("رجوع 🔙", callback_data="mr_list"))
    return keyboard

@bot.message_handler(commands=["start"])
def start(message):
    data, group = get_group(message.chat.id)
    sent = bot.send_message(message.chat.id, make_board(message.chat.id), parse_mode="HTML", reply_markup=main_keyboard(message.chat.id))
    group["message_id"] = sent.message_id
    save_data(data)

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    data, group = get_group(chat_id)
    
    target_markup = "main"

    # --- أزرار المستخدمين ---
    if call.data == "reader":
        if not group.get("list_open", True): return bot.answer_callback_query(call.id, "القائمة مغلقة 🔴", show_alert=True)
        group["readers"] = [r for r in group["readers"] if r["id"] != user_id]
        group["listeners"] = [u for u in group["listeners"] if u["id"] != user_id]
        group["excused"] = [u for u in group["excused"] if u["id"] != user_id]
        group["readers"].append({"id": user_id, "name": user_name, "done": False})
        bot.answer_callback_query(call.id, "تم تسجيلك كقارئ ✅")

    elif call.data == "delete_last":
        target_index = -1
        for i in range(len(group["readers"]) - 1, -1, -1):
            if group["readers"][i]["id"] == user_id:
                target_index = i
                break
        if target_index != -1:
            group["readers"].pop(target_index)
            bot.answer_callback_query(call.id, "تم حذف آخر دور لك 🗑️")
        else:
            bot.answer_callback_query(call.id, "ليس لديك أدوار لحذفها ⚠️", show_alert=True)

    elif call.data == "done":
        found = False
        for r in group["readers"]:
            if r["id"] == user_id and not r.get("done"):
                r["done"] = True
                found = True
                break
        if found: bot.answer_callback_query(call.id, "تم تأكيد فراغك ✅")
        else: bot.answer_callback_query(call.id, "ليس لديك دور لتأكيده ⚠️", show_alert=True)

    elif call.data == "listener":
        group["readers"] = [r for r in group["readers"] if r["id"] != user_id]
        group["listeners"] = [u for u in group["listeners"] if u["id"] != user_id]
        group["excused"] = [u for u in group["excused"] if u["id"] != user_id]
        group["listeners"].append({"id": user_id, "name": user_name})
        bot.answer_callback_query(call.id, "تم تسجيلك كمستمع 🎧")
        
    elif call.data == "excused":
        group["readers"] = [r for r in group["readers"] if r["id"] != user_id]
        group["listeners"] = [u for u in group["listeners"] if u["id"] != user_id]
        group["excused"] = [u for u in group["excused"] if u["id"] != user_id]
        group["excused"].append({"id": user_id, "name": user_name})
        bot.answer_callback_query(call.id, "تم تسجيل اعتذارك ❌")

    # --- أزرار المشرفين ---
    elif is_admin(user_id, chat_id):
        if call.data == "settings": target_markup = "settings"
        elif call.data == "back_to_main": target_markup = "main"
        elif call.data == "toggle_list": group["list_open"] = not group.get("list_open", True)
        elif call.data == "toggle_extra": group["extra_roles_open"] = not group.get("extra_roles_open", False)
        elif call.data == "reset": group["readers"] = []; group["listeners"] = []; group["excused"] = []
        elif call.data == "final_stats":
            stats = f"📊 إحصائية المجلس ({get_dates()}):\n\n"
            stats += f"📖 القراء ({len(group['readers'])}):\n" + "\n".join([f"- {r['name']}" for r in group['readers']])
            stats += f"\n\n🎧 المستمعون ({len(group['listeners'])}):\n" + "\n".join([f"- {l['name']}" for l in group['listeners']])
            stats += f"\n\n❌ المعتذرون ({len(group['excused'])}):\n" + "\n".join([f"- {e['name']}" for e in group['excused']])
            bot.send_message(chat_id, stats)
            target_markup = "settings"
        elif call.data == "call":
            not_done = [mention(r['id'], r['name']) for r in group["readers"] if not r.get('done')]
            if not_done: bot.send_message(chat_id, "📢 نداء للقراء:\n" + "\n".join(not_done), parse_mode="HTML")
            else: bot.answer_callback_query(call.id, "الجميع أنهى القراءة ✨", show_alert=True)
            target_markup = "settings"
        elif call.data == "mr_list": target_markup = "readers_list"
        elif call.data.startswith("mr_sel_"):
            idx = int(call.data.split("_")[2])
            if group["swap_state"] is not None:
                i1, i2 = group["swap_state"], idx
                group["readers"][i1], group["readers"][i2] = group["readers"][i2], group["readers"][i1]
                group["swap_state"] = None
            else: group["swap_state"] = idx
            target_markup = "readers_list"
        elif call.data == "mr_cancel_swap": group["swap_state"] = None; target_markup = "readers_list"
        elif call.data.startswith("mr_up_"):
            idx = int(call.data.split("_")[2])
            if idx > 0: group["readers"][idx], group["readers"][idx-1] = group["readers"][idx-1], group["readers"][idx]
            target_markup = "readers_list"
        elif call.data.startswith("mr_dn_"):
            idx = int(call.data.split("_")[2])
            if idx < len(group["readers"])-1: group["readers"][idx], group["readers"][idx+1] = group["readers"][idx+1], group["readers"][idx]
            target_markup = "readers_list"
        elif call.data.startswith("mr_sw_"): target_markup = "readers_list" # للتسهيل
        elif call.data == "resend":
            try: bot.delete_message(chat_id, group["message_id"])
            except: pass
            sent = bot.send_message(chat_id, make_board(chat_id), parse_mode="HTML", reply_markup=main_keyboard(chat_id))
            group["message_id"] = sent.message_id
    
    save_data(data)
    # تحديث الواجهة
    markup = main_keyboard(chat_id)
    if target_markup == "settings": markup = settings_keyboard(chat_id)
    elif target_markup == "readers_list": markup = readers_list_keyboard(chat_id)
    
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=group["message_id"], text=make_board(chat_id), parse_mode="HTML", reply_markup=markup)
    except: pass
    try: bot.answer_callback_query(call.id)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=10000), daemon=True).start()
    bot.infinity_polling()
