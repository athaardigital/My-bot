import os
import time
import json
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv

import telebot
from telebot import types
from upstash_redis import Redis
from hijri_converter import Gregorian

# =====================================
# تَحْمِيلُ الْمُتَغَيِّرَاتِ
# =====================================

load_dotenv()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
REDIS_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
REDIS_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

if not BOT_TOKEN:
    raise Exception("TOKEN NOT FOUND")
if not REDIS_URL or not REDIS_TOKEN:
    raise Exception("UPSTASH CREDENTIALS NOT FOUND")

bot = telebot.TeleBot(BOT_TOKEN)

# =====================================
# الِاتِّصَالُ بِقَاعِدَةِ الْبَيَانَاتِ (Upstash Redis)
# =====================================

redis_client = Redis(url=REDIS_URL, token=REDIS_TOKEN)

# =====================================
# Flask & Webhook
# =====================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running on Cloud Database!", 200

@app.route("/" + BOT_TOKEN, methods=["POST"])
def receive_update():
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

# =====================================
# بَيَانَاتُ الْمَجْمُوعَةِ السَّحَابِيَّةِ
# =====================================

def default_group():
    return {
        "message_id": None,
        "list_open": False,
        "readers": [],      # يَقْبَلُ التَّكْرَارَ: {"id": str, "name": str, "done": bool}
        "listeners": [],    # {"id": str, "name": str}
        "excused": []       # {"id": str, "name": str}
    }

def get_group(chat_id):
    chat_id = str(chat_id)
    data = redis_client.get(f"group:{chat_id}")
    if not data:
        group = default_group()
        redis_client.set(f"group:{chat_id}", json.dumps(group))
        return group
    if isinstance(data, str):
        return json.loads(data)
    return data

def save_group(chat_id, group):
    redis_client.set(f"group:{str(chat_id)}", json.dumps(group))

# =====================================
# الصَّلَاحِيَّاتُ (الْمُشْرِفَاتُ)
# =====================================

