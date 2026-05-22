import os
import json
from flask import Flask, request
import telebot
from telebot import types

# 1. الإعدادات
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = "https://my-bot-0z5k.onrender.com"  # استبدليه برابط موقعك الفعلي
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
app = Flask(__name__)
DATA_FILE = "recitation_data.json"

# 2. الدوال الأساسية
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"members": [], "read": [], "list_open": False}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def is_admin(user_id, chat_id):
    try: return bot.get_chat_member(chat_id, user_id).status in ("administrator", "creator")
    except: return False

def get_markup(user_id, chat_id):
    data = load_data()
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📝 تسجيل اسمي", callback_data="reg"),
        types.InlineKeyboardButton("🗑️ حذف اسمي", callback_data="del"),
        types.InlineKeyboardButton("✅ تم الفراغ من القراءة", callback_data="read"),
        types.InlineKeyboardButton("📖 عرض القائمة", callback_data="show")
    )
    if is_admin(user_id, chat_id):
        markup.add(types.InlineKeyboardButton("🔒 فتح/إغلاق القائمة", callback_data="toggle"))
        markup.add(types.InlineKeyboardButton("🔄 إعادة ضبط", callback_data="reset"))
    return markup

# 3. معالجة الأزرار
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    user = call.from_user
    data = load_data()

    if call.data == "reg":
        if not any(m['id'] == str(user.id) for m in data['members']):
            data['members'].append({'id': str(user.id), 'name': user.first_name})
            save_data(data)
            bot.answer_callback_query(call.id, "✅ تم التسجيل")
    
    elif call.data == "show":
        text = "📖 *قائمة التلاوة:*\n" + "\n".join([f"{i+1}. {m['name']}" for i, m in enumerate(data['members'])])
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=get_markup(user.id, chat_id))
    
    # (يمكنك إضافة باقي المنطق هنا بنفس الطريقة)
    bot.answer_callback_query(call.id)

# 4. الويب هوك والتشغيل
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return "!", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
