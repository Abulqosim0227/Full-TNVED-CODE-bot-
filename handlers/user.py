import logging
from aiogram import Router, types, F, Bot
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, FSInputFile
from aiogram.filters import CommandStart, Command, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramForbiddenError
from utils.predictor import search_product, smart_search, EnhancedProductSearchSystem
from utils.db import get_connection, log_not_found_query, save_search_result
from utils.db_search import search_classifier_db

async def handle_blocked_user(user_id: int, action: str = "send_message"):
    """Handle when a user blocks the bot"""
    try:
        conn = await get_connection()
        # Mark user as blocked in database
        await conn.execute("""
            UPDATE users SET blocked = TRUE, blocked_at = CURRENT_TIMESTAMP 
            WHERE telegram_id = $1
        """, user_id)
        await conn.close()
        logging.info(f"User {user_id} blocked the bot during {action}")
    except Exception as e:
        logging.error(f"Error handling blocked user {user_id}: {e}")

async def safe_send_message(message: Message, text: str, **kwargs):
    """Send message with error handling for blocked users"""
    try:
        return await message.answer(text, **kwargs)
    except TelegramForbiddenError:
        await handle_blocked_user(message.from_user.id, "send_message")
        return None
    except Exception as e:
        logging.error(f"Error sending message to user {message.from_user.id}: {e}")
        return None
from pathlib import Path

# Database-only architecture - no CSV file dependency