def is_admin(user_id, chat_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

# =====================================
# الْمَنْشَن
# =====================================

def mention(user_id, name):
    safe_name = name.replace("<", "").replace(">", "")
    return f"<a href='tg://user?id={user_id}'>{safe_name}</a>"

# =====================================
# اللَّوْحَةُ الرَّئِيسِيَّةُ
# =====================================

def make_board(chat_id):
    group = get_group(chat_id)
    
    now = datetime.now()
    greg_date = now.strftime("%Y/%m/%d")
    hijri_date = Gregorian(now.year, now.month, now.day).to_hijri()
    today_str = f"{greg_date} م | {hijri_date.year}/{hijri_date.month}/{hijri_date.day} هـ"

    state = "🟢 مَفْتُوحَة" if group.get("list_open", False) else "🔴 مُغْلَقَة"

    text = (
        f"📅 <b>التَّارِيخ:</b> {today_str}\n\n"
        "اعْلَمِي رَعَاكِ اللَّهُ أَنَّ حُضُورَكِ مَجَالِسَ الْعِلْمِ النَّافِعِ "
        "هُوَ مَحْضُ اصْطِفَاءٍ مِنْ رَبِّكِ، فَاحْمَدِيهِ عَلَى هَذِهِ النِّعْمَةِ "
        "وَأَحْسِنِي رِعَايَتَهَا.\n\n"
        "✨ <b>قَائِمَةُ تِلَاوَةِ الْقُرْآنِ الْكَرِيمِ لِلْمَجْلِسِ الْحَالِيِّ</b> ✨\n\n"
    )

    # 1. القَارِئَاتُ
    text += "━━━━━━━━━━━━━━━\n"
    text += f"📖 <b>الْقَارِئَاتُ / الْقُرَّاءُ</b> ({len(group.get('readers', []))})\n\n"

    if not group.get("readers"):
        text += "لَا يُوجَدُ قَارِئَاتٌ حَالِيّاً.\n"
    else:
        for i, member in enumerate(group["readers"], start=1):
            done = " ✅" if member.get("done", False) else ""
            text += f"{i}. {mention(member['id'], member['name'])}{done}\n"

    text += "\n"

    # 2. الْمُسْتَمِعَاتُ
    text += "━━━━━━━━━━━━━━━\n"
    text += f"🎧 <b>الْـمُسْتَمِعَاتُ / الْـمُسْتَمِعُونَ</b> ({len(group.get('listeners', []))})\n\n"

    if not group.get("listeners"):
        text += "لَا يُوجَدُ مُسْتَمِعَاتٌ حَالِيّاً.\n"
    else:
        for i, member in enumerate(group["listeners"], start=1):
            text += f"{i}. {mention(member['id'], member['name'])}\n"

    text += "\n"

    # 3. الْمُعْتَذِرَاتُ
    text += "━━━━━━━━━━━━━━━\n"
    text += f"🌿 <b>الْـمُعْتَذِرَاتُ / الْـمُعْتَذِرُونَ</b> ({len(group.get('excused', []))})\n\n"

    if not group.get("excused"):
        text += "لَا يُوجَدُ مُعْتَذِرَاتٌ حَالِيّاً.\n"
    else:
        for i, member in enumerate(group["excused"], start=1):
            text += f"{i}. {mention(member['id'], member['name'])}\n"

    text += "\n━━━━━━━━━━━━━━━\n"
    text += f"🔒 <b>حَالَةُ الْقَائِمَةِ:</b> {state}"

    return text

# =====================================
# لَوْحَاتُ الْأَزْرَارِ
# =====================================

def main_keyboard(chat_id, user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📝 تَسْجِيلُ اسْمِي", callback_data="register_menu")
    )
    keyboard.add(
        types.InlineKeyboardButton("🗑️ حَذْفُ آخِرِ دَوْرٍ", callback_data="delete_last"),
        types.InlineKeyboardButton("✅ تَمَّ الْفَرَاغُ مِنَ الْقِرَاءَةِ", callback_data="done")
    )

    if is_admin(user_id, chat_id):
        keyboard.add(
            types.InlineKeyboardButton("⚙️ إِعْدَادَاتُ الْمُشْرِفَاتِ", callback_data="settings")
        )

    return keyboard

def register_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("📖 قَارِئٌ / قَارِئَة", callback_data="role_reader"),
        types.InlineKeyboardButton("🎧 مُسْتَمِعٌ / مُسْتَمِعَة", callback_data="role_listener"),
        types.InlineKeyboardButton("🌿 مُعْتَذِرٌ / مُعْتَذِرَة", callback_data="role_excused"),
        types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْقَائِمَةِ الرَّئِيسِيَّةِ", callback_data="back_to_main")
    )
    return keyboard

def settings_keyboard(chat_id):
    group = get_group(chat_id)
    state_button = "🔒 إِغْلَاقُ الْقَائِمَةِ" if group.get("list_open", False) else "🔓 فَتْحُ الْقَائِمَةِ"

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(types.InlineKeyboardButton(state_button, callback_data="toggle"))
    keyboard.add(types.InlineKeyboardButton("📖 تَحْدِيثُ الْقَائِمَةِ", callback_data="refresh"))
    keyboard.add(types.InlineKeyboardButton("📢 الْمُنَادَاةُ", callback_data="call"))
    keyboard.add(types.InlineKeyboardButton("🔄 إِعَادَةُ ضَبْطِ الْقَائِمَةِ", callback_data="reset"))
    keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْمَجْلِسِ", callback_data="back_to_main"))

    return keyboard

# =====================================
# تَحْدِيثُ اللَّوْحَةِ
# =====================================

def update_board(chat_id, user_id):
    group = get_group(chat_id)
    if not group.get("message_id"):
        return

    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=group["message_id"],
            text=make_board(chat_id),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=main_keyboard(chat_id, user_id)
        )
    except Exception as e:
        print(f"Update Board Error: {e}")

