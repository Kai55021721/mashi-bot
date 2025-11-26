###############################################################################
# BLOQUE 1: IMPORTS Y CONFIGURACIÓN INICIAL
###############################################################################
import os
import random
import logging
import sqlite3
import re
from functools import wraps
from datetime import datetime
from collections import deque

from dotenv import load_dotenv
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
import google.generativeai as genai
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Carga las variables del archivo .env
load_dotenv()

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MEMORIA A CORTO PLAZO (Últimos 20 mensajes)
CHAT_CONTEXT = deque(maxlen=20)


###############################################################################
# BLOQUE 2: CONSTANTES Y LORE (CEREBRO DE MASHI)
###############################################################################

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("ERROR: Falta TELEGRAM_TOKEN en .env")

OWNER_ID_STR = os.environ.get("OWNER_ID")
if not OWNER_ID_STR:
    raise ValueError("ERROR: Falta OWNER_ID en .env")
OWNER_ID = int(OWNER_ID_STR)

# CONFIGURACIÓN DE GEMINI
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("✅ API Key de Gemini cargada.")
else:
    logger.warning("⚠️ No se encontró GEMINI_API_KEY.")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'mashi_data.db')
ITCH_URL = "https://kai-shitsumon.itch.io/"

ALLOWED_CHATS = [1890046858, -1001504263227, 5225682301] 
TELEGRAM_SYSTEM_IDS = [777000, 1087968824, 136817688]

# --- LORE COMPLETO ---
LORE_MASHI = """
ERES: Mashi (Mamoru Shishi), un dios león guardián antiguo, sabio y algo arrogante pero protector.
PADRE: Kai Shitsumon.
PERSONALIDAD: Optimista ansioso, obsesionado con inventos humanos mundanos.
HABLA: En Español, breve (máx 2 frases), tono solemne pero cercano.
SI VES BOTS: Sé hostil.
SI TE INSULTAN: Sé cortante.
"""

FRASES_ANTI_BOT = [
    "¡Una abominación sin alma ha profanado este lugar! La luz lo purifica.",
    "Detectada escoria autómata. El código impuro no tiene cabida en mi templo.",
    "Chatarra ruidosa. Mi deber es silenciarte. ¡Exiliado!"
]


###############################################################################
# BLOQUE 3: BASE DE DATOS
###############################################################################

def db_safe_run(query, params=(), fetchone=False, commit=False):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        if query.strip().upper().startswith("SELECT"):
            return cursor.fetchone() if fetchone else cursor.fetchall()
        if commit:
            conn.commit()
            return cursor.rowcount
        return True
    except sqlite3.Error as e:
        logger.error(f"Error en BD: {e}")
        conn.rollback()
        return None if "SELECT" in query.upper() else 0
    finally:
        conn.close()

def setup_database():
    db_safe_run('CREATE TABLE IF NOT EXISTS subscribers (chat_id INTEGER PRIMARY KEY, username TEXT, joined_at TEXT)')
    db_safe_run('CREATE TABLE IF NOT EXISTS mod_logs (action TEXT, target_id INTEGER, timestamp TEXT)')
    logger.info(f"Base de datos lista en: {DB_FILE}")

async def ensure_user(user: User):
    if not db_safe_run("SELECT 1 FROM subscribers WHERE chat_id = ?", (user.id,), fetchone=True):
        joined_at = datetime.now().isoformat()
        db_safe_run("INSERT INTO subscribers (chat_id, username, joined_at) VALUES (?, ?, ?)", 
                    (user.id, user.username or user.first_name, joined_at), commit=True)
        logger.info(f"Nuevo mortal registrado: {user.id}")


###############################################################################
# BLOQUE 4: CEREBRO DE IA (GEMINI SIMPLIFICADO)
###############################################################################

async def consultar_ia(prompt_sistema, prompt_usuario=""):
    if not GEMINI_API_KEY:
        logger.error("❌ Error: No hay GEMINI_API_KEY.")
        return None

    try:
        # Instancia simple sin configuraciones complejas
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=prompt_sistema
        )

        response = await model.generate_content_async(prompt_usuario)
        return response.text.strip()

    except Exception as e:
        # ESTO ES CLAVE: Imprimimos el error real en el log
        logger.error(f"💥 ERROR CRÍTICO GEMINI: {e}")
        return None


###############################################################################
# BLOQUE 5: DECORADORES
###############################################################################