# Initialize the enhanced prediction system (database-only)
predictor = EnhancedProductSearchSystem()
# Localization dictionary
MESSAGES = {
    "choose_language": {
        "ru": "Пожалуйста, выберите язык:\nIltimos, tilni tanlang:\nPlease choose a language:",
        "uz": "Iltimos, tilni tanlang:\nПожалуйста, выберите язык:\nPlease choose a language:",
        "en": "Please choose a language:\nПожалуйста, выберите язык:\nIltimos, tilni tanlang:"
    },
    "welcome": {
        "ru": "👋 Добро пожаловать в бот Nihol! Я помогу вам найти коды ТН ВЭД для ваших товаров.",
        "uz": "👋 Nihol botiga xush kelibsiz! Men sizga mahsulotlaringiz uchun TN VED kodlarini topishda yordam beraman.",
        "en": "👋 Welcome to the Nihol bot! I will help you find HS/TN VED codes for your products."
    },
    "register_prompt": {
        "ru": "Пожалуйста, зарегистрируйтесь, если вы новый пользователь.",
        "uz": "Agar siz yangi foydalanuvchi bo'lsangiz, iltimos, ro'yxatdan o'ting.",
        "en": "Please register if you are a new user."
    },
    "send_name": {
        "ru": "Чтобы начать, отправьте ваше имя и фамилию:",
        "uz": "Boshlash uchun ismingiz va familiyangizni yuboring:",
        "en": "To get started, please send your first name and last name:"
    },
    "send_contact": {
        "ru": "📲 Теперь отправьте ваш контакт:",
        "uz": "📲 Endi kontakt raqamingizni yuboring:",
        "en": "📲 Now please share your contact:"
    },
    "registration_done": {
        "ru": "✅ Регистрация завершена. Добро пожаловать!",
        "uz": "✅ Ro'yxatdan o'tish yakunlandi. Xush kelibsiz!",
        "en": "✅ Registration complete. Welcome!"
    },
    "not_registered": {
        "ru": "⚠️ Вы не зарегистрированы. Пожалуйста, отправьте /start и пройдите регистрацию.",
        "uz": "⚠️ Siz ro'yxatdan o'tmagansiz. Iltimos, /start ni yuboring va ro'yxatdan o'ting.",
        "en": "⚠️ You are not registered. Please send /start and complete the registration."
    },
    "search_prompt": {
        "ru": "✏️ Введите описание товара для поиска кода ТН ВЭД:",
        "uz": "✏️ TN VED kodini topish uchun mahsulot tavsifini kiriting:",
        "en": "✏️ Enter the description of the product to search for HS/TN VED codes:"
    },
    "search_prompt_continue": {
        "ru": "🔄 Введите описание следующего товара или нажмите Отмена:",
        "uz": "🔄 Keyingi mahsulot tavsifini kiriting yoki Bekor qilish tugmasini bosing:",
        "en": "🔄 Enter the description of the next product or click Cancel:"
    },
    "search_cancelled": {
        "ru": "❌ Поиск отменён.",
        "uz": "❌ Qidiruv bekor qilindi.",
        "en": "❌ Search cancelled."
    },
    "wait_message": {
        "ru": "⏳ Пожалуйста, подождите, это может занять некоторое время...",
        "uz": "⏳ Iltimos, kuting, bu biroz vaqt olishi mumkin...",
        "en": "⏳ Please wait, this may take some time..."
    },
    "search_error": {
        "ru": "❌ Произошла ошибка при поиске. Пожалуйста, попробуйте снова.",
        "uz": "❌ Qidiruvda xatolik yuz berdi. Iltimos, qayta urinib ko'ring.",
        "en": "❌ An error occurred while searching. Please try again later."
    },
    "contacts": {
        "ru": "📞 Связь с нами:\n• 🌐 https://nihol.uz\n• 📧 info@nihol.uz\n• 📱 +998 71 208 58 44",
        "uz": "📞 Biz bilan bog'lanish:\n• 🌐 https://nihol.uz\n• 📧 info@nihol.uz\n• 📱 +998 71 208 58 44",
        "en": "📞 Contact us:\n• 🌐 https://nihol.uz\n• 📧 info@nihol.uz\n• 📱 +998 71 208 58 44"
    },
    "myinfo_not_found": {
        "ru": "❌ Пользователь не найден. Пожалуйста, зарегистрируйтесь снова.",
        "uz": "❌ Foydalanuvchi topilmadi. Iltimos, qayta ro'yxatdan o'ting.",
        "en": "❌ User not found. Please register again."
    },
    "help": {
        "ru": "💡 Доступные команды:\n/search — Поиск по описанию товара\n/contacts — Контакты технической поддержки\n/myinfo — Информация о вас\n/help — Справка по боту\n/language — Сменить язык",
        "uz": "💡 Mavjud buyruqlar:\n/search — Mahsulot tavsifi bo'yicha qidiruv\n/contacts — Texnik yordam kontaktlari\n/myinfo — Siz haqingizdagi ma'lumot\n/help — Bot bo'yicha yordam\n/language — Tilni o'zgartirish",
        "en": "💡 Available commands:\n/search — Search by product description\n/contacts — Technical support contacts\n/myinfo — Your information\n/help — Bot help\n/language — Change language"
    },
    "fallback": {
        "ru": "❗ Пожалуйста, используйте меню или команды /start или /search.",
        "uz": "❗ Iltimos, menyudan yoki /start yoki /search buyruqlaridan foydalaning.",
        "en": "❗ Please use the menu or commands /start or /search."
    },
    "language_changed": {
        "ru": "✅ Язык успешно изменён на русский.",
        "uz": "✅ Til muvaffaqiyatli o'zbekchaga o'zgartirildi.",
        "en": "✅ Language successfully changed to English."
    },
    "not_found": {
        "ru": "❌ Товар '{query}' не найден. Попробуйте использовать другие варианты написания или более общее описание.",
        "uz": "❌ '{query}' mahsuloti topilmadi. Boshqa yozuv variantlaridan foydalaning yoki tavsifni umumiyroq qiling.",
        "en": "❌ Product '{query}' not found. Try using different spelling variations or a more general description."
    },
    "not_found_with_suggestions": {
        "ru": "❌ Точное соответствие для '{query}' не найдено. Вот несколько похожих вариантов:",
        "uz": "❌ '{query}' uchun aniq moslik topilmadi. Mana bir nechta o'xshash variantlar:",
        "en": "❌ No exact match found for '{query}'. Here are some similar options:"
    },
    "suggestions": {
        "ru": [
            "Попробуйте использовать единственное число (например, 'майка' вместо 'майки')",
            "Используйте более общее описание (например, 'одежда' вместо конкретного типа)",
            "Добавьте характеристики (например, 'хлопковая майка', 'спортивная майка')"
        ],
        "uz": [
            "🇷🇺 Ruscha yozing - ma'lumotlar bazasida o'zbekcha mahsulotlar yo'q (masalan, 'полипропиленовые мешки' o'rniga 'polipropilen qop')",
            "Birlik sonidan foydalaning (masalan, 'mayka' o'rniga 'maykalar')",
            "Umumiyroq tavsifdan foydalaning (masalan, 'kiyim' o'rniga aniq turi)",
            "Xususiyatlarni qo'shing (masalan, 'paxtali mayka', 'sport maykasi')"
        ],
        "en": [
            "Try using singular form (e.g., 't-shirt' instead of 't-shirts')",
            "Use more general description (e.g., 'clothing' instead of specific type)",
            "Add characteristics (e.g., 'cotton t-shirt', 'sports t-shirt')"
        ]
    }
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
router = Router()

async def send_info_audio(message: Message, lang: str = "ru"):
    """Send the info.mp3 audio file to the user"""
    try:
        # Try multiple possible paths to find the audio file
        possible_paths = [
            Path(__file__).parent.parent / "welcome" / "Info.mp3",  # bot/welcome/Info.mp3 (from handlers/)
            Path("welcome/Info.mp3"),  # welcome/Info.mp3 (if running from bot/)
            Path("bot/welcome/Info.mp3"),  # bot/welcome/Info.mp3 (if running from project root)
            Path.cwd() / "bot" / "welcome" / "Info.mp3",  # absolute path from current working directory
        ]
        
        audio_path = None
        for path in possible_paths:
            if path.exists():
                audio_path = path
                break
        
        if audio_path:
            logging.info(f"Found audio file at: {audio_path}")
            audio_file = FSInputFile(str(audio_path))
            
            # Audio titles based on language
            if lang == "ru":
                title = "Информация о боте"
                performer = "Nihol Bot"
            elif lang == "uz":
                title = "Bot haqida ma'lumot"
                performer = "Nihol Bot"
            else:  # English
                title = "Bot Information"
                performer = "Nihol Bot"
            
            await message.answer_audio(
                audio=audio_file,
                title=title,
                performer=performer
            )
        else:
            logging.warning(f"Audio file not found in any of these locations:")
            for i, path in enumerate(possible_paths, 1):
                logging.warning(f"  {i}. {path.resolve()}")
    except TelegramForbiddenError:
        await handle_blocked_user(message.from_user.id, "send_audio")
    except Exception as e:
        logging.error(f"Error sending audio: {e}")

def t(key, lang):
    return MESSAGES.get(key, {}).get(lang, MESSAGES.get(key, {}).get("ru", ""))

async def get_user_language(user_id):
    conn = await get_connection()
    user = await conn.fetchrow("SELECT language FROM users WHERE telegram_id = $1", user_id)
    await conn.close()
    return user['language'] if user and user['language'] else "ru"

def main_keyboard(lang):
    if lang == "ru":
        search_text = "🔍 Поиск товара"
        contacts_text = "📞 Контакты"
        help_text = "🆘 Помощь"
        my_data_text = "🧾 Мои данные"
        change_lang_text = "🌐 Сменить язык"
        placeholder = "Выберите действие..."
    elif lang == "uz":
        search_text = "🔍 Mahsulot qidirish"
        contacts_text = "📞 Kontaktlar"
        help_text = "🆘 Yordam"
        my_data_text = "🧾 Ma'lumotlarim"
        change_lang_text = "🌐 Tilni o'zgartirish"
        placeholder = "Amalni tanlang..."
    else:  # English
        search_text = "🔍 Product Search"
        contacts_text = "📞 Contacts"
        help_text = "🆘 Help"
        my_data_text = "🧾 My Data"
        change_lang_text = "🌐 Change Language"
        placeholder = "Choose an action..."
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=search_text),
                KeyboardButton(text=contacts_text)
            ],
            [
                KeyboardButton(text=help_text),
                KeyboardButton(text=my_data_text)
            ],
            [
                KeyboardButton(text=change_lang_text)
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder=placeholder
    )

