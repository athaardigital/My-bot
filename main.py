import os
import json
import html
import threading
import time
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv
import telebot
from telebot import types
from hijri_converter import Gregorian
from pymongo import MongoClient

load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# الربط بقاعدة بيانات MongoDB السحابية
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["AthaarDigitalDB"]
groups_col = db["groups"]
users_col = db["users"]

file_lock = threading.RLock()
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running perfectly on Cloud Backend!", 200

# مسار Webhook لاستقبال التحديثات من تليجرام ومنع الخطأ 409
@app.route("/" + BOT_TOKEN, methods=["POST"])
def getMessage():
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

def default_group():
    return {
        "message_id": None,
        "list_open": True,
        "extra_roles_open": False,
        "readers": [], 
        "listeners": [],
        "excused": [],
        "swap_state": None,
        "history": []
    }

def get_group(chat_id):
    chat_id = str(chat_id)
    doc = groups_col.find_one({"chat_id": chat_id})
    if not doc:
        group = default_group()
        groups_col.insert_one({"chat_id": chat_id, "group": group})
    else:
        group = doc["group"]
    
    # محاكاة الهيكل القديم لضمان عدم تعطل الكود الأساسي
    data = {chat_id: group}
    return data, group

def save_data(data):
    for chat_id, group in data.items():
        groups_col.update_one({"chat_id": str(chat_id)}, {"$set": {"group": group}}, upsert=True)

