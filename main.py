import os
import logging
import json
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# 1. إعداد نظام السجلات (Logging)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot_errors.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# تحميل متغيرات البيئة
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

DATA_FILE = "quran_recitation_data.json"

# 2. إدارة قاعدة البيانات المحلية وحفظها تلقائياً في ملف JSON لحمايتها من إعادة تشغيل خادم Render
def load_database() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                return {int(k): v for k, v in raw_data.items()}
        except Exception as e:
            logger.error(f"خطأ أثناء قراءة ملف قاعدة البيانات: {e}")
    return {}

def save_database(database: dict):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(database, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"خطأ أثناء حفظ قاعدة البيانات: {e}")

groups_database = load_database()

def get_group_data(chat_id: int) -> dict:
    if chat_id not in groups_database:
        groups_database[chat_id] = {"members": [], "read": []}
        save_database(groups_database)
    return groups_database[chat_id]

# 3. التحقق من صلاحيات المسؤول
async def is_user_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if ADMIN_ID and str(user_id) == str(ADMIN_ID):
        return True
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        return chat_member.status in [ChatMember.OWNER, ChatMember.ADMINISTRATOR]
    except Exception:
        return False

# 4. بناء واجهة الأزرار التفاعلية (Inline Keyboard)
def build_keyboard(is_admin_user: bool) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📝 تَسْجِيلُ دَوْرِي", callback_data="register_turn"),
            InlineKeyboardButton("✅ فَرَغْتُ مِنَ الْقِرَاءَةِ", callback_data="finish_read")
        ],
        [
            InlineKeyboardButton("📢 نِدَاءُ الْحَلَقَةِ", callback_data="call_members")
        ]
    ]
    # أزرار الإشراف تظهر للمسؤولين فقط
    if is_admin_user:
        keyboard.append([InlineKeyboardButton("🔄 إِعَادَةُ ضَبْطِ الْقَائِمَةِ", callback_data="reset_list")])
        
    return InlineKeyboardMarkup(keyboard)

# 5. بناء نص القائمة والإحصائيات للمجموعات
def build_list_text(chat_id: int) -> str:
    group_data = get_group_data(chat_id)
    members = group_data.get("members", [])
    read_list = group_data.get("read", [])
    
    if not members:
        return "📋 <b>قَائِمَةُ التَّلَاوَةِ الْحَالِيَّةِ:</b>\n\n<i>الْقَائِمَةُ فَارِغَةٌ تَمَاماً حَالِيّاً، بَانْتِظَارِ تَسْجِيلِ الْمُشْتَرِكَاتِ.</i>"
        
    lines = ["📋 <b>قَائِمَةُ تِلَاوَةِ الْقُرْآنِ الْكَرِيمِ:</b>\n"]
    for i, member in enumerate(members, 1):
        uid = member["id"]
        status = "✅ قَرَأَتْ" if uid in read_list else "⏳ فِي الِانْتِظَارِ"
        lines.append(f"{i}. {status} ── {member['name']}")
        
    total = len(members)
    read_count = len(read_list)
    lines.append(f"\n📈 <b>الْإِحْصَائِيَّاتُ الحَالِيَّةُ: {read_count} مِنْ أَصْلِ {total} خَتَمْنَ الْوِرْدَ</b>")
    return "\n".join(lines)

# 6. معالجة الأوامر
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    # أولاً: إذا كان الإرسال في الخاص (Private Chat)
    if chat.type == "private":
        welcome_private = (
            "السَّلَامُ عَلَيْكُمْ وَرَحْمَةُ اللَّهِ وَبَرَكَاتُهُ.\n\n"
            "هَذَا الْبُوتُ صَدَقَةٌ عَنِّي وَوَالِدَيَّ وَعَنْ مَقْرَأَتِنَا وَكُلِّ الْمُسْلِمِينَ وَالْمُسْلِمَاتِ "
            "وَالْمُؤْمِنِينَ وَالْمُؤْمِنَاتِ الْأَحْيَاءِ مِنْهُمْ وَالْأَمْوَاتِ.\n\n"
            "📌 <b>تَنْبِيهٌ:</b> يَرْجَى إِضَافَةُ الْبُوتِ إِلَى الْمَجْمُوعَةِ لِتَبْدَأَ حَلَقَاتُ التَّلَاوَةِ."
        )
        await update.message.reply_text(welcome_private, parse_mode="HTML")
        return
        
    # ثانياً: إذا كان الإرسال داخل المجموعة
    admin_status = await is_user_admin(update, context)
    list_text = build_list_text(chat.id)
    await update.message.reply_text(
        list_text,
        parse_mode="HTML",
        reply_markup=build_keyboard(admin_status)
    )

