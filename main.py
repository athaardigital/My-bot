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
            recurrence = lesson.get("recurrence", "مرة واحدة").strip()
            day_or_date = lesson.get("day_or_date", "").strip()

            is_today = False
            if recurrence == "يوميا":
                is_today = True
            elif recurrence == "أسبوعيا":
                if day_or_date == current_day_ar:
                    is_today = True
                else:
                    try:
                        dt = datetime.strptime(day_or_date, "%Y-%m-%d")
                        if dt.weekday() == now.weekday():
                            is_today = True
                    except:
                        pass
            else:
                if day_or_date == current_date_str or day_or_date == current_day_ar:
                    is_today = True

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
        "list_open": True,  
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
# الصَّلَاحِيَّاتُ (تَمَّ التَّعْدِيلُ وَالْإِحْكَامُ هُنَا)
# =====================================

def is_admin(user_id, chat_id):
    # إِذَا كَانَ الْمُسْتَخْدِمُ مَشْرِفاً مَخْفِيّاً (Anonymous Bot ID) يُعْتَبَرُ مُشْرِفاً تِلْقَائِيّاً
    if str(user_id) == "1087968824":
        return True
    try:
        member = bot.get_chat_member(int(chat_id), int(user_id))
        # التَّحَقُّقُ مِنْ جَمِيعِ صِيَغِ الْمُشْرِفِ وَالْمَالِكِ لِضَمَانِ التَّعَرُّفِ الْكَامِلِ
        if member.status in ["administrator", "creator", "owner"]:
            return True
        if type(member).__name__ in ["ChatMemberOwner", "ChatMemberAdministrator"]:
            return True
        return False
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
    if not group:
        return "⚠️ هَذَا الْمَجْلِسُ لَمْ يَعُدْ مُفَعَّلاً كُلِّيّاً."
    
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
        "<b>قَائِمَةُ تِلَاوَةِ الْقُرْآنِ الْكَرِيمِ لِلْمَجْلِسِ الْحَالِيِّ</b>\n\n"
    )

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

    text += "━━━━━━━━━━━━━━━\n"
    text += f"🎧 <b>الْـمُسْتَمِعُونَ</b> ({len(group.get('listeners', []))})\n\n"

    if not group.get("listeners"):
        text += "لَا يُوجَدُ حَالِيّاً.\n"
    else:
        for i, member in enumerate(group["listeners"], start=1):
            text += f"{i}. {mention(member['id'], member['name'])}\n"

    text += "\n"

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
# اللَّوْحَاتُ وَالْأَزْرَارُ
# =====================================

def main_keyboard(chat_id):
    group = get_group(chat_id)
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        types.InlineKeyboardButton("📝 تَسْجِيلُ اسْمِي", callback_data="register_menu"),
        types.InlineKeyboardButton("✅ تَمَّ الْقِرَاءَةُ", callback_data="done")
    )
    
    if group.get("allow_extra_turns", False):
        keyboard.add(
            types.InlineKeyboardButton("➕ تَسْجِيلُ دَوْرٍ إِضَافِيٍّ", callback_data="role_extra"),
            types.InlineKeyboardButton("🗑️ حَذْفُ الِاسْمِ", callback_data="delete")
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton("🗑️ حَذْفُ الِاسْمِ", callback_data="delete")
        )
        
    try:
        bot_username = bot.get_me().username
        keyboard.add(
            types.InlineKeyboardButton("🔔 تَفْعِيلُ التَّنْبِيهَاتِ (خَاص)", url=f"https://t.me/{bot_username}?start=sub_{chat_id}")
        )
    except:
        pass

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
    keyboard.add(types.InlineKeyboardButton("🔔 الْحِصَص", callback_data="manage_lessons"))
    keyboard.add(types.InlineKeyboardButton("🔄 إِرْسَالُ آخِرِ قَائِمَةٍ", callback_data="refresh"))  
    keyboard.add(types.InlineKeyboardButton("📢 الْمُنَادَاةُ", callback_data="call"))
    keyboard.add(types.InlineKeyboardButton("🔄 تَصْفِيرُ الْقَائِمَةِ", callback_data="reset"))  
    keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْمَجْلِسِ", callback_data="back_to_main"))

    return keyboard