def is_admin(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

def mention(user_id, name):
    return f"<a href='tg://user?id={user_id}'>{html.escape(name)}</a>"

def get_dates():
    now = datetime.now()
    ar_days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    ar_months_miladi = ["جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان", "جويلية", "أوت", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    ar_months_hijri = ["محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"]
    
    miladi = f"{ar_days[now.weekday()]} {now.day} {ar_months_miladi[now.month - 1]} {now.year} م"
    
    try:
        h = Gregorian.fromdate(now.date()).to_hijri()
        hijri = f"{ar_days[now.weekday()]} {h.day} {ar_months_hijri[h.month - 1]} {h.year} هـ"
        return f"{hijri}\n\n{miladi}"
    except Exception:
        return miladi

def make_board(chat_id):
    _, group = get_group(chat_id)
    text = f"📅 {get_dates()}\n\n"
    text += "⏳ ---------------------------------- ⏳\n\n"
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
    
    if group.get("extra_roles_open", False):
        keyboard.row(types.InlineKeyboardButton("دور إضافي ➕", callback_data="extra_role"))
        
    keyboard.row(types.InlineKeyboardButton("❌ معتذر/ة", callback_data="excused"), types.InlineKeyboardButton("🎧 مستمع/ة", callback_data="listener"))
    keyboard.row(types.InlineKeyboardButton("✅ تم الفراغ من القراءة", callback_data="done"))
    keyboard.row(types.InlineKeyboardButton("⚙️ إعدادات المشرفين", callback_data="settings"))
    return keyboard

def settings_keyboard(chat_id):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("إدارة وتبديل الأدوار 🔄", callback_data="mr_list"))
    keyboard.row(types.InlineKeyboardButton("القائمة الإضافية 🔓/🔒", callback_data="toggle_extra"), types.InlineKeyboardButton("القائمة الأساسية 🔓/🔒", callback_data="toggle_list"))
    keyboard.row(types.InlineKeyboardButton("السجل الإحصائي 📈", callback_data="history_stats"), types.InlineKeyboardButton("الإحصاء النهائي 📊", callback_data="final_stats"))
    keyboard.row(types.InlineKeyboardButton("تحديث 🔄", callback_data="resend"), types.InlineKeyboardButton("تصفير القائمة 🔄", callback_data="reset"))
    keyboard.row(types.InlineKeyboardButton("عودة للمجلس ↩️", callback_data="back_to_main"))
    return keyboard

def readers_list_keyboard(chat_id):
    _, group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup()
    readers = group.get("readers", [])
    for i, r in enumerate(readers):
        text_name = f"{i+1}. {r['name']}"
        if group.get("swap_state") == i:
            text_name += " (محدد للتبديل 🔄)"
        keyboard.add(types.InlineKeyboardButton(text_name, callback_data=f"mr_sel_{i}"))
    
    if group.get("swap_state") is not None:
        keyboard.add(types.InlineKeyboardButton("إلغاء التبديل ❌", callback_data="mr_cancel_swap"))
        
    keyboard.add(types.InlineKeyboardButton("رجوع للإعدادات 🔙", callback_data="settings"))
    return keyboard

def reader_action_keyboard(index):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(types.InlineKeyboardButton("تقديم (لأعلى) ⬆️", callback_data=f"mr_up_{index}"), types.InlineKeyboardButton("تأخير (لأسفل) ⬇️", callback_data=f"mr_dn_{index}"))
    keyboard.row(types.InlineKeyboardButton("التبديل مع... 🔄", callback_data=f"mr_sw_{index}"))
    keyboard.row(types.InlineKeyboardButton("رجوع للأسماء 🔙", callback_data="mr_list"))
    return keyboard

def private_start_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup()
    user = users_col.find_one({"user_id": user_id})
    is_subbed = user.get("subscribed", False) if user else False
    
    if is_subbed:
        keyboard.add(types.InlineKeyboardButton("إلغاء تفعيل أذكار الجمعة 🔕", callback_data="toggle_azkar_off"))
    else:
        keyboard.add(types.InlineKeyboardButton("تفعيل أذكار الجمعة 🔔", callback_data="toggle_azkar_on"))
    return keyboard

@bot.message_handler(commands=["start"])
def start(message):
    if message.chat.type == "private":
        welcome_text = "السلام عليكم ورحمة الله وبركاته\n\nحيَّاكم الله.\n\n📌 أنشروا البوت فضلًا فهو صدقةٌ عنِّي وعن والديَّ ومقرأتنا وكل المسلمين والمسلمات الأحياء منهم والأموات."
        bot.send_message(message.chat.id, welcome_text, reply_markup=private_start_keyboard(message.from_user.id))

    with file_lock:
        data, group = get_group(message.chat.id)
        sent = bot.send_message(message.chat.id, make_board(message.chat.id), parse_mode="HTML", reply_markup=main_keyboard(message.chat.id))
        group["message_id"] = sent.message_id
        save_data(data)

def remove_user_from_all(user_id, group):
    for lst in ["readers", "listeners", "excused"]:
        group[lst] = [u for u in group[lst] if u["id"] != user_id]

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    try:
        chat_id = call.message.chat.id
        user_id = call.from_user.id
        user_name = call.from_user.first_name
        
        target_markup = "main"
        should_edit = True

        # أزرار الاشتراك الاختياري في أذكار الجمعة بالخاص
        if call.data == "toggle_azkar_on":
            users_col.update_one({"user_id": user_id}, {"$set": {"subscribed": True}}, upsert=True)
            bot.answer_callback_query(call.id, "تم تفعيل استقبال أذكار الجمعة بنجاح! ✨", show_alert=True)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=private_start_keyboard(user_id))
            return
        elif call.data == "toggle_azkar_off":
            users_col.update_one({"user_id": user_id}, {"$set": {"subscribed": False}}, upsert=True)
            bot.answer_callback_query(call.id, "تم إلغاء تفعيل أذكار الجمعة. 🔕", show_alert=True)
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=private_start_keyboard(user_id))
            return

        with file_lock:
            data, group = get_group(chat_id)
            
            is_admin_action = call.data in ["settings", "toggle_extra", "toggle_list", "final_stats", "history_stats", "call", "resend", "reset"] or call.data.startswith("mr_")
            if is_admin_action and not is_admin(user_id, chat_id):
                bot.answer_callback_query(call.id, "❌ عذراً، هذا الزر مخصص للمشرفين فقط.", show_alert=True)
                return

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
                    bot.answer_callback_query(call.id, "يجب إتمام أدوارك السابقة أولاً! ⚠️", show_alert=True)
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
                for r in group["readers"]:
                    if r["id"] == user_id and not r.get("done"):
                        r["done"] = True
                        found = True
                        break
                if found:
                    bot.answer_callback_query(call.id, "تم تأكيد فراغك من القراءة تقبل الله ✅")
                else:
                    bot.answer_callback_query(call.id, "ليس لديك أدوار متبقية لختمها ⚠️", show_alert=True)

            elif call.data == "delete_last":
                target_index = -1
                for i in range(len(group["readers"]) - 1, -1, -1):
                    if group["readers"][i]["id"] == user_id:
                        target_index = i
                        break
                
                if target_index != -1:
                    group["readers"].pop(target_index)
                    bot.answer_callback_query(call.id, "تم حذف آخر دور مسجل لك 🗑️")
                else:
                    bot.answer_callback_query(call.id, "ليس لديك أي أدوار مسجلة لحذفها! ⚠️", show_alert=True)

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
                # الأرشفة التلقائية في السجل قبل طباعة الإحصاء
                if "history" not in group:
                    group["history"] = []
                today_str = datetime.now().strftime("%Y-%m-%d")
                if not any(h.get("date") == today_str for h in group["history"]):
                    group["history"].append({
                        "date": today_str,
                        "readers_count": len(group['readers']),
                        "listeners_count": len(group['listeners']),
                        "excused_count": len(group['excused'])
                    })
                
                stats_text = f"📊 الإحصاء النهائي للمجلس:\n\n"
                stats_text += f"📖 الْقَارِئُونَ/ات ({len(group['readers'])}):\n"
                if group['readers']:
                    stats_text += "\n".join([f"👤 {r['name']}" + (" ✅" if r.get('done') else "") for r in group['readers']])
                else:
                    stats_text += "لا يوجد"
                    
                stats_text += f"\n\n🎧 الْمُسْتَمِعُونَ/ات ({len(group['listeners'])}):\n"
                if group['listeners']:
                    stats_text += "\n".join([f"👤 {l['name']}" for l in group['listeners']])
                else:
                    stats_text += "لا يوجد"
                    
                stats_text += f"\n\n❌ الْمُعْتَذِرُونَ/ات ({len(group['excused'])}):\n"
                if group['excused']:
                    stats_text += "\n".join([f"👤 {e['name']}" for e in group['excused']])
                else:
                    stats_text += "لا يوجد"

                bot.send_message(chat_id, stats_text)
                bot.answer_callback_query(call.id, "تم إرسال الإحصاء النهائي وأرشفته 📊")
                target_markup = "settings"

            elif call.data == "history_stats":
                history = group.get("history", [])
                if not history:
                    bot.answer_callback_query(call.id, "لا توجد مجالس مؤرشفة في السجل بعد! 📈", show_alert=True)
                else:
                    history_text = "📈 السجل الإحصائي التراكمي للمجالس:\n\n"
                    for h in history[-10:]:  # عرض آخر 10 مجالس لضمان جمالية الرسالة
                        history_text += f"📅 تاريخ: {h['date']}\n"
                        history_text += f" 📖 قراء: {h['readers_count']} | 🎧 مستمعين: {h['listeners_count']} | ❌ معتذرين: {h['excused_count']}\n"
                        history_text += "----------------------------------------\n"
                    bot.send_message(chat_id, history_text)
                    bot.answer_callback_query(call.id, "تم فتح الأرشيف الإحصائي 📉")
                target_markup = "settings"

            elif call.data == "call":
                not_done = [mention(r['id'], r['name']) for r in group["readers"] if not r.get('done')]
                if not_done:
                    bot.send_message(chat_id, f"📢 تذكير لمن لم يتم القراءة:\n\n" + "\n".join(not_done), parse_mode="HTML")
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
                should_edit = False

            elif call.data == "settings":
                group["swap_state"] = None
                bot.answer_callback_query(call.id, "إعدادات المشرفين ⚙️")
                target_markup = "settings"

            elif call.data == "back_to_main":
                bot.answer_callback_query(call.id, "العودة للمجلس ↩️")
                target_markup = "main"

            elif call.data == "mr_list":
                if not group.get("readers", []):
                    bot.answer_callback_query(call.id, "لا يوجد قراء لإدارتهم! ⚠️", show_alert=True)
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

            if should_edit:
                save_data(data)
                
        if should_edit:
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
        if "too many requests" in str(e).lower():
            try: bot.answer_callback_query(call.id, "⚠️ أبطئ قليلاً! جاري معالجة طلباتك...", show_alert=True)
            except: pass
    except Exception as e:
        print(f"General Error in callbacks: {e}")

