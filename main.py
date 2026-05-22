import os
import threading
import json
import time
from datetime import datetime
from flask import Flask
from dotenv import load_dotenv
import telebot
from telebot import types

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="MarkdownV2")

DATA_FILE = "recitation_data.json"

def get_empty_group_structure():
    return {
        "members": [], 
        "read": [], 
        "listeners": [], 
        "excused": [], 
        "list_open": True, 
        "extra_roles_open": False, 
        "current_date": ""
    }

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[خطأ في حفظ البيانات] {e}")

def is_admin(user_id: int, chat_id: int) -> bool:
    try:
        if chat_id == user_id:
            return True
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        print(f"[خطأ في التحقق من الإشراف] {e}")
        return False

def escape_markdown_v2(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + c if c in escape_chars else c for c in text)

def get_full_date_string():
    days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    months_miladi = ["جانفي", "فيفري", "مارس", "أفريل", "ماي", "جوان", "جويلية", "أوت", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    
    now = datetime.now()
    day_name = days[now.weekday()]
    month_m_name = months_miladi[now.month - 1]
    
    ref_date = datetime(2026, 5, 22)
    delta_days = (now - ref_date).days
    hijri_day = 5 + delta_days
    
    hijri_str = f"🌙 {day_name} {hijri_day} ذو الحجة 1447 هـ"
    if hijri_day > 30:
        hijri_str = f"🌙 {day_name} {hijri_day - 30} محرم 1448 هـ"
        
    miladi_str = f"📅 {now.day} {month_m_name} {now.year} م"
    
    return f"*{escape_markdown_v2(hijri_str)}*\n*{escape_markdown_v2(miladi_str)}*"

def get_main_inline_keyboard(chat_id_str):
    all_data = load_data()
    group_data = all_data.get(chat_id_str, get_empty_group_structure())
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📝 تسجيل اسمي", callback_data="sub_menu_register"),
        types.InlineKeyboardButton("🗑️ حذف آخر دور", callback_data="action_delete_last")
    )
    
    if group_data.get("extra_roles_open", False):
        markup.add(types.InlineKeyboardButton("➕ تسجيل دور إضافي", callback_data="action_extra_role"))
        
    markup.add(types.InlineKeyboardButton("✅ تم الفراغ من القراءة", callback_data="action_read"))
    markup.add(types.InlineKeyboardButton("⚙️ إعدادات المشرفات", callback_data="admin_menu"))
    return markup