def contact_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(
            text="📱 Отправить контакт" if lang == "ru" else "📱 Kontaktni yuborish",
            request_contact=True
        )]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def lang_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Русский"), KeyboardButton(text="O'zbekcha"), KeyboardButton(text="English")]],
        resize_keyboard=True
    )

class RegisterState(StatesGroup):
    waiting_for_full_name = State()
    waiting_for_contact = State()
    waiting_for_language = State()

class SearchState(StatesGroup):
    waiting_for_description = State()

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await safe_send_message(message, t("choose_language", "ru"), reply_markup=lang_keyboard())
    await state.set_state(RegisterState.waiting_for_language)

@router.message(or_f(Command("language"), F.text.in_(["🌐 Сменить язык", "🌐 Tilni o'zgartirish", "🌐 Change Language"])))
async def cmd_change_language(message: types.Message, state: FSMContext):
    await state.clear()
    await safe_send_message(message, t("choose_language", "ru"), reply_markup=lang_keyboard())
    await state.set_state(RegisterState.waiting_for_language)

@router.message(or_f(Command("search"), F.text.in_(["🔍 Поиск товара", "🔍 Mahsulot qidirish", "🔍 Product Search"])))
async def cmd_search(message: types.Message, state: FSMContext):
    await state.clear()
    
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    
    conn = await get_connection()
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", user_id)
    await conn.close()
    
    if not user:
        await safe_send_message(message, t("not_registered", lang), reply_markup=main_keyboard(lang))
        return

    await state.set_state(SearchState.waiting_for_description)
    cancel_keyboard = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="❌ Отмена" if lang == "ru" else ("❌ Bekor qilish" if lang == "uz" else "❌ Cancel"))
        ]],
        resize_keyboard=True
    )
    
    await safe_send_message(message, t("search_prompt", lang), reply_markup=cancel_keyboard)