# 7. معالجة ضغطات الأزرار (Callback Queries)
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    user = query.from_user
    user_id = user.id
    user_name = user.first_name.replace("<", "&lt;").replace(">", "&gt;")
    
    group_data = get_group_data(chat_id)
    await query.answer() # إغلاق مؤشر التحميل على الزر
    
    # أ. زر تسجيل الدور
    if query.data == "register_turn":
        existing = next((m for m in group_data["members"] if m["id"] == user_id), None)
        if existing:
            await query.answer(text=f"أَنْتِ مُسَجَّلَةٌ بِالْفِعْلِ فِي الْقَائِمَةِ يَا أُخْتِي.", show_alert=True)
            return
            
        group_data["members"].append({"id": user_id, "name": user.first_name})
        save_database(groups_database)
        
        # ظهور رسالة منبثقة على شاشة المستخدم فقط
        await query.answer(
            text="رَعَاكِ اللَّهُ كُونِي عَلَى الْمَوْعِدِ وَالْتَزِمِي بِدَوْرِكِ، يُؤْنِسُنَا وَالْمَلَائِكَةَ انْضِمَامُكِ لِمَجْلِسِنَا.",
            show_alert=True
        )
        # تحديث القائمة في المجموعة فوراً
        admin_status = await is_user_admin(update, context)
        await query.edit_message_text(text=build_list_text(chat_id), parse_mode="HTML", reply_markup=build_keyboard(admin_status))

    # ب. زر الفراغ من القراءة
    elif query.data == "finish_read":
        member = next((m for m in group_data["members"] if m["id"] == user_id), None)
        if not member:
            await query.answer(text="عُذْراً، يَجِبُ تَسْجِيلُ اسْمِكِ فِي الْقَائِمَةِ أَوَّلاً عَبْرَ زِرِّ التَّسْجِيلِ.", show_alert=True)
            return
            
        if user_id in group_data["read"]:
            await query.answer(text="لَقَدْ تَمَّ تَسْجِيلُ قِرَاءَتِكِ مِثْلَ ذِي قَبْلُ.", show_alert=True)
            return
            
        group_data["read"].append(user_id)
        save_database(groups_database)
        
        # ظهور نافذة منبثقة للمستخدم بالثناء
        await query.answer(
            text=f"بَارَكَ اللَّهُ فِيكِ يَا أُخْتِي، تَمَّتْ إِضَافَتُكِ إِلَى حَلَقَةِ التَّلَاوَةِ بِنَجَاحٍ. جَعَلَكِ اللَّهُ مِنْ أَهْلِ الْقُرْآنِ.",
            show_alert=True
        )
        admin_status = await is_user_admin(update, context)
        await query.edit_message_text(text=build_list_text(chat_id), parse_mode="HTML", reply_markup=build_keyboard(admin_status))

    # ج. زر نداء الحلقة (المنشن التلقائي لجميع العضوات)
    elif query.data == "call_members":
        members = group_data.get("members", [])
        if not members:
            await query.answer(text="الْقَائِمَةُ فَارِغَةٌ حَالِيّاً، لَا يُوجَدُ مَنْ نُنَادِي عَلَيْهِ.", show_alert=True)
            return
            
        mentions = []
        for m in members:
            clean_name = m["name"].replace("<", "&lt;").replace(">", "&gt;")
            mentions.append(f'<a href="tg://user?id={m["id"]}">{clean_name}</a>')
            
        mention_text = "📢 <b>هَلُمُّوا لِمَجْلِسٍ تَحُفُّهُ الْمَلَائِكَةُ!</b>\n\n" + " ".join(mentions)
        await context.bot.send_message(chat_id=chat_id, text=mention_text, parse_mode="HTML")

    # د. زر إعادة ضبط القائمة (خاص بالمشرفات)
    elif query.data == "reset_list":
        if not await is_user_admin(update, context):
            await query.answer(text="⛔ عُذْراً، هَذَا الْإِجْرَاءُ مَقْصُورٌ عَلَى مُشْرِفَاتِ الْمَجْمُوعَةِ فَقَطْ.", show_alert=True)
            return
            
        group_data["members"] = []
        group_data["read"] = []
        save_database(groups_database)
        
        await query.answer(text="🔄 تَمَّتْ إِعادةُ ضَبْطِ الْقَائِمَةِ وَتَصْفِيرِ الْبَياناتِ لِخَتْمَةٍ جَدِيدَةٍ.", show_alert=True)
        await query.edit_message_text(text=build_list_text(chat_id), parse_mode="HTML", reply_markup=build_keyboard(True))

# 8. نقطة الانطلاق والتشغيل (Main Configuration)
def main():
    if not BOT_TOKEN:
        print("❌ خطأ: لم يتم العثور على TOKEN الخاص بالبوت في متغيرات البيئة!")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # تسجيل معالجات الأوامر والضغطات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_buttons))

    print("🚀 البوت المبارك يعمل الآن وجاهز لخدمة المقرأة...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