def build_board_text(group_data):
    group_data["current_date"] = get_full_date_string()
        
    readers = [m for m in group_data["members"] if m["extra_id"] in group_data["read"] or (m["id"] not in group_data["listeners"] and m["id"] not in group_data["excused"])]
    listeners = [m for m in group_data["members"] if m["id"] in group_data["listeners"]]
    excused = [m for m in group_data["excused"]]
    
    stats_header = f"📊 *إِحْصَاءُ الْمَجْلِسِ الْحَالِي:* 📖 قَارِئَات: {len(readers)} | 🎧 مُسْتَمِعَات: {len(listeners)} | ❌ مُعْتَذِرَات: {len(excused)}"
    stats_header = escape_markdown_v2(stats_header).replace(r'\*', '*').replace(r'\|', '|')

    quote_text = (
        ">اعلمي رعاكِ الله أن حضوركِ مجالس العلم النافع\n"
        ">هو محض اصطفاء من ربكِ فحمديه على هذه النعمة\n"
        ">وأحسني رعايتها \.\.\."
    )
    
    board_text = (
        f"{group_data['current_date']}\n\n"
        f"{stats_header}\n"
        f"⏳ ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈ِم ⏳\n\n"
        f"{quote_text}\n\n"
        f"✨ *قَائِمَةُ تِلَاوَةِ الْقُرْآنِ الْكَرِيمِ لِلْمَجْلِسِ الْحَالِيِّ* ✨\n\n"
    )
    
    idx = 1
    board_text += f"📖 *الْقَارِئَاتُ:*\n"
    if not readers:
        board_text += " لا يوجد قارئات حالياً\n"
    else:
        for member in readers:
            status = "✅ قرأت" if member["extra_id"] in group_data["read"] else "⏳ في الانتظار"
            safe_name = escape_markdown_v2(member["name"])
            board_text += f" {idx}\. {status} ── [{safe_name}](tg://user?id={member['id']})\n"
            idx += 1
            
    board_text += "\n"
    board_text += f"🎧 *الْمُسْتَمِعَاتُ:*\n"
    if not listeners:
        board_text += " لا يوجد مستمعات حالياً\n"
    else:
        for member in listeners:
            safe_name = escape_markdown_v2(member["name"])
            board_text += f" {idx}\. 🎧 مستمعة ── [{safe_name}](tg://user?id={member['id']})\n"
            idx += 1
            
    board_text += "\n"
    board_text += f"❌ *الْمَعْتَذِرَاتُ:*\n"
    if not excused:
        board_text += " لا يوجد معتذرات حالياً\n"
    else:
        seen_excused = set()
        for member in excused:
            if member["id"] not in seen_excused:
                seen_excused.add(member["id"])
                safe_name = escape_markdown_v2(member["name"])
                board_text += f" {idx}\. ❌ معتذرة ── [{safe_name}](tg://user?id={member['id']})\n"
                idx += 1
            
    board_text += f"\n┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n\n"
    status_text = "🟢 مفتوحة" if group_data["list_open"] else "🔴 مغلقة"
    extra_status = "🟢 مفتوحة" if group_data.get("extra_roles_open", False) else "🔴 مغلقة"
    board_text += f"حالة القائمة: *{status_text}*\n"
    board_text += f"الأدوار الإضافية: *{extra_status}*"
    
    return board_text

def send_group_board(chat_id):
    chat_id_str = str(chat_id)
    all_data = load_data()
    if chat_id_str not in all_data:
        all_data[chat_id_str] = get_empty_group_structure()
        save_data(all_data)
        
    board_text = build_board_text(all_data[chat_id_str])
    
    remove_markup = types.ReplyKeyboardRemove(selective=False)
    clear_msg = bot.send_message(chat_id, "🔄 جَارٍ تَحْيِينُ لَوْحَةِ الْمَجْلِسِ وَتَنْظِيفِ الْقَائِمَةِ\.\.\.", reply_markup=remove_markup)
    try:
        bot.delete_message(chat_id, clear_msg.message_id)
    except Exception:
        pass
        
    bot.send_message(chat_id, board_text, reply_markup=get_main_inline_keyboard(chat_id_str))

def update_board_message(message):
    chat_id_str = str(message.chat.id)
    all_data = load_data()
    if chat_id_str not in all_data:
        all_data[chat_id_str] = get_empty_group_structure()
        save_data(all_data)
        
    board_text = build_board_text(all_data[chat_id_str])
    try:
        bot.edit_message_text(board_text, message.chat.id, message.message_id, reply_markup=get_main_inline_keyboard(chat_id_str))
    except Exception as e:
        print(f"[خطأ أثناء تحديث اللوحة] {e}")

