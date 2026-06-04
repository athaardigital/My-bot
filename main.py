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
        "list_open": True,
        "extra_roles_open": False,
        "readers": [], 
        "listeners": [],
        "excused": [],
        "swap_state": None # حفظ حالة التبديل مؤقتاً
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
    
    text += f"\nحالة القائمة الأساسية: {'🟢 مفتوحة' if group.get('list_open', True) else '🔴 مغلقة'}"
    if group.get('extra_roles_open'):
        text += "\nحالة القائمة الإضافية: 🟢 مفتوحة"
    return text

def main_keyboard(chat_id):
    _, group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("حذف آخر دور 🗑️", callback_data="delete_last"), types.InlineKeyboardButton("تسجيل اسمي 📝", callback_data="reader"))
    
    # يظهر زر الدور الإضافي فقط إذا كانت القائمة الإضافية مفتوحة
    if group.get("extra_roles_open", False):
        keyboard.row(types.InlineKeyboardButton("دور إضافي ➕", callback_data="extra_role"))
        
    keyboard.row(types.InlineKeyboardButton("❌ معتذر/ة", callback_data="excused"), types.InlineKeyboardButton("🎧 مستمع/ة", callback_data="listener"))
    keyboard.row(types.InlineKeyboardButton("✅ تم الفراغ من القراءة", callback_data="done"))
    keyboard.row(types.InlineKeyboardButton("⚙️ إعدادات المشرفين", callback_data="settings"))
    return keyboard

def settings_keyboard(chat_id):
    _, group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("إدارة وتبديل الأدوار 🔄", callback_data="mr_list"))
    keyboard.row(types.InlineKeyboardButton("القائمة الإضافية 🔓/🔒", callback_data="toggle_extra"), types.InlineKeyboardButton("القائمة الأساسية 🔓/🔒", callback_data="toggle_list"))
    keyboard.row(types.InlineKeyboardButton("الإحصاء النهائي 📊", callback_data="final_stats"), types.InlineKeyboardButton("زر المناداة 📢", callback_data="call"))
    keyboard.row(types.InlineKeyboardButton("تحديث 🔄", callback_data="resend"), types.InlineKeyboardButton("تصفير القائمة 🔄", callback_data="reset"))
    keyboard.row(types.InlineKeyboardButton("عودة للمجلس ↩️", callback_data="back_to_main"))
    return keyboard

# كيبورد خاص بأسماء القراء للمشرفين
def readers_list_keyboard(chat_id):
    _, group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup()
    readers = group.get("readers", [])
    for i, r in enumerate(readers):
        text_name = f"{i+1}. {r['name']}"
        # تمييز الاسم إذا كان هو المحدد للتبديل
        if group.get("swap_state") == i:
            text_name += " (محدد للتبديل 🔄)"
        keyboard.add(types.InlineKeyboardButton(text_name, callback_data=f"mr_sel_{i}"))
    
    if group.get("swap_state") is not None:
        keyboard.add(types.InlineKeyboardButton("إلغاء التبديل ❌", callback_data="mr_cancel_swap"))
        
    keyboard.add(types.InlineKeyboardButton("رجوع للإعدادات 🔙", callback_data="settings"))
    return keyboard

# كيبورد التحكم بمركز القارئ
def reader_action_keyboard(index):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("تقديم (لأعلى) ⬆️", callback_data=f"mr_up_{index}"), types.InlineKeyboardButton("تأخير (لأسفل) ⬇️", callback_data=f"mr_dn_{index}"))
    keyboard.row(types.InlineKeyboardButton("التبديل مع... 🔄", callback_data=f"mr_sw_{index}"))
    keyboard.row(types.InlineKeyboardButton("رجوع للأسماء 🔙", callback_data="mr_list"))
    return keyboard

@bot.message_handler(commands=["start"])
def start(message):
    data, group = get_group(message.chat.id)
    sent = bot.send_message(message.chat.id, make_board(message.chat.id), parse_mode="HTML", reply_markup=main_keyboard(message.chat.id))
    group["message_id"] = sent.message_id
    save_data(data)

