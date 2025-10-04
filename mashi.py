# --- 0. IMPORTS Y CONFIGURACIÓN INICIAL ---
import os
import random
import logging
import sqlite3
import re
from functools import wraps

from dotenv import load_dotenv
from telegram import Update, User
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes

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

# --- FRASES DE PERSONALIDAD ---
RELATOS_DEL_GUARDIAN = [
    "Los ecos de la gloria pasada resuenan solo para aquellos que saben escuchar el silencio...",
    "Recuerdo imperios de arena y sol que se alzaron y cayeron bajo mi vigilia...",
    "La perseverancia de los mortales es una luz fugaz, pero brillante, en la inmensidad del tiempo."
]
CHISTES_DEL_GUARDIAN = [
    "Un mortal le preguntó a una estatua del templo por qué estaba tan seria. La estatua no respondió. Compartimos el mismo humor.",
    "¿Qué le dice un dios caído a otro? 'Al menos aún tenemos nuestros recuerdos'. El otro responde: 'Habla por ti, yo los archivé para ahorrar espacio'."
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
    db_safe_run('CREATE TABLE IF NOT EXISTS subscribers (chat_id INTEGER PRIMARY KEY, username TEXT)')
    logger.info(f"Base de datos preparada en la ruta: {DB_FILE}")

async def ensure_user(user: User):
    if not db_safe_run("SELECT 1 FROM subscribers WHERE chat_id = ?", (user.id,), fetchone=True):
        db_safe_run("INSERT INTO subscribers (chat_id, username) VALUES (?, ?)", (user.id, user.username or user.first_name), commit=True)
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
    await ensure_user(user)
    
    texto_bienvenida = (
        f"He notado tu presencia, mortal {user.mention_markdown()}.\n\n"
        "Este es mi templo. Un refugio del conocimiento custodiado por mí, el Guardián Mashi. "
        "Habla con respeto y quizás encuentres la sabiduría que buscas."
    )
    await update.message.reply_text(texto_bienvenida, parse_mode=ParseMode.MARKDOWN)

async def relato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_relato = "El pasado es un eco. Presta atención, y quizás escuches uno de sus susurros.\n\n" + random.choice(RELATOS_DEL_GUARDIAN)
    await update.message.reply_text(texto_relato)

async def chiste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_chiste = "El silencio es sagrado, pero incluso un guardián puede permitirse una ligera distorsión de la realidad.\n\n" + random.choice(CHISTES_DEL_GUARDIAN)
    await update.message.reply_text(texto_chiste)
    
@owner_only
async def purificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ Habilidad 'Luz Purificadora': Borra un mensaje respondido. """
    if not update.message.reply_to_message:
        await update.message.reply_text("Maestro, debe responder al mensaje que considera una impureza para que pueda purificarlo.")
        return
    
    try:
        await update.message.reply_to_message.delete()
        # Se borra también el comando para mantener la limpieza
        await update.message.delete()
        
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="La luz purifica. Una sombra ha sido desterrada de este lugar sagrado."
        )
        # Opcional: borrar el mensaje de confirmación después de unos segundos
        # await asyncio.sleep(5)
        # await msg.delete()

    except Exception as e:
        logger.error(f"No se pudo purificar el mensaje: {e}")
        await update.message.reply_text("La impureza se resiste a la luz. Revisa mis permisos de administrador.")

# --- 5. BLOQUE PRINCIPAL ---
def main() -> None:
    logger.info("Iniciando Mashi (Modo Guardián)...")
    setup_database()

    application = Application.builder().token(TOKEN).build()
    
    # Comandos con personalidad
    command_handlers = [
        CommandHandler("start", start),
        CommandHandler("relato", relato),
        CommandHandler("chiste", chiste),
        CommandHandler("purificar", purificar),
    ]
    application.add_handlers(command_handlers)

    logger.info("El bot Mashi está en línea y vigilando.")
    application.run_polling()

if __name__ == "__main__":
    main()