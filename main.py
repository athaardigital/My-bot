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

try:
    bot.remove_webhook()
except Exception as webhook_error:
    print(f"Warning: Could not remove webhook: {webhook_error}")

DATA_FILE = "groups_data.json"
file_lock = threading.Lock()

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
# هيكلية بيانات المجموعات والتحديث
# =====================================

def default_group():
    return {
        "message_id": None,
        "list_open": False,
        "extra_roles_open": False,
        "readers": [],   # {"id": str, "name": str, "done": bool}
        "listeners": [], # {"id": str, "name": str}
        "excused": []    # {"id": str, "name": str}
    }

def get_group(chat_id):
    data = load_data()
    chat_id = str(chat_id)
    
    if chat_id not in data:
        data[chat_id] = default_group()
        save_data(data)
    else:
        # ترقية البيانات القديمة للتوافق مع التحديث الجديد
        changed = False
        group = data[chat_id]
        if "extra_roles_open" not in group:
            group["extra_roles_open"] = False
            changed = True
        
        if "completed" in group:
            completed_ids = group["completed"]
            for r in group.get("readers", []):
                if "done" not in r:
                    r["done"] = (str(r["id"]) in completed_ids)
            del group["completed"]
            changed = True
            
        for r in group.get("readers", []):
            if "done" not in r:
                r["done"] = False
                changed = True
                
        if changed:
            save_data(data)

    return data, data[chat_id]