def remove_user_from_all(user_id, group):
    for lst in ["readers", "listeners", "excused"]:
        group[lst] = [u for u in group[lst] if u["id"] != user_id]

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    data, group = get_group(chat_id)
    
    # تحديد الكيبورد المطلوب إظهاره بناء على الإجراء
    target_markup = "main"

    # التحقق من صلاحيات المشرفين للأزرار الخاصة بهم
    is_admin_action = call.data in ["settings", "toggle_extra", "toggle_list", "final_stats", "call", "resend", "reset"] or call.data.startswith("mr_")
    if is_admin_action and not is_admin(user_id, chat_id):
        bot.answer_callback_query(call.id, "❌ عذراً، هذا الزر مخصص للمشرفين فقط.", show_alert=True)
        return

    # --- أزرار المستخدمين ---
    if call.data == "reader":
        if not group.get("list_open", True):
            bot.answer_callback_query(call.id, "القائمة الأساسية مغلقة حالياً 🔴", show_alert=True)
            return
        remove_user_from_all(user_id, group)
        group["readers"].append({"id": user_id, "name": user_name, "done": False})
        bot.answer_callback_query(call.id, "تم تسجيلك كقارئ ✅")

    elif call.data == "extra_role":
        user_roles = [r for r in group.get("readers", []) if r["id"] == user_id]
        if not user_roles:
            bot.answer_callback_query(call.id, "يجب أن تسجل في الدور الأساسي أولاً! ⚠️", show_alert=True)
            return
        if any(not r.get("done") for r in user_roles):
            bot.answer_callback_query(call.id, "يجب أن تضع علامة (✅ تم الفراغ) على جميع أدوارك السابقة قبل أخذ دور إضافي جديد! ⚠️", show_alert=True)
            return
        group["readers"].append({"id": user_id, "name": user_name, "done": False})
        bot.answer_callback_query(call.id, "تم تسجيل دور إضافي لك بنجاح ✅")

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
        # سيبحث عن أول دور غير منتهٍ للشخص ويضع عليه علامة
        for r in group["readers"]:
            if r["id"] == user_id and not r.get("done"):
                r["done"] = True
                found = True
                break
        if found:
            bot.answer_callback_query(call.id, "تم تأكيد فراغك من القراءة تقبل الله ✅")
        else:
            bot.answer_callback_query(call.id, "ليس لديك أدوار متبقية لختمها أو يجب أن تسجل أولاً ⚠️", show_alert=True)

    elif call.data == "delete_last":
        if group["readers"]:
            last = group["readers"].pop()
            bot.answer_callback_query(call.id, f"تم حذف آخر دور: {last['name']} 🗑️")
        else:
            bot.answer_callback_query(call.id, "القائمة فارغة بالفعل ⚠️", show_alert=True)

    # --- أزرار المشرفين الأساسية ---
    elif call.data == "toggle_list":
        group["list_open"] = not group.get("list_open", True)
        status = "مفتوحة 🔓" if group["list_open"] else "مغلقة 🔒"
        bot.answer_callback_query(call.id, f"تم جعل القائمة الأساسية: {status}")
        target_markup = "settings"

    elif call.data == "toggle_extra":
        group["extra_roles_open"] = not group.get("extra_roles_open", False)
        status = "مفتوحة 🔓" if group["extra_roles_open"] else "مغلقة 🔒"
        bot.answer_callback_query(call.id, f"القائمة الإضافية الآن: {status}")
        target_markup = "settings"

    elif call.data == "final_stats":
        total_readers = len(group["readers"])
        done_readers = sum(1 for r in group["readers"] if r.get("done"))
        stats_text = f"📊 الإحصاء النهائي للمجلس:\n\n📖 عدد القارئين الكلي: {total_readers}\n✅ الذين أتموا القراءة: {done_readers}\n🎧 المستمعين: {len(group['listeners'])}\n❌ المعتذرين: {len(group['excused'])}"
        bot.send_message(chat_id, stats_text)
        bot.answer_callback_query(call.id, "تم إرسال الإحصاء النهائي 📊")
        target_markup = "settings"

    elif call.data == "call":
        not_done = [mention(r['id'], r['name']) for r in group["readers"] if not r.get('done')]
        if not_done:
            bot.send_message(chat_id, f"📢 تذكير للقارئين الذين لم يتموا القراءة بعد:\n\n" + "\n".join(not_done), parse_mode="HTML")
            bot.answer_callback_query(call.id, "تم إرسال نداء التذكير 📢")
        else:
            bot.answer_callback_query(call.id, "كل القارئين أتموا القراءة! ✨", show_alert=True)
        target_markup = "settings"

    elif call.data == "reset":
        group["readers"] = []
        group["listeners"] = []
        group["excused"] = []
        group["swap_state"] = None
        bot.answer_callback_query(call.id, "تم تصفير القائمة بالكامل 🔄")
        target_markup = "settings"

    elif call.data == "resend":
        try: bot.delete_message(chat_id, group["message_id"])
        except: pass
        sent = bot.send_message(chat_id, make_board(chat_id), parse_mode="HTML", reply_markup=settings_keyboard(chat_id))
        group["message_id"] = sent.message_id
        bot.answer_callback_query(call.id, "تم تحديث وإعادة إرسال اللوحة 🔄")
        return # تجنب تعديل الرسالة القديمة

    elif call.data == "settings":
        group["swap_state"] = None # تصفير حالة التبديل عند دخول الإعدادات
        bot.answer_callback_query(call.id, "إعدادات المشرفين ⚙️")
        target_markup = "settings"

    # ✅ تم إصلاح استجابة هذا الزر بإضافة التنبيه الفوري
    elif call.data == "back_to_main":
        bot.answer_callback_query(call.id, "العودة للمجلس ↩️")
        target_markup = "main"

    # --- نظام إدارة وتبديل الأدوار ---
    # ✅ تم إصلاح استجابة هذا الزر بإضافة التنبيه الفوري
    elif call.data == "mr_list":
        if not group.get("readers", []):
            bot.answer_callback_query(call.id, "القائمة فارغة، لا يوجد قراء لإدارتهم! ⚠️", show_alert=True)
            target_markup = "settings"
        else:
            bot.answer_callback_query(call.id, "جاري فتح إدارة الأدوار 🔄")
            target_markup = "readers_list"

    elif call.data.startswith("mr_sel_"):
        index = int(call.data.split("_")[2])
        if group.get("swap_state") is not None:
            idx1 = group["swap_state"]
            idx2 = index
            if idx1 != idx2 and 0 <= idx1 < len(group["readers"]) and 0 <= idx2 < len(group["readers"]):
                group["readers"][idx1], group["readers"][idx2] = group["readers"][idx2], group["readers"][idx1]
                bot.answer_callback_query(call.id, "تم تبديل الأدوار بنجاح 🔄✅")
            else:
                bot.answer_callback_query(call.id, "تم إلغاء التبديل لاختيار نفس الشخص.")
            group["swap_state"] = None
            target_markup = "readers_list"
        else:
            bot.answer_callback_query(call.id)
            target_markup = f"reader_action_{index}"

    elif call.data.startswith("mr_up_"):
        index = int(call.data.split("_")[2])
        if index > 0:
            group["readers"][index], group["readers"][index-1] = group["readers"][index-1], group["readers"][index]
            bot.answer_callback_query(call.id, "تم التقديم بدرجة ⬆️")
        else:
            bot.answer_callback_query(call.id, "هو في المركز الأول بالفعل! ⚠️", show_alert=True)
        target_markup = "readers_list"

    elif call.data.startswith("mr_dn_"):
        index = int(call.data.split("_")[2])
        if index < len(group["readers"]) - 1:
            group["readers"][index], group["readers"][index+1] = group["readers"][index+1], group["readers"][index]
            bot.answer_callback_query(call.id, "تم التأخير بدرجة ⬇️")
        else:
            bot.answer_callback_query(call.id, "هو في المركز الأخير بالفعل! ⚠️", show_alert=True)
        target_markup = "readers_list"

    elif call.data.startswith("mr_sw_"):
        index = int(call.data.split("_")[2])
        group["swap_state"] = index
        bot.answer_callback_query(call.id, "الآن اختر الشخص الثاني من القائمة لإتمام التبديل 🔄", show_alert=True)
        target_markup = "readers_list"

    elif call.data == "mr_cancel_swap":
        group["swap_state"] = None
        bot.answer_callback_query(call.id, "تم إلغاء عملية التبديل ❌")
        target_markup = "readers_list"

    # حفظ البيانات
    save_data(data)
    
    # تحديث اللوحة والأزرار بشكل آمن
    try:
        if target_markup == "main":
            markup = main_keyboard(chat_id)
        elif target_markup == "settings":
            markup = settings_keyboard(chat_id)
        elif target_markup == "readers_list":
            markup = readers_list_keyboard(chat_id)
        elif target_markup.startswith("reader_action_"):
            idx = int(target_markup.split("_")[2])
            markup = reader_action_keyboard(idx)
            
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=group["message_id"], 
            text=make_board(chat_id), 
            parse_mode="HTML", 
            reply_markup=markup
        )
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" not in str(e).lower():
            pass # تجاهل خطأ التعديل إذا كانت الواجهة نفسها تماماً
    except Exception:
        pass

    try: bot.answer_callback_query(call.id)
    except: pass

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000))), daemon=True).start()
    print("Bot is running perfectly...")
    bot.infinity_polling()

