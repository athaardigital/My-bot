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
# Flask & Webhook & Reminders Engine
# =====================================

app = Flask(__name__)

def get_arabic_day_name(weekday_idx):
    days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    return days[weekday_idx]

@app.route("/")
def home():
    return "Bot is running securely on Upstash Redis!", 200

@app.route("/" + BOT_TOKEN, methods=["POST"])
def receive_update():
    json_string = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/check_reminders", methods=["GET", "POST"])
def check_reminders():
    """مَحَرِّكُ التَّنْبِيهَاتِ الْمَجَّانِيِّ الَّذِي يَتِمُّ اسْتِدْعَاؤُهُ عَبْرَ الـ Cron Job"""
    group_ids = redis_client.smembers("active_groups")
    if not group_ids:
        return "No active groups found.", 200

    now = datetime.now()
    current_day_ar = get_arabic_day_name(now.weekday())
    current_date_str = now.strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M")

    for cid in group_ids:
        cid_str = str(cid)
        lessons_data = redis_client.get(f"group:{cid_str}:lessons")
        if not lessons_data:
            continue
            
        lessons = json.loads(lessons_data)
        subs_data = redis_client.get(f"group:{cid_str}:subscribers")
        subs = json.loads(subs_data) if subs_data else []

        updated_lessons = []
        for lesson in lessons:
            is_today = (lesson["day_or_date"] == current_day_ar or lesson["day_or_date"] == current_date_str)
            if is_today:
                try:
                    l_time = datetime.strptime(lesson["time"], "%H:%M")
                    now_time = datetime.strptime(current_time_str, "%H:%M")
                    diff_minutes = (l_time - now_time).total_seconds() / 60

                    trigger_key = f"{current_date_str}_{current_time_str}"
                    if 0 <= diff_minutes <= int(lesson["remind_before"]) and lesson.get("last_triggered") != trigger_key:
                        lesson["last_triggered"] = trigger_key
                        for sub_id in subs:
                            try:
                                bot.send_message(
                                    int(sub_id),
                                    f"🔔 <b>تَذْكِيرٌ بِمَوْعِدِ حِصَّةٍ شَرْعِيَّةٍ!</b>\n\n"
                                    f"📚 <b>الْحِصَّة:</b> {lesson['name']}\n"
                                    f"⏰ <b>الْمَوْعِد:</b> {lesson['time']}\n"
                                    f"🌿 <b>بَقِيَ عَلَى الْحِصَّةِ:</b> {int(diff_minutes)} دَقِيقَة.\n\n"
                                    f"جَهِّزُوا أَنْفُسَكُمْ وَاحْرِصُوا عَلَى الْحُضُورِ نَفَعَ اللَّهُ بِكُمْ.",
                                    parse_mode="HTML"
                                )
                            except:
                                pass
                except Exception as e:
                    print(f"Error checking lesson time: {e}")
            updated_lessons.append(lesson)
        redis_client.set(f"group:{cid_str}:lessons", json.dumps(updated_lessons))

    return "Reminders verified successfully!", 200

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
    extra_state = "🟢 مَسْمُوحَة" if group.get("allow_extra_turns", False) else "🔴 مَمْنُوعَة"

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
        user_counts = {}
        for i, member in enumerate(group["readers"], start=1):
            uid = str(member["id"])
            user_counts[uid] = user_counts.get(uid, 0) + 1
            completed_times = group.get("completed", []).count(uid)
            
            done = " ✅" if user_counts[uid] <= completed_times else ""
            extra_badge = " <b>(إِضَافِيّ)</b>" if member.get("is_extra") else ""
            text += f"{i}. {mention(member['id'], member['name'])}{extra_badge}{done}\n"

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
    text += f"🔒 <b>حَالَةُ الْقَائِمَةِ:</b> {state}\n"
    text += f"🔄 <b>الْأَدْوَارُ الْإِضَافِيَّةُ:</b> {extra_state}"

    return text

# =====================================
# لَوْحَاتُ الْأَزْرَارِ الْمُنَظَّمَةِ
# =====================================