def is_admin(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

def mention(user_id, name):
    safe_name = html.escape(name)
    return f"<a href='tg://user?id={user_id}'>{safe_name}</a>"

def get_arabic_date():
    ar_days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    ar_months = ["جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان", "جويلية", "أوت", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    now = datetime.now()
    return f"{ar_days[now.weekday()]} {now.day} {ar_months[now.month - 1]} {now.year} م"

# =====================================
# بناء لوحة العرض الرئيسية
# =====================================

def make_board(chat_id):
    _, group = get_group(chat_id)
    
    text = f"📅 {get_arabic_date()}\n\n"
    text += "📊 إحصاء المجلس الحالي:\n"
    text += "⏳ ---------------------------------- ⏳\n\n"
    
    text += "❝ اعلمي رعاك الله أن حضورك مجالس العلم النافع\n"
    text += "هو محض اصطفاء من ربك فحمديه على هذه النعمة\n"
    text += "وأحسني رعايتها ❞\n\n"
    
    text += "⏳ ---------------------------------- ⏳\n\n"
    text += "✨ قَائِمَةُ تِلَاوَةِ الْقُرْآنِ الْكَرِيمِ لِلْمَجْلِسِ الْحَالِيِّ ✨\n\n"

    # القارئات
    text += f"📖 القَارِئَاتُ: {len(group['readers'])}\n"
    if not group['readers']:
        text += "لا يوجد قارئات حالياً\n"
    else:
        for i, r in enumerate(group['readers'], 1):
            done_str = " ✅ قرأت" if r.get("done") else ""
            text += f"{i}. {mention(r['id'], r['name'])}{done_str}\n"
    text += "\n"

    # المستمعات
    text += f"🎧 المُسْتَمِعَاتُ: {len(group['listeners'])}\n"
    if not group['listeners']:
        text += "لا يوجد مستمعات حالياً\n"
    else:
        for i, l in enumerate(group['listeners'], 1):
            text += f"{i}. {mention(l['id'], l['name'])}\n"
    text += "\n"

    # المعتذرات
    text += f"❌ المُعْتَذِرَاتُ: {len(group['excused'])}\n"
    if not group['excused']:
        text += "لا يوجد معتذرات حالياً\n"
    else:
        for i, e in enumerate(group['excused'], 1):
            text += f"{i}. {mention(e['id'], e['name'])}\n"
    
    text += "\n----------------------------------------------\n"
    
    status_list = "🟢 مفتوحة" if group['list_open'] else "🔴 مغلقة"
    status_extra = "🟢 مفتوحة" if group['extra_roles_open'] else "🔴 مغلقة"
    
    text += f"حالة القائمة: {status_list}\n"
    text += f"الأدوار الإضافية: {status_extra}"

    return text

# =====================================
# صناعة لوحات الأزرار
# =====================================

def main_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    
    keyboard.row(
        types.InlineKeyboardButton("حذف آخر دور 🗑️", callback_data="delete_last"),
        types.InlineKeyboardButton("تسجيل اسمي 📝", callback_data="reader")
    )
    # أزرار المستمعة والمعتذرة مدمجة للمحافظة على الوظيفة مع الشكل
    keyboard.row(
        types.InlineKeyboardButton("❌ معتذرة", callback_data="excused"),
        types.InlineKeyboardButton("🎧 مستمعة", callback_data="listener")
    )
    keyboard.row(
        types.InlineKeyboardButton("✅ تم الفراغ من القراءة", callback_data="done")
    )
    keyboard.row(
        types.InlineKeyboardButton("⚙️ إعدادات المشرفات", callback_data="settings")
    )
    return keyboard

def settings_keyboard(chat_id):
    _, group = get_group(chat_id)
    
    btn_list = "إغلاق القائمة 🔒" if group["list_open"] else "فتح القائمة 🔓"
    btn_extra = "إغلاق الأدوار 🔒" if group["extra_roles_open"] else "فتح الأدوار الإضافية 🔓"
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton(btn_extra, callback_data="toggle_extra"),
        types.InlineKeyboardButton(btn_list, callback_data="toggle_list")
    )
    keyboard.row(
        types.InlineKeyboardButton("الإحصاء النهائي 📊", callback_data="final_stats"),
        types.InlineKeyboardButton("زر المناداة 📢", callback_data="call")
    )
    keyboard.row(
        types.InlineKeyboardButton("تحديث وإعادة إرسال 🔄", callback_data="resend"),
        types.InlineKeyboardButton("تصفير القائمة 🔄", callback_data="reset")
    )
    keyboard.row(
        types.InlineKeyboardButton("عودة للمجلس ↩️", callback_data="back_to_main")
    )
    return keyboard

# =====================================
# تحديث اللوحة
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
    except Exception:
        pass

# =====================================
# استجابة الأمر /start
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    if message.chat.type == "private":
        bot.send_message(
            message.chat.id,
            "السلام عليكم ورحمة الله وبركاته\n\n"
            "حيَّاكم الله.\n\n"
            "📌 أنشروا البوت فضلًا فهو صدقةٌ عنِّي وعن والديَّ ومقرأتنا وكل المسلمين والمسلمات الأحياء منهم والأموات."
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

def remove_from_others(group, user_id_str, keep_in=""):
    """دالة مساعدة لمسح العضوة من القوائم الأخرى عند التبديل"""
    if keep_in != "listeners":
        group["listeners"] = [x for x in group["listeners"] if str(x["id"]) != user_id_str]
    if keep_in != "excused":
        group["excused"] = [x for x in group["excused"] if str(x["id"]) != user_id_str]
    if keep_in != "readers":
        group["readers"] = [x for x in group["readers"] if str(x["id"]) != user_id_str]

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    user = call.from_user
    user_id_str = str(user.id)
    
    data, group = get_group(chat_id)

    full_name = user.first_name or "مستخدمة"
    if user.last_name:
        full_name += f" {user.last_name}"

    member_base = {"id": user_id_str, "name": full_name}

    admin_actions = ["settings", "toggle_list", "toggle_extra", "reset", "call", "final_stats", "resend"]

    if call.data in admin_actions:
        if not is_admin(user.id, chat_id):
            bot.answer_callback_query(call.id, "❌ عذرًا، هذا الإجراء متاح للمشرفات فقط.", show_alert=True)
            return

    # 1. تسجيل اسمي (قارئة)
    if call.data == "reader":
        if not group["list_open"]:
            bot.answer_callback_query(call.id, "⚠️ القائمة مغلقة حاليًا من قِبل الإدارة.", show_alert=True)
            return
            
        user_entries = [r for r in group["readers"] if str(r["id"]) == user_id_str]
        
        if not user_entries:
            # أول مرة تسجل في هذا المجلس
            remove_from_others(group, user_id_str, "readers")
            new_entry = member_base.copy()
            new_entry["done"] = False
            group["readers"].append(new_entry)
            bot.answer_callback_query(call.id, "✅ تم تسجيلكِ كقارئة.")
        else:
            # تملك دوراً سابقاً (نظام الأدوار الإضافية)
            if not group["extra_roles_open"]:
                bot.answer_callback_query(call.id, "⚠️ الأدوار الإضافية مغلقة حاليًا.", show_alert=True)
                return
                
            last_entry = user_entries[-1]
            if not last_entry["done"]:
                bot.answer_callback_query(call.id, "⚠️ لا يمكنكِ أخذ دور إضافي قبل الفراغ من دورك الحالي وتحديد (✅ تم الفراغ).", show_alert=True)
                return
                
            new_entry = member_base.copy()
            new_entry["done"] = False
            group["readers"].append(new_entry)
            bot.answer_callback_query(call.id, "✅ تم تسجيل دور إضافي لكِ.")

    # 2. مستمعة
    elif call.data == "listener":
        remove_from_others(group, user_id_str, "listeners")
        group["listeners"].append(member_base)
        bot.answer_callback_query(call.id, "🎧 تم تسجيلكِ كمستمعة.")

    # 3. معتذرة
    elif call.data == "excused":
        remove_from_others(group, user_id_str, "excused")
        group["excused"].append(member_base)
        bot.answer_callback_query(call.id, "❌ تم تسجيل اعتذاركِ.")

    # 4. تم الفراغ من القراءة
    elif call.data == "done":
        user_entries = [r for r in group["readers"] if str(r["id"]) == user_id_str]
        if not user_entries:
            bot.answer_callback_query(call.id, "⚠️ أنتِ لستِ مسجلة كقارئة!", show_alert=True)
            return
            
        # نبحث عن آخر دور غير مكتمل لتسجيل الفراغ منه
        marked = False
        for r in reversed(group["readers"]):
            if str(r["id"]) == user_id_str:
                if r["done"]:
                    bot.answer_callback_query(call.id, "⚠️ لقد أتممتِ قراءتك مسبقاً.", show_alert=True)
                    return
                else:
                    r["done"] = True
                    marked = True
                    bot.answer_callback_query(call.id, "🎉 تقبل الله منكِ وطهر قلبكِ.", show_alert=True)
                    break

    # 5. حذف آخر دور
    elif call.data == "delete_last":
        deleted = False
        # الحذف من القارئات أولاً (لأنه قد يحوي أدواراً متعددة)
        for r in reversed(group["readers"]):
            if str(r["id"]) == user_id_str:
                group["readers"].remove(r)
                deleted = True
                break
                
        if not deleted:
            for l in reversed(group["listeners"]):
                if str(l["id"]) == user_id_str:
                    group["listeners"].remove(l)
                    deleted = True
                    break
        if not deleted:
            for e in reversed(group["excused"]):
                if str(e["id"]) == user_id_str:
                    group["excused"].remove(e)
                    deleted = True
                    break
                    
        if deleted:
            bot.answer_callback_query(call.id, "🗑️ تم حذف آخر دور لكِ.")
        else:
            bot.answer_callback_query(call.id, "⚠️ لا يوجد اسم أو دور مسجل لكِ لحذفه.", show_alert=True)

    # 6. فتح إعدادات المشرفات
    elif call.data == "settings":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="⚙️ لوحة تحكم المشرفات والمالكة:",
            reply_markup=settings_keyboard(chat_id)
        )
        bot.answer_callback_query(call.id, "⚙️ تم فتح لوحة التحكم.")
        return

    # 7. التبديل: القائمة الرئيسية
    elif call.data == "toggle_list":
        group["list_open"] = not group["list_open"]
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=settings_keyboard(chat_id)
        )
        status = "مفتوحة" if group["list_open"] else "مغلقة"
        bot.answer_callback_query(call.id, f"⚙️ القائمة {status}.")
        return

    # 8. التبديل: الأدوار الإضافية
    elif call.data == "toggle_extra":
        group["extra_roles_open"] = not group["extra_roles_open"]
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=settings_keyboard(chat_id)
        )
        status = "مفتوحة" if group["extra_roles_open"] else "مغلقة"
        bot.answer_callback_query(call.id, f"⚙️ الأدوار الإضافية {status}.")
        return

    # 9. الإحصاء النهائي
    elif call.data == "final_stats":
        stats_text = "بحمد الله نختم مجلسنا اليوم\n\n"
        
        stats_text += "✅ القارئات اللاتي قرأن:\n"
        readers_who_read = [r for r in group["readers"] if r.get("done")]
        if not readers_who_read:
            stats_text += "• لا يوجد\n"
        else:
            read_names = []
            for r in readers_who_read:
                if r["name"] not in read_names:
                    read_names.append(r["name"])
            for i, name in enumerate(read_names, 1):
                stats_text += f"{i}. {name}\n"
                
        stats_text += "\n🎧 المستمعات:\n"
        if not group["listeners"]:
            stats_text += "• لا يوجد\n"
        else:
            for i, l in enumerate(group["listeners"], 1):
                stats_text += f"{i}. {l['name']}\n"
                
        stats_text += "\n❌ المعتذرات:\n"
        if not group["excused"]:
            stats_text += "• لا يوجد\n"
        else:
            for i, e in enumerate(group["excused"], 1):
                stats_text += f"{i}. {e['name']}\n"
                
        bot.send_message(chat_id, stats_text)
        bot.answer_callback_query(call.id, "✅ تم إرسال الإحصاء النهائي للمجلس.")
        return

    # 10. إعادة الإرسال والتحديث
    elif call.data == "resend":
        try:
            bot.delete_message(chat_id, group["message_id"])
        except:
            pass
            
        sent = bot.send_message(
            chat_id,
            make_board(chat_id),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=main_keyboard()
        )
        group["message_id"] = sent.message_id
        bot.answer_callback_query(call.id, "✅ تم التحديث وإعادة الإرسال.")
        save_data(data)
        return

    # 11. إعادة ضبط القائمة وتصفير الأسماء
    elif call.data == "reset":
        old_message = group["message_id"]
        data[str(chat_id)] = default_group()
        data[str(chat_id)]["message_id"] = old_message
        bot.answer_callback_query(call.id, "🔄 تم تصفير القائمة بالكامل.", show_alert=True)

    # 12. عودة للمجلس (من الإعدادات للرئيسية)
    elif call.data == "back_to_main":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=make_board(chat_id),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=main_keyboard()
        )
        bot.answer_callback_query(call.id, "🔙 عدتِ للمجلس.")
        return

    # 13. زر المناداة
    elif call.data == "call":
        all_members = group["readers"] + group["listeners"] + group["excused"]
        unique_members = {v['id']: v for v in all_members}.values()
        
        bot.answer_callback_query(call.id, "📢 جاري إرسال التنبيهات في الخاص...")
        for member in unique_members:
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