# =====================================
# دَوَالُّ التَّعْدِيلِ عَلَى الْأَعْضَاءِ
# =====================================

def remove_member_completely(group, user_id):
    user_id_str = str(user_id)
    group["readers"] = [x for x in group.get("readers", []) if str(x["id"]) != user_id_str]
    group["listeners"] = [x for x in group.get("listeners", []) if str(x["id"]) != user_id_str]
    group["excused"] = [x for x in group.get("excused", []) if str(x["id"]) != user_id_str]

def delete_last_turn(group, user_id):
    user_id_str = str(user_id)
    
    readers = group.get("readers", [])
    indices = [i for i, x in enumerate(readers) if str(x["id"]) == user_id_str]
    if indices:
        readers.pop(indices[-1])
        group["readers"] = readers
        return True

    listeners_before = len(group.get("listeners", []))
    group["listeners"] = [x for x in group.get("listeners", []) if str(x["id"]) != user_id_str]
    if len(group["listeners"]) < listeners_before:
        return True

    excused_before = len(group.get("excused", []))
    group["excused"] = [x for x in group.get("excused", []) if str(x["id"]) != user_id_str]
    if len(group["excused"]) < excused_before:
        return True

    return False

# =====================================
# أَمْرُ الِابْتِدَاءِ (start)
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    if message.chat.type == "private":
        bot.send_message(
            message.chat.id,
            "السَّلَامُ عَلَيْكُمْ وَرَحْمَةُ اللَّهِ وَبَرَكَاتُهُ\n\nحَيَّاكُمُ اللَّهُ.\n\n"
            "نَشْرُكُمْ لِهَذَا الْبُوتِ يُعَدُّ صَدَقَةً جَارِيَةً عَنِّي وَعَنْ وَالِدَيَّ "
            "وَمَقْرَأَتِنَا وَكَافَّةِ الْمُسْلِمِينَ وَالْمُسْلِمَاتِ."
        )
        return

    chat_id = str(message.chat.id)
    group = default_group()

    sent = bot.send_message(
        message.chat.id,
        make_board(chat_id),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=main_keyboard(message.chat.id, message.from_user.id)
    )

    group["message_id"] = sent.message_id
    save_group(chat_id, group)

