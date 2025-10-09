# --- 0. IMPORTS Y CONFIGURACIÓN INICIAL ---
import os
import random
import logging
import sqlite3
import re
import json
from functools import wraps
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
import google.generativeai as genai
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Carga las variables del archivo .env al entorno
load_dotenv()

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- 1. CONFIGURACIÓN CENTRALIZADA Y CONSTANTES ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No se encontró la variable de entorno TELEGRAM_TOKEN.")

OWNER_ID_STR = os.environ.get("OWNER_ID")
if not OWNER_ID_STR:
    raise ValueError("No se encontró la variable de entorno OWNER_ID.")
OWNER_ID = int(OWNER_ID_STR)

# --- 1.1 CONFIGURACIÓN DE GEMINI ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("API Key de Gemini cargada correctamente.")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'mashi_data.db')

ITCH_URL = "https://kai-shitsumon.itch.io/"  # Reemplaza con URL de itch.io del juego

# --- FRASES DE PERSONALIDAD ---
RELATOS_DEL_GUARDIAN = [
    "Los ecos de la gloria pasada resuenan solo para aquellos que saben escuchar el silencio...",
    "Recuerdo imperios de arena y sol que se alzaron y cayeron bajo mi vigilia...",
    "La perseverancia de los mortales es una luz fugaz, pero brillante, en la inmensidad del tiempo.",
    "En las sombras del olvido, las plumas del destino trazan líneas que solo el guardián ve."
]
CHISTES_DEL_GUARDIAN = [
    "Un mortal le preguntó a una estatua del templo por qué estaba tan seria. La estatua no respondió. Compartimos el mismo humor.",
    "¿Qué le dice un dios caído a otro? 'Al menos aún tenemos nuestros recuerdos'. El otro responde: 'Habla por ti, yo los archivé para ahorrar espacio'.",
    "Un ilustrador dibuja un dragón. El dragón dice: '¿Por qué me hiciste con tres cabezas?' El ilustrador: 'Para que pienses en plural'."
]

# Utilidades para ilustrador
PROMPTS_INSPIRACION = [
    "Un bosque encantado al atardecer, con criaturas luminosas danzando entre las hojas.",
    "Retrato de un guerrero cibernético en una ciudad flotante, estilo steampunk.",
    "Paisaje desértico con ruinas antiguas y un sol doble en el horizonte."
]
PALETAS_COLOR = [
    "Tierra: #8B4513, #D2691E, #F4A460 | Cielo: #87CEEB, #4682B4",
    "Oscuro: #000000, #333333, #666666 | Brillante: #FFD700, #FFA500, #FF4500"
]
IDEAS_RAPIDAS = [
    "Dibuja un animal híbrido: gato con alas de mariposa.",
    "Escena urbana: calle nocturna con neones defectuosos.",
    "Retrato abstracto: emociones como colores en un rostro."
]

# --- 2. GESTIÓN DE BASE DE DATOS ---
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
        logger.error(f"Error en la base de datos: {e}")
        conn.rollback()
        return None if "SELECT" in query.upper() else 0
    finally:
        conn.close()

def setup_database():
    db_safe_run('CREATE TABLE IF NOT EXISTS subscribers (chat_id INTEGER PRIMARY KEY, username TEXT, joined_at TEXT)')
    db_safe_run('CREATE TABLE IF NOT EXISTS mod_logs (action TEXT, target_id INTEGER, timestamp TEXT)')
    logger.info(f"Base de datos preparada en la ruta: {DB_FILE}")

