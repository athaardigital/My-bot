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

if not BOT_TOKEN:
    raise ValueError("⚠️ TELEGRAM_BOT_TOKEN NOT FOUND IN ENV")
if not REDIS_URL or not REDIS_TOKEN:
    raise ValueError("⚠️ UPSTASH CREDENTIALS NOT FOUND IN ENV")

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
    return "Bot is running securely on Upstash Redis!", 200

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
        "allow_extra_turns": False,
        "readers": [],      
        "listeners": [],    
        "excused": [],      
        "completed": []     
    }

def get_group(chat_id):
    chat_id = str(chat_id)
    data = redis_client.get(f"group:{chat_id}")
    if not data:
        group = default_group()
        redis_client.set(f"group:{chat_id}", json.dumps(group))
        return group
    
    if isinstance(data, str):
        group = json.loads(data)
    else:
        group = data
        
    if "allow_extra_turns" not in group:
        group["allow_extra_turns"] = False
    if "completed" not in group:
        group["completed"] = []
        
    return group

def save_group(chat_id, group):
    redis_client.set(f"group:{str(chat_id)}", json.dumps(group))

# =====================================
# الصَّلَاحِيَّاتُ
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
    try:
        hijri_date = Gregorian(now.year, now.month, now.day).to_hijri()
        today_str = f"{greg_date} م | {hijri_date.year}/{hijri_date.month}/{hijri_date.day} هـ"
    except:
        today_str = f"{greg_date} م"

    state = "🟢 مَفْتُوحَة" if group.get("list_open", False) else "🔴 مُغْلَقَة"

    text = (
        f"📅 <b>التَّارِيخ:</b> {today_str}\n\n"
        "<blockquote>اعْلَمْ رَعَاكَ اللَّهُ أَنَّ حُضُورَكَ مَجَالِسَ الْعِلْمِ النَّافِعِ "
        "هُوَ مَحْضُ اصْطِفَاءٍ مِنْ رَبِّكَ، فَاحْمَدْهُ عَلَى هَذِهِ النِّعْمَةِ "
        "وَأَحْسِنْ رِعَايَتَهَا.</blockquote>\n\n"
        "✨ <b>قَائِمَةُ تِلَاوَةِ الْقُرْآنِ الْكَرِيمِ لِلْمَجْلِسِ الْحَالِيِّ</b> ✨\n\n"
    )

    # 1. القَارِئُونَ
    text += "━━━━━━━━━━━━━━━\n"
    text += f"📖 <b>الْقَارِئُونَ</b> ({len(group.get('readers', []))})\n\n"

    if not group.get("readers"):
        text += "لَا يُوجَدُ حَالِيّاً.\n"
    else:
        for i, member in enumerate(group["readers"], start=1):
            done = " ✅" if str(member["id"]) in group.get("completed", []) else ""
            text += f"{i}. {mention(member['id'], member['name'])}{done}\n"

    text += "\n"

    # 2. الْمُسْتَمِعُونَ
    text += "━━━━━━━━━━━━━━━\n"
    text += f"🎧 <b>الْـمُسْتَمِعُونَ</b> ({len(group.get('listeners', []))})\n\n"

    if not group.get("listeners"):
        text += "لَا يُوجَدُ حَالِيّاً.\n"
    else:
        for i, member in enumerate(group["listeners"], start=1):
            text += f"{i}. {mention(member['id'], member['name'])}\n"

    text += "\n"

    # 3. الْمُعْتَذِرُونَ
    text += "━━━━━━━━━━━━━━━\n"
    text += f"🌿 <b>الْـمُعْتَذِرُونَ</b> ({len(group.get('excused', []))})\n\n"

    if not group.get("excused"):
        text += "لَا يُوجَدُ حَالِيّاً.\n"
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
        types.InlineKeyboardButton("🗑️ حَذْفُ الِاسْمِ", callback_data="delete"),
        types.InlineKeyboardButton("✅ تَمَّ الْفَرَاغُ مِنَ الْقِرَاءَةِ", callback_data="done")
    )

    if is_admin(user_id, chat_id):
        keyboard.add(
            types.InlineKeyboardButton("⚙️ إِعْدَادَاتُ الْإِشْرَافِ", callback_data="settings")
        )

    return keyboard