# خيط برمي خلفي لبث أذكار الجمعة تلقائياً للمشتركين فقط دون إزعاج البقية
def friday_broadcast_loop():
    while True:
        try:
            now = datetime.now()
            # الإرسال التلقائي كل يوم جمعة في تمام الساعة 09:00 صباحاً
            if now.weekday() == 4 and now.hour == 9 and now.minute == 0:
                subscribers = users_col.find({"subscribed": True})
                azkar_msg = "✨ *أذكار يوم الجمعة المباركة* ✨\n\nاللهم صلِ وسلم على نبينا محمد وعلى آله وصحبه أجمعين. لا تنسوا قراءة سورة الكهف والدعاء في ساعة الإجابة. 🌿"
                for sub in subscribers:
                    try:
                        bot.send_message(sub["user_id"], azkar_msg, parse_mode="Markdown")
                        time.sleep(0.05)
                    except Exception:
                        pass
                time.sleep(60)
        except Exception as e:
            print(f"Error in broadcast loop: {e}")
        time.sleep(30)

if __name__ == "__main__":
    # تشغيل خيط البث الدوري
    threading.Thread(target=friday_broadcast_loop, daemon=True).start()
    
    # إعداد الـ Webhook الخاص بـ Render ديناميكياً لحل المشكلة 409
    bot.remove_webhook()
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
    if RENDER_URL:
        bot.set_webhook(url=RENDER_URL + "/" + BOT_TOKEN)
        
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
