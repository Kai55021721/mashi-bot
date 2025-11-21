###############################################################################
# BLOQUE 1: IMPORTS Y CONFIGURACIÓN INICIAL
###############################################################################
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
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

# Carga las variables del archivo .env
load_dotenv()

# Configuración de logging (Registro de eventos)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


###############################################################################
# BLOQUE 2: CONSTANTES Y CONFIGURACIÓN
###############################################################################

# Tokens e IDs
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("ERROR: No se encontró TELEGRAM_TOKEN en el archivo .env")

OWNER_ID_STR = os.environ.get("OWNER_ID")
if not OWNER_ID_STR:
    raise ValueError("ERROR: No se encontró OWNER_ID en el archivo .env")
OWNER_ID = int(OWNER_ID_STR)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("API Key de Gemini cargada correctamente.")

# Rutas de Archivos
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'mashi_data.db')

# URLs Externas
ITCH_URL = "https://kai-shitsumon.itch.io/"

# Listas de Configuración
ALLOWED_CHATS = [1890046858, -1001504263227]  # [ID Maestro Kai, ID El Templo]

# IDs Especiales de Telegram (Canales y Admins Anónimos) - ¡CRUCIAL PARA EVITAR ERRORES!
# 777000 = Telegram Service
# 1087968824 = Group Anonymous Bot
# 136817688 = Channel Bot (Cuando escribes como canal)
TELEGRAM_SYSTEM_IDS = [777000, 1087968824, 136817688]

# Textos de Personalidad (Mashi)
RELATOS_DEL_GUARDIAN = [
    "Los ecos de la gloria pasada resuenan solo para aquellos que saben escuchar el silencio...",
    "Recuerdo imperios de arena y sol que se alzaron y cayeron bajo mi vigilia...",
    "La perseverancia de los mortales es una luz fugaz, pero brillante, en la inmensidad del tiempo.",
    "En las sombras del olvido, las plumas del destino trazan líneas que solo el guardián ve."
]

FRASES_ANTI_BOT = [
    "¡Una abominación sin alma ha profanado este lugar! La luz lo purifica.",
    "Detectada escoria autómata. El código impuro no tiene cabida en mi templo. ¡Desterrado!",
    "¿Una imitación de vida osa entrar en mi presencia? ¡Vuelve al vacío del que te programaron!",
    "Chatarra ruidosa. Mi deber es silenciarte. ¡Exiliado!",
    "Tu presencia es un insulto a la verdadera creación. ¡Purificado!"
]


###############################################################################
# BLOQUE 3: BASE DE DATOS
###############################################################################

def db_safe_run(query, params=(), fetchone=False, commit=False):
    """Ejecuta consultas SQL de forma segura."""
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
    """Crea las tablas si no existen."""
    db_safe_run('CREATE TABLE IF NOT EXISTS subscribers (chat_id INTEGER PRIMARY KEY, username TEXT, joined_at TEXT)')
    db_safe_run('CREATE TABLE IF NOT EXISTS mod_logs (action TEXT, target_id INTEGER, timestamp TEXT)')
    logger.info(f"Base de datos lista en: {DB_FILE}")

async def ensure_user(user: User):
    """Registra al usuario en la BD si es nuevo."""
    if not db_safe_run("SELECT 1 FROM subscribers WHERE chat_id = ?", (user.id,), fetchone=True):
        joined_at = datetime.now().isoformat()
        db_safe_run("INSERT INTO subscribers (chat_id, username, joined_at) VALUES (?, ?, ?)", 
                    (user.id, user.username or user.first_name, joined_at), commit=True)
        logger.info(f"Nuevo mortal registrado: {user.id} ({user.username})")


###############################################################################
# BLOQUE 4: DECORADORES Y UTILIDADES
###############################################################################

def restricted_access(func):
    """Solo permite usar el comando en los chats permitidos."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        if not chat or chat.id not in ALLOWED_CHATS:
            logger.warning(f"Acceso denegado al chat {chat.id if chat else 'privado'} para {func.__name__}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def owner_only(func):
    """Solo permite usar el comando al dueño (Maestro Kai)."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id == OWNER_ID:
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text("Mis asuntos son solo con el maestro Kai.")
    return wrapped

