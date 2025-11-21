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

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("API Key de Gemini cargada correctamente.")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'mashi_data.db')
ITCH_URL = "https://kai-shitsumon.itch.io/"

ALLOWED_CHATS = [1890046858, -1001504263227] 

# IDs del Sistema de Telegram (Para evitar que Mashi se ataque a sí mismo o al canal)
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
# BLOQUE 4: DECORADORES Y UTILIDADES
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
# BLOQUE 5: COMANDOS PÚBLICOS
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
    if not GEMINI_API_KEY:
        await send_random_choice(update, context, "El pasado es un eco...", RELATOS_DEL_GUARDIAN)
        return
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = "Actúa como Mashi, un dios león guardián antiguo y solemne. Escribe un micro-relato (3 frases) sobre una gloria olvidada."
        response = await model.generate_content_async(prompt)
        await update.message.reply_text(f"📜 *Ecos del Pasado:*\n\n{response.text}", parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await update.message.reply_text("El éter está nublado. Intenta más tarde.")

@restricted_access
async def tienda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Explora las Ofrendas", url=ITCH_URL)]]
    await update.message.reply_text("Entra al santuario de creaciones.", reply_markup=InlineKeyboardMarkup(keyboard))


###############################################################################
# BLOQUE 6: COMANDOS DE ADMINISTRADOR
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
# BLOQUE 7: LÓGICA CONVERSACIONAL Y GESTIÓN DE EVENTOS
###############################################################################

async def conversacion_natural(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cerebro Conversacional: Decide si responder a mensajes normales.
    """
    # 1. Filtros básicos
    if not GEMINI_API_KEY: 
        print("❌ Error: No hay API KEY de Gemini")
        return
    if not update.message or not update.message.text: return
    
    # NOTA: Comenta esta línea si quieres probar en el chat privado contigo mismo
    # if update.effective_chat.id not in ALLOWED_CHATS: return
    
    user = update.effective_user
    msg_text = update.message.text
    
    # Imprimir en consola local para ver qué llega (DEBUG)
    print(f"📩 Mensaje recibido de {user.first_name}: {msg_text}")
    
    # 2. Guardar en memoria a corto plazo
    CHAT_CONTEXT.append(f"{user.first_name}: {msg_text}")

    # 3. ¿Debe responder Mashi?
    
    # A) Si responden a un mensaje de Mashi
    is_reply = (update.message.reply_to_message and 
                update.message.reply_to_message.from_user.id == context.bot.id)
    
    # B) Si el texto contiene palabras clave
    is_keyword = re.search(r"(mashi|guardián|león|mamoru)", msg_text, re.IGNORECASE)

    # C) Si mencionan al bot (@NombreDelBot) - NUEVO
    is_mentioned = False
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type == "mention":
                # Verificar si la mención es para este bot
                # (Telegram a veces lo maneja automático, pero esto ayuda)
                is_mentioned = True
    
    # D) Probabilidad aleatoria (5%)
    random_chance = random.random() < 0.05

    # --- DEBUG: Ver por qué decide hablar ---
    if is_reply: print("✅ Decisión: Es una respuesta a mí.")
    elif is_keyword: print("✅ Decisión: Detecté palabra clave.")
    elif is_mentioned: print("✅ Decisión: Me han mencionado con @.")
    elif random_chance: print("✅ Decisión: Probabilidad aleatoria activada.")
    else: print("❌ Decisión: Ignorar mensaje.")

    if is_reply or is_keyword or is_mentioned or random_chance:
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            
            # Contexto para la IA
            historial = "\n".join(CHAT_CONTEXT)
            print("🤔 Consultando a Gemini...") # DEBUG
            
            prompt = (
                "Eres Mamoru Shishi (Mashi), un dios guardián león antiguo, sabio y algo arrogante pero protector. "
                "Responde al último mensaje del chat. Sé breve (máx 2 frases). "
                "Si te insultan, sé cortante. Si hablan de arte, interésate. "
                f"\n\nCHAT RECIENTE:\n{historial}\n\nTU RESPUESTA:"
            )
            
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = await model.generate_content_async(prompt)
            respuesta = response.text
            
            # Guardar la respuesta propia en el contexto
            CHAT_CONTEXT.append(f"Mashi: {respuesta}")
            
            print(f"🗣️ Respondiendo: {respuesta}") # DEBUG
            await update.message.reply_text(respuesta)
        except Exception as e:
            logger.error(f"Error en conversación: {e}")
            print(f"❌ Error crítico en IA: {e}")

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Expulsa bots mortales, tolera bots admins, verifica edad humanos."""
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
    """Purga reactiva de bots no autorizados."""
    if not update.effective_chat or update.effective_chat.id not in ALLOWED_CHATS: return
    user = update.effective_user
    if not user or user.id in TELEGRAM_SYSTEM_IDS: return
    
    if not user.is_bot or user.id == context.bot.id: return

    try:
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        if user.id in [a.user.id for a in admins]: return
    except: pass

    # Si es bot no admin:
    try:
        await update.message.delete()
        await context.bot.ban_chat_member(update.effective_chat.id, user.id)
        await context.bot.send_message(update.effective_chat.id, f"Abominación {user.mention_html()} silenciada y exiliada.", parse_mode=ParseMode.HTML)
    except: pass


###############################################################################
# BLOQUE 8: EJECUCIÓN PRINCIPAL
###############################################################################

def main() -> None:
    logger.info("Iniciando Mashi...")
    setup_database()
    application = Application.builder().token(TOKEN).build()
    
    # 1. Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("relato", relato))
    application.add_handler(CommandHandler("tienda", tienda))
    application.add_handler(CommandHandler("purificar", purificar))
    application.add_handler(CommandHandler("exilio", exilio))
    
    # 2. Nuevos miembros
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    
    # 3. Botones
    application.add_handler(CallbackQueryHandler(age_verification_handler, pattern="^age_"))
    
    # 4. Conversación Humana (¡NUEVO!) - Debe ir antes que la purga
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), conversacion_natural))
    
    # 5. Purga Reactiva (Bots)
    application.add_handler(MessageHandler(filters.ALL, handle_bot_messages))

    logger.info("Mashi está en línea.")
    application.run_polling()

if __name__ == "__main__":
    main()