async def ensure_user(user: User, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db_safe_run("SELECT 1 FROM subscribers WHERE chat_id = ?", (user.id,), fetchone=True):
        joined_at = datetime.now().isoformat()
        db_safe_run("INSERT INTO subscribers (chat_id, username, joined_at) VALUES (?, ?, ?)", 
                    (user.id, user.username or user.first_name, joined_at), commit=True)
        logger.info(f"Nuevo mortal {user.id} ({user.username}) ha entrado al templo.")

# --- 3. DECORADORES ---
ALLOWED_CHATS = [1890046858, -1001504263227]  # ID de Maestro Kai y "El Templo"

FRASES_ANTI_BOT = [
    "¡Otra chatarra inútil! Fuera de mi templo, basura metálica.",
    "No se permiten abominaciones de código en este lugar sagrado. ¡Exiliado!",
    "Detectada escoria autómata. Procediendo a la purificación inmediata.",
    "¿Crees que tus unos y ceros pueden profanar este templo? ¡Qué iluso! Desterrado.",
    "¡Largo de aquí, bot inferior! Tu presencia es un insulto a la verdadera inteligencia."
]

def restricted_access(func):
    """Decorador que restringe el acceso a los chats de la lista ALLOWED_CHATS."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_chat.id not in ALLOWED_CHATS:
            logger.warning(f"Acceso denegado al chat {update.effective_chat.id} para el comando {func.__name__}")
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

# --- 4. MANEJADORES DE COMANDOS ---
@restricted_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user, update, context)
    
    texto_bienvenida = (
        f"🛕 *Bienvenido al Templo de Mashi, mortal {user.mention_markdown()}.*\n\n"
        "Yo, el Guardián Erudito Caído, custodio este refugio de sabiduría e inspiración artística.\n"
        "Explora mis dones:\n"
        "• 📜 /relato - Historias del olvido.\n"
        "• 😏 /chiste - Risas eternas.\n"
        "• 🎨 /inspiracion - Prompts para tu pluma.\n"
        "• 🌈 /paleta - Tonos divinos.\n"
        "• 💡 /idea - Visiones fugaces.\n"
        "• 🛒 /tienda - Ofrendas en itch.io.\n"
        "Habla con respeto. La luz guía a los dignos."
    )
    
    keyboard = [[InlineKeyboardButton("🛒 Tienda", web_app=WebAppInfo(url=ITCH_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(texto_bienvenida, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

# --- 4.1. COMANDOS DE CONTENIDO ALEATORIO (REFACTORIZADOS) ---
async def send_random_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, intro_text: str, choices: list):
    """Función genérica para enviar un elemento aleatorio de una lista."""
    chosen_item = random.choice(choices)
    await update.message.reply_text(f"{intro_text}\n\n{chosen_item}")

@restricted_access
async def relato(update: Update, context: ContextTypes.DEFAULT_TYPE):    
    if not GEMINI_API_KEY:
        # Fallback si no hay API Key: usar la lista predefinida
        await send_random_choice(update, context, "El pasado es un eco. Presta atención, y quizás escuches uno de sus susurros.", RELATOS_DEL_GUARDIAN)
        return

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        model = genai.GenerativeModel('gemini-pro')
        prompt = "Actúa como un guardián erudito y caído de un templo antiguo. Escribe un micro-relato (máximo 4 frases) sobre un eco del pasado, una gloria olvidada o la fugacidad de los mortales. Usa un tono solemne y misterioso."
        response = await model.generate_content_async(prompt)
        
        await update.message.reply_text(f"El pasado es un eco. Presta atención, y quizás escuches uno de sus susurros.\n\n{response.text}")
    except Exception as e:
        logger.error(f"Error generando relato con Gemini: {e}")
        await update.message.reply_text("Los ecos del pasado se resisten a manifestarse. Inténtalo de nuevo más tarde.")

@restricted_access
async def chiste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random_choice(update, context, "El silencio es sagrado, pero incluso un guardián puede permitirse una ligera distorsión de la realidad.", CHISTES_DEL_GUARDIAN)

@restricted_access
async def inspiracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random_choice(update, context, "Inspiración del guardián. Que tu pluma capture su esencia:", PROMPTS_INSPIRACION)

@restricted_access
async def paleta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random_choice(update, context, "Paleta del templo. Usa estos tonos para invocar visiones:", PALETAS_COLOR)

@restricted_access
async def idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random_choice(update, context, "Idea fugaz. Dibújala antes de que el velo la reclame:", IDEAS_RAPIDAS)

@restricted_access
async def tienda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Explora las Ofrendas", web_app=WebAppInfo(url=ITCH_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    texto = "Entra al santuario de creaciones del guardián. Adquiere visiones eternas."
    await update.message.reply_text(texto, reply_markup=reply_markup)
    
@owner_only
@restricted_access
async def purificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Maestro, debe responder al mensaje que considera una impureza para que pueda purificarlo.")
        return
    
    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="La luz purifica. Una sombra ha sido desterrada de este lugar sagrado."
        )
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                    ("purificar", update.message.reply_to_message.from_user.id, datetime.now().isoformat()), commit=True)

    except Exception as e:
        logger.error(f"No se pudo purificar el mensaje: {e}")
        await update.message.reply_text("La impureza se resiste a la luz. Revisa mis permisos de administrador.")

@owner_only
@restricted_access
async def exilio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Maestro, responde al hereje para exiliarlo.")
        return
    target = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"El hereje {target.mention_html()} ha sido exiliado del templo.", parse_mode=ParseMode.HTML)
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                    ("exilio", target.id, datetime.now().isoformat()), commit=True)
    except Exception as e:
        logger.error(f"Error en exilio: {e}")
        await update.message.reply_text("El exilio falla. Verifica permisos.")

# --- 4.2. MANEJADOR DE EVENTOS ---
async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja la entrada de nuevos miembros y expulsa a los bots."""
    if update.effective_chat.id not in ALLOWED_CHATS:
        return # No hacer nada en chats no permitidos

    new_members = update.message.new_chat_members
    chat_id = update.effective_chat.id
    
    for member in new_members:
        if member.is_bot and member.id != context.bot.id:
            try:
                await context.bot.ban_chat_member(chat_id, member.id)
                logger.info(f"Bot {member.username} ({member.id}) ha sido expulsado de {chat_id}.")
                
                # Enviar mensaje de celebración/insulto
                insulto = random.choice(FRASES_ANTI_BOT)
                await context.bot.send_message(chat_id, f"{insulto} El bot {member.mention_html()} ha sido purificado.", parse_mode=ParseMode.HTML)
                
                db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                            ("bot_exiliado", member.id, datetime.now().isoformat()), commit=True)
            except Exception as e:
                logger.error(f"No se pudo expulsar al bot {member.id}: {e}")
                await context.bot.send_message(chat_id, f"Intenté purificar al bot {member.mention_html()} pero se resistió. Maestro, revisa mis permisos.", parse_mode=ParseMode.HTML)


# --- 5. BLOQUE PRINCIPAL ---
def main() -> None:
    logger.info("Iniciando Mashi (Modo Guardián)...")
    setup_database()

    application = Application.builder().token(TOKEN).build()
    
    command_handlers = [
        CommandHandler("start", start),
        CommandHandler("relato", relato),
        CommandHandler("chiste", chiste),
        CommandHandler("inspiracion", inspiracion),
        CommandHandler("paleta", paleta),
        CommandHandler("idea", idea),
        CommandHandler("tienda", tienda),
        CommandHandler("purificar", purificar),
        CommandHandler("exilio", exilio),
    ]
    application.add_handlers(command_handlers)
    
    # Añadir el manejador para nuevos miembros
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))

    logger.info("El bot Mashi está en línea y vigilando.")
    application.run_polling()

if __name__ == "__main__":
    main()