def get_admin_inline_keyboard(group_data):
    markup = types.InlineKeyboardMarkup(row_width=2)
    toggle_label = "🔒 إغلاق القائمة" if group_data["list_open"] else "🔓 فتح القائمة"
    extra_toggle_label = "🔒 غلق الأدوار الإضافية" if group_data.get("extra_roles_open", False) else "🔓 فتح الأدوار الإضافية"
    
    markup.add(
        types.InlineKeyboardButton(toggle_label, callback_data="admin_toggle"),
        types.InlineKeyboardButton(extra_toggle_label, callback_data="admin_toggle_extra")
    )
    markup.add(
        types.InlineKeyboardButton("📊 الإحصاء النهائي", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 زر المناداة", callback_data="admin_call")
    )
    markup.add(
        types.InlineKeyboardButton("🔄 تصفير القائمة", callback_data="admin_reset_confirm"),
        types.InlineKeyboardButton("🔄 تحديث وإعادة إرسال", callback_data="admin_resend")
    )
    markup.add(types.InlineKeyboardButton("↩️ عودة للمجلس", callback_data="main_menu"))
    return markup

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id_str = str(call.message.chat.id)
    all_data = load_data()
    
    if chat_id_str not in all_data:
        all_data[chat_id_str] = get_empty_group_structure()
        
    group_data = all_data[chat_id_str]
    uid_str = str(user_id)
    
    if call.data.startswith("admin_"):
        if not is_admin(user_id, call.message.chat.id):
            bot.answer_callback_query(call.id, "⛔ عذراً، زر الإعدادات متاح فقط لمالكة المجموعة والمشرفات المعتمدات\.", show_alert=True)
            return
    
    if call.data == "sub_menu_register":
        if not group_data["list_open"]:
            bot.answer_callback_query(call.id, "🔴 عذراً، قائمة التلاوة مغلقة حالياً من قِبل الإشراف\.", show_alert=True)
            return
            
        reg_markup = types.InlineKeyboardMarkup(row_width=3)
        reg_markup.add(
            types.InlineKeyboardButton("📖 قارئة", callback_data="reg_reader"),
            types.InlineKeyboardButton("🎧 مستمعة", callback_data="reg_listener"),
            types.InlineKeyboardButton("❌ معتذرة", callback_data="reg_excused")
        )
        reg_markup.add(types.InlineKeyboardButton("↩️ عودة للمجلس", callback_data="main_menu"))
        
        safe_first_name = escape_markdown_v2(call.from_user.first_name)
        bot.edit_message_text(
            f"📌 *عَمَلِيَّةُ تَسْجِيلٍ لِلْأُخْتِ:* {safe_first_name}\nالرجاء اختيار صفتكِ للمجلس الحالي:",
            call.message.chat.id, call.message.message_id, reply_markup=reg_markup
        )
        bot.answer_callback_query(call.id)

    elif call.data in ["reg_reader", "reg_listener", "reg_excused"]:
        user = call.from_user
        name = user.first_name + (f" {user.last_name}" if user.last_name else "")
        
        group_data["members"] = [m for m in group_data["members"] if m["id"] != uid_str]
        group_data["read"] = [r for r in group_data["read"] if not r.startswith(f"{uid_str}_")]
        group_data["listeners"] = [l for l in group_data["listeners"] if l != uid_str]
        group_data["excused"] = [e for e in group_data["excused"] if e["id"] != uid_str]
        
        if call.data == "reg_excused":
            group_data["members"].append({"id": uid_str, "extra_id": f"{uid_str}_base", "name": name})
            group_data["excused"].append({"id": uid_str, "name": name})
        elif call.data == "reg_listener":
            group_data["members"].append({"id": uid_str, "extra_id": f"{uid_str}_base", "name": name})
            group_data["listeners"].append(uid_str)
        else:
            group_data["members"].append({"id": uid_str, "extra_id": f"{uid_str}_base", "name": name})
            
        all_data[chat_id_str] = group_data
        save_data(all_data)
        
        alert_msg = "السلام عليكم ورحمة الله وبركاته حياكِ الله\nفضلاً التزموا بأدواركم وكونوا على الموعد، حضوركم يؤنس مجلسنا\."
        bot.answer_callback_query(call.id, alert_msg, show_alert=True)
        update_board_message(call.message)

    elif call.data == "action_delete_last":
        user_roles = [m for m in group_data["members"] if m["id"] == uid_str]
        
        if not user_roles:
            bot.answer_callback_query(call.id, "⚠️ اسمكِ غير مسجل في القائمة لتتم إزالته\.", show_alert=True)
            return
            
        last_role = user_roles[-1]
        
        for idx in range(len(group_data["members"]) - 1, -1, -1):
            if group_data["members"][idx]["extra_id"] == last_role["extra_id"]:
                group_data["members"].pop(idx)
                break
                
        if last_role["extra_id"] in group_data["read"]:
            group_data["read"].remove(last_role["extra_id"])
            
        if last_role["extra_id"] == f"{uid_str}_base":
            group_data["listeners"] = [l for l in group_data["listeners"] if l != uid_str]
            group_data["excused"] = [e for e in group_data["excused"] if e["id"] != uid_str]
            bot.answer_callback_query(call.id, "🗑️ تم حذف اسمكِ بالكامل من المجلس الحالي\.", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "🗑️ تم حذف آخر دور إضافي قمتِ بتسجيله بنجاح\.", show_alert=True)
            
        all_data[chat_id_str] = group_data
        save_data(all_data)
        update_board_message(call.message)

    elif call.data == "action_extra_role":
        if not group_data.get("extra_roles_open", False):
            bot.answer_callback_query(call.id, "🔴 عذراً، تم غلق استقبال الأدوار الإضافية حالياً\.", show_alert=True)
            return
            
        is_registered = any(m["id"] == uid_str for m in group_data["members"])
        if not is_registered:
            bot.answer_callback_query(call.id, "⚠️ يجب تسجيل اسمكِ أولاً عبر زر 'تسجيل اسمي' كقارئة قبل طلب دور إضافي\.", show_alert=True)
            return
            
        is_excused = any(e["id"] == uid_str for e in group_data["excused"])
        if uid_str in group_data["listeners"] or is_excused:
            bot.answer_callback_query(call.id, "⚠️ لا يمكن للمستمعات أو المعتذرات طلب دور تلاوة إضافي\.", show_alert=True)
            return
            
        base_role_id = f"{uid_str}_base"
        if base_role_id not in group_data["read"]:
            bot.answer_callback_query(call.id, "⚠️ عذراً رعاكِ الله، يجب أن تنتهي من قراءة دوركِ الحالي (الأساسي) أولاً قبل طلب دور إضافي!", show_alert=True)
            return
            
        user = call.from_user
        name = user.first_name + (f" {user.last_name}" if user.last_name else "")
        
        current_roles_count = sum(1 for m in group_data["members"] if m["id"] == uid_str)
        new_extra_id = f"{uid_str}_extra_{current_roles_count}"
        
        group_data["members"].append({"id": uid_str, "extra_id": new_extra_id, "name": f"{name} (دور إضافي)"})
        all_data[chat_id_str] = group_data
        save_data(all_data)
        
        bot.answer_callback_query(call.id, "✅ تم تسجيل دور إضافي لكِ بنجاح في نهاية القائمة\.", show_alert=True)
        update_board_message(call.message)

    elif call.data == "action_read":
        student_roles = [m for m in group_data["members"] if m["id"] == uid_str]
        
        if not student_roles:
            bot.answer_callback_query(call.id, "⚠️ يجب تسجيل اسمكِ في القائمة أولاً\.", show_alert=True)
            return
            
        next_role = next((r for r in student_roles if r["extra_id"] not in group_data["read"]), None)
        
        if not next_role:
            bot.answer_callback_query(call.id, "لقد أتممتِ القراءة لجميع أدواركِ المسجلة حالياً، زادكِ الله حرصاً\.", show_alert=True)
            return
            
        group_data["read"].append(next_role["extra_id"])
        all_data[chat_id_str] = group_data
        save_data(all_data)
        
        read_alert = "جزاكِ الله خيراً وبارك فيكِ وطيب أنفاسكِ ونفعكِ بما تلوتِ وتعلمتِ، احرصي على المراجعة واستغفري\."
        bot.answer_callback_query(call.id, read_alert, show_alert=True)
        update_board_message(call.message)

    elif call.data == "admin_menu":
        bot.answer_callback_query(call.id)
        markup = get_admin_inline_keyboard(group_data)
        bot.edit_message_text("⚙️ *لوحة تحكم المشرفات والمالكة:*", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_toggle":
        group_data["list_open"] = not group_data["list_open"]
        all_data[chat_id_str] = group_data
        save_data(all_data)
        
        bot.answer_callback_query(call.id, "تم تغيير حالة القائمة بنجاح\.")
        markup = get_admin_inline_keyboard(group_data)
        bot.edit_message_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_toggle_extra":
        group_data["extra_roles_open"] = not group_data.get("extra_roles_open", False)
        all_data[chat_id_str] = group_data
        save_data(all_data)
        
        bot.answer_callback_query(call.id, "تم تعديل حالة الأدوار الإضافية بنجاح\.")
        markup = get_admin_inline_keyboard(group_data)
        bot.edit_message_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_stats":
        bot.answer_callback_query(call.id)
        readers_done = [escape_markdown_v2(m["name"]) for m in group_data["members"] if m["extra_id"] in group_data["read"]]
        listeners_list = [escape_markdown_v2(m["name"]) for m in group_data["members"] if m["id"] in group_data["listeners"]]
        excused_list = [escape_markdown_v2(m["name"]) for m in group_data["excused"]]
        
        stats_msg = (
            "بحمد الله نختم مجلسنا اليوم\n\n"
            f"✅ *القارئات اللاتي قرأن:*\n" + ("\n".join([f"• {r}" for r in readers_done]) if readers_done else "• لا يوجد") + "\n\n"
            f"🎧 *المستمعات:*\n" + ("\n".join([f"• {l}" for l in listeners_list]) if listeners_list else "• لا يوجد") + "\n\n"
            f"❌ *المعتذرات:*\n" + ("\n".join([f"• {e}" for e in excused_list]) if excused_list else "• لا يوجد")
        )
        bot.send_message(call.message.chat.id, stats_msg)

    elif call.data == "admin_call":
        seen_ids = set()
        for member in group_data["members"]:
            if member["id"] not in seen_ids:
                seen_ids.add(member["id"])
                try:
                    bot.send_message(int(member["id"]), "هلموا لمجلس تحفه الملائكة")
                except Exception:
                    pass
                    
        bot.send_message(call.message.chat.id, "هلموا لمجلس تحفه الملائكة")
        bot.answer_callback_query(call.id, "تم إرسال نداء المجلس وتنبيه المسجلات صَوْتِيّاً\.", show_alert=True)

    elif call.data == "admin_resend":
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: pass
        send_group_board(call.message.chat.id)
        bot.answer_callback_query(call.id, "تم تحديث وإعادة إرسال القائمة بنجاح\.")

    elif call.data == "admin_reset_confirm":
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ نعم، صفر القائمة", callback_data="admin_reset_execute"),
            types.InlineKeyboardButton("❌ تراجع", callback_data="admin_menu")
        )
        bot.edit_message_text("⚠️ *هل أنتِ متأكدة من رغبتكِ في تصفير بيانات المجلس الحالي؟*", call.message.chat.id, call.message.message_id, reply_markup=markup)

    elif call.data == "admin_reset_execute":
        all_data[chat_id_str] = get_empty_group_structure()
        save_data(all_data)
        bot.answer_callback_query(call.id, "تمت إعادة ضبط وتصفير البيانات بنجاح\.", show_alert=True)
        update_board_message(call.message)

    elif call.data == "main_menu":
        bot.answer_callback_query(call.id)
        update_board_message(call.message)

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Athaar Recitation Bot is active and fully optimized!", 200

if __name__ == "__main__":
    flask_thread = threading.Thread(target=lambda: flask_app.run(host="0.0.0.0", port=10000), daemon=True)
    flask_thread.start()
    
    # تحصين صارم: حظر الـ Webhook وحذف أي جلسات معلقة قديمة فوراً لمنع تعليق البوت
    try:
        bot.remove_webhook()
        time.sleep(1)
    except Exception:
        pass
        
    # تعديل جوهري: تفعيل خاصية الحظر التلقائي للجلسات المتداخلة (عدم السماح بأكثر من اتصال)
    # التعديل تم عبر تمرير خيار منع التداخل لإنهاء أي نُسخة معلقة على السيرفر
    bot.infinity_polling(none_stop=True, interval=0, timeout=20)
