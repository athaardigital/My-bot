import os
import time
import json
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv

import telebot
from telebot import types
from upstash_redis import Redis
from hijridate import Gregorian

# =====================================
# تَحْمِيلُ الْمُتَغَيِّرَاتِ
# =====================================
load_dotenv()
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)
redis_client = Redis(url=REDIS_URL, token=REDIS_TOKEN)
app = Flask(__name__)

# =====================================
# دَوَالُّ الْبَيَانَاتِ وَالْعَرْضِ
# =====================================
def get_group(chat_id):
    chat_id = str(chat_id)
    data = redis_client.get(f"group:{chat_id}")
    if not data:
        group = {
            "message_id": None, 
            "list_open": True, 
            "allow_extra_turns": False, 
            "readers": [], 
            "listeners": [], 
            "excused": [], 
            "completed": []
        }
        redis_client.set(f"group:{chat_id}", json.dumps(group))
        return group
    return json.loads(data) if isinstance(data, str) else data

def save_group(chat_id, group):
    redis_client.set(f"group:{str(chat_id)}", json.dumps(group))

def generate_list_text(group):
    """توليد نص القائمة بشكل منسق مع التاريخ الهجري"""
    try:
        hijri = Gregorian.today().to_hijri()
        date_str = f"📅 <b>تَارِيخُ الْيَوْمِ:</b> {hijri.day} {hijri.month_name()} {hijri.year} هـ\n"
    except:
        date_str = ""
        
    text = f"✨ <b>مَقْرَأَةُ الْقُرْآنِ الْكَرِيمِ</b> ✨\n{date_str}"
    text += "ـ" * 20 + "\n\n"
    
    text += "👥 <b>قَائِمَةُ الْقُرَّاءِ الْحَالِيَّةِ:</b>\n"
    if not group.get("readers"):
        text += "<i>لا يوجد قرّاء مسجلين حالياً.</i>\n"
    else:
        for i, r in enumerate(group["readers"]):
            status = "📖 يقرأ الآن" if i == 0 else "⏳ في الانتظار"
            text += f"{i+1}. <b>{r['name']}</b> ({status})\n"
            
    text += "\n🎧 <b>الْمُسْتَمِعُونَ:</b>\n"
    if not group.get("listeners"):
        text += "<i>لا يوجد مستمعين حالياً.</i>\n"
    else:
        for l in group["listeners"]:
            text += f"- {l['name']}\n"
            
    text += "\n✅ <b>الَّذِينَ أَتَمُّوا الْقِرَاءَةَ:</b>\n"
    if not group.get("completed"):
        text += "<i>لا أحد بعد.</i>\n"
    else:
        for c in group["completed"]:
            text += f"- {c['name']}  ✅\n"
            
    return text

# =====================================
# اللَّوْحَاتُ (الْأَزْرَارُ)
# =====================================
def main_keyboard(chat_id, user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(types.InlineKeyboardButton("📝 تَسْجِيلُ اسْمِي", callback_data="register_menu"))
    keyboard.add(types.InlineKeyboardButton("🗑️ حَذْفُ الِاسْمِ", callback_data="delete"),
                 types.InlineKeyboardButton("✅ تَمَّ الْفَرَاغُ", callback_data="done"))
    
    # التحقق من صلاحيات الإشراف لعرض الزر الخاص بالإعدادات
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.status in ["administrator", "creator"]:
            keyboard.add(types.InlineKeyboardButton("⚙️ إِعْدَادَاتُ الْإِشْرَافِ", callback_data="settings"))
    except:
        pass
    return keyboard

def settings_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("🔄 تَرْتِيبُ وَتَبْدِيلُ الْقُرَّاءِ", callback_data="manage_roles"),
        types.InlineKeyboardButton("❌ تَصْفِيرُ الْقَائِمَةِ كَامِلَةً", callback_data="clear_all"),
        types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْقَائِمَةِ الرَّئِيسِيَّةِ", callback_data="back_to_main")
    )
    return keyboard

