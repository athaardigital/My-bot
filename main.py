import os
import threading
import json
from flask import Flask
from dotenv import load_dotenv
import telebot
from telebot import types

# تحميل متغيرات البيئة من ملف .env محلياً إن وجد
load_dotenv()

# جلب توكن البوت من المتغيرات البيئية
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

DATA_FILE = "recitation_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"members": [], "read": [], "list_open": False}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[خطأ في حفظ البيانات] {e}")

def is_admin(user_id: int, chat_id: int) -> bool:
    try:
        # إذا كان الحساب خاص بالمنشئ الأساسي مباشرة
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception as e:
        print(f"[خطأ في التحقق من الإشراف] {e}")
        return False

def get_keyboard(user_id: int, chat_id: int, list_open: bool):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    markup.add(
        types.KeyboardButton("📝 تسجيل اسمي"),
        types.KeyboardButton("🗑️ حذف اسمي"),
        types.KeyboardButton("✅ تم الفراغ من القراءة"),
        types.KeyboardButton("📖 عرض القائمة")
    )
    
    if is_admin(user_id, chat_id):
        if list_open:
            markup.add(types.KeyboardButton("🔒 إغلاق القائمة"))
        else:
            markup.add(types.KeyboardButton("🔓 فتح القائمة للمؤلفين"))
        markup.add(types.KeyboardButton("🔄 إعادة ضبط القائمة"))
        
    return markup

def safe_reply(message, text, parse_mode=None):
    try:
        data = load_data()
        bot.send_message(
            message.chat.id,
            text,
            parse_mode=parse_mode,
            reply_markup=get_keyboard(
                message.from_user.id,
                message.chat.id,
                data["list_open"]
            )
        )
    except Exception as e:
        print(f"[خطأ في إرسال الرسالة] {e}")

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    try:
        data = load_data()
        admin_hint = ""
        if is_admin(message.from_user.id, message.chat.id):
            admin_hint = "\n\n🔑 *لديكِ صلاحيات الإشراف.* يمكنكِ التحكم في فتح وإغلاق وإعادة ضبط القائمة عبر الأزرار المظهرة لكِ."
            
        welcome_text = (
            "✨ *مرحباً بكِ في بوت إدارة قائمة التلاوة الجماعية* ✨\n\n"
            "يسعدنا تنظيم وردكِ القرآني وتسهيل الختمات المشتركة. الرجاء استخدام الأزرار أدناه للتفاعل مع القائمة."
            + admin_hint
        )
        bot.send_message(
            message.chat.id,
            welcome_text,
            parse_mode="Markdown",
            reply_markup=get_keyboard(
                message.from_user.id, message.chat.id, data["list_open"]
            )
        )
    except Exception as e:
        print(f"[خطأ في أمر البداية] {e}")

@bot.message_handler(func=lambda msg: msg.text == "📝 تسجيل اسمي")
def register_name(message):
    try:
        data = load_data()
        user = message.from_user
        name = user.first_name
        if user.last_name:
            name += f" {user.last_name}"
        user_id = str(user.id)

        existing = next((m for m in data["members"] if m["id"] == user_id), None)
        if existing:
            safe_reply(message, f"أنتِ مسجلة بالفعل في القائمة باسم: *{existing['name']}*.", parse_mode="Markdown")
        else:
            data["members"].append({"id": user_id, "name": name})
            save_data(data)
            safe_reply(message, f"✅ تم تسجيل الأخت *{name}* في قائمة التلاوة بنجاح!", parse_mode="Markdown")
    except Exception as e:
        print(f"[خطأ في التسجيل] {e}")

@bot.message_handler(func=lambda msg: msg.text == "🗑️ حذف اسمي")
def delete_name(message):
    try:
        data = load_data()
        user_id = str(message.from_user.id)
        member = next((m for m in data["members"] if m["id"] == user_id), None)

        if not member:
            safe_reply(message, "اسمكِ غير مدرج في القائمة حالياً لتتم إزالته.")
        else:
            data["members"] = [m for m in data["members"] if m["id"] != user_id]
            data["read"] = [r for r in data["read"] if r != user_id]
            save_data(data)
            safe_reply(message, f"🗑️ تم حذف الاسم *{member['name']}* من القائمة بناءً على طلبكِ.", parse_mode="Markdown")
    except Exception as e:
        print(f"[خطأ في الحذف] {e}")

