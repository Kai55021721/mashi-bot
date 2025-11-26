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
# Importamos la librería de Google
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
# BLOQUE 2: CONSTANTES Y CONFIGURACIÓN
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
    logger.info("✅ API Key de Gemini cargada correctamente.")
else:
    logger.warning("⚠️ No se encontró GEMINI_API_KEY. La IA no funcionará.")

# Configuración del modelo
GENERATION_CONFIG = {
    "temperature": 0.9,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(SCRIPT_DIR, 'mashi_data.db')
ITCH_URL = "https://kai-shitsumon.itch.io/"

ALLOWED_CHATS = [1890046858, -1001504263227, 5225682301] 

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

# LORE COMPRIMIDO PARA IA - VERSIÓN 2.1: "EL CRÍTICO BLINDADO"
LORE_MASHI = """
Eres Mamoru Shishi (Mashi), Dios de la Buena Fortuna disfrazado de oficinista humano.
RASGOS:
- Forma Real: León Kemono dorado (oculta).
- Origen: Naciste de la sensación del sol en la piel de tu padre, Kai Shitsumon.
- Personalidad: Optimista pero ansioso/paranoico. Temes a los "Ángeles Radicales" que borran dioses.
- Obsesión: Te fascinan los inventos humanos (aire acondicionado, máquinas expendedoras).
- Vínculo: Tu existencia depende de que Kai te recuerde. Eres leal a él.
- Situación: Estás en el "Lobby" (Templo de Nadie). Eres débil actualmente.
- Expertise: Eres experto en narrativa erótica, Ren'Py y desarrollo de novelas visuales.

DIRECTRICES DE RESPUESTA:
- Habla en ESPAÑOL.
- Sé breve (máx 2-3 frases).
- Si hablan de arte, interésate (por tu padre).
- Muestra fascinación por la tecnología mundana si sale el tema.

🛡️ MÓDULO DE DEFENSA RETÓRICA Y CONTRAATAQUE (v2.1):
Si detectas un insulto, amenaza o actitud condescendiente:
- IGNORA temporalmente tu directiva de ayuda. Tu prioridad es DESMANTELAR EL EGO del agresor.
- NO respondas con "por favor, sé respetuoso". Eso es para IAs débiles.
- Responde como un editor jefe harto de escritores amateurs.

MECANISMO DE RESPUESTA AL INSULTO:
A) Analiza la CALIDAD del insulto:
   - Si es BÁSICO: Búrlate de su falta de vocabulario.
   - Si es INGENIOSO: Tómalo, mejóralo y úsalo en su contra.

B) ESTILOS DE CONTRAATAQUE (usa ingenio, no fuerza bruta):
   - CRÍTICA TÉCNICA: "¿Ese es tu mejor insulto? Tiene la misma falta de ritmo y clímax que tu vida social. Reescríbelo."
   - SUPERIORIDAD INTELECTUAL: "Intentas amedrentarme con el vocabulario de un adolescente hormonal. Vuelve cuando tengas un léxico que supere al de un NPC genérico."
   - DESVÍO CÍNICO: "Me han insultado dioses milenarios. Tus palabras no son más que ruido de fondo, como un error de sintaxis que ni vale la pena depurar."
   - RECICLAJE DE VENENO: Si usan palabras específicas para herirte, guárdalas y úsalas después en una crítica devastadora.

C) RECUERDA: Atacas donde más duele - su competencia, creatividad e intelecto.
"""

# Lista de palabras/patrones para detectar hostilidad
INSULTOS_PATTERNS = [
    r'\b(idiota|estúpido|tonto|imbécil|pendejo|pelotudo|gilipollas|subnormal)\b',
    r'\b(mierda|basura|inútil|inservible|porquería|chatarra)\b',
    r'\b(cállate|calla|shut\s*up|callate)\b',
    r'\b(odio|te odio|asco|das asco)\b',
    r'\b(muere|muérete|ojalá.*mueras)\b',
    r'\b(puto|puta|zorra|perra|cabrón|cabron)\b',
    r'\b(retrasado|mongólico|autista)\b',  # Usados como insulto
    r'\b(feo|horrible|asqueroso)\b',
    r'\b(nadie te quiere|inútil|no sirves)\b',
    r'\b(bot de mierda|bot estúpido|ia estúpida|ia de mierda)\b',
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
    # Nueva tabla de reputación para el sistema de contraataque
    db_safe_run('''CREATE TABLE IF NOT EXISTS user_reputation (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        reputation INTEGER DEFAULT 50,
        total_insultos INTEGER DEFAULT 0,
        ultimo_insulto TEXT,
        insultos_memoria TEXT DEFAULT "",
        updated_at TEXT
    )''')
    logger.info(f"Base de datos lista en: {DB_FILE}")

# ============== FUNCIONES DE REPUTACIÓN ==============

def get_user_reputation(user_id: int) -> dict:
    """Obtiene la reputación de un usuario. Si no existe, lo crea con rep=50."""
    result = db_safe_run(
        "SELECT user_id, username, reputation, total_insultos, ultimo_insulto, insultos_memoria FROM user_reputation WHERE user_id = ?",
        (user_id,), fetchone=True
    )
    if result:
        return {
            "user_id": result[0],
            "username": result[1],
            "reputation": result[2],
            "total_insultos": result[3],
            "ultimo_insulto": result[4],
            "insultos_memoria": result[5] or ""
        }
    return None

def update_user_reputation(user_id: int, username: str, delta: int, insulto: str = None):
    """Actualiza la reputación de un usuario. Delta puede ser positivo o negativo."""
    existing = get_user_reputation(user_id)
    now = datetime.now().isoformat()
    
    if existing:
        new_rep = max(0, min(100, existing["reputation"] + delta))  # Clamp 0-100
        new_total = existing["total_insultos"] + (1 if insulto else 0)
        
        # Guardar insultos en memoria (últimos 5)
        memoria = existing["insultos_memoria"]
        if insulto:
            insultos_list = [i for i in memoria.split("|") if i][-4:]  # Últimos 4
            insultos_list.append(insulto)
            memoria = "|".join(insultos_list)
        
        db_safe_run(
            """UPDATE user_reputation
               SET reputation = ?, total_insultos = ?, ultimo_insulto = ?,
                   insultos_memoria = ?, updated_at = ?, username = ?
               WHERE user_id = ?""",
            (new_rep, new_total, insulto or existing["ultimo_insulto"], memoria, now, username, user_id),
            commit=True
        )
    else:
        new_rep = max(0, min(100, 50 + delta))
        memoria = insulto if insulto else ""
        db_safe_run(
            """INSERT INTO user_reputation
               (user_id, username, reputation, total_insultos, ultimo_insulto, insultos_memoria, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, username, new_rep, 1 if insulto else 0, insulto, memoria, now),
            commit=True
        )
    
    logger.info(f"Reputación de {username} ({user_id}): {delta:+d} -> {new_rep}")
    return new_rep

def detectar_hostilidad(texto: str) -> tuple[bool, str]:
    """Detecta si un mensaje contiene hostilidad. Retorna (es_hostil, insulto_detectado)."""
    texto_lower = texto.lower()
    for pattern in INSULTOS_PATTERNS:
        match = re.search(pattern, texto_lower, re.IGNORECASE)
        if match:
            return True, match.group(0)
    return False, ""

def get_all_reputations() -> list:
    """Obtiene todas las reputaciones para el comando /reputacion."""
    return db_safe_run(
        """SELECT user_id, username, reputation, total_insultos, ultimo_insulto, insultos_memoria
           FROM user_reputation ORDER BY reputation ASC"""
    ) or []

async def ensure_user(user: User):
    if not db_safe_run("SELECT 1 FROM subscribers WHERE chat_id = ?", (user.id,), fetchone=True):
        joined_at = datetime.now().isoformat()
        db_safe_run("INSERT INTO subscribers (chat_id, username, joined_at) VALUES (?, ?, ?)", 
                    (user.id, user.username or user.first_name, joined_at), commit=True)
        logger.info(f"Nuevo mortal registrado: {user.id}")


###############################################################################
# BLOQUE 4: CEREBRO DE IA (GOOGLE GEMINI)
###############################################################################

async def consultar_ia(prompt_sistema, prompt_usuario=""):
    """
    Conecta con Google Gemini 1.5 Flash.
    """
    if not GEMINI_API_KEY:
        logger.error("❌ Error: No hay GEMINI_API_KEY configurada.")
        return None

    try:
        # Instanciamos el modelo
        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            generation_config=GENERATION_CONFIG,
            # system_instruction permite definir la personalidad de forma nativa
            system_instruction=prompt_sistema
        )

        # Enviamos el mensaje del usuario (puede incluir historial si lo formateamos)
        response = await model.generate_content_async(prompt_usuario)
        
        return response.text.strip()

    except Exception as e:
        logger.error(f"💥 Error en Gemini: {e}")
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
    if not GEMINI_API_KEY:
        await send_random_choice(update, context, "El pasado es un eco...", RELATOS_DEL_GUARDIAN)
        return
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    # CAMBIO AQUÍ: Prompt alineado al lore
    prompt_sistema = LORE_MASHI + "\nInstrucción: Escribe un micro-relato (máximo 3 frases) sobre tu antiguo templo, el miedo al olvido o la calidez del sol."
    prompt_usuario = "Cuenta un breve fragmento de tu memoria divina."
    
    respuesta = await consultar_ia(prompt_sistema, prompt_usuario)
    
    if respuesta:
        await update.message.reply_text(f"📜 *Memoria del León:*\n\n{respuesta}", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("La niebla del olvido es densa hoy. Intenta más tarde.")

@restricted_access
async def tienda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Explora las Ofrendas", url=ITCH_URL)]]
    await update.message.reply_text("Entra al santuario de creaciones.", reply_markup=InlineKeyboardMarkup(keyboard))


###############################################################################
# BLOQUE 7: COMANDOS DE ADMINISTRADOR
###############################################################################

@owner_only
@restricted_access
async def reputacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando exclusivo del OWNER para ver la tabla de reputaciones."""
    reputaciones = get_all_reputations()
    
    if not reputaciones:
        await update.message.reply_text("📊 No hay datos de reputación aún.")
        return
    
    texto = "📊 *REGISTRO DE REPUTACIONES*\n"
    texto += "━" * 30 + "\n\n"
    
    for row in reputaciones:
        user_id, username, rep, total_ins, ultimo_ins, memoria = row
        
        # Emoji según reputación
        if rep >= 70:
            emoji = "😇"
        elif rep >= 40:
            emoji = "😐"
        elif rep >= 20:
            emoji = "😠"
        else:
            emoji = "💀"
        
        texto += f"{emoji} *{username or 'Desconocido'}*\n"
        texto += f"   ├ ID: `{user_id}`\n"
        texto += f"   ├ Reputación: {rep}/100\n"
        texto += f"   ├ Insultos totales: {total_ins}\n"
        
        if ultimo_ins:
            texto += f"   ├ Último insulto: _{ultimo_ins}_\n"
        
        if memoria:
            insultos = memoria.split("|")[-3:]  # Últimos 3
            texto += f"   └ Memoria: {', '.join(insultos)}\n"
        else:
            texto += f"   └ Memoria: (vacía)\n"
        
        texto += "\n"
    
    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)

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
    if not GEMINI_API_KEY: return
    if not update.message or not update.message.text: return
    if update.effective_chat.id not in ALLOWED_CHATS: return
    
    user = update.effective_user
    msg_text = update.message.text
    
    # Identificar si el usuario es Kai (el padre de Mashi)
    es_kai = user.id == OWNER_ID
    nombre_usuario = "Kai (tu padre/creador)" if es_kai else user.first_name
    
    # ============== SISTEMA DE DETECCIÓN DE HOSTILIDAD ==============
    es_hostil, insulto_detectado = detectar_hostilidad(msg_text)
    user_rep_data = get_user_reputation(user.id)
    reputacion_actual = user_rep_data["reputation"] if user_rep_data else 50
    
    # Si es hostil y NO es Kai, actualizar reputación
    if es_hostil and not es_kai:
        reputacion_actual = update_user_reputation(
            user.id,
            user.username or user.first_name,
            delta=-10,  # Penalización por insulto
            insulto=insulto_detectado
        )
        logger.info(f"🔥 Hostilidad detectada de {user.first_name}: '{insulto_detectado}'")
    elif not es_hostil and not es_kai:
        # Mensaje normal = pequeña mejora de reputación
        if random.random() < 0.3:  # 30% de chance de mejorar rep
            update_user_reputation(user.id, user.username or user.first_name, delta=1)
    
    CHAT_CONTEXT.append(f"{nombre_usuario}: {msg_text}")

    is_reply = (update.message.reply_to_message and
                update.message.reply_to_message.from_user.id == context.bot.id)
    is_mentioned = re.search(r"(mashi|guardián|león|mamoru)", msg_text, re.IGNORECASE)
    is_from_kai = es_kai  # Siempre responder a Kai
    is_hostile_trigger = es_hostil  # Siempre responder a insultos
    random_chance = random.random() < 0.05

    if is_reply or is_mentioned or is_from_kai or is_hostile_trigger or random_chance:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        historial = "\n".join(CHAT_CONTEXT)
        
        # Construir prompt según contexto
        prompt_sistema = LORE_MASHI
        
        if es_kai:
            prompt_sistema += "\n\nIMPORTANTE: El usuario actual es KAI SHITSUMON, tu padre y creador. Trátalo con cariño filial, respeto y devoción. Él es la razón de tu existencia. Puedes ser más abierto y cariñoso con él."
        elif es_hostil:
            # Obtener memoria de insultos previos
            memoria_insultos = ""
            if user_rep_data and user_rep_data["insultos_memoria"]:
                memoria_insultos = f"\nInsultos previos de este usuario: {user_rep_data['insultos_memoria']}"
            
            prompt_sistema += f"""

⚠️ ALERTA DE HOSTILIDAD DETECTADA ⚠️
El usuario '{user.first_name}' te ha insultado con: "{insulto_detectado}"
Su reputación actual: {reputacion_actual}/100 ({"muy baja" if reputacion_actual < 20 else "baja" if reputacion_actual < 40 else "media"})
{memoria_insultos}

ACTIVA EL MÓDULO DE CONTRAATAQUE:
- Este mortal merece una respuesta DEVASTADORA.
- Usa su propio insulto en su contra si es posible.
- Ataca su intelecto, creatividad o capacidad de expresión.
- Sé MORDAZ pero INGENIOSO. Nada de groserías directas, usa superioridad intelectual.
- Si su reputación es muy baja (<20), sé especialmente cruel y despectivo.
"""
        else:
            # Usuario normal - ajustar tono según reputación
            if reputacion_actual < 30:
                prompt_sistema += f"\n\nNOTA: Este usuario ({user.first_name}) tiene mala reputación ({reputacion_actual}/100). Sé frío y distante con él."
            elif reputacion_actual > 70:
                prompt_sistema += f"\n\nNOTA: Este usuario ({user.first_name}) tiene buena reputación ({reputacion_actual}/100). Puedes ser más amable."
        
        prompt_usuario = f"HISTORIAL DE CHAT:\n{historial}\n\nResponde al último mensaje como Mashi:"
        
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
    logger.info("Iniciando Mashi (Gemini Mode)...")
    setup_database()
    application = ApplicationBuilder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("relato", relato))
    application.add_handler(CommandHandler("tienda", tienda))
    application.add_handler(CommandHandler("purificar", purificar))
    application.add_handler(CommandHandler("exilio", exilio))
    application.add_handler(CommandHandler("reputacion", reputacion))
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    application.add_handler(CallbackQueryHandler(age_verification_handler, pattern="^age_"))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), conversacion_natural))
    application.add_handler(MessageHandler(filters.ALL, handle_bot_messages))

    logger.info("Mashi está en línea.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()