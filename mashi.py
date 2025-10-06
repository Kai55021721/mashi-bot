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

OWNER_ID = 1890046858 # ID del Maestro Kai

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'mashi_data_v2.db')

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
    db_safe_run('CREATE TABLE IF NOT EXISTS scores (id INTEGER PRIMARY KEY, user_id INTEGER, username TEXT, score INTEGER, level INTEGER, timestamp TEXT)')
    logger.info(f"Base de datos preparada en la ruta: {DB_FILE}")

async def ensure_user(user: User, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db_safe_run("SELECT 1 FROM subscribers WHERE chat_id = ?", (user.id,), fetchone=True):
        joined_at = datetime.now().isoformat()
        db_safe_run("INSERT INTO subscribers (chat_id, username, joined_at) VALUES (?, ?, ?)", 
                    (user.id, user.username or user.first_name, joined_at), commit=True)
        logger.info(f"Nuevo mortal {user.id} ({user.username}) ha entrado al templo.")

# --- 3. DECORADORES ---
def owner_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id == OWNER_ID:
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text("Mis asuntos son solo con el maestro Kai.")
    return wrapped

# --- 4. MANEJADORES DE COMANDOS ---
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
        "• 🎮 /juego - Defiende el templo de invasores.\n\n"
        "Habla con respeto. La luz guía a los dignos."
    )
    
    keyboard = [[InlineKeyboardButton("🛒 Tienda", web_app=WebAppInfo(url=ITCH_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(texto_bienvenida, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def relato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_relato = "El pasado es un eco. Presta atención, y quizás escuches uno de sus susurros.\n\n" + random.choice(RELATOS_DEL_GUARDIAN)
    await update.message.reply_text(texto_relato)

async def chiste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_chiste = "El silencio es sagrado, pero incluso un guardián puede permitirse una ligera distorsión de la realidad.\n\n" + random.choice(CHISTES_DEL_GUARDIAN)
    await update.message.reply_text(texto_chiste)

async def inspiracion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = random.choice(PROMPTS_INSPIRACION)
    texto = f"Inspiración del guardián: {prompt}. Que tu pluma capture su esencia."
    await update.message.reply_text(texto)

async def paleta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    paleta = random.choice(PALETAS_COLOR)
    texto = f"Paleta del templo: {paleta}. Usa estos tonos para invocar visiones."
    await update.message.reply_text(texto)

async def idea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idea = random.choice(IDEAS_RAPIDAS)
    texto = f"Idea fugaz: {idea}. Dibújala antes de que el velo la reclame."
    await update.message.reply_text(texto)

async def tienda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Explora las Ofrendas", web_app=WebAppInfo(url=ITCH_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    texto = "Entra al santuario de creaciones del guardián. Adquiere visiones eternas."
    await update.message.reply_text(texto, reply_markup=reply_markup)

async def juego(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎮 Jugar Invaders del Guardián", web_app=WebAppInfo(url=ITCH_URL))]]  # Usa URL de itch.io del juego
    reply_markup = InlineKeyboardMarkup(keyboard)
    texto = "¡Defiende el templo estelar de la invasión! Muestra tu valor, mortal."
    await update.message.reply_text(texto, reply_markup=reply_markup)

async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.effective_message.web_app_data.data
    try:
        score_data = json.loads(data)
        user = update.effective_user
        db_safe_run("INSERT INTO scores (user_id, username, score, level, timestamp) VALUES (?, ?, ?, ?, ?)", 
                    (user.id, user.username or user.first_name, score_data.get('score', 0), score_data.get('level', 1), datetime.now().isoformat()), commit=True)
        await update.message.reply_text(f"¡Puntuación {score_data.get('score', 0)} guardada en el templo, {user.mention_html()}! Nivel {score_data.get('level', 1)}. La luz te bendice.", parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error guardando score: {e}")
        await update.message.reply_text("Error al guardar. Intenta de nuevo.")
    
@owner_only
async def purificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Maestro, debe responder al mensaje que considera una impureza para que pueda purificarlo.")
        return
    
    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="La luz purifica. Una sombra ha sido desterrada de este lugar sagrado."
        )
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                    ("purificar", update.message.reply_to_message.from_user.id, datetime.now().isoformat()), commit=True)

    except Exception as e:
        logger.error(f"No se pudo purificar el mensaje: {e}")
        await update.message.reply_text("La impureza se resiste a la luz. Revisa mis permisos de administrador.")

@owner_only
async def exilio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("Maestro, responde al hereje para exiliarlo.")
        return
    target = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await update.message.delete()
        msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"El hereje {target.mention_html()} ha sido exiliado del templo.", parse_mode=ParseMode.HTML)
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                    ("exilio", target.id, datetime.now().isoformat()), commit=True)
    except Exception as e:
        logger.error(f"Error en exilio: {e}")
        await update.message.reply_text("El exilio falla. Verifica permisos.")

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
        CommandHandler("juego", juego),
        CommandHandler("purificar", purificar),
        CommandHandler("exilio", exilio),
    ]
    application.add_handlers(command_handlers)
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))

    logger.info("El bot Mashi está en línea y vigilando.")
    application.run_polling()

if __name__ == "__main__":
    main()