def main_keyboard(chat_id):
    group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    # الصَّفُّ الْأَوَّلُ: تَسْجِيلُ الِاسْمِ وَتَمَّتِ الْقِرَاءَةُ
    keyboard.add(
        types.InlineKeyboardButton("📝 تَسْجِيلُ اسْمِي", callback_data="register_menu"),
        types.InlineKeyboardButton("✅ تَمَّ الْقِرَاءَةُ", callback_data="done")
    )
    
    # الصَّفُّ الثَّانِي: زِرُّ الدَّوْرِ الْإِضَافِيِّ يَظْهَرُ فَقَطْ إِذَا كَانَ مُفَعَّلاً مَعَ زِرِّ الْحَذْفِ[span_2](start_span)[span_2](end_span)
    if group.get("allow_extra_turns", False):
        keyboard.add(
            types.InlineKeyboardButton("➕ تَسْجِيلُ دَوْرٍ إِضَافِيٍّ", callback_data="role_extra"),
            types.InlineKeyboardButton("🗑️ حَذْفُ الِاسْمِ", callback_data="delete")
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton("🗑️ حَذْفُ الِاسْمِ", callback_data="delete")
        )
        
    # زِرُّ تَفْعِيلُ التَّنْبِيهَاتِ (خَاصٌّ عَبْرَ الرَّابِطِ الْعَمِيقِ لِحِفْظِ الْخُصُوصِيَّةِ)[span_3](start_span)[span_3](end_span)
    try:
        bot_username = bot.get_me().username
        keyboard.add(
            types.InlineKeyboardButton("🔔 تَفْعِيلُ التَّنْبِيهَاتِ (خَاص)", url=f"https://t.me/{bot_username}?start=sub_{chat_id}")
        )
    except:
        pass

    # زِرُّ إِعْدَادَاتِ الْإِشْرَافِ (يَظْهَرُ تِلْقَائِيّاً لِلْجَمِيعِ عِنْدَ التَّفْعِيلِ لَكِنَّهُ مَحْمِيٌّ)[span_4](start_span)[span_4](end_span)
    keyboard.add(
        types.InlineKeyboardButton("⚙️ إِعْدَادَاتُ الْإِشْرَافِ", callback_data="settings")
    )

    return keyboard

def register_keyboard(chat_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📖 قَارِئٌ", callback_data="role_reader"),
        types.InlineKeyboardButton("🎧 مُسْتَمِعٌ", callback_data="role_listener")
    )
    keyboard.add(
        types.InlineKeyboardButton("🌿 مُعْتَذِرٌ", callback_data="role_excused"),
        types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْقَائِمَةِ", callback_data="back_to_main")
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
    keyboard.add(types.InlineKeyboardButton("🔔 عَرْضُ الْحِصَصِ الْمُسْجَّلَةِ", callback_data="view_lessons"))
    keyboard.add(types.InlineKeyboardButton("🔄 إِعَادَةُ إِرْسَالِ الْقَائِمَةِ", callback_data="refresh"))
    keyboard.add(types.InlineKeyboardButton("📢 الْمُنَادَاةُ", callback_data="call"))
    keyboard.add(types.InlineKeyboardButton("🔄 إِعَادَةُ ضَبْطِ الْقَائِمَةِ", callback_data="reset"))
    keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْمَجْلِسِ", callback_data="back_to_main"))

    return keyboard

# =====================================
# تَحْدِيثُ اللَّوْحَةِ
# =====================================

def update_board(chat_id):
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
            reply_markup=main_keyboard(chat_id)
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

def show_manage_roles(call, chat_id, group):
    if not group.get("readers"):
        bot.answer_callback_query(call.id, "⚠️ لَا يُوجَدُ قُرَّاءٌ مُسَجَّلُونَ حَالِيّاً.", show_alert=True)
        return

    keyboard = types.InlineKeyboardMarkup(row_width=1)
    for i, r in enumerate(group["readers"]):
        extra_badge = " (إِضَافِيّ)" if r.get("is_extra") else ""
        keyboard.add(types.InlineKeyboardButton(f"{i+1}. {r['name']}{extra_badge}", callback_data=f"edit_turn:{i}"))
    keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْإِعْدَادَاتِ", callback_data="settings"))

    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text="🔄 <b>اخْتَرْ أَحَدَ الْأَدْوَارِ لِتَعْدِيلِهِ أَوْ تَبْدِيلِهِ:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# =====================================
# أَمْرُ الِابْتِدَاءِ (start) وَالْحِصَصِ
# =====================================

@bot.message_handler(commands=["start"])
def start(message):
    if message.chat.type == "private":
        args = message.text.split()
        if len(args) > 1 and args[1].startswith("sub_"):
            target_chat_id = args[1].replace("sub_", "")
            subs_data = redis_client.get(f"group:{target_chat_id}:subscribers")
            subs = json.loads(subs_data) if subs_data else []
            
            if str(message.from_user.id) not in subs:
                subs.append(str(message.from_user.id))
                redis_client.set(f"group:{target_chat_id}:subscribers", json.dumps(subs))
                redis_client.sadd("active_groups", target_chat_id)
            
            bot.send_message(
                message.chat.id,
                "✅ <b>تَمَّ تفعيلُ التَّنْبِيهَاتِ بِنَجَاحٍ!</b>\n\n"
                "سَتَصِلُكَ تَنْبِيهَاتُ الْحِصَصِ لِهَذَا الْمَجْلِسِ هُنَا فِي الْخَاصِّ تِلْقَائِيّاً 🌿.",
                parse_mode="HTML"
            )
            return

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
        reply_markup=main_keyboard(message.chat.id)
    )

    group["message_id"] = sent.message_id
    save_group(chat_id, group)
    redis_client.sadd("active_groups", chat_id)