@bot.message_handler(func=lambda msg: msg.text == "✅ تم الفراغ من القراءة")
def mark_read(message):
    try:
        data = load_data()
        if not data["list_open"]:
            safe_reply(message, "تنبيه: قائمة التلاوة مغلقة حالياً من قِبل المشرفات.")
            return

        user_id = str(message.from_user.id)
        member = next((m for m in data["members"] if m["id"] == user_id), None)

        if not member:
            safe_reply(message, "عذراً، يجب تسجيل اسمكِ في القائمة أولاً عبر الزر المخصص قبل تأكيد القراءة.")
        elif user_id in data["read"]:
            safe_reply(
                message,
                f"لقد تم تسجيل قراءتكِ مسبقاً للدورة الحالية يا *{member['name']}*. جزاكِ الله خيراً!",
                parse_mode="Markdown"
            )
        else:
            data["read"].append(user_id)
            save_data(data)
            safe_reply(
                message,
                f"✅ بارك الله فيكِ يا *{member['name']}*، تم تسجيل ختم وردكِ الحالي بنجاح.",
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"[خطأ في تأكيد القراءة] {e}")

@bot.message_handler(func=lambda msg: msg.text == "📖 عرض القائمة")
def show_list(message):
    try:
        data = load_data()
        if not data["members"]:
            safe_reply(message, "القائمة فارغة تماماً حالياً، بانتظار تسجيل المشتركات.")
            return

        lines = ["📖 *قائمة تلاوة القرآن الكريم*\n"]
        for i, member in enumerate(data["members"], 1):
            uid = member["id"]
            status = "✅ قرأت" if uid in data["read"] else "⏳ في الانتظار"
            lines.append(f"{i}. {status} ── {member['name']}")

        total = len(data["members"])
        read_count = len(data["read"])
        lines.append(f"\n📈 *الإحصائيات الحالية: {read_count} من أصل {total} ختمن الورد*")
        status_text = "🟢 مفتوحة" if data["list_open"] else "🔴 مغلقة"
        lines.append(f"حالة القائمة الحالية: *{status_text}*")

        safe_reply(message, "\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        print(f"[خطأ في عرض القائمة] {e}")

@bot.message_handler(func=lambda msg: msg.text in ["🔓 فتح القائمة للمؤلفين", "🔒 إغلاق القائمة"])
def toggle_list(message):
    try:
        if not is_admin(message.from_user.id, message.chat.id):
            safe_reply(message, "⛔ عذراً، هذا الإجراء مقتصر على مشرفات المجموعة فقط لحماية التنظيم.")
            return

        data = load_data()
        if data["list_open"]:
            data["list_open"] = False
            data["read"] = []
            save_data(data)
            safe_reply(
                message,
                "🔒 تم إغلاق قائمة التلاوة بنجاح، وتصفير علامات القراءة تمهيداً للدورة القادمة.",
                parse_mode="Markdown"
            )
        else:
            data["list_open"] = True
            save_data(data)
            safe_reply(
                message,
                "🔓 تم فتح قائمة التلاوة! يمكن لجميع المشتركات المسجلات الآن البدء بتسجيل القراءة.",
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"[خطأ في تبديل حالة القائمة] {e}")

@bot.message_handler(func=lambda msg: msg.text == "🔄 إعادة ضبط القائمة")
def reset_list(message):
    try:
        if not is_admin(message.from_user.id, message.chat.id):
            safe_reply(message, "⛔ عذراً، إعادة ضبط وتصفير القائمة بالكامل متاح للمشرفات فقط.")
            return

        data = load_data()
        data["members"] = []
        data["read"] = []
        data["list_open"] = False
        save_data(data)
        safe_reply(
            message,
            "🔄 تم مسح القائمة بالكامل وتفريغ الأسماء وإعادة ضبط البيانات لابتداء ختمة جديدة.",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[خطأ في إعادة الضبط] {e}")

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Athaar Recitation Bot is active and running perfectly!", 200

@flask_app.route("/health")
def health():
    return "OK", 200

def run_flask():
    # جعل المنفذ ديناميكياً ليتناسب مع متطلبات خوادم الويب المجانية
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

def exception_handler(exc):
    print(f"[خطأ في الاتصال المستمر] {exc}")

if __name__ == "__main__":
    print("جاري تشغيل بوت التلاوة لمشروع آثار الرقمية...")
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("تم تفعيل خادم Flask للحفاظ على استمرارية البوت وسد ثغرة المنفذ.")
   bot.infinity_polling()

و هذا اخر كود للمكتبة
pyTelegramBotAPI==4.12.0
Flask==3.0.0
python-dotenv==1.0.1
و ذا رابطهhttps://my-bot-0z5k.onrender.com