# =====================================
# تَحْدِيثُ اللَّوْحَةِ
# =====================================

def update_board(chat_id):
    group = get_group(chat_id)
    if not group or not group.get("message_id"):
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
            
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton("✅ نَعَمْ، أُوَافِقُ وَأُرِيدُ التَّنْبِيهَاتِ", callback_data=f"confsub:{target_chat_id}"),
                types.InlineKeyboardButton("❌ لَا، لَا أُرِيدُ التَّلَقِّي", callback_data="cancel_sub")
            )
            bot.send_message(
                message.chat.id,
                "🌿 <b>تَفْعِيلُ تَنْبِيهَاتِ وَتَذْكِيرَاتِ الْمَجَالِسِ:</b>\n\n"
                "هَلْ تُوَافِقُ عَلَى تَلَقِّي تَنْبِيهَاتِ الْحِصَصِ الشَّرْعِيَّةِ وَالتَّحْدِيثَاتِ "
                "الْخَاصَّةِ بِهَذَا الْمَجْلِسِ مُبَاشَرَةً هُنَا فِي الْخَاصِّ؟",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            return

        bot.send_message(
            message.chat.id,
            "السَّلَامُ عَلَيْكُمْ وَرَحْمَةُ اللَّهِ وَبَرَكَاتُهُ\n\nحَيَّاكُمُ اللَّهُ فِي بُوتِ مَجَالِسِ الْعِلْم.\n\n"
            "📢 <b>تَنْبِيه:</b> يُمْكِنُكَ الِاشْتِرَاكُ فِي نِظَامِ التَّذْكِيرِ لِأَيِّ مَجْلِسٍ تَنْتَمِي إِلَيْهِ "
            "عَبْرَ الضَّغْطِ عَلَى زِرِّ (تَفْعِيلُ التَّنْبِيهَاتِ) دَاخِلَ الْمَجْمُوعَةِ وَالْمُوَافَقَةِ هُنَا.\n\n"
            "انْشُرُوا الْبُوتَ فَضْلاً فَهُوَ صَدَقَةٌ عَنِّي وَعَنْ وَالِدَيَّ وَمَقْرَأَتِنَا وَكُلِّ الْمُسْلِمِينَ وَالْمُسْلِمَاتِ."
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
        
    text = message.text.strip()
    
    if "|" in text:
        parts = [p.strip() for p in text.replace("/lesson", "").split("|") if p.strip()]
    else:
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if lines and lines[0].startswith("/lesson"):
            parts = lines[1:]
        else:
            parts = lines

    if not parts:
        bot.send_message(
            message.chat.id,
            "ℹ️ <b>طَرِيقَةُ إِضَافَةِ حِصَّةٍ شَرْعِيَّةٍ (سَطْراً بِسَطْراً):</b>\n\n"
            "<code>/lesson</code>\n"
            "<code>اسم الحصة</code>\n"
            "<code>اليوم أو التاريخ (مثال: 2026-06-30)</code>\n"
            "<code>الوقت (مثال: 15:00)</code>\n"
            "<code>دقائق التذكير (مثال: 15)</code>\n"
            "<code>التكرار (مرة واحدة | يوميا | أسبوعيا)</code>",
            parse_mode="HTML"
        )
        return
        
    if len(parts) < 4:
        bot.send_message(message.chat.id, "⚠️ عُذْراً، يَجِبُ مَلْءُ 4 حُقُولٍ عَلَى الْأَقَلِّ (الِاسْمُ، التَّارِيخُ، الْوَقْتُ، التَّذْكِيرُ).")
        return
        
    name = parts[0]
    raw_date = parts[1]
    l_time = parts[2].replace(" ", "")
    remind_before = parts[3].replace(" ", "")
    recurrence = parts[4].strip() if len(parts) > 4 else "مرة واحدة"
    
    if "يوم" in recurrence:
        recurrence = "يوميا"
    elif "أسبوع" in recurrence or "اسبوع" in recurrence:
        recurrence = "أسبوعيا"
    else:
        recurrence = "مرة واحدة"

    day_or_date = raw_date
    for sep in ["-", "/"]:
        if sep in raw_date:
            date_parts = [dp.strip() for dp in raw_date.split(sep) if dp.strip()]
            if len(date_parts) == 3:
                try:
                    y = date_parts[0]
                    m = date_parts[1].zfill(2)
                    d = date_parts[2].zfill(2)
                    if len(y) == 4:
                        day_or_date = f"{y}-{m}-{d}"
                    elif len(d) == 4:
                        day_or_date = f"{d}-{m}-{y}"
                except:
                    pass

    try:
        datetime.strptime(l_time, "%H:%M")
    except:
        bot.send_message(message.chat.id, "⚠️ خَطَأٌ فِي تَنْسِيقِ الْوَقْتِ! يَجِبُ أَنْ يَكُونَ مِثْلَ: 15:00")
        return
        
    new_lesson = {
        "name": name,
        "day_or_date": day_or_date,
        "time": l_time,
        "remind_before": remind_before,
        "recurrence": recurrence,
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
        f"🔔 <b>التَّذْكِير:</b> قَبْلَهَا بِـ {remind_before} دَقِيقَة.\n"
        f"🔄 <b>التَّكْرَار:</b> {recurrence}",
        parse_mode="HTML"
    )

# =====================================
# مَعَالِجُ التَّفَاعُلِ مَعَ الْأَزْرَارِ
# =====================================

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    if call.data.startswith("confsub:"):
        target_chat_id = call.data.split(":")[1]
        subs_data = redis_client.get(f"group:{target_chat_id}:subscribers")
        subs = json.loads(subs_data) if subs_data else []
        
        if str(call.from_user.id) not in subs:
            subs.append(str(call.from_user.id))
            redis_client.set(f"group:{target_chat_id}:subscribers", json.dumps(subs))
            redis_client.sadd("active_groups", target_chat_id)
        
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="✅ <b>تَمَّتِ الْمُوَافَقَةُ وَتَفْعِيلُ التَّنْبِيهَاتِ بِنَجَاحٍ!</b>\n\n"
                     "سَتَصِلُكَ تَنْبِيهَاتُ هَذَا الْمَجْلِسِ هُنَا تِلْقَائِيّاً 🌿.",
                parse_mode="HTML"
            )
        except:
            pass
        bot.answer_callback_query(call.id)
        return

    if call.data == "cancel_sub":
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="❌ <b>تَمَّ إِلْغَاءُ الْعَمَلِيَّةِ وَلَنْ تَتَلَقَّى أَيَّ تَنْبِيهَاتٍ.</b>",
                parse_mode="HTML"
            )
        except:
            pass
        bot.answer_callback_query(call.id)
        return

    chat_id = call.message.chat.id
    group = get_group(chat_id)
    user = call.from_user

    full_name = user.first_name or "مُسْتَخْدِمٌ"
    if user.last_name:
        full_name += f" {user.last_name}"

    member = {"id": str(user.id), "name": full_name}
    user_id_str = str(user.id)

    admin_callbacks = [
        "settings", "toggle", "toggle_extra", "manage_roles", "stats", "refresh", 
        "reset", "call", "view_lessons", "delete_group_all", "manage_lessons", 
        "lessons_delete_menu", "delete_specific_lesson_menu", "delete_all_lessons", "lessons_add_info"
    ]
    if call.data in admin_callbacks or call.data.startswith(("edit_turn:", "move_up:", "move_down:", "swap_turn:", "doswap:", "del_lesson:")):
        if not is_admin(user.id, chat_id):
            bot.answer_callback_query(call.id, "❌ عُذْراً! هَذِهِ الْإِعْدَادَاتُ مَحْصُورَةٌ لِلْمُشْرِفِينَ فَقَطْ.", show_alert=True)
            return

    if call.data == "register_menu":
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=register_keyboard(chat_id))
        bot.answer_callback_query(call.id)
        return

    elif call.data == "back_to_main":
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=make_board(chat_id), parse_mode="HTML", disable_web_page_preview=True, reply_markup=main_keyboard(chat_id))
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
        bot.edit_message_reply_markup(chat_id=chat_id, message_id=call.message.message_id, reply_markup=settings_keyboard(chat_id))
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
        bot.answer_callback_query(call.id, "🔄 تَمَّ إِرْسَالُ آخِرِ قَائِمَةٍ.", show_alert=True)

    elif call.data == "stats":
        readers = group.get("readers", [])
        stats_text = "📊 <b>إِحْصَائِيَّاتُ الْمَجْلِسِ النِّهَائِيَّةِ</b> 📊\n\n"
        for i, m in enumerate(readers, start=1):
            status = "✅" if group.get("completed", []).count(str(m["id"])) > 0 else "❌"
            extra_badge = " (إِضَافِيّ)" if m.get("is_extra") else ""
            stats_text += f"{i}. {m['name']}{extra_badge} {status}\n"
        bot.send_message(chat_id, stats_text, parse_mode="HTML")
        bot.answer_callback_query(call.id)

    elif call.data == "manage_lessons":
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("📊 عَرْضُ الْمَجَالِسِ الْحَالِيَّةِ", callback_data="view_lessons"),
            types.InlineKeyboardButton("🗑️ حَذْفٌ", callback_data="lessons_delete_menu"),
            types.InlineKeyboardButton("➕ إِضَافَةُ مَجْلِسٍ", callback_data="lessons_add_info"),
            types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْإِعْدَادَاتِ", callback_data="settings")
        )
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🔔 <b>إِدَارَةُ مَجَالِسِ وَحِصَصِ الْمَجْمُوعَةِ:</b>", parse_mode="HTML", reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    elif call.data == "view_lessons":
        lessons_data = redis_client.get(f"group:{chat_id}:lessons")
        lessons = json.loads(lessons_data) if lessons_data else []
        txt = "🔔 <b>الْمَجَالِسُ وَالْحِصَصُ الْحَالِيَّةُ الْمُسَجَّلَةُ:</b>\n\n"
        if not lessons:
            txt += "لَا يُوجَدُ مَجَالِسُ مُسَجَّلَةٌ حَالِيّاً."
        for i, l in enumerate(lessons, start=1):
            rec = l.get("recurrence", "مرة واحدة")
            txt += f"{i}. {l['name']} | 📅 {l['day_or_date']} | ⏰ {l['time']} ({rec})\n"
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ", callback_data="manage_lessons"))
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=txt, parse_mode="HTML", reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    elif call.data == "lessons_delete_menu":
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("❌ حَذْفُ مَجْلِسٍ مَا", callback_data="delete_specific_lesson_menu"),
            types.InlineKeyboardButton("🔥 حَذْفُ الْجَمِيعِ", callback_data="delete_all_lessons"),
            types.InlineKeyboardButton("🔙 عَوْدَةٌ", callback_data="manage_lessons")
        )
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🗑️ <b>اخْتَرْ خِيَارَ الْحَذْفِ الْمَطْلُوبِ:</b>", parse_mode="HTML", reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    elif call.data == "delete_specific_lesson_menu":
        lessons_data = redis_client.get(f"group:{chat_id}:lessons")
        lessons = json.loads(lessons_data) if lessons_data else []
        if not lessons:
            bot.answer_callback_query(call.id, "⚠️ لَا يُوجَدُ مَجَالِسُ لِحَذْفِهَا!", show_alert=True)
            return
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        for i, l in enumerate(lessons):
            keyboard.add(types.InlineKeyboardButton(f"{i+1}. {l['name']}", callback_data=f"del_lesson:{i}"))
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ", callback_data="lessons_delete_menu"))
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="❌ <b>اخْتَرْ الْمَجْلِسَ الَّذِي تُرِيدُ حَذْفَهُ مِنَ الْقَائِمَةِ:</b>", parse_mode="HTML", reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    elif call.data.startswith("del_lesson:"):
        idx = int(call.data.split(":")[1])
        lessons_data = redis_client.get(f"group:{chat_id}:lessons")
        lessons = json.loads(lessons_data) if lessons_data else []
        if idx < len(lessons):
            removed_name = lessons[idx]['name']
            lessons.pop(idx)
            redis_client.set(f"group:{chat_id}:lessons", json.dumps(lessons))
            bot.answer_callback_query(call.id, f"✅ تَمَّ حَذْفُ مَجْلِسِ ({removed_name}) بِنَجَاحٍ.", show_alert=True)
            if lessons:
                keyboard = types.InlineKeyboardMarkup(row_width=1)
                for i, l in enumerate(lessons):
                    keyboard.add(types.InlineKeyboardButton(f"{i+1}. {l['name']}", callback_data=f"del_lesson:{i}"))
                keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ", callback_data="lessons_delete_menu"))
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="❌ <b>اخْتَرْ الْمَجْلِسَ الَّذِي تُرِيدُ حَذْفَهُ مِنَ الْقَائِمَةِ:</b>", parse_mode="HTML", reply_markup=keyboard)
            else:
                keyboard = types.InlineKeyboardMarkup(row_width=1)
                keyboard.add(
                    types.InlineKeyboardButton("📊 عَرْضُ الْمَجَالِسِ الْحَالِيَّةِ", callback_data="view_lessons"),
                    types.InlineKeyboardButton("🗑️ حَذْفٌ", callback_data="lessons_delete_menu"),
                    types.InlineKeyboardButton("➕ إِضَافَةُ مَجْلِسٍ", callback_data="lessons_add_info"),
                    types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْإِعْدَادَاتِ", callback_data="settings")
                )
                bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🔔 <b>إِدَارَةُ مَجَالِسِ وَحِصَصِ الْمَجْمُوعَةِ:</b>", parse_mode="HTML", reply_markup=keyboard)
        else:
            bot.answer_callback_query(call.id, "⚠️ هَذَا الْمَجْلِسُ لَمْ يَعُدْ مَوْجُوداً.", show_alert=True)

    elif call.data == "delete_all_lessons":
        redis_client.set(f"group:{chat_id}:lessons", json.dumps([]))
        bot.answer_callback_query(call.id, "🔥 تَمَّ حَذْفُ جَمِيعِ الْمَجَالِسِ وَالْحِصَصِ نِهَائِيّاً.", show_alert=True)
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            types.InlineKeyboardButton("📊 عَرْضُ الْمَجَالِسِ الْحَالِيَّةِ", callback_data="view_lessons"),
            types.InlineKeyboardButton("🗑️ حَذْفٌ", callback_data="lessons_delete_menu"),
            types.InlineKeyboardButton("➕ إِضَافَةُ مَجْلِسٍ", callback_data="lessons_add_info"),
            types.InlineKeyboardButton("🔙 عَوْدَةٌ لِلْإِعْدَادَاتِ", callback_data="settings")
        )
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🔔 <b>إِدَارَةُ مَجَالِسِ وَحِصَصِ الْمَجْمُوعَةِ:</b>", parse_mode="HTML", reply_markup=keyboard)

    elif call.data == "lessons_add_info":
        form_text = (
            "➕ <b>إِسْتِمَارَةُ جَدْوَلَةِ مَجْلِسٍ جَدِيدٍ:</b>\n\n"
            "لِإِضَافَةِ مَجْلِسٍ، قُمْ بِنَسْخِ الِاسْتِمَارَةِ أَدْنَاهُ وَمَلْءِ بَيَانَاتِهَا ثُمَّ أَرْسِلْهَا كَرِسَالَةٍ عادِيَّةٍ دَاخِلَ الْمَجْمُوعَةِ:\n\n"
            "<code>/lesson</code>\n"
            "<code>اِسْمُ الْمَجْلِسِ</code>\n"
            "<code>الْيَوْمُ أَوْ التَّارِيخُ (مِثَال: 2026-06-30 أَوْ الْجُمُعَة)</code>\n"
            "<code>الْوَقْتُ (بِتَنْسِيقِ 24 سَاعَة مِثَال: 15:30)</code>\n"
            "<code>دَقَائِقُ التَّنْبِيهِ قَبْلَ الْمَوْعِدِ (مِثَال: 15)</code>\n"
            "<code>التَّكْرَارُ (مرة واحدة | يوميا | أسبوعيا)</code>"
        )
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🔙 عَوْدَةٌ", callback_data="manage_lessons"))
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=form_text, parse_mode="HTML", reply_markup=keyboard)
        bot.answer_callback_query(call.id)

    elif call.data == "reset":
        old_message = group.get("message_id")
        group = default_group()
        group["message_id"] = old_message
        save_group(chat_id, group)
        update_board(chat_id)
        bot.answer_callback_query(call.id, "🔄 تَمَّ تَصْفِيرُ الْقَائِمَةِ تَمَاماً.", show_alert=True)

    elif call.data == "delete_group_all":
        redis_client.srem("active_groups", str(chat_id))
        redis_client.delete(f"group:{chat_id}")
        redis_client.delete(f"group:{chat_id}:lessons")
        redis_client.delete(f"group:{chat_id}:subscribers")
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=call.message.message_id,
                text="🗑️ <b>تَمَّ حَذْفُ هَذَا الْمَجْلِسِ كُلِّيّاً مِنَ النِّظَامِ.</b>",
                parse_mode="HTML"
            )
        except:
            pass
        bot.answer_callback_query(call.id, "✅ تم حذف المجلس وإلغاء التنبيهات نهائياً.", show_alert=True)

    elif call.data == "call":
        subs_data = redis_client.get(f"group:{chat_id}:subscribers")
        subs = json.loads(subs_data) if subs_data else []
        
        if not subs:
            bot.answer_callback_query(call.id, "⚠️ لَا يُوجَدُ مُشْتَرِكُونَ نَشِطُونَ فِي تَنْبِيهَاتِ هَذِهِ الْمَجْمُوعَةِ حَالِيّاً.", show_alert=True)
            return

        for sub_id in subs:
            try: 
                bot.send_message(int(sub_id), "هَلُمُّوا لِمَجْلِسٍ تَحُفُّهُ الْمَلَائِكَةُ 🌿")
            except: 
                pass
        bot.answer_callback_query(call.id, "📢 تَمَّ إِرْسَالُ النِّدَاءِ لِجَمِيعِ الْمُشْتَرِكِينَ النَّشِطِينَ فِي هَذِهِ الْمَجْمُوعَةِ.", show_alert=True)

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
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"⚙️ <b>تَعْدِيلُ دَوْرِ رَقْم ({idx+1}):</b> {target_name}", parse_mode="HTML", reply_markup=keyboard)
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
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"🔄 <b>اخْتَرْ دَوْراً لِتَبْدِيلِ الْمَرَاكِزِ مَعَ ({target_name}):</b>", parse_mode="HTML", reply_markup=keyboard)
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