# =====================================
# الدَّالَّةُ الرَّئِيسِيَّةُ لِتَحْدِيثِ الْعَرْضِ
# =====================================
def refresh_interface(call, chat_id, text, keyboard):
    """تحديث الرسالة الحالية بأمان وتفادي مشاكل التكرار"""
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, 
                              text=text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        print(f"Update error: {e}")

# =====================================
# مُعَالِجُ الْأَوَامِرِ (START)
# =====================================
@bot.message_handler(commands=["start"])
def start(message):
    chat_id = message.chat.id
    
    # حذف الرسالة القديمة إن وجدت لتنظيف الشاشة ومنع الفوضى
    old_group = get_group(chat_id)
    if old_group and old_group.get("message_id"):
        try:
            bot.delete_message(chat_id, old_group["message_id"])
        except:
            pass
            
    # [تعديل جذري] تصفير وتجديد البيانات بالكامل لفتح قائمة جديدة كلياً عند الضغط على start
    group = {
        "message_id": None,
        "list_open": True,
        "allow_extra_turns": False,
        "readers": [],
        "listeners": [],
        "excused": [],
        "completed": []
    }
    
    initial_text = generate_list_text(group)
    sent = bot.send_message(chat_id, initial_text, parse_mode="HTML", 
                            reply_markup=main_keyboard(chat_id, message.from_user.id))
    
    group["message_id"] = sent.message_id
    save_group(chat_id, group)