def register_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        types.InlineKeyboardButton("📖 قَارِئٌ", callback_data="role_reader"),
        types.InlineKeyboardButton("🎧 مُسْتَمِعٌ", callback_data="role_listener"),
        types.InlineKeyboardButton("🌿 مُعْتَذِرٌ", callback_data="role_excused"),
        types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْقَائِمَةِ الرَّئِيسِيَّةِ", callback_data="back_to_main")
    )
    return keyboard

def settings_keyboard(chat_id):
    group = get_group(chat_id)
    state_button = "🔒 إِغْلَاقُ الْقَائِمَةِ" if group.get("list_open", False) else "🔓 فَتْحُ الْقَائِمَةِ"
    extra_button = "🔒 مَنْعُ الْأَدْوَارِ الْإِضَافِيَّةِ" if group.get("allow_extra_turns", False) else "🔓 السَّمَاحُ بِالْأَدْوَارِ الْإِضَافِيَّةِ"

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(types.InlineKeyboardButton(state_button, callback_data="toggle"))
    keyboard.add(types.InlineKeyboardButton(extra_button, callback_data="toggle_extra"))
    keyboard.add(types.InlineKeyboardButton("🔄 تِغْيِيرُ الْأَدْوَارِ (التَّرْتِيبِ)", callback_data="manage_roles"))
    keyboard.add(types.InlineKeyboardButton("📊 إِحْصَاءُ الْحِصَّةِ", callback_data="stats"))
    keyboard.add(types.InlineKeyboardButton("🔄 إِعَادَةُ إِرْسَالِ الْقَائِمَةِ", callback_data="refresh"))
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

def remove_member(group, user_id):
    user_id_str = str(user_id)
    group["readers"] = [x for x in group.get("readers", []) if str(x["id"]) != user_id_str]
    group["listeners"] = [x for x in group.get("listeners", []) if str(x["id"]) != user_id_str]
    group["excused"] = [x for x in group.get("excused", []) if str(x["id"]) != user_id_str]
    group["completed"] = [x for x in group.get("completed", []) if str(x) != user_id_str]

