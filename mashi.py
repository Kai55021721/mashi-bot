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
import httpx 
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

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
# BLOQUE 2: CONSTANTES Y CONFIGURACIÓN
###############################################################################

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("ERROR: Falta TELEGRAM_TOKEN en .env")

OWNER_ID_STR = os.environ.get("OWNER_ID")
if not OWNER_ID_STR:
    raise ValueError("ERROR: Falta OWNER_ID en .env")
OWNER_ID = int(OWNER_ID_STR)

# USAREMOS LA KEY DE HUGGING FACE
HF_API_KEY = os.environ.get("HF_API_KEY")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'mashi_data.db')
ITCH_URL = "https://kai-shitsumon.itch.io/"

ALLOWED_CHATS = [1890046858, -1001504263227] 

TELEGRAM_SYSTEM_IDS = [777000, 1087968824, 136817688]

RELATOS_DEL_GUARDIAN = [
    "Los ecos de la gloria pasada resuenan solo para aquellos que saben escuchar el silencio...",
    "Recuerdo imperios de arena y sol que se alzaron y cayeron bajo mi vigilia...",
    "La perseverancia de los mortales es una luz fugaz, pero brillante, en la inmensidad del tiempo."
]

FRASES_ANTI_BOT = [
    "¡Una abominación sin alma ha profanado este lugar! La luz lo purifica.",
    "Detectada escoria autómata. El código impuro no tiene cabida en mi templo.",
    "¿Una imitación de vida osa entrar en mi presencia? ¡Vuelve al vacío!",
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
# BLOQUE 4: CEREBRO DE IA (HUGGING FACE)
###############################################################################

async def consultar_ia(prompt_sistema, prompt_usuario=""):
    """
    Conecta con la API de Hugging Face usando el modelo Mistral-7B.
    """
    if not HF_API_KEY:
        return None

    # Modelo: Mistral-7B-Instruct-v0.2
    API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}

    # Mistral usa el formato [INST] ... [/INST]
    full_prompt = f"[INST] {prompt_sistema}\n\n{prompt_usuario} [/INST]"

    payload = {
        "inputs": full_prompt,
        "parameters": {
            "max_new_tokens": 250, 
            "temperature": 0.8,
            "return_full_text": False
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(API_URL, headers=headers, json=payload, timeout=30.0)
            
            if response.status_code != 200:
                logger.error(f"Error HuggingFace: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            if isinstance(data, list) and len(data) > 0 and "generated_text" in data[0]:
                return data[0]["generated_text"].strip()
            else:
                return None
                
        except Exception as e:
            logger.error(f"Excepción conectando a Hugging Face: {e}")
            return None


###############################################################################
# BLOQUE 5: DECORADORES Y UTILIDADES
###############################################################################

def restricted_access(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        if not chat or chat.id not in ALLOWED_CHATS:
            return
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

async def send_random_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, intro_text: str, choices: list):
    chosen_item = random.choice(choices)
    await update.message.reply_text(f"{intro_text}\n\n{chosen_item}")


###############################################################################
# BLOQUE 6: COMANDOS PÚBLICOS
###############################################################################

@restricted_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    texto = (
        f"🛕 *Bienvenido al Templo de Mashi, mortal {user.mention_markdown()}.*\n\n"
        "Yo, el Guardián Erudito Caído, custodio este refugio de sabiduría.\n"
        "Explora mis dones:\n• 📜 /relato\n• 🛒 /tienda"
    )
    keyboard = [[InlineKeyboardButton("🛒 Tienda", url=ITCH_URL)]]
    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

@restricted_access
async def relato(update: Update, context: ContextTypes.DEFAULT_TYPE):    
    if not HF_API_KEY:
        await send_random_choice(update, context, "El pasado es un eco...", RELATOS_DEL_GUARDIAN)
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    prompt = "Actúa como Mashi, un dios león guardián antiguo y solemne. Escribe un micro-relato MUY BREVE (máximo 3 frases) sobre una gloria olvidada de tu pasado."
    
    respuesta = await consultar_ia(prompt)
    
    if respuesta:
        await update.message.reply_text(f"📜 *Ecos del Pasado:*\n\n{respuesta}", parse_mode=ParseMode.MARKDOWN)
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
        await context.bot.send_message(update.effective_chat.id, "La luz purifica. Sombra desterrada.")
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", ("purificar", update.message.reply_to_message.from_user.id, datetime.now().isoformat()), commit=True)
    except Exception:
        await update.message.reply_text("La impureza se resiste.")

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
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", ("exilio", target.id, datetime.now().isoformat()), commit=True)
    except Exception:
        await update.message.reply_text("El exilio falló.")


###############################################################################
# BLOQUE 8: LÓGICA CONVERSACIONAL Y EVENTOS
###############################################################################

async def conversacion_natural(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not HF_API_KEY: return
    if not update.message or not update.message.text: return
    if update.effective_chat.id not in ALLOWED_CHATS: return
    
    user = update.effective_user
    msg_text = update.message.text
    
    CHAT_CONTEXT.append(f"{user.first_name}: {msg_text}")

    is_reply = (update.message.reply_to_message and 
                update.message.reply_to_message.from_user.id == context.bot.id)
    is_mentioned = re.search(r"(mashi|guardián|león|mamoru)", msg_text, re.IGNORECASE)
    random_chance = random.random() < 0.05

    if is_reply or is_mentioned or random_chance:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        historial = "\n".join(CHAT_CONTEXT)
        prompt_sistema = (
            "Eres Mamoru Shishi (Mashi), un dios guardián león antiguo, sabio y algo arrogante pero protector. "
            "Responde al último mensaje del chat. Sé breve (máx 2 frases). "
            "Si te insultan, sé cortante. Si hablan de arte, interésate. Habla siempre en ESPAÑOL."
        )
        prompt_usuario = f"Historial:\n{historial}\n\nMashi:"
        
        respuesta = await consultar_ia(prompt_sistema, prompt_usuario)
        
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
    except:
        admin_ids = [OWNER_ID]

    for member in new_members:
        if member.is_bot and member.id != context.bot.id:
            if adder.id in admin_ids:
                await context.bot.send_message(chat_id, f"Acepto al autómata {member.mention_html()} por orden de la autoridad.", parse_mode=ParseMode.HTML)
            else:
                try:
                    await context.bot.ban_chat_member(chat_id, member.id)
                    await context.bot.send_message(chat_id, f"{random.choice(FRASES_ANTI_BOT)} ({member.mention_html()})", parse_mode=ParseMode.HTML)
                except: pass
        elif not member.is_bot:
            await ensure_user(member)
            kb = [[InlineKeyboardButton("Soy Mayor de 18", callback_data=f"age_yes:{member.id}")],
                  [InlineKeyboardButton("Soy Menor", callback_data=f"age_no:{member.id}")]]
            await context.bot.send_message(chat_id, f"Mortal {member.mention_html()}, confirma tu edad (+18) para permanecer en el templo.", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def age_verification_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        action, target_id = query.data.split(":")
        target_id = int(target_id)
    except: return await query.answer()

    if query.from_user.id != target_id:
        return await query.answer("No es tu verificación.", show_alert=True)

    await query.answer()
    if action == "age_yes":
        await query.edit_message_text(f"El mortal {query.from_user.mention_html()} ha sido aceptado.", parse_mode=ParseMode.HTML)
    elif action == "age_no":
        try:
            await context.bot.ban_chat_member(query.effective_chat.id, target_id)
            await query.edit_message_text(f"El mortal {query.from_user.mention_html()} ha confesado ser menor. Exiliado.", parse_mode=ParseMode.HTML)
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
        await context.bot.send_message(update.effective_chat.id, f"Abominación {user.mention_html()} silenciada y exiliada.", parse_mode=ParseMode.HTML)
    except: pass


###############################################################################
# BLOQUE 9: EJECUCIÓN PRINCIPAL
###############################################################################

def main() -> None:
    logger.info("Iniciando Mashi (HF Mode)...")
    setup_database()
    application = Application.builder().token(TOKEN).build()
    
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
    application.run_polling()

if __name__ == "__main__":
    main()