@router.message(RegisterState.waiting_for_language, F.text.in_(["Русский", "O'zbekcha", "English"]))
async def set_language(message: types.Message, state: FSMContext):
    if message.text == "Русский":
        lang = "ru"
    elif message.text == "O'zbekcha":
        lang = "uz"
    else:
        lang = "en"
    
    await state.update_data(lang=lang)
    
    user_id = message.from_user.id
    conn = await get_connection()
    
    user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", user_id)
    
    if user:
        # Existing user changing language - only send confirmation
        await conn.execute("UPDATE users SET language = $1 WHERE telegram_id = $2", lang, user_id)
        await conn.close()
        await state.clear()
        await safe_send_message(message, t("language_changed", lang), reply_markup=main_keyboard(lang))
    else:
        # New user during registration - send welcome + registration flow
        await conn.close()
        await safe_send_message(message, f"{t('welcome', lang)}\n\n{t('register_prompt', lang)}", reply_markup=ReplyKeyboardRemove())
        await safe_send_message(message, t("send_name", lang), reply_markup=ReplyKeyboardRemove())
        await state.set_state(RegisterState.waiting_for_full_name)

@router.message(RegisterState.waiting_for_full_name, F.text)
async def get_full_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    full_name = message.text.strip()
    await state.update_data(full_name=full_name)
    await safe_send_message(message, t("send_contact", lang), reply_markup=contact_keyboard(lang))
    await state.set_state(RegisterState.waiting_for_contact)