# =====================================
# مَعَالِجُ التَّفَاعُلِ مَعَ الْأَزْرَارِ
# =====================================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    group = get_group(chat_id)
    user = call.from_user

    full_name = user.first_name or "مُسْتَخْدِمٌ/ة"
    if user.last_name:
        full_name += f" {user.last_name}"

    user_id_str = str(user.id)

    admin_callbacks = ["settings", "toggle", "refresh", "reset", "call"]
    if call.data in admin_callbacks:
        if not is_admin(user.id, chat_id):
            bot.answer_callback_query(call.id, "❌ عُذْراً! هَذِهِ الْإِعْدَادَاتُ مَحْصُورَةٌ لِمُشْرِفَاتِ الْمَجْلِسِ فَقَطْ.", show_alert=True)
            return

    if call.data == "register_menu":
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=register_keyboard()
        )
        bot.answer_callback_query(call.id)
        return

    elif call.data == "back_to_main":
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=main_keyboard(chat_id, user.id)
        )
        bot.answer_callback_query(call.id)
        return

    elif call.data == "role_reader":
        if not group.get("list_open", False):
            bot.answer_callback_query(call.id, "❌ الْقَائِمَةُ مُغْلَقَةٌ حَالِيّاً! لَا يُمْكِنُ تَسْجِيلُ الْأَدْوَارِ.", show_alert=True)
            return

        user_turns = [x for x in group.get("readers", []) if str(x["id"]) == user_id_str]
        if user_turns:
            last_turn = user_turns[-1]
            if not last_turn.get("done", False):
                bot.answer_callback_query(call.id, "⚠️ لَا يُمْكِنُكِ طَلَبُ دَوْرٍ إِضَافِيٍّ حَتَّى تَنْتَهِي مِنْ قِرَاءَةِ دَوْرِكِ الْحَالِيِّ وتُؤَكِّدِيهِ!", show_alert=True)
                return

        group["listeners"] = [x for x in group.get("listeners", []) if str(x["id"]) != user_id_str]
        group["excused"] = [x for x in group.get("excused", []) if str(x["id"]) != user_id_str]
        
        group["readers"].append({"id": user_id_str, "name": full_name, "done": False})
        bot.answer_callback_query(call.id, "✅ تَمَّ تَسْجِيلُكِ فِي qَائِمَةِ الْقِرَاءَةِ.")

    elif call.data == "role_listener":
        remove_member_completely(group, user.id)
        group["listeners"].append({"id": user_id_str, "name": full_name})
        bot.answer_callback_query(call.id, "🎧 تَمَّ تَسْجِيلُكِ كَمُسْتَمِعَةٍ.")

    elif call.data == "role_excused":
        remove_member_completely(group, user.id)
        group["excused"].append({"id": user_id_str, "name": full_name})
        bot.answer_callback_query(call.id, "🌿 تَمَّ تَسْجِيلُ اعْتِذَارِكِ.")

    elif call.data == "delete_last":
        success = delete_last_turn(group, user.id)
        if success:
            bot.answer_callback_query(call.id, "🗑️ تَمَّ حَذْفُ آخِرِ دَوْرٍ لَكِ.")
        else:
            bot.answer_callback_query(call.id, "❌ اسْمُكِ غَيْرُ مُسَجَّلٍ فِي أَيِّ قَائِمَةٍ!", show_alert=True)

    elif call.data == "done":
        updated = False
        for member in group.get("readers", []):
            if str(member["id"]) == user_id_str and not member.get("done", False):
                member["done"] = True
                updated = True
                break

        if updated:
            bot.answer_callback_query(call.id, "✅ هَنِيئاً! تَمَّ تَأْكِيدُ انْتِهَاءِ الْقِرَاءَةِ.")
        else:
            bot.answer_callback_query(call.id, "❌ لَيْسَ لَدَيْكِ دَوْرٌ نَشِطٌ (غَيْرُ مُكْتَمِلٍ) فِي الْقِرَاءَةِ!", show_alert=True)

    elif call.data == "settings":
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=settings_keyboard(chat_id)
        )
        bot.answer_callback_query(call.id)
        return

    elif call.data == "toggle":
        group["list_open"] = not group.get("list_open", False)
        bot.answer_callback_query(call.id, "🔄 تَمَّتْ تَوْسِعَةُ/تَعْدِيلُ حَالَةِ الْقَائِمَةِ.")

    elif call.data == "refresh":
        bot.answer_callback_query(call.id, "🔄 تَمَّ التَّحْدِيثُ.")

    elif call.data == "reset":
        old_message = group.get("message_id")
        group = default_group()
        group["message_id"] = old_message
        bot.answer_callback_query(call.id, "🔄 تَمَّتْ إِعَادَةُ ضَبْطِ الْمَجْلِسِ.")

    elif call.data == "call":
        all_members = group.get("readers", []) + group.get("listeners", []) + group.get("excused", [])
        called_ids = set()
        for mem in all_members:
            mem_id = int(mem["id"])
            if mem_id not in called_ids:
                try:
                    bot.send_message(mem_id, "هَلُمُّوا لِمَجْلِسٍ تَحُفُّهُ الْمَلَائِكَةُ 🌿")
                    called_ids.add(mem_id)
                except:
                    pass
        bot.answer_callback_query(call.id, "📢 تَمَّ إِرْسَالُ نِدَاءِ الْمُنَادَاةِ.")

    save_group(chat_id, group)
    update_board(chat_id, user.id)

# =====================================
# التَّشْغِيلُ مَعَ Webhook
# =====================================

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
    if RENDER_URL:
        bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
        print(f"Webhook set to {RENDER_URL}/{BOT_TOKEN}")
    else:
        print("⚠️ لم يتم العثور على RENDER_EXTERNAL_URL في البيئة.")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