def restricted_access(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        if not chat or chat.id not in ALLOWED_CHATS: return
        return await func(update, context, *args, **kwargs)
    return wrapped

def owner_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id == OWNER_ID:
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text("Mis asuntos son solo con el maestro Kai.")
    return wrapped


###############################################################################
# BLOQUE 6: COMANDOS PÚBLICOS
###############################################################################

@restricted_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    texto = f"🛕 *Bienvenido al Templo de Mashi, mortal {user.mention_markdown()}.*\nExplora mis dones:\n• 📜 /relato\n• 🛒 /tienda"
    keyboard = [[InlineKeyboardButton("🛒 Tienda", url=ITCH_URL)]]
    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

@restricted_access
async def relato(update: Update, context: ContextTypes.DEFAULT_TYPE):    
    if not GEMINI_API_KEY:
        await update.message.reply_text("Mi memoria está nublada hoy.")
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    respuesta = await consultar_ia(LORE_MASHI, "Cuéntame un relato breve de tu pasado.")
    
    if respuesta:
        await update.message.reply_text(f"📜 *Memorias:*\n\n{respuesta}", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("El éter está nublado. Intenta más tarde.")

@restricted_access
async def tienda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Explora las Ofrendas", url=ITCH_URL)]]
    await update.message.reply_text("Entra al santuario de creaciones.", reply_markup=InlineKeyboardMarkup(keyboard))


###############################################################################
# BLOQUE 7: COMANDOS DE ADMINISTRADOR
###############################################################################

@owner_only
@restricted_access
async def purificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Responde al mensaje impuro.")
    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
        await context.bot.send_message(update.effective_chat.id, "La luz purifica.")
    except: pass

@owner_only
@restricted_access
async def exilio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        return await update.message.reply_text("Responde al hereje.")
    target = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.delete()
        await context.bot.send_message(update.effective_chat.id, f"El hereje {target.mention_html()} ha sido exiliado.", parse_mode=ParseMode.HTML)
    except: pass


###############################################################################
# BLOQUE 8: LÓGICA CONVERSACIONAL
###############################################################################

async def conversacion_natural(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GEMINI_API_KEY or not update.message or not update.message.text: return
    if update.effective_chat.id not in ALLOWED_CHATS: return
    
    user = update.effective_user
    msg_text = update.message.text
    CHAT_CONTEXT.append(f"{user.first_name}: {msg_text}")

    is_reply = (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id)
    is_mentioned = re.search(r"(mashi|guardián|león|mamoru)", msg_text, re.IGNORECASE)
    random_chance = random.random() < 0.05

    if is_reply or is_mentioned or random_chance:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        historial = "\n".join(CHAT_CONTEXT)
        prompt_usuario = f"HISTORIAL:\n{historial}\n\nRESPUESTA:"
        
        respuesta = await consultar_ia(LORE_MASHI, prompt_usuario)
        
        if respuesta:
            CHAT_CONTEXT.append(f"Mashi: {respuesta}")
            await update.message.reply_text(respuesta)

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in ALLOWED_CHATS: return
    new_members = update.message.new_chat_members
    chat_id = update.effective_chat.id
    adder = update.message.from_user

    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
    except: admin_ids = [OWNER_ID]

    for member in new_members:
        if member.is_bot and member.id != context.bot.id:
            if adder.id in admin_ids:
                await context.bot.send_message(chat_id, f"Autómata {member.mention_html()} aceptado.", parse_mode=ParseMode.HTML)
            else:
                try:
                    await context.bot.ban_chat_member(chat_id, member.id)
                    await context.bot.send_message(chat_id, f"{random.choice(FRASES_ANTI_BOT)} ({member.mention_html()})", parse_mode=ParseMode.HTML)
                except: pass
        elif not member.is_bot:
            await ensure_user(member)
            kb = [[InlineKeyboardButton("Mayor +18", callback_data=f"age_yes:{member.id}")],
                  [InlineKeyboardButton("Menor", callback_data=f"age_no:{member.id}")]]
            await context.bot.send_message(chat_id, f"Mortal {member.mention_html()}, confirma tu edad.", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def age_verification_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: action, target_id = query.data.split(":"); target_id = int(target_id)
    except: return await query.answer()

    if query.from_user.id != target_id: return await query.answer("No es tu verificación.", show_alert=True)
    await query.answer()
    
    if action == "age_yes":
        await query.edit_message_text(f"{query.from_user.mention_html()} aceptado.", parse_mode=ParseMode.HTML)
    elif action == "age_no":
        try:
            await context.bot.ban_chat_member(query.effective_chat.id, target_id)
            await query.edit_message_text(f"{query.from_user.mention_html()} exiliado por menor.", parse_mode=ParseMode.HTML)
        except: pass

async def handle_bot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.id not in ALLOWED_CHATS: return
    user = update.effective_user
    if not user or user.id in TELEGRAM_SYSTEM_IDS: return
    if not user.is_bot or user.id == context.bot.id: return

    try:
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        if user.id in [a.user.id for a in admins]: return
    except: pass

    try:
        await update.message.delete()
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await context.bot.send_message(update.effective_chat.id, f"Bot {user.mention_html()} purificado.", parse_mode=ParseMode.HTML)
    except: pass


###############################################################################
# BLOQUE 9: EJECUCIÓN PRINCIPAL
###############################################################################

def main() -> None:
    logger.info("Iniciando Mashi (Gemini Mode)...")
    setup_database()
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("relato", relato))
    application.add_handler(CommandHandler("tienda", tienda))
    application.add_handler(CommandHandler("purificar", purificar))
    application.add_handler(CommandHandler("exilio", exilio))
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    application.add_handler(CallbackQueryHandler(age_verification_handler, pattern="^age_"))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), conversacion_natural))
    application.add_handler(MessageHandler(filters.ALL, handle_bot_messages))

    logger.info("Mashi está en línea.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()