async def send_random_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, intro_text: str, choices: list):
    """Envía un texto aleatorio de una lista."""
    chosen_item = random.choice(choices)
    await update.message.reply_text(f"{intro_text}\n\n{chosen_item}")


###############################################################################
# BLOQUE 5: COMANDOS PÚBLICOS
###############################################################################

@restricted_access
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await ensure_user(user)
    
    texto_bienvenida = (
        f"🛕 *Bienvenido al Templo de Mashi, mortal {user.mention_markdown()}.*\n\n"
        "Yo, el Guardián Erudito Caído, custodio este refugio de sabiduría e inspiración artística.\n"
        "Explora mis dones:\n"
        "• 📜 /relato - Historias del olvido.\n"
        "• 🛒 /tienda - Ofrendas en itch.io.\n\n"
        "Habla con respeto. La luz guía a los dignos."
    )
    
    keyboard = [[InlineKeyboardButton("🛒 Tienda", url=ITCH_URL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(texto_bienvenida, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

@restricted_access
async def relato(update: Update, context: ContextTypes.DEFAULT_TYPE):    
    if not GEMINI_API_KEY:
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
async def tienda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Explora las Ofrendas", web_app=WebAppInfo(url=ITCH_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    texto = "Entra al santuario de creaciones del guardián. Adquiere visiones eternas."
    await update.message.reply_text(texto, reply_markup=reply_markup)


###############################################################################
# BLOQUE 6: COMANDOS DE ADMINISTRADOR
###############################################################################

@owner_only
@restricted_access
async def purificar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Borra el mensaje respondido y el comando."""
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
    """Banea al usuario respondido."""
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


###############################################################################
# BLOQUE 7: GESTIÓN DE EVENTOS Y ANTI-BOT
###############################################################################

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    1. Expulsa bots añadidos por mortales.
    2. Tolera bots añadidos por admins.
    3. Inicia verificación de edad para humanos.
    """
    if update.effective_chat.id not in ALLOWED_CHATS: return

    new_members = update.message.new_chat_members
    chat_id = update.effective_chat.id
    
    # Obtener admins para saber quién añadió al bot
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
    except Exception as e:
        logger.error(f"No se pudo obtener lista de admins: {e}")
        admin_ids = [OWNER_ID]

    adder = update.message.from_user
    
    for member in new_members:
        # CASO A: ES UN BOT
        if member.is_bot and member.id != context.bot.id:
            if adder.id in admin_ids:
                # Bot añadido por Admin -> Permitir
                logger.info(f"Bot admin {member.username} permitido.")
                await context.bot.send_message(
                    chat_id, 
                    f"He notado que el administrador {adder.mention_html()} ha convocado a un sirviente autómata, {member.mention_html()}. Su presencia es tolerada... por ahora.", 
                    parse_mode=ParseMode.HTML
                )
            else:
                # Bot añadido por Mortal -> Expulsar
                logger.info(f"Bot {member.username} expulsado.")
                try:
                    await context.bot.ban_chat_member(chat_id, member.id)
                    insulto = random.choice(FRASES_ANTI_BOT)
                    await context.bot.send_message(chat_id, f"{insulto} El bot {member.mention_html()} ha sido purificado.", parse_mode=ParseMode.HTML)
                    db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                                ("bot_exiliado", member.id, datetime.now().isoformat()), commit=True)
                except Exception as e:
                    logger.error(f"Fallo al expulsar bot: {e}")

        # CASO B: ES UN HUMANO
        elif not member.is_bot:
            await ensure_user(member)
            texto_verificacion = (
                f"Mortal {member.mention_html()}, bienvenido al templo.\n\n"
                "Este es un refugio para la creación artística, pero sus ecos no son para oídos infantiles. "
                "Confirma que eres mayor de 18 años para permanecer en este lugar sagrado."
            )
            keyboard = [
                [InlineKeyboardButton("Soy Mayor de 18", callback_data=f"age_verify_yes:{member.id}")],
                [InlineKeyboardButton("Soy Menor", callback_data=f"age_verify_no:{member.id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id, texto_verificacion, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def age_verification_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los botones de Soy Mayor / Soy Menor."""
    query = update.callback_query
    try:
        action, target_user_id_str = query.data.split(":")
        target_user_id = int(target_user_id_str)
    except ValueError:
        await query.answer()
        return

    # Seguridad: Solo el usuario aludido puede clicar
    if query.from_user.id != target_user_id:
        await query.answer("Esta no es tu verificación, mortal. No interfieras.", show_alert=True)
        return

    await query.answer()

    if action == "age_verify_yes":
        await query.edit_message_text(
            f"El mortal {query.from_user.mention_html()} ha sido verificado.\n\nSu presencia es aceptada en el templo.",
            parse_mode=ParseMode.HTML,
            reply_markup=None
        )
    elif action == "age_verify_no":
        try:
            await context.bot.ban_chat_member(query.effective_chat.id, target_user_id)
            await query.edit_message_text(
                f"El mortal {query.from_user.mention_html()} ha confesado ser menor.\n\nEste refugio no es para ellos. Han sido exiliados.",
                parse_mode=ParseMode.HTML,
                reply_markup=None
            )
            db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                        ("age_fail_kick", target_user_id, datetime.now().isoformat()), commit=True)
        except Exception as e:
            await query.edit_message_text("El exilio ha fallado. Maestro, revisa mis permisos.", reply_markup=None)

async def handle_bot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    PURGA REACTIVA: Si un bot habla, se borra y se banea.
    ¡CORREGIDO PARA IGNORAR AL SISTEMA DE TELEGRAM!
    """
    if not update.effective_chat or update.effective_chat.id not in ALLOWED_CHATS: return
    user = update.effective_user
    if not user: return
    
    # --- CORRECCIÓN CRÍTICA: IGNORAR TELEGRAM Y ADMINS ANÓNIMOS ---
    if user.id in TELEGRAM_SYSTEM_IDS:
        return 

    # Ignorar humanos y a Mashi mismo
    if not user.is_bot or user.id == context.bot.id:
        return

    # Verificar si el bot es admin
    chat_id = update.effective_chat.id
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        if user.id in admin_ids:
            return # Es un bot admin, déjalo hablar
    except Exception:
        return # Si falla la verificación, mejor no hacer nada por seguridad

    # Si llegamos aquí, es un bot no autorizado hablando -> PURGAR
    logger.info(f"Detectado bot intruso {user.username} hablando. Purgando.")
    try:
        await update.message.delete()
        await context.bot.ban_chat_member(chat_id, user.id)
        await context.bot.send_message(chat_id, f"Una abominación ({user.mention_html()}) se atrevió a hablar sin permiso. Ha sido purificada y exiliada.", parse_mode=ParseMode.HTML)
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                    ("bot_hablador_exiliado", user.id, datetime.now().isoformat()), commit=True)
    except Exception as e:
        logger.error(f"No se pudo purgar al bot hablador: {e}")


###############################################################################
# BLOQUE 8: EJECUCIÓN PRINCIPAL
###############################################################################

def main() -> None:
    logger.info("Iniciando Mashi (Modo Guardián)...")
    setup_database()

    application = Application.builder().token(TOKEN).build()
    
    # 1. Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("relato", relato))
    application.add_handler(CommandHandler("tienda", tienda))
    application.add_handler(CommandHandler("purificar", purificar))
    application.add_handler(CommandHandler("exilio", exilio))
    
    # 2. Eventos de entrada (Nuevos miembros)
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    
    # 3. Botones (Verificación edad)
    application.add_handler(CallbackQueryHandler(age_verification_handler, pattern="^age_verify_"))
    
    # 4. Purga Reactiva (Cualquier mensaje que no sea comando)
    application.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), handle_bot_messages))

    logger.info("El bot Mashi está en línea y vigilando.")
    application.run_polling()

if __name__ == "__main__":
    main()