# =====================================
# مُعَالِجُ الْأَزْرَارِ (CALLBACK QUERY)
# =====================================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    group = get_group(chat_id)
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    
    # [تعديل جوهري] فك تعليق الأزرار مباشرة في أول السطر لتفادي الـ Lag وعلامة التحميل
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

    # --- 1. منطق التقديم والتأخير (التبديل) ---
    if call.data.startswith("move_up:"):
        idx = int(call.data.split(":")[1])
        if idx > 0:
            group["readers"][idx], group["readers"][idx-1] = group["readers"][idx-1], group["readers"][idx]
            save_group(chat_id, group)
        call.data = "manage_roles"  # تحويل المسار لعرض القائمة المحدثة فوراً

    elif call.data.startswith("move_down:"):
        idx = int(call.data.split(":")[1])
        if idx < len(group["readers"]) - 1:
            group["readers"][idx], group["readers"][idx+1] = group["readers"][idx+1], group["readers"][idx]
            save_group(chat_id, group)
        call.data = "manage_roles"  # تحويل المسار لعرض القائمة المحدثة فوراً

    # --- 2. عرض لوحة التحكم بالترتيب والتبديل للمشرفين ---
    # تم تحويلها إلى 'if' مستقلة لكي تعمل مباشرة وتحدث الشاشة بعد الضغط على التقديم/التأخير
    if call.data == "manage_roles":
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for i, r in enumerate(group["readers"]):
            keyboard.add(types.InlineKeyboardButton(
                f"{i+1}. {r['name']}", callback_data=f"edit_turn:{i}"
            ))
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْإِعْدَادَاتِ", callback_data="settings"))
        refresh_interface(call, chat_id, "🔄 <b>تَرْتِيبُ الْقُرَّاءِ:\nاضغط على اسم القارئ لتقديمه أو تأخيره:</b>", keyboard)
        return

    # --- 3. خيارات تعديل مستخدم معين ---
    elif call.data.startswith("edit_turn:"):
        idx = int(call.data.split(":")[1])
        if idx >= len(group["readers"]):
            call.data = "manage_roles"
            return
            
        target_user = group["readers"][idx]
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        # إظهار أزرار التحكم بناءً على موقع الاسم في المصفوفة
        if idx > 0:
            keyboard.add(types.InlineKeyboardButton("🔼 تَقْدِيمٌ لِلْأَعْلَى", callback_data=f"move_up:{idx}"))
        if idx < len(group["readers"]) - 1:
            keyboard.add(types.InlineKeyboardButton("🔽 تَأْخِيرٌ لِلْأَسْفَلِ", callback_data=f"move_down:{idx}"))
            
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْقَائِمَةِ", callback_data="manage_roles"))
        refresh_interface(call, chat_id, f"⚙️ <b>التحكم في ترتيب القارئ: {target_user['name']}</b>", keyboard)
        return

    # --- 4. نافذة الإعدادات الرئيسية للمشرفين ---
    elif call.data == "settings":
        refresh_interface(call, chat_id, "⚙️ <b>لَوْحَةُ إِعْدَادَاتِ الْإِشْرَافِ:</b>", settings_keyboard())
        return

    # --- 5. العودة للقائمة الرئيسية ---
    elif call.data == "back_to_main":
        refresh_interface(call, chat_id, generate_list_text(group), main_keyboard(chat_id, user_id))
        return

    # --- 6. خيار تصفير القائمة كاملاً من المشرف ---
    elif call.data == "clear_all":
        group["readers"] = []
        group["listeners"] = []
        group["completed"] = []
        save_group(chat_id, group)
        refresh_interface(call, chat_id, "🗑️ تم تصفير القائمة بنجاح.", settings_keyboard())
        return

    # --- 7. قائمة خيارات التسجيل (قارئ / مستمع) ---
    elif call.data == "register_menu":
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("📖 قَارِئٌ", callback_data="reg_reader"),
            types.InlineKeyboardButton("🎧 مُسْتَمِعٌ", callback_data="reg_listener")
        )
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ", callback_data="back_to_main"))
        refresh_interface(call, chat_id, "📝 <b>اخْتَرِ الصِّفَةَ الْمُنَاسِبَةَ لَكَ:</b>", keyboard)
        return

    # --- 8. تنفيذ التسجيل كقارئ ---
    elif call.data == "reg_reader":
        # منع التكرار في القراء
        if any(r["id"] == user_id for r in group["readers"]):
            return
        # إزالة الاسم من المستمعين إن وجد لمنع التداخل
        group["listeners"] = [l for l in group["listeners"] if l["id"] != user_id]
        
        group["readers"].append({"id": user_id, "name": user_name})
        save_group(chat_id, group)
        refresh_interface(call, chat_id, generate_list_text(group), main_keyboard(chat_id, user_id))
        return

    # --- 9. تنفيذ التسجيل كمستمع ---
    elif call.data == "reg_listener":
        if any(l["id"] == user_id for l in group["listeners"]):
            return
        group["readers"] = [r for r in group["readers"] if r["id"] != user_id]
        
        group["listeners"].append({"id": user_id, "name": user_name})
        save_group(chat_id, group)
        refresh_interface(call, chat_id, generate_list_text(group), main_keyboard(chat_id, user_id))
        return

    # --- 10. حذف الاسم بالكامل ---
    elif call.data == "delete":
        group["readers"] = [r for r in group["readers"] if r["id"] != user_id]
        group["listeners"] = [l for l in group["listeners"] if l["id"] != user_id]
        group["completed"] = [c for c in group["completed"] if c["id"] != user_id]
        save_group(chat_id, group)
        refresh_interface(call, chat_id, generate_list_text(group), main_keyboard(chat_id, user_id))
        return

    # --- 11. تم الفراغ من القراءة ---
    elif call.data == "done":
        user_reader = next((r for r in group["readers"] if r["id"] == user_id), None)
        if user_reader:
            group["readers"].remove(user_reader)
            if not any(c["id"] == user_id for c in group["completed"]):
                group["completed"].append(user_reader)
            save_group(chat_id, group)
        refresh_interface(call, chat_id, generate_list_text(group), main_keyboard(chat_id, user_id))
        return

# =====================================
# التَّشْغِيلُ
# =====================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