# =====================================
# أَمْرُ الِابْتِدَاءِ (start)
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    if message.chat.type == "private":
        bot.send_message(
            message.chat.id,
            "السَّلَامُ عَلَيْكُمْ وَرَحْمَةُ اللَّهِ وَبَرَكَاتُهُ\n\nحَيَّاكُمُ اللَّهُ.\n\n"
            "انْشُرُوا الْبُوتَ فَضْلاً فَهُوَ صَدَقَةٌ عَنِّي وَعَنْ وَالِدَيَّ وَمَقْرَأَتِنَا "
            "وَكُلِّ الْمُسْلِمِينَ وَالْمُسْلِمَاتِ."
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

    full_name = user.first_name or "مُسْتَخْدِمٌ"
    if user.last_name:
        full_name += f" {user.last_name}"

    member = {"id": str(user.id), "name": full_name}
    user_id_str = str(user.id)

    # -------------------------------------
    # حِمَايَةُ أَزْرَارِ الْمُشْرِفِينَ
    # -------------------------------------
    admin_callbacks = ["settings", "toggle", "toggle_extra", "manage_roles", "stats", "refresh", "reset", "call"]
    if call.data in admin_callbacks or call.data.startswith("edit_turn:") or call.data.startswith("move_up:") or call.data.startswith("move_down:") or call.data.startswith("swap_turn:") or call.data.startswith("doswap:"):
        if not is_admin(user.id, chat_id):
            bot.answer_callback_query(call.id, "❌ عُذْراً! هَذِهِ الْإِعْدَادَاتُ مَحْصُورَةٌ لِلْمُشْرِفِينَ فَقَطْ.", show_alert=True)
            return

    # -------------------------------------
    # مَنْطِقُ الْأَزْرَارِ
    # -------------------------------------
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
            bot.answer_callback_query(call.id, "❌ الْقَائِمَةُ مُغْلَقَةٌ حَالِيّاً! لَا يُمْكِنُ التَّسْجِيلُ.", show_alert=True)
            return

        is_already_reader = any(str(x["id"]) == user_id_str for x in group.get("readers", []))
        
        if is_already_reader:
            if not group.get("allow_extra_turns", False):
                bot.answer_callback_query(call.id, "❌ الْأَدْوَارُ الْإِضَافِيَّةُ مُغْلَقَةٌ حَالِيّاً مِنْ قِبَلِ الْمُشْرِفِينَ!", show_alert=True)
                return

            if user_id_str not in group.get("completed", []):
                bot.answer_callback_query(call.id, "⚠️ لَا يُمْكِنُكَ طَلَبُ دَوْرٍ إِضَافِيٍّ حَتَّى تُؤَكِّدَ الِانْتِهَاءَ مِنْ دَوْرِكَ السَّابِقِ!", show_alert=True)
                return
            
            # إِذَا كَانَ يُرِيدُ دَوْراً إِضَافِيّاً، نُزِيلُهُ مِنَ الْمُنْتَهِينَ لِيَبْدَأَ دَوْرَهُ الْجَدِيدَ
            group["completed"].remove(user_id_str)

        group["listeners"] = [x for x in group.get("listeners", []) if str(x["id"]) != user_id_str]
        group["excused"] = [x for x in group.get("excused", []) if str(x["id"]) != user_id_str]
        
        if not is_already_reader:
            group["readers"].append(member)
            
        save_group(chat_id, group)
        update_board(chat_id, user.id)
        
        bot.answer_callback_query(call.id, "✅ تَمَّ تَسْجِيلُكَ فِي قَائِمَةِ الْقُرَّاءِ.")
        bot.send_message(
            chat_id,
            f"🌿 بَارَكَ اللَّهُ فِيكَ يَا {mention(user.id, full_name)}، احْرِصْ عَلَى حُضُورِ دَوْرِكَ وَالِالْتِزَامِ بِهِ.",
            parse_mode="HTML"
        )

    elif call.data == "role_listener":
        remove_member(group, user.id)
        group["listeners"].append(member)
        save_group(chat_id, group)
        update_board(chat_id, user.id)
        bot.answer_callback_query(call.id, "🎧 تَمَّ تَسْجِيلُكَ كَمُسْتَمِعٍ.")

    elif call.data == "role_excused":
        remove_member(group, user.id)
        group["excused"].append(member)
        save_group(chat_id, group)
        update_board(chat_id, user.id)
        bot.answer_callback_query(call.id, "🌿 تَمَّ تَسْجِيلُ اعْتِذَارِكَ.")

    elif call.data == "delete":
        remove_member(group, user.id)
        save_group(chat_id, group)
        update_board(chat_id, user.id)
        bot.answer_callback_query(call.id, "🗑️ تَمَّ حَذْفُ اسْمِكَ مِنَ الْقَائِمَةِ.", show_alert=True)

    elif call.data == "done":
        is_registered = any(str(x["id"]) == user_id_str for x in group.get("readers", []))
        if not is_registered:
            bot.answer_callback_query(call.id, "⚠️ يَجِبُ أَنْ تَكُونَ مُسَجَّلاً فِي قَائِمَةِ الْقُرَّاءِ أَوَّلاً!", show_alert=True)
            return

        if user_id_str not in group.get("completed", []):
            group["completed"].append(user_id_str)
            save_group(chat_id, group)
            update_board(chat_id, user.id)
            bot.answer_callback_query(call.id, "✅ هَنِيئاً لَكَ! تَمَّ تَأْكِيدُ الْفَرَاغِ مِنَ الْقِرَاءَةِ.")
            bot.send_message(
                chat_id,
                f"✨ يَا {mention(user.id, full_name)}... جَزَاكَ اللَّهُ خَيْراً عَلَى الْحُضُورِ وَالْمُشَارَكَةِ. تَذَكَّرْ رَضِيَ اللَّهُ عَنْكَ أَنْ تُرَاجِعَ مَحْفُوظَكَ وَتَتَدَرَّبَ عَلَى تَقْوِيمِ أَخْطَائِكَ وَمُرَاجَعَةِ مُلَاحَظَاتِ مُعَلِّمِكَ، وَإِيَّاكَ أَنْ تَهْجُرَ صَاحِبَكَ الْقُرْآنَ.",
                parse_mode="HTML"
            )
        else:
            bot.answer_callback_query(call.id, "ℹ️ لَقَدْ قُمْتَ بِتَأْكِيدِ الْقِرَاءَةِ مُسْبَقاً.", show_alert=True)

    elif call.data == "settings":
        bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=settings_keyboard(chat_id)
        )
        bot.answer_callback_query(call.id)

    elif call.data == "toggle":
        group["list_open"] = not group.get("list_open", False)
        save_group(chat_id, group)
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=settings_keyboard(chat_id))
        bot.answer_callback_query(call.id, "🔄 تَمَّ تَعْدِيلُ حَالَةِ الْقَائِمَةِ.")

    elif call.data == "toggle_extra":
        group["allow_extra_turns"] = not group.get("allow_extra_turns", False)
        save_group(chat_id, group)
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=settings_keyboard(chat_id))
        bot.answer_callback_query(call.id, "🔄 تَمَّ تَعْدِيلُ حَالَةِ الْأَدْوَارِ الْإِضَافِيَّةِ.")

    elif call.data == "refresh":
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        sent = bot.send_message(
            chat_id,
            make_board(chat_id),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=main_keyboard(chat_id, user.id)
        )
        group["message_id"] = sent.message_id
        save_group(chat_id, group)
        bot.answer_callback_query(call.id, "🔄 تَمَّتْ إِعَادَةُ إِرْسَالِ الْقَائِمَةِ بِالنِّهَايَةِ.")

    elif call.data == "stats":
        readers = group.get("readers", [])
        listeners = group.get("listeners", [])
        excused = group.get("excused", [])
        completed = group.get("completed", [])
        
        stats_text = "📊 <b>إِحْصَائِيَّاتُ الْمَجْلِسِ النِّهَائِيَّةِ</b> 📊\n\n"
        
        stats_text += "📖 <b>الْقُرَّاءُ:</b>\n"
        if not readers:
            stats_text += "لَا يُوجَدُ\n"
        else:
            for i, m in enumerate(readers, start=1):
                status = "✅" if str(m["id"]) in completed else "❌"
                stats_text += f"{i}. {m['name']} {status}\n"
                
        stats_text += "\n🎧 <b>الْمُسْتَمِعُونَ:</b>\n"
        if not listeners:
            stats_text += "لَا يُوجَدُ\n"
        else:
            for i, m in enumerate(listeners, start=1):
                stats_text += f"{i}. {m['name']}\n"
                
        stats_text += "\n🌿 <b>الْمُعْتَذِرُونَ:</b>\n"
        if not excused:
            stats_text += "لَا يُوجَدُ\n"
        else:
            for i, m in enumerate(excused, start=1):
                stats_text += f"{i}. {m['name']}\n"
                
        bot.send_message(chat_id, stats_text, parse_mode="HTML")
        bot.answer_callback_query(call.id, "📊 تَمَّ إِصْدَارُ الْإِحْصَاءِ.", show_alert=True)

    elif call.data == "reset":
        old_message = group.get("message_id")
        group = default_group()
        group["message_id"] = old_message
        save_group(chat_id, group)
        update_board(chat_id, user.id)
        bot.answer_callback_query(call.id, "🔄 تَمَّتْ إِعَادَةُ ضَبْطِ الْمَجْلِسِ تَمَاماً.", show_alert=True)

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
        bot.answer_callback_query(call.id, "📢 تَمَّ إِرْسَالُ نِدَاءِ الْمُنَادَاةِ لِلْجَمِيعِ.", show_alert=True)

    # ==================================================
    # إِدَارَةُ الْأَدْوَارِ وَالتَّرْتِيبِ
    # ==================================================
    
    elif call.data == "manage_roles":
        if not group.get("readers"):
            bot.answer_callback_query(call.id, "⚠️ لَا يُوجَدُ قُرَّاءٌ مُسَجَّلُونَ حَالِيّاً لِتَعْدِيلِ أَدْوَارِهِمْ.", show_alert=True)
            return

        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for r in group["readers"]:
            keyboard.add(types.InlineKeyboardButton(r["name"], callback_data=f"edit_turn:{r['id']}"))
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْإِعْدَادَاتِ", callback_data="settings"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="🔄 <b>اخْتَرْ أَحَدَ الْقُرَّاءِ لِتَعْدِيلِ أَوْ تَبْدِيلِ دَوْرِهِ:</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)

    elif call.data.startswith("edit_turn:"):
        target_id = call.data.split(":")[1]
        target_name = next((x["name"] for x in group["readers"] if str(x["id"]) == target_id), "الْقَارِئُ")

        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("تَقْدِيمٌ ⬆️", callback_data=f"move_up:{target_id}"),
            types.InlineKeyboardButton("تَأْخِيرٌ ⬇️", callback_data=f"move_down:{target_id}")
        )
        keyboard.add(types.InlineKeyboardButton("تَبْدِيلٌ مَعَهُ 🔄", callback_data=f"swap_turn:{target_id}"))
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْقَائِمَةِ", callback_data="manage_roles"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"⚙️ <b>إِدَارَةُ تَرْتِيبِ الْعُضْوِ:</b> {target_name}\n\nاخْتَرْ إِجْرَاءً التَّعْدِيلِ الْمُعْتَمَدِ:",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)

    elif call.data.startswith("move_up:"):
        target_id = call.data.split(":")[1]
        readers = group["readers"]
        idx = next((i for i, x in enumerate(readers) if str(x["id"]) == target_id), None)

        if idx is not None and idx > 0:
            readers[idx], readers[idx - 1] = readers[idx - 1], readers[idx]
            save_group(chat_id, group)
            bot.answer_callback_query(call.id, "✅ تَمَّ تَقْدِيمُ دَوْرِ الْقَارِئِ بِنَجَاحٍ.", show_alert=True)
            callbacks(telebot.types.CallbackQuery(call.id, call.from_user, call.message, "manage_roles", call.chat_instance))
        else:
            bot.answer_callback_query(call.id, "⚠️ الْعُضْوُ فِي بِدَايَةِ الْقَائِمَةِ بِالْفِعْلِ!", show_alert=True)

    elif call.data.startswith("move_down:"):
        target_id = call.data.split(":")[1]
        readers = group["readers"]
        idx = next((i for i, x in enumerate(readers) if str(x["id"]) == target_id), None)

        if idx is not None and idx < len(readers) - 1:
            readers[idx], readers[idx + 1] = readers[idx + 1], readers[idx]
            save_group(chat_id, group)
            bot.answer_callback_query(call.id, "✅ تَمَّ تَأْخِيرُ دَوْرِ الْقَارِئِ بِنَجَاحٍ.", show_alert=True)
            callbacks(telebot.types.CallbackQuery(call.id, call.from_user, call.message, "manage_roles", call.chat_instance))
        else:
            bot.answer_callback_query(call.id, "⚠️ الْعُضْوُ فِي نِهَايَةِ الْقَائِمَةِ بِالْفِعْلِ!", show_alert=True)

    elif call.data.startswith("swap_turn:"):
        target_id = call.data.split(":")[1]
        target_name = next((x["name"] for x in group["readers"] if str(x["id"]) == target_id), "الْقَارِئُ")

        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for r in group["readers"]:
            if str(r["id"]) != target_id:
                keyboard.add(types.InlineKeyboardButton(f"تَبْدِيلٌ مَعَ: {r['name']}", callback_data=f"doswap:{target_id}:{r['id']}"))
        keyboard.add(types.InlineKeyboardButton("🔙 إِلْغَاءٌ", callback_data=f"edit_turn:{target_id}"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"🔄 <b>اخْتَرْ عُضْواً آخَرَ لِتَبْدِيلِ الْمَرَاكِزِ مَعَ ({target_name}):</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)

    elif call.data.startswith("doswap:"):
        id1 = call.data.split(":")[1]
        id2 = call.data.split(":")[2]
        readers = group["readers"]

        idx1 = next((i for i, x in enumerate(readers) if str(x["id"]) == id1), None)
        idx2 = next((i for i, x in enumerate(readers) if str(x["id"]) == id2), None)

        if idx1 is not None and idx2 is not None:
            readers[idx1], readers[idx2] = readers[idx2], readers[idx1]
            save_group(chat_id, group)
            bot.answer_callback_query(call.id, "✅ تَمَّ تَبْدِيلُ أَدْوَارِ الْعُضْوَيْنِ بِنَجَاحٍ.", show_alert=True)
            callbacks(telebot.types.CallbackQuery(call.id, call.from_user, call.message, "manage_roles", call.chat_instance))
        else:
            bot.answer_callback_query(call.id, "⚠️ حَدَثَ خَطَأٌ، لَمْ يَعُدْ أَحَدُ الْأَعْضَاءِ مُسَجَّلاً.", show_alert=True)

# =====================================
# التَّشْغِيلُ مَعَ Webhook
# =====================================

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    
    RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
    if RENDER_URL:
        bot.set_webhook(url=f"{RENDER_URL}/{BOT_TOKEN}")
        print(f"Webhook securely set to {RENDER_URL}/{BOT_TOKEN}")
    else:
        print("⚠️ RENDER_EXTERNAL_URL NOT FOUND IN ENV.")

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