@bot.message_handler(commands=["lesson"])
def add_lesson(message):
    if message.chat.type == "private":
        bot.send_message(message.chat.id, "⚠️ هَذَا الْأَمْرُ يُسْتَخْدَمُ دَاخِلَ الْمَجْمُوعَةِ لِتَحْدِيدِ حِصَصِهَا.")
        return
        
    chat_id = str(message.chat.id)
    if not is_admin(message.from_user.id, chat_id):
        bot.send_message(message.chat.id, "❌ عُذْراً! هَذَا الْأَمْرُ مَخْصُوصٌ لِلْمُشْرِفِينَ فَقَطْ.")
        return
        
    text = message.text.replace("/lesson", "").strip()
    if not text:
        bot.send_message(
            message.chat.id,
            "ℹ️ <b>طَرِيقَةُ إِضَافَةِ حِصَّةٍ شَرْعِيَّةٍ جَدِيدَةٍ:</b>\n\n"
            "<code>/lesson اسم الحصة | اليوم أو التاريخ | الوقت | دقائق التذكير</code>\n\n"
            "<b>أَمْثِلَة:</b>\n"
            "<code>/lesson مجلس التفسير | الأحد | 18:00 | 30</code>\n"
            "<code>/lesson مراجعة المتون | 2026-07-05 | 15:30 | 15</code>",
            parse_mode="HTML"
        )
        return
        
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 4:
        bot.send_message(message.chat.id, "⚠️ عُذْراً، يَجِبُ مَلْءُ جَمِيعِ الْحُقُولِ وبِفَاصِلِ الْخَطِّ ( | ).")
        return
        
    name, day_or_date, l_time, remind_before = parts[0], parts[1], parts[2], parts[3]
    
    try:
        datetime.strptime(l_time, "%H:%M")
    except:
        bot.send_message(message.chat.id, "⚠️ خَطَأٌ فِي تَنْسِيقِ الْوَقْتِ! يَجِبُ أَنْ يَكُونَ مِثْلَ: 18:00")
        return
        
    new_lesson = {
        "name": name,
        "day_or_date": day_or_date,
        "time": l_time,
        "remind_before": remind_before,
        "last_triggered": ""
    }
    
    lessons_data = redis_client.get(f"group:{chat_id}:lessons")
    lessons = json.loads(lessons_data) if lessons_data else []
    lessons.append(new_lesson)
    
    redis_client.set(f"group:{chat_id}:lessons", json.dumps(lessons))
    redis_client.sadd("active_groups", chat_id)
    
    bot.send_message(
        message.chat.id,
        f"✅ <b>تَمَّتْ إِضَافَةُ الْحِصَّةِ بِنَجَاحٍ!</b>\n\n"
        f"📚 <b>الْحِصَّة:</b> {name}\n"
        f"📅 <b>الْمَوْعِد:</b> {day_or_date} عِنْدَ {l_time}\n"
        f"🔔 <b>التَّذْكِير:</b> قَبْلَهَا بِـ {remind_before} دَقِيقَة.",
        parse_mode="HTML"
    )

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

    # حِمَايَةُ أَزْرَارِ الْمُشْرِفِينَ دَاخِلَ الْمَجْمُوعَةِ[span_5](start_span)[span_5](end_span)
    admin_callbacks = ["settings", "toggle", "toggle_extra", "manage_roles", "stats", "refresh", "reset", "call", "view_lessons"]
    if call.data in admin_callbacks or call.data.startswith(("edit_turn:", "move_up:", "move_down:", "swap_turn:", "doswap:")):
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
            reply_markup=register_keyboard(chat_id)
        )
        bot.answer_callback_query(call.id)
        return

    elif call.data == "back_to_main":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=make_board(chat_id),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=main_keyboard(chat_id)
        )
        bot.answer_callback_query(call.id)
        return

    elif call.data == "role_reader":
        if not group.get("list_open", False):
            bot.answer_callback_query(call.id, "❌ الْقَائِمَةُ مُغْلَقَةٌ حَالِيّاً! لَا يُمْكِنُ التَّسْجِيلُ.", show_alert=True)
            return

        registered_times = len([x for x in group.get("readers", []) if str(x["id"]) == user_id_str])
        if registered_times > 0:
            bot.answer_callback_query(call.id, "⚠️ أَنْتَ مُسَجَّلٌ بِالْفِعْلِ كَقَارِئٍ!", show_alert=True)
            return

        remove_member(group, user.id)
        member["is_extra"] = False
        
        insert_index = len(group.get("readers", []))
        for i, r in enumerate(group.get("readers", [])):
            if r.get("is_extra", False):
                insert_index = i
                break
                
        group["readers"].insert(insert_index, member)
        save_group(chat_id, group)
        update_board(chat_id)
        bot.answer_callback_query(call.id, "✅ تَمَّ تَسْجِيلُكَ كَقَارِئٍ.", show_alert=True)

    elif call.data == "role_extra":
        if not group.get("allow_extra_turns", False):
            bot.answer_callback_query(call.id, "❌ الْأَدْوَارُ الْإِضَافِيَّةُ مُغْلَقَةٌ حَالِيّاً!", show_alert=True)
            return
        
        registered_times = len([x for x in group.get("readers", []) if str(x["id"]) == user_id_str])
        completed_times = group.get("completed", []).count(user_id_str)

        if registered_times == 0:
            bot.answer_callback_query(call.id, "⚠️ يَجِبُ أَنْ تُسَجِّلَ دَوْراً أَسَاسِيّاً أَوَّلاً!", show_alert=True)
            return
        
        if completed_times < registered_times:
            bot.answer_callback_query(call.id, "⚠️ لَا يُمْكِنُكَ طَلَبُ دَوْرٍ إِضَافِيٍّ حَتَّى تُتِمَّ دَوْرَكَ الْحَالِيَّ!", show_alert=True)
            return
        
        member["is_extra"] = True
        group["readers"].append(member)
        save_group(chat_id, group)
        update_board(chat_id)
        bot.answer_callback_query(call.id, "✅ تَمَّ تَسْجِيلُ دَوْرٍ إِضَافِيٍّ لَكَ.", show_alert=True)

    elif call.data == "role_listener":
        remove_member(group, user.id)
        group["listeners"].append(member)
        save_group(chat_id, group)
        update_board(chat_id)
        bot.answer_callback_query(call.id, "🎧 تَمَّ تَسْجِيلُكَ كَمُسْتَمِعٍ.")

    elif call.data == "role_excused":
        remove_member(group, user.id)
        group["excused"].append(member)
        save_group(chat_id, group)
        update_board(chat_id)
        bot.answer_callback_query(call.id, "🌿 تَمَّ تَسْجِيلُ اعْتِذَارِكَ.")

    elif call.data == "delete":
        remove_member(group, user.id)
        save_group(chat_id, group)
        update_board(chat_id)
        bot.answer_callback_query(call.id, "🗑️ تَمَّ حَذْفُ اسْمِكَ.", show_alert=True)

    elif call.data == "done":
        registered_times = len([x for x in group.get("readers", []) if str(x["id"]) == user_id_str])
        completed_times = group.get("completed", []).count(user_id_str)

        if registered_times == 0:
            bot.answer_callback_query(call.id, "⚠️ يَجِبُ أَنْ تَكُونَ مُسَجَّلاً فِي الْقُرَّاءِ أَوَّلاً!", show_alert=True)
            return

        if completed_times < registered_times:
            group["completed"].append(user_id_str)
            save_group(chat_id, group)
            update_board(chat_id)
            bot.answer_callback_query(call.id, "✅ هَنِيئاً لَكَ إِتْمَامُ الْقِرَاءَةِ!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "ℹ️ لَقَدْ أَكَّدْتَ الْقِرَاءَةَ لِجَمِيعِ أَدْوَارِكَ مُسْبَقاً.", show_alert=True)

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
        update_board(chat_id)
        bot.answer_callback_query(call.id, "🔄 تَمَّ تَعْدِيلُ حَالَةِ الْقَائِمَةِ.")

    elif call.data == "toggle_extra":
        group["allow_extra_turns"] = not group.get("allow_extra_turns", False)
        save_group(chat_id, group)
        update_board(chat_id)
        bot.answer_callback_query(call.id, "🔄 تَمَّ تَعْدِيلُ حَالَةِ الْأَدْوَارِ الْإِضَافِيَّةِ.")

    elif call.data == "refresh":
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        sent = bot.send_message(chat_id, make_board(chat_id), parse_mode="HTML", reply_markup=main_keyboard(chat_id))
        group["message_id"] = sent.message_id
        save_group(chat_id, group)
        bot.answer_callback_query(call.id, "🔄 تَمَّتْ إِعَادَةُ إِرْسَالِ الْقَائِمَةِ.")

    elif call.data == "stats":
        readers = group.get("readers", [])
        stats_text = "📊 <b>إِحْصَائِيَّاتُ الْمَجْلِسِ النِّهَائِيَّةِ</b> 📊\n\n"
        for i, m in enumerate(readers, start=1):
            status = "✅" if group.get("completed", []).count(str(m["id"])) > 0 else "❌"
            extra_badge = " (إِضَافِيّ)" if m.get("is_extra") else ""
            stats_text += f"{i}. {m['name']}{extra_badge} {status}\n"
        bot.send_message(chat_id, stats_text, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    elif call.data == "view_lessons":
        lessons_data = redis_client.get(f"group:{chat_id}:lessons")
        lessons = json.loads(lessons_data) if lessons_data else []
        txt = "🔔 <b>حِصَصُ الْمَجْلِسِ الْمُسْجَّلَةِ:</b>\n\n"
        if not lessons: txt += "لَا يُوجَدُ حِصَصٌ حَالِيّاً."
        for i, l in enumerate(lessons, start=1):
            txt += f"{i}. {l['name']} | 📅 {l['day_or_date']} | ⏰ {l['time']} (تَنْبِيه {l['remind_before']} د)\n"
        bot.send_message(chat_id, txt, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    elif call.data == "reset":
        old_message = group.get("message_id")
        group = default_group()
        group["message_id"] = old_message
        save_group(chat_id, group)
        update_board(chat_id)
        bot.answer_callback_query(call.id, "🔄 تَمَّتْ إِعَادَةُ ضَبْطِ الْمَجْلِسِ تَمَاماً.", show_alert=True)

    elif call.data == "call":
        all_members = group.get("readers", []) + group.get("listeners", []) + group.get("excused", [])
        for mem in all_members:
            try: bot.send_message(int(mem["id"]), "هَلُمُّوا لِمَجْلِسٍ تَحُفُّهُ الْمَلَائِكَةُ 🌿")
            except: pass
        bot.answer_callback_query(call.id, "📢 تَمَّ إِرْسَالُ النِّدَاءِ لِلْجَمِيعِ.", show_alert=True)

    elif call.data == "manage_roles":
        show_manage_roles(call, chat_id, group)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("edit_turn:"):
        idx = int(call.data.split(":")[1])
        if idx >= len(group.get("readers", [])):
            bot.answer_callback_query(call.id, "⚠️ الدَّوْرُ لَمْ يَعُدْ مُسَجَّلاً.", show_alert=True)
            return
            
        target_name = group["readers"][idx]["name"]
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("تَقْدِيمٌ ⬆️", callback_data=f"move_up:{idx}"),
            types.InlineKeyboardButton("تَأْخِيرٌ ⬇️", callback_data=f"move_down:{idx}")
        )
        keyboard.add(types.InlineKeyboardButton("تَبْدِيلٌ مَعَهُ 🔄", callback_data=f"swap_turn:{idx}"))
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْقَائِمَة", callback_data="manage_roles"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"⚙️ <b>تَعْدِيلُ دَوْرِ رَقْم ({idx+1}):</b> {target_name}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)

    elif call.data.startswith("move_up:"):
        idx = int(call.data.split(":")[1])
        readers = group.get("readers", [])
        if idx > 0 and idx < len(readers):
            readers[idx], readers[idx - 1] = readers[idx - 1], readers[idx]
            save_group(chat_id, group)
            bot.answer_callback_query(call.id, "✅ تَمَّ تَقْدِيمُ الدَّوْرِ.", show_alert=True)
            show_manage_roles(call, chat_id, group)
        else:
            bot.answer_callback_query(call.id, "⚠️ الدَّوْرُ فِي بِدَايَةِ الْقَائِمَةِ!", show_alert=True)

    elif call.data.startswith("move_down:"):
        idx = int(call.data.split(":")[1])
        readers = group.get("readers", [])
        if idx >= 0 and idx < len(readers) - 1:
            readers[idx], readers[idx + 1] = readers[idx + 1], readers[idx]
            save_group(chat_id, group)
            bot.answer_callback_query(call.id, "✅ تَمَّ تَأْخِيرُ الدَّوْرِ.", show_alert=True)
            show_manage_roles(call, chat_id, group)
        else:
            bot.answer_callback_query(call.id, "⚠️ الدَّوْرُ فِي نِهَايَةِ الْقَائِمَةِ!", show_alert=True)

    elif call.data.startswith("swap_turn:"):
        idx = int(call.data.split(":")[1])
        target_name = group["readers"][idx]["name"]
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for i, r in enumerate(group["readers"]):
            if i != idx:
                keyboard.add(types.InlineKeyboardButton(f"تَبْدِيلٌ مَعَ: {i+1}. {r['name']}", callback_data=f"doswap:{idx}:{i}"))
        keyboard.add(types.InlineKeyboardButton("🔙 إِلْغَاءٌ", callback_data=f"edit_turn:{idx}"))

        bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text=f"🔄 <b>اخْتَرْ دَوْراً لِتَبْدِيلِ الْمَرَاكِزِ مَعَ ({target_name}):</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        bot.answer_callback_query(call.id)

    elif call.data.startswith("doswap:"):
        idx1 = int(call.data.split(":")[1])
        idx2 = int(call.data.split(":")[2])
        readers = group.get("readers", [])
        if idx1 < len(readers) and idx2 < len(readers):
            readers[idx1], readers[idx2] = readers[idx2], readers[idx1]
            save_group(chat_id, group)
            bot.answer_callback_query(call.id, "✅ تَمَّ تَبْدِيلُ الْأَدْوَارِ.", show_alert=True)
            show_manage_roles(call, chat_id, group)

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
