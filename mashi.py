# --- 0. IMPORTS Y CONFIGURACIÓN INICIAL ---
import os
import random
import logging
import sqlite3
import re
import json
from functools import wraps
from datetime import datetime
from time import time
from dotenv import load_dotenv
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
import google.generativeai as genai
# Se añade CallbackQueryHandler para los botones
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

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

ITCH_URL = "https://kai-shitsumon.itch.io/"

# --- FRASES DE PERSONALIDAD ---
RELATOS_DEL_GUARDIAN = [
    "Los ecos de la gloria pasada resuenan solo para aquellos que saben escuchar el silencio...",
    "Recuerdo imperios de arena y sol que se alzaron y cayeron bajo mi vigilia...",
    "La perseverancia de los mortales es una luz fugaz, pero brillante, en la inmensidad del tiempo.",
    "En las sombras del olvido, las plumas del destino trazan líneas que solo el guardián ve."
]

# --- NUEVA LISTA DE INSULTOS ANTI-BOT ---
FRASES_ANTI_BOT = [
    "¡Una abominación sin alma ha profanado este lugar! La luz lo purifica.",
    "Detectada escoria autómata. El código impuro no tiene cabida en mi templo. ¡Desterrado!",
    "¿Una imitación de vida osa entrar en mi presencia? ¡Vuelve al vacío del que te programaron!",
    "Chatarra ruidosa. Mi deber es silenciarte. ¡Exiliado!",
    "Tu presencia es un insulto a la verdadera creación. ¡Purificado!"
]

# --- 2. GESTIÓN DE BASE DE DATOS ---
def db_safe_run(query, params=(), fetchone=False, commit=False):
    # (El código de esta función no cambia)
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
    db_safe_run('CREATE TABLE IF NOT EXISTS relatos_generados (id INTEGER PRIMARY KEY AUTOINCREMENT, relato_texto TEXT NOT NULL, timestamp TEXT NOT NULL)')
    logger.info(f"Base de datos preparada en la ruta: {DB_FILE}")

async def ensure_user(user: User):
    """Asegura que un usuario esté en la base de datos usando INSERT OR IGNORE para eficiencia."""
    joined_at = datetime.now().isoformat()
    username = user.username or user.first_name
    
    rows_affected = db_safe_run(
        "INSERT OR IGNORE INTO subscribers (chat_id, username, joined_at) VALUES (?, ?, ?)",
        (user.id, username, joined_at),
        commit=True
    )
    if rows_affected:
        logger.info(f"Nuevo mortal {user.id} ({username}) ha entrado al templo y ha sido registrado.")

# --- 3. DECORADORES ---
ALLOWED_CHATS = [1890046858, -1001504263227]  # ID de Maestro Kai y "El Templo"

def restricted_access(func):
    """Decorador que restringe el acceso a los chats de la lista ALLOWED_CHATS."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        chat = update.effective_chat
        if not chat or chat.id not in ALLOWED_CHATS:
            logger.warning(f"Acceso denegado al chat {chat.id if chat else 'privado'} para el comando {func.__name__}")
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

# --- 3.1 FUNCIONES DE AYUDA ---
async def get_admin_ids(chat_id: int, context: ContextTypes.DEFAULT_TYPE, cache_duration_seconds: int = 300) -> list[int]:
    """
    Obtiene los IDs de los administradores del chat, usando un caché para evitar llamadas excesivas a la API.
    """
    now = time()
    cache_key = f"admin_ids_{chat_id}"
    
    # Comprobar si hay datos en caché y si no han expirado
    if cache_key in context.chat_data and (now - context.chat_data[cache_key]['timestamp'] < cache_duration_seconds):
        logger.info(f"Usando lista de admins en caché para el chat {chat_id}.")
        return context.chat_data[cache_key]['data']

    logger.info(f"Refrescando lista de admins para el chat {chat_id}.")
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        context.chat_data[cache_key] = {'timestamp': now, 'data': admin_ids}
        return admin_ids
    except Exception as e:
        logger.error(f"No se pudo obtener la lista de admins para el chat {chat_id}: {e}")
        return [OWNER_ID] # Fallback de seguridad

# --- 4. MANEJADORES DE COMANDOS ---
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
    
    keyboard = [[InlineKeyboardButton("🛒 Tienda", web_app=WebAppInfo(url=ITCH_URL))]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(texto_bienvenida, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

@restricted_access
async def relato(update: Update, context: ContextTypes.DEFAULT_TYPE):    
    if not GEMINI_API_KEY:
        await send_random_choice(update, context, "El pasado es un eco. Presta atención, y quizás escuches uno de sus susurros.", RELATOS_DEL_GUARDIAN)
        return

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = "Actúa como un guardián erudito y caído de un templo antiguo. Escribe un micro-relato (máximo 4 frases) sobre un eco del pasado, una gloria olvidada o la fugacidad de los mortales. Usa un tono solemne y misterioso."
        response = await model.generate_content_async(prompt)
        
        # --- GUARDAR RELATO EN LA BASE DE DATOS ---
        db_safe_run(
            "INSERT INTO relatos_generados (relato_texto, timestamp) VALUES (?, ?)",
            (response.text, datetime.now().isoformat()),
            commit=True
        )
        logger.info("Nuevo relato de Gemini guardado en la base de datos.")
        # -----------------------------------------

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
    
@owner_only
@restricted_access
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
        # Opcional: Borrar el mensaje de confirmación después de unos segundos
        # await asyncio.sleep(5)
        # await msg.delete()
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
    """Maneja la entrada de nuevos miembros, expulsa bots Y VERIFICA EDAD."""
    if update.effective_chat.id not in ALLOWED_CHATS: return

    new_members = update.message.new_chat_members
    chat_id = update.effective_chat.id
    
    # --- Obtener lista de Admins (una sola vez) ---
    admin_ids = await get_admin_ids(chat_id, context)

    # Quién añadió a los miembros
    adder = update.message.from_user
    
    for member in new_members:
        if member.is_bot and member.id != context.bot.id:
            # --- Lógica Anti-Bot MEJORADA ---
            if adder.id in admin_ids:
                # Bot añadido por un admin: Se permite
                logger.info(f"Bot {member.username} fue añadido por el admin {adder.username}. Se permite.")
                await context.bot.send_message(
                    chat_id, 
                    f"He notado que el administrador {adder.mention_html()} ha convocado a un sirviente autómata, {member.mention_html()}. Su presencia es tolerada... por ahora.", 
                    parse_mode=ParseMode.HTML
                )
            else:
                # Bot añadido por un mortal: Se purifica
                logger.info(f"Bot {member.username} fue añadido por un mortal {adder.username}. ¡Expulsando!")
                try:
                    await context.bot.ban_chat_member(chat_id, member.id)
                    insulto = random.choice(FRASES_ANTI_BOT)
                    await context.bot.send_message(chat_id, f"{insulto} El bot {member.mention_html()} (añadido por un mortal) ha sido purificado.", parse_mode=ParseMode.HTML)
                    db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                                ("bot_exiliado", member.id, datetime.now().isoformat()), commit=True)
                except Exception as e:
                    logger.error(f"No se pudo expulsar al bot {member.id}: {e}")
                    await context.bot.send_message(chat_id, f"Intenté purificar al bot {member.mention_html()} pero se resistió. Maestro, revisa mis permisos.", parse_mode=ParseMode.HTML)
        
        elif not member.is_bot:
            # --- Lógica de Verificación de Edad (sin cambios) ---
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

# --- 4.3. MANEJADOR DE BOTONES (VERIFICACIÓN DE EDAD) ---
async def age_verification_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja las respuestas de los botones de verificación de edad."""
    query = update.callback_query
    
    try:
        action, target_user_id_str = query.data.split(":")
        target_user_id = int(target_user_id_str)
    except ValueError:
        logger.warning(f"CallbackQuery con formato incorrecto: {query.data}")
        await query.answer()
        return

    if query.from_user.id != target_user_id:
        await query.answer("Esta no es tu verificación, mortal. No interfieras.", show_alert=True)
        return

    await query.answer() 

    if action == "age_verify_yes":
        logger.info(f"Usuario {target_user_id} verificado como mayor de edad.")
        await query.edit_message_text(
            f"El mortal {query.from_user.mention_html()} ha sido verificado.\n\nSu presencia es aceptada en el templo.",
            parse_mode=ParseMode.HTML,
            reply_markup=None
        )
    elif action == "age_verify_no":
        logger.info(f"Usuario {target_user_id} confesó ser menor. Expulsando.")
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
            logger.error(f"Error al expulsar a {target_user_id} por edad: {e}")
            await query.edit_message_text("El exilio ha fallado. Maestro, revisa mis permisos.", reply_markup=None)

# --- 4.4. NUEVA FUNCIÓN: PURGA REACTIVA DE BOTS ---
async def handle_bot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detecta bots que hablan y los purga si no son admins."""
    
    # Salir si el chat no está en la lista o si no hay mensaje/usuario
    if not update.effective_chat or update.effective_chat.id not in ALLOWED_CHATS: return
    user = update.effective_user
    if not user: return
    
    # Ignorar humanos y a sí mismo
    if not user.is_bot or user.id == context.bot.id:
        return

    chat_id = update.effective_chat.id

    # Revisar si el bot que habla es un admin
    admin_ids = await get_admin_ids(chat_id, context)
    if user.id in admin_ids:
        logger.info(f"El bot admin {user.username} habló. Ignorando.")
        return # El bot que habló es un admin, se le permite

    # --- Si llega aquí, es un bot no-admin que habló. ¡PURIFICAR! ---
    logger.info(f"Detectado bot no-admin {user.username} hablando. ¡Purgando!")
    try:
        # Borrar el mensaje ofensivo
        await update.message.delete()
        # Banear al bot
        await context.bot.ban_chat_member(chat_id, user.id)
        await context.bot.send_message(chat_id, f"Una abominación ({user.mention_html()}) se atrevió a hablar sin permiso. Ha sido purificada y exiliada.", parse_mode=ParseMode.HTML)
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", 
                    ("bot_hablador_exiliado", user.id, datetime.now().isoformat()), commit=True)
    except Exception as e:
        logger.error(f"No se pudo purgar al bot hablador {user.id}: {e}")

# --- 5. BLOQUE PRINCIPAL ---
def main() -> None:
    logger.info("Iniciando Mashi (Modo Guardián)...")
    setup_database()

    application = Application.builder().token(TOKEN).build()
    
    # Handlers de comandos actualizados
    command_handlers = [
        CommandHandler("start", start),
        CommandHandler("relato", relato),
        CommandHandler("tienda", tienda),
        CommandHandler("purificar", purificar),
        CommandHandler("exilio", exilio),
    ]
    application.add_handlers(command_handlers)
    
    # Añadir el manejador para nuevos miembros (ahora también verifica edad)
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    
    # Añadir el manejador para los botones de verificación
    application.add_handler(CallbackQueryHandler(age_verification_handler, pattern="^age_verify_"))
    
    # --- AÑADIR NUEVO HANDLER DE PURGA REACTIVA ---
    # Se aplica a todos los mensajes de texto, fotos, stickers, etc. que no sean de un humano o admin.
    application.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), handle_bot_messages))

    logger.info("El bot Mashi está en línea y vigilando.")
    application.run_polling()

if __name__ == "__main__":
    main()