@router.message(RegisterState.waiting_for_contact, F.contact)
async def register_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    full_name = data.get("full_name")
    
    user = message.from_user
    contact = message.contact
    
    conn = await get_connection()
    try:
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS language VARCHAR(2) DEFAULT 'ru'")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked BOOLEAN DEFAULT FALSE")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS blocked_at TIMESTAMP")
    except:
        pass  
    
    await conn.execute("""
        INSERT INTO users (telegram_id, full_name, username, phone, language)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (telegram_id) DO UPDATE SET 
            full_name = $2, username = $3, phone = $4, language = $5
    """, user.id, full_name, user.username, contact.phone_number, lang)
    await conn.close()
    
    await state.clear()
    await safe_send_message(message, t("registration_done", lang), reply_markup=main_keyboard(lang))
    
    # Send info audio after successful registration
    await send_info_audio(message, lang)

@router.message(SearchState.waiting_for_description, F.text)
async def handle_search(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    query = message.text.strip()
    
    state_data = await state.get_data()
    prompt_message_id = state_data.get("prompt_message_id")
    if prompt_message_id is not None and message.message_id <= prompt_message_id:
        return

    cancel_texts = ["отмена", "bekor qilish", "cancel", "❌ отмена", "❌ bekor qilish", "❌ cancel"]
    if query.strip().lower() in cancel_texts:
        await state.clear()
        await safe_send_message(message, t("search_cancelled", lang), reply_markup=main_keyboard(lang))
        return

    menu_buttons = [
        "🔍 Поиск товара", "📞 Контакты", "🆘 Помощь", "🧾 Мои данные", "🌐 Сменить язык",
        "🔍 Mahsulot qidirish", "📞 Kontaktlar", "🆘 Yordam", "🧾 Ma'lumotlarim", "🌐 Tilni o'zgartirish",
        "🔍 Product Search", "📞 Contacts", "🆘 Help", "🧾 My Data", "🌐 Change Language"
    ]
    if query.startswith("/") or query in menu_buttons:
        await state.clear()
        # Let the respective handler manage the response
        return

    waiting_msg = None
    if len(query.split()) > 2:
        waiting_msg = await safe_send_message(message, t("wait_message", lang), reply_markup=ReplyKeyboardRemove())

    try:
        result = await smart_search(query, lang, limit=5)
    except Exception as e:
        logging.error(f"Error in smart_search: {str(e)}", exc_info=True)
        if waiting_msg: await waiting_msg.delete()
        await safe_send_message(message, t("search_error", lang), reply_markup=main_keyboard(lang))
        return

    if waiting_msg:
        try:
            await waiting_msg.delete()
        except Exception:
            pass

    # Log usage
    conn = await get_connection()
    await conn.execute("INSERT INTO usage_logs (user_id, query) VALUES ($1, $2)", user_id, query)
    await conn.execute("UPDATE users SET requests_today = requests_today + 1 WHERE telegram_id = $1", user_id)
    await conn.close()

    # Save detailed search result (for successful searches)
    if result["status"] != "not_found" and result["results"]:
        main_result = result["results"][0]
        similar_results = result["results"][1:4] if len(result["results"]) > 1 else []
        total_results = len(result["results"])
        
        await save_search_result(
            user_id=user_id,
            query=query,
            main_result=main_result,
            similar_results=similar_results,
            language=lang,
            total_results_found=total_results
        )

    if result["status"] == "not_found" or not result["results"]:
        # Log the not found query
        try:
            await log_not_found_query(user_id, query, lang)
        except Exception as e:
            logging.error(f"Failed to log not found query: {e}")
        
        msg = f"❌ {t('not_found', lang).format(query=query)}"
        suggestions_text = "Tavsiyalar" if lang == "uz" else "Рекомендации"
        msg += f"\n\n💡 {suggestions_text}:\n" + "\n".join([f"• {s}" for s in MESSAGES["suggestions"][lang]])
    else:
        # Build and send results with accuracy/confidence
        main_item = result["results"][0]
        code = main_item.get('code', 'N/A')
        desc = main_item.get('description', 'Описание отсутствует')
        accuracy = main_item.get('desc_score', 0)
        
        lang_note = ""
        if lang != "ru":
            lang_note = "\n<i>(Описание на русском языке)</i>\n"

        msg = (
            f"📦 <b>Наиболее подходящий код ТН ВЭД:</b>\n"
            f"<b>Код:</b> <code>{code}</code>\n"
            f"<b>Описание:</b> {desc}{lang_note}\n"
            f"<b>Точность:</b> {accuracy:.2f}\n\n"
            f"❗️Автоматический подбор. Проверьте у специалиста по таможенному оформлению."
        )

        if len(result["results"]) > 1:
            msg += "\n\n📌 <b>Похожие коды:</b>\n"
            for item in result["results"][1:4]:
                code2 = item.get('code', 'N/A')
                desc2 = item.get('description', '')
                acc2 = item.get('desc_score', 0)
                msg += f"• <code>{code2}</code>: {desc2} (Точность: {acc2:.2f})\n"

    if len(msg) > 4000:
        msg = msg[:3900] + "\n\n... (текст сокращен)"
    
    await safe_send_message(message, msg, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    
    # Prompt for next search
    prompt_message = await safe_send_message(message,
        t("search_prompt_continue", lang),
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отмена" if lang=="ru" else "Bekor qilish")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    if prompt_message:
        await state.update_data(prompt_message_id=prompt_message.message_id)

@router.message(or_f(Command("contacts"), F.text.in_(["📞 Контакты", "📞 Kontaktlar", "📞 Contacts"])))
async def cmd_contacts(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    await safe_send_message(message, t("contacts", lang), reply_markup=main_keyboard(lang))

@router.message(or_f(Command("myinfo"), F.text.in_(["🧾 Мои данные", "🧾 Ma'lumotlarim", "🧾 My Data"])))
async def cmd_myinfo(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    conn = await get_connection()
    user = await conn.fetchrow("""
        SELECT full_name, phone, telegram_id, language, registered_at
        FROM users WHERE telegram_id = $1
    """, user_id)
    await conn.close()
    
    lang = user['language'] if user else "ru"
    
    if not user:
        await safe_send_message(message, t("myinfo_not_found", lang), reply_markup=main_keyboard(lang))
        return
    
    registered_at = user['registered_at'].strftime('%Y-%m-%d %H:%M:%S') if user['registered_at'] else "Unknown"
    
    if lang == "ru":
        info_text = f"👤 Информация о вас:\n\n📋 Имя: {user['full_name']}\n📱 Телефон: {user['phone']}\n🆔 Telegram ID: {user['telegram_id']}\n🌐 Язык: {user['language']}\n📅 Дата регистрации: {registered_at}"
    elif lang == "uz":
        info_text = f"👤 Siz haqingizda ma'lumot:\n\n📋 Ism: {user['full_name']}\n📱 Telefon: {user['phone']}\n🆔 Telegram ID: {user['telegram_id']}\n🌐 Til: {user['language']}\n📅 Ro'yxatdan o'tgan sana: {registered_at}"
    else:
        info_text = f"👤 Your information:\n\n📋 Name: {user['full_name']}\n📱 Phone: {user['phone']}\n🆔 Telegram ID: {user['telegram_id']}\n🌐 Language: {user['language']}\n📅 Registration date: {registered_at}"
    
    await safe_send_message(message, info_text, reply_markup=main_keyboard(lang))

@router.message(or_f(Command("help"), F.text.in_(["🆘 Помощь", "🆘 Yordam", "🆘 Help"])))
async def cmd_help(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    await safe_send_message(message, t("help", lang), reply_markup=main_keyboard(lang))

@router.message(F.text)
async def fallback(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    current_state = await state.get_state()
    
    if current_state != SearchState.waiting_for_description:
        await safe_send_message(message, t("fallback", lang), reply_markup=main_keyboard(lang))