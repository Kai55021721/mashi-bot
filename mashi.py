# --- 0. IMPORTS Y CONFIGURACIÓN INICIAL ---
import os
import random
import logging
import sqlite3
import time
import re
from functools import wraps

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, User, CallbackQuery
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

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

OWNER_ID = 1890046858
MAIN_CHAT_ID = -1001504263227
COMMAND_COOLDOWN_SECONDS = 5 # Para producción, se recomienda 300 (5 minutos)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'mashi_data_v2.db')

PRODUCTOS = {
    "boceto_1p": {"nombre": "Boceto 1 Personaje", "costo": 500},
    "boceto_2p": {"nombre": "Boceto 2 Personajes", "costo": 900},
    "nsfw_add": {"nombre": "Extra NSFW", "costo": 300}
}
STICKERS_MASHI = {"rugido": "CAACAgUAAxkBAAM1aH80YqFYWuboCHmRQbSUlFDBZgMAAq4GAAJq0coFCIV7sNzZaeo2BA"}
CHISTES_MASHI = ["¿Qué le dice un león a otro? ¿Vamos a la carnicería o esperamos el delivery de gacelas?"]
RELATOS_DEL_GUARDIAN = ["A veces, por la noche, escucho los susurros de las estatuas del templo."]

def escape_markdown(text: str) -> str:
    """Escapa caracteres especiales de Markdown V2."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

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
    db_safe_run('CREATE TABLE IF NOT EXISTS subscribers (chat_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, estrellas INTEGER DEFAULT 1)')
    db_safe_run('CREATE TABLE IF NOT EXISTS chismes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, username TEXT, gossip_text TEXT NOT NULL, status TEXT DEFAULT "PENDIENTE")')
    try:
        db_safe_run('ALTER TABLE subscribers ADD COLUMN estrellas INTEGER DEFAULT 1')
    except sqlite3.OperationalError:
        pass # La columna ya existe
    logger.info(f"Base de datos preparada en la ruta: {DB_FILE}")

async def ensure_user(user: User):
    if not db_safe_run("SELECT 1 FROM subscribers WHERE chat_id = ?", (user.id,), fetchone=True):
        db_safe_run("INSERT INTO subscribers (chat_id, username, points, estrellas) VALUES (?, ?, 0, 1)", (user.id, user.username or user.first_name), commit=True)
        logger.info(f"Usuario {user.id} ({user.username}) añadido a la BD.")

def get_user_points(chat_id: int) -> int:
    result = db_safe_run("SELECT points FROM subscribers WHERE chat_id = ?", (chat_id,), fetchone=True)
    return result[0] if result else 0

def get_top_users(limit: int = 5) -> list:
    return db_safe_run("SELECT username, points FROM subscribers ORDER BY points DESC LIMIT ?", (limit,)) or []

def girar_ruleta(user_id: int) -> (bool, int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT estrellas FROM subscribers WHERE chat_id = ?", (user_id,))
        result = cursor.fetchone()
        if result is None or result[0] < 1: return False, 0

        cursor.execute("UPDATE subscribers SET estrellas = estrellas - 1 WHERE chat_id = ?", (user_id,))
        premios = [0, 1, 5, 10, 50]
        probabilidades = [0.40, 0.35, 0.15, 0.08, 0.02]
        puntos_ganados = random.choices(premios, probabilidades, k=1)[0]

        if puntos_ganados > 0:
            cursor.execute("UPDATE subscribers SET points = points + ? WHERE chat_id = ?", (puntos_ganados, user_id))
        
        conn.commit()
        return True, puntos_ganados
    except sqlite3.Error as e:
        logger.error(f"Error en la transacción de la ruleta: {e}")
        conn.rollback()
        return False, -1
    finally:
        conn.close()

# --- 3. DECORADORES ---
def owner_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id == OWNER_ID:
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text("Mis asuntos son solo con el maestro Kai.")
    return wrapped

def command_cooldown(seconds: int):
    def decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            is_callback = bool(update.callback_query)
            user = update.callback_query.from_user if is_callback else update.effective_user
            command_name = func.__name__

            if 'cooldowns' not in context.user_data: context.user_data['cooldowns'] = {}
            last_used = context.user_data.get(f"{user.id}_{command_name}", 0)
            elapsed = time.time() - last_used
            
            if user.id == OWNER_ID or elapsed >= seconds:
                context.user_data[f"{user.id}_{command_name}"] = time.time()
                return await func(update, context, *args, **kwargs)
            else:
                remaining_time = int(seconds - elapsed)
                if is_callback:
                    await update.callback_query.answer(f"Paciencia. Debes esperar {remaining_time}s.", show_alert=True)
                else:
                    await update.message.reply_text(f"Paciencia, mortal. Debes esperar {remaining_time}s.")
        return wrapped
    return decorator

# --- 4. MANEJADORES DE COMANDOS Y LÓGICA PRINCIPAL ---
async def mostrar_menu_principal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user or update.callback_query.from_user
    await ensure_user(user)
    
    result = db_safe_run("SELECT points, estrellas FROM subscribers WHERE chat_id = ?", (user.id,), fetchone=True)
    puntos, estrellas = (result[0], result[1]) if result else (0, 0)
    
    texto_menu = (
        f"🦁 **Templo del Guardián Mashi** 🦁\n\n"
        f"Tu saldo: **{puntos} Puntos** y **{estrellas} Estrellas** 🌟.\n\n"
        "Elige una acción:"
    )
    
    keyboard = [
        [InlineKeyboardButton("Girar Ruleta 🎰", callback_data="menu_girar"), InlineKeyboardButton("Mi Saldo 💰", callback_data="mis_puntos")],
        [InlineKeyboardButton("Rugido 🦁", callback_data="menu_rugir"), InlineKeyboardButton("Chiste 😂", callback_data="menu_chiste"), InlineKeyboardButton("Relato 📜", callback_data="menu_relato")],
        [InlineKeyboardButton("Tienda de Recompensas 🛍️", callback_data="menu_tienda")],
        [InlineKeyboardButton("Ver Ranking 🏆", callback_data="ranking")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(texto_menu, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except BadRequest: pass
    else:
        await update.message.reply_text(texto_menu, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mostrar_menu_principal(update, context)

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.message.delete()
    except: pass
    await mostrar_menu_principal(update, context)

async def tienda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_callback = bool(update.callback_query)
    user = update.callback_query.from_user if is_callback else update.effective_user
    
    await ensure_user(user)
    puntos = get_user_points(user.id)
    
    texto_tienda = f"🛍️ **Tienda de Recompensas** 🛍️\n\nTu saldo: **{puntos}** Puntos.\n\nSelecciona un objeto para canjear:"
    
    keyboard = [[InlineKeyboardButton(f"{detalles['nombre']} ({detalles['costo']} P)", callback_data=f"buy_{id_producto}")] for id_producto, detalles in PRODUCTOS.items()]
    keyboard.append([InlineKeyboardButton("⬅️ Volver al Menú", callback_data="volver_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if is_callback:
        await update.callback_query.edit_message_text(texto_tienda, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(texto_tienda, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

@command_cooldown(COMMAND_COOLDOWN_SECONDS)
async def rugir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.callback_query.from_user if update.callback_query else update.effective_user
    chat = update.callback_query.message.chat if update.callback_query else update.effective_chat
    await ensure_user(user)
    await context.bot.send_sticker(chat_id=chat.id, sticker=STICKERS_MASHI["rugido"])
    await award_points(context, user, 1, MAIN_CHAT_ID, "por un rugido poderoso")

# --- FUNCIONES RESTAURADAS ---
@command_cooldown(COMMAND_COOLDOWN_SECONDS)
async def chiste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.callback_query.from_user if update.callback_query else update.effective_user
    chat = update.callback_query.message.chat if update.callback_query else update.effective_chat
    await ensure_user(user)
    await context.bot.send_message(chat.id, "Te permitiré una distracción. " + random.choice(CHISTES_MASHI))
    await award_points(context, user, 1, MAIN_CHAT_ID, "por entender mi humor")

@command_cooldown(COMMAND_COOLDOWN_SECONDS)
async def relato(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.callback_query.from_user if update.callback_query else update.effective_user
    chat = update.callback_query.message.chat if update.callback_query else update.effective_chat
    await ensure_user(user)
    await context.bot.send_message(chat.id, "Escucha en silencio. " + random.choice(RELATOS_DEL_GUARDIAN))
    await award_points(context, user, 1, MAIN_CHAT_ID, "por atender a mis relatos")
# --- FIN DE FUNCIONES RESTAURADAS ---

async def _execute_girar(user: User, chat_id: int, context: ContextTypes.DEFAULT_TYPE, message_to_edit=None):
    await ensure_user(user)
    
    mensaje_ruleta = message_to_edit or await context.bot.send_message(chat_id=chat_id, text="Iniciando...")
    
    animation_frames = ["🎰", "🍒", "💰", "💎", "⭐"]
    for _ in range(5):
        frame_text = "Girando... " + " | ".join(random.sample(animation_frames, 3))
        try:
            await mensaje_ruleta.edit_text(frame_text)
            time.sleep(0.4)
        except BadRequest: pass

    exito, puntos = girar_ruleta(user.id)
    
    if not exito and puntos == 0: texto_final = "No tienes estrellas 🌟 para girar."
    elif not exito and puntos == -1: texto_final = "La máquina ha sufrido una avería mística."
    elif puntos > 0: texto_final = f"¡Felicidades, {user.mention_markdown()}! Has ganado **{puntos}** puntos."
    else: texto_final = f"Mejor suerte la próxima vez, {user.mention_markdown()}."
    
    await mensaje_ruleta.edit_text(texto_final, parse_mode=ParseMode.MARKDOWN)
    time.sleep(3)

async def girar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _execute_girar(update.effective_user, update.effective_chat.id, context)

async def ofrenda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.reply_to_message or not update.message.reply_to_message.photo:
        await update.message.reply_text("Para hacer una ofrenda, envía una imagen y **respóndele** con /ofrenda.")
        return
    # ... Lógica de ofrenda ...
    await update.message.reply_text("Ofrenda recibida. Será presentada al maestro.")

async def chisme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Debes susurrar algo. Uso: `/chisme <tu secreto>`")
        return
    # ... Lógica de chisme ...
    await update.message.reply_text("He escuchado tu secreto.")

@owner_only
async def dar_estrellas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.reply_to_message:
            user_id = update.message.reply_to_message.from_user.id
            cantidad = int(context.args[0])
        else:
            cantidad = int(context.args[0])
            user_id = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: `/dar_estrellas <cant> <id>` o responde con `/dar_estrellas <cant>`.")
        return
    
    if db_safe_run("UPDATE subscribers SET estrellas = estrellas + ? WHERE chat_id = ?", (cantidad, user_id), commit=True):
        await update.message.reply_text(f"Otorgadas {cantidad} estrellas 🌟 al usuario `{user_id}`.")
    else:
        await update.message.reply_text(f"No se pudo encontrar al usuario `{user_id}`.")

# --- 5. MANEJADOR DE BOTONES ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'volver_menu': await mostrar_menu_principal(update, context)
    elif data == 'menu_girar':
        await _execute_girar(query.from_user, query.message.chat.id, context, message_to_edit=query.message)
        await mostrar_menu_principal(update, context)
    elif data in ('menu_rugir', 'menu_chiste', 'menu_relato'):
        func_map = {'menu_rugir': rugir, 'menu_chiste': chiste, 'menu_relato': relato}
        await func_map[data](update, context)
    elif data == 'menu_tienda': await tienda(update, context)
    elif data == 'mis_puntos':
        p, e = db_safe_run("SELECT points, estrellas FROM subscribers WHERE chat_id=?", (query.from_user.id,), fetchone=True) or (0,0)
        await query.answer(f"Saldo: {p} Puntos, {e} Estrellas 🌟", show_alert=True)
    elif data == 'ranking':
        top_users = get_top_users()
        message = "🏆 **Ranking de Lealtad** 🏆\n\n" + ("Aún no hay mortales con puntos." if not top_users else "".join(
            f"{'🥇🥈🥉'[i] if i<3 else f'{i+1}.'} **{escape_markdown(username or 'Anónimo')}** - {points} pts\n"
            for i, (username, points) in enumerate(top_users)
        ))
        keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data="volver_menu")]]
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    elif data.startswith("buy_"):
        id_producto = data.split("_", 1)[1]
        producto = PRODUCTOS.get(id_producto)
        if not producto: return await query.answer("Producto no válido.", show_alert=True)

        user_id = query.from_user.id
        costo = producto['costo']
        
        rows_affected = db_safe_run("UPDATE subscribers SET points = points - ? WHERE chat_id = ? AND points >= ?", (costo, user_id, costo), commit=True)
        
        if rows_affected:
            await query.answer(f"¡Has canjeado '{producto['nombre']}'!", show_alert=True)
            user_info = query.from_user
            await context.bot.send_message(OWNER_ID, f"🔥 **Recompensa Canjeada** 🔥\n- **Usuario:** {user_info.mention_markdown()} (`{user_info.id}`)\n- **Producto:** {producto['nombre']}", parse_mode=ParseMode.MARKDOWN)
            await tienda(update, context)
        else:
            await query.answer("No tienes suficientes puntos.", show_alert=True)
    
# --- 6. BLOQUE PRINCIPAL ---
def main() -> None:
    logger.info("Iniciando Mashi v6.3 (Guardián Final)...")
    setup_database()

    application = Application.builder().token(TOKEN).build()
    
    command_handlers = [
        CommandHandler("start", start),
        CommandHandler("menu", menu),
        CommandHandler("tienda", tienda),
        CommandHandler("girar", girar),
        CommandHandler("ofrenda", ofrenda),
        CommandHandler("chisme", chisme),
        CommandHandler("dar_estrellas", dar_estrellas)
    ]
    
    application.add_handlers(command_handlers)
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("El bot Mashi está en línea y vigilando.")
    application.run_polling()

if __name__ == "__main__":
    main()