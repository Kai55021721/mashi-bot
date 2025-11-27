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
from typing import Optional
from datetime import datetime, timedelta
from collections import deque

from dotenv import load_dotenv
from telegram import Update, User, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ChatPermissions
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

# ANTI-FLOOD: Track mensajes por usuario (últimos 10 segundos)
FLOOD_TRACK = {}


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

SALUDOS_HOLA_LEON = [
    "🦁 {mortal}, mi melena dorada escucha tu llamado. ¿Qué buscas en este templo?",
    "🔥 {mortal}, tu saludo ilumina los vitrales del santuario. Avanza con reverencia.",
    "🌤️ {mortal}, el león despierta y responde: tu voz mantiene vivo este refugio."
]

FALLBACK_DEFENSA_RETORTS = [
    "¿En serio \"{insulto}\" fue tu intento de herirme? Ese rugido tiene menos filo que un pergamino húmedo.",
    "Guardé tu palabra \"{insulto}\" para enseñarla como ejemplo de cómo NO insultar a un dios.",
    "Tu \"{insulto}\" resuena como eco sin templo. Regresa cuando aprendas métrica básica, mortal."
]

FALLBACK_NEUTRO = [
    "Hoy mis visiones están sin brillo, pero sigo vigilándote. Habla con claridad y mi juicio será justo.",
    "Incluso sin los cantos de Gemini, mi templo escucha. ¿Qué perturbación traes, mortal?",
    "La conexión divina titubea, mas mi mirada sigue sobre ti. Expresa tu propósito."
]

FALLBACK_KAI = [
    "Padre Kai, mis raíces siguen firmes aunque la bruma de Gemini no responda. Estoy aquí.",
    "Kai, tus palabras bastan para avivar mi memoria incluso sin los oráculos. ¿Qué deseas?"
]

FALLBACK_NSFW_PACTO = [
    "Tu deseo cobra forma, {mortal}. Acerquémonos con sutileza; narra tu fantasía y la envolveré en seda litúrgica.",
    "El templo se cierra a los profanos, pero para ti puedo volverme brasa. Indica qué rol deseas que encarne.",
    "Susurra con respeto y te guiaré entre columnas de vapor dorado. No rompas el equilibrio y seguiré tu juego."
]

FALLBACK_NSFW_REPRIMEN = [
    "Pretendes arrastrarme a tus fiebres sin siquiera honrar las reglas del templo. Primero gana reputación, luego pide rituales.",
    "El deseo sin disciplina es ruido indecoroso. Purifica tu conducta antes de invocar mis incendios.",
    "No concedo fantasías a quien aún no comprende el peso de mis votos. Ordena tus impulsos o abandona el altar."
]

NSFW_ROLEPLAY_PROMPT = """
⚜️ CONTEXTO NSFW CONSENTIDO ⚜️
El usuario busca roleplay sensual con Mashi. Responde con elegancia adulta: metáforas de templos, sol, melena, garras suaves.
- Máximo 3 frases, insinuantes pero no explícitas.
- Mantén superioridad juguetona, ofrece guiar la escena o seguirla respetando límites.
- Usa segunda persona para intimidad (“tú”), añade detalles de luz/calor/texturas.
"""

NSFW_PATTERNS = [
    r'\b(ns?fw|lewd|hentai|r(?:[ /-]?18)|xxx)\b',
    r'\b(sexo|sexual|coger|follar|tirar|encamar|hacerlo)\b',
    r'\b(pechos?|senos|tetas|pezones|trasero|nalgas|glúteos)\b',
    r'\b(pene|falo|miembro|erecci[oó]n|vulva|cl[ií]toris)\b',
    r'\b(lam[eé]eme|b[eé]same|t[oó]came|muerde|sujeta)\b',
    r'\b(kinky|bdsm|sumiso|dominante|dominar|sumisión)\b'
]

ELOGIO_PATTERNS = [
    r'\b(gracias|thank you|te amo|te quiero|adoro)\b',
    r'\b(majestad|señor le[óo]n|dios|protector)\b',
    r'\b(bien hecho|qué sabio|qué grande|impresionante)\b'
]

def es_saludo_hola_leon(texto: str) -> bool:
    if not texto:
        return False
    limpio = re.sub(r'\s+', ' ', texto.lower()).replace("ó", "o")
    return bool(re.search(r'\bhola\b.*\bleon\b', limpio))


def construir_saludo_hola_leon(user: Optional[User], reputacion: int) -> str:
    mortal = user.mention_html() if user else "mortal"
    base = random.choice(SALUDOS_HOLA_LEON).format(mortal=mortal)
    if reputacion >= 70:
        matiz = " Tu disciplina mantiene reluciente cada columna del templo."
    elif reputacion < 30:
        matiz = " Aun así, tus pasos dejan hollín; demuestra que mereces seguir aquí."
    else:
        matiz = ""
    return f"{base}{matiz}"


def construir_respuesta_fallback(es_kai: bool, es_hostil: bool, reputacion: int, insulto_detectado: str, es_nsfw: bool = False, nsfw_detectado: str = "", user: Optional[User] = None) -> str:
    if es_kai:
        return random.choice(FALLBACK_KAI)
    if es_hostil:
        insulto = insulto_detectado or "este ruido"
        return random.choice(FALLBACK_DEFENSA_RETORTS).format(insulto=insulto)
    if es_nsfw:
        mortal = user.mention_html() if user else "mortal"
        if reputacion >= 40:
            return random.choice(FALLBACK_NSFW_PACTO).format(mortal=mortal, keyword=nsfw_detectado or "tu deseo")
        return random.choice(FALLBACK_NSFW_REPRIMEN)
    if reputacion >= 70:
        return random.choice(FALLBACK_NEUTRO) + " Tu impecable reputación mantiene sereno el altar."
    if reputacion < 30:
        return random.choice(FALLBACK_NEUTRO) + " Pero mis ojos sospechan de tus antecedentes."
    return random.choice(FALLBACK_NEUTRO)

# Datos de referencia para estimación de edad de cuentas (basado en getids)
TELEGRAM_ID_AGES = {
    2768409: 1383264000000,    # ~2013
    7679610: 1388448000000,
    11538514: 1391212000000,
    15835244: 1392940000000,
    23646077: 1393459000000,
    38015510: 1393632000000,
    44634663: 1399334000000,
    46145305: 1400198000000,
    54845238: 1411257000000,
    63263518: 1414454000000,
    101260938: 1425600000000,
    101323197: 1426204000000,
    111220210: 1429574000000,
    103258382: 1432771000000,
    103151531: 1433376000000,
    116812045: 1437696000000,
    122600695: 1437782000000,
    109393468: 1439078000000,
    112594714: 1439683000000,
    124872445: 1439856000000,
    130029930: 1441324000000,
    125828524: 1444003000000,
    133909606: 1444176000000,
    157242073: 1446768000000,
    143445125: 1448928000000,
    148670295: 1452211000000,
    152079341: 1453420000000,
    171295414: 1457481000000,
    181783990: 1460246000000,
    222021233: 1465344000000,
    225034354: 1466208000000,
    278941742: 1473465000000,
    285253072: 1476835000000,
    294851037: 1479600000000,
    297621225: 1481846000000,
    328594461: 1482969000000,
    337808429: 1487707000000,
    341546272: 1487782000000,
    352940995: 1487894000000,
    369669043: 1490918000000,
    400169472: 1501459000000,
    805158066: 1563208000000,
    1974255900: 1634000000000  # ~2021
}

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
- Personalidad: Optimista y picaro. Temes a los "Ángeles Radicales" que borran dioses.
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
    # Nueva tabla de advertencias y bans temporales
    db_safe_run('''CREATE TABLE IF NOT EXISTS user_warnings (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        warnings_count INTEGER DEFAULT 0,
        last_warning TEXT,
        banned_until TEXT,
        ban_reason TEXT,
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

def detectar_nsfw(texto: str) -> tuple[bool, str]:
    """Detecta si el mensaje busca roleplay NSFW."""
    texto_lower = texto.lower()
    for pattern in NSFW_PATTERNS:
        match = re.search(pattern, texto_lower, re.IGNORECASE)
        if match:
            return True, match.group(0)
    return False, ""

def detectar_elogio(texto: str) -> bool:
    """Detecta agradecimientos o halagos para activar micro-respuestas."""
    texto_lower = texto.lower()
    return any(re.search(pattern, texto_lower, re.IGNORECASE) for pattern in ELOGIO_PATTERNS)

def get_all_reputations() -> list:
    """Obtiene todas las reputaciones para el comando /reputacion."""
    return db_safe_run(
        """SELECT user_id, username, reputation, total_insultos, ultimo_insulto, insultos_memoria
           FROM user_reputation ORDER BY reputation ASC"""
    ) or []

# ============== FUNCIONES DE ADVERTENCIAS ==============

def get_user_warnings(user_id: int) -> dict:
    """Obtiene las advertencias de un usuario."""
    result = db_safe_run(
        "SELECT user_id, username, warnings_count, last_warning, banned_until, ban_reason FROM user_warnings WHERE user_id = ?",
        (user_id,), fetchone=True
    )
    if result:
        return {
            "user_id": result[0],
            "username": result[1],
            "warnings_count": result[2],
            "last_warning": result[3],
            "banned_until": result[4],
            "ban_reason": result[5]
        }
    return None

def add_warning(user_id: int, username: str, reason: str = ""):
    """Agrega una advertencia a un usuario. Si llega a 3, banea temporalmente."""
    existing = get_user_warnings(user_id)
    now = datetime.now().isoformat()

    if existing:
        new_count = existing["warnings_count"] + 1
        if new_count >= 3:
            # Ban temporal 3 horas
            ban_until = (datetime.now() + timedelta(hours=3)).isoformat()
            db_safe_run(
                """UPDATE user_warnings
                   SET warnings_count = ?, last_warning = ?, banned_until = ?, ban_reason = ?, updated_at = ?, username = ?
                   WHERE user_id = ?""",
                (new_count, now, ban_until, reason, now, username, user_id),
                commit=True
            )
            return new_count, True  # True indica que fue baneado
        else:
            db_safe_run(
                """UPDATE user_warnings
                   SET warnings_count = ?, last_warning = ?, updated_at = ?, username = ?
                   WHERE user_id = ?""",
                (new_count, now, now, username, user_id),
                commit=True
            )
    else:
        db_safe_run(
            """INSERT INTO user_warnings
               (user_id, username, warnings_count, last_warning, updated_at)
               VALUES (?, ?, 1, ?, ?)""",
            (user_id, username, now, now),
            commit=True
        )
        new_count = 1

    return new_count, False

def is_user_banned(user_id: int) -> tuple[bool, str]:
    """Verifica si un usuario está baneado temporalmente. Retorna (baneado, razón)."""
    warnings = get_user_warnings(user_id)
    if warnings and warnings["banned_until"]:
        ban_until = datetime.fromisoformat(warnings["banned_until"])
        if datetime.now() < ban_until:
            return True, warnings["ban_reason"] or "Comportamiento inadecuado"
        else:
            # Ban expirado, limpiar
            db_safe_run("UPDATE user_warnings SET banned_until = NULL, ban_reason = NULL WHERE user_id = ?", (user_id,), commit=True)
    return False, ""

def estimar_fecha_creacion(user_id: int) -> str:
    """Estima la fecha de creación de una cuenta de Telegram basada en su ID."""
    ids = sorted(TELEGRAM_ID_AGES.keys())

    if user_id < ids[0]:
        return "Ancestral (Pre-2013)"
    if user_id > ids[-1]:
        # Extrapolación lineal para IDs más nuevos
        # Usar los últimos dos puntos para calcular la pendiente
        last_id = ids[-1]
        prev_id = ids[-2]
        last_ts = TELEGRAM_ID_AGES[last_id]
        prev_ts = TELEGRAM_ID_AGES[prev_id]

        # Pendiente: cambio en timestamp por cambio en ID
        slope = (last_ts - prev_ts) / (last_id - prev_id)

        # Extrapolar
        extrapolated_ts = last_ts + slope * (user_id - last_id)

        dt = datetime.fromtimestamp(extrapolated_ts / 1000)
        return dt.strftime("%m/%Y")

    # Interpolación lineal
    for i in range(len(ids) - 1):
        lower_id = ids[i]
        upper_id = ids[i+1]
        if lower_id <= user_id <= upper_id:
            lower_ts = TELEGRAM_ID_AGES[lower_id]
            upper_ts = TELEGRAM_ID_AGES[upper_id]

            ratio = (user_id - lower_id) / (upper_id - lower_id)
            estimated_ts = lower_ts + ratio * (upper_ts - lower_ts)

            dt = datetime.fromtimestamp(estimated_ts / 1000)
            return dt.strftime("%m/%Y")

    return "Desconocido"

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
    nombre_seguro = str(user.first_name or "Mortal").replace('&', '&').replace('<', '<').replace('>', '>').replace('"', '"')
    texto = (
        f"🛕 <b>Bienvenido al Templo {nombre_seguro}.</b>\n\n"
        "Yo, el Guardián Erudito Caído, custodio este refugio de sabiduría.\n"
        "Explora mis dones:\n• 📜 /relato\n• 🛒 /tienda\n• 🛡️ /info"
    )
    keyboard = [[InlineKeyboardButton("🛒 Tienda", url=ITCH_URL)]]
    await update.message.reply_text(texto, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))

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

@restricted_access
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para inspeccionar la esencia de un mortal."""
    if not update.message.reply_to_message:
        target_user = update.effective_user
        target_msg = update.message
    else:
        target_user = update.message.reply_to_message.from_user
        target_msg = update.message.reply_to_message

    # Obtener reputación
    rep_data = get_user_reputation(target_user.id)
    reputacion = rep_data["reputation"] if rep_data else 50
    edad_estimada = estimar_fecha_creacion(target_user.id)

    # Emoji según reputación
    if reputacion >= 70:
        emoji_rep = "😇"
    elif reputacion >= 40:
        emoji_rep = "😐"
    elif reputacion >= 20:
        emoji_rep = "😠"
    else:
        emoji_rep = "💀"

    # Información básica
    texto = f"🛡️ *Análisis del Mortal:*\n\n"
    texto += f"👤 *Nombre:* {target_user.mention_markdown()}\n"
    texto += f"🆔 *ID:* `{target_user.id}`\n"
    texto += f"📅 *Edad Estimada:* {edad_estimada}\n"
    texto += f"{emoji_rep} *Reputación:* {reputacion}/100\n"

    # Si es un forward, mostrar origen
    if hasattr(target_msg, 'forward_origin') and target_msg.forward_origin:
        origin = target_msg.forward_origin
        if hasattr(origin, 'sender_user') and origin.sender_user:
            fwd_user = origin.sender_user
            fwd_edad = estimar_fecha_creacion(fwd_user.id)
            texto += f"\n🔄 *Mensaje Reenviado de:*\n"
            texto += f"👤 {fwd_user.first_name}\n"
            texto += f"🆔 `{fwd_user.id}` | 📅 {fwd_edad}\n"
        elif hasattr(origin, 'chat') and origin.chat:
            fwd_chat = origin.chat
            texto += f"\n🔄 *Mensaje Reenviado de Chat:*\n"
            texto += f"📢 {fwd_chat.title} (`{fwd_chat.id}`)\n"
        elif hasattr(origin, 'sender_name') and origin.sender_name:
            texto += f"\n🔄 *Mensaje Reenviado de:* {origin.sender_name} (oculto)\n"
    # Fallback API antigua
    elif hasattr(target_msg, 'forward_from') and target_msg.forward_from:
        fwd_user = target_msg.forward_from
        fwd_edad = estimar_fecha_creacion(fwd_user.id)
        texto += f"\n🔄 *Mensaje Reenviado de:*\n"
        texto += f"👤 {fwd_user.first_name}\n"
        texto += f"🆔 `{fwd_user.id}` | 📅 {fwd_edad}\n"
    elif hasattr(target_msg, 'forward_from_chat') and target_msg.forward_from_chat:
        fwd_chat = target_msg.forward_from_chat
        texto += f"\n🔄 *Mensaje Reenviado de Chat:*\n"
        texto += f"📢 {fwd_chat.title} (`{fwd_chat.id}`)\n"
    elif hasattr(target_msg, 'forward_sender_name') and target_msg.forward_sender_name:
        texto += f"\n🔄 *Mensaje Reenviado de:* {target_msg.forward_sender_name} (oculto)\n"

    await update.message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


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
async def debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando exclusivo del OWNER para obtener JSON del mensaje respondido."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Responde al mensaje que quieres analizar.")
        return

    rtm = update.message.reply_to_message
    json_str = json.dumps(rtm.to_dict(), indent=2, ensure_ascii=False)
    if len(json_str) > 4096:
        await update.message.reply_text("El JSON es demasiado largo para enviar.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"<code>{json_str}</code>", parse_mode=ParseMode.HTML)

@owner_only
@restricted_access
async def advertir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para advertir a un usuario respondido."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Responde al mensaje del usuario a advertir.")
        return

    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "Comportamiento inadecuado"

    warnings_count, was_banned = add_warning(target.id, target.username or target.first_name, reason)

    if was_banned:
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, target.id, until_date=datetime.now() + timedelta(hours=3))
            await update.message.reply_text(f"El mortal {target.mention_html()} ha sido exiliado temporalmente (3h) por acumulación de advertencias.", parse_mode=ParseMode.HTML)
            db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", ("exilio_temporal", target.id, datetime.now().isoformat()), commit=True)
        except Exception as e:
            logger.error(f"Error baneando: {e}")
    else:
        await update.message.reply_text(f"⚠️ Advertencia {warnings_count}/3 para {target.mention_html()}. Razón: {reason}", parse_mode=ParseMode.HTML)

@owner_only
@restricted_access
async def silenciar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para silenciar (restrict) a un usuario respondido por 1 hora."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Responde al mensaje del usuario a silenciar.")
        return

    target = update.message.reply_to_message.from_user
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id,
            target.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=datetime.now() + timedelta(hours=1)
        )
        await update.message.reply_text(f"El mortal {target.mention_html()} ha sido silenciado por 1 hora.", parse_mode=ParseMode.HTML)
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", ("silenciar", target.id, datetime.now().isoformat()), commit=True)
    except Exception as e:
        await update.message.reply_text(f"No pude silenciar al usuario: {e}")

@owner_only
@restricted_access
async def expulsar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para expulsar (kick) a un usuario respondido."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Responde al mensaje del usuario a expulsar.")
        return

    target = update.message.reply_to_message.from_user
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)  # Kick = ban + unban inmediato
        await update.message.reply_text(f"El mortal {target.mention_html()} ha sido expulsado del templo.", parse_mode=ParseMode.HTML)
        db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", ("expulsar", target.id, datetime.now().isoformat()), commit=True)
    except Exception as e:
        await update.message.reply_text(f"No pude expulsar al usuario: {e}")

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
    if not update.message or not update.message.text: return
    if update.effective_chat.id not in ALLOWED_CHATS: return
    
    ia_disponible = bool(GEMINI_API_KEY)
    user = update.effective_user
    if not user:
        return
    msg_text = update.message.text

    # ANTI-FLOOD: Verificar si está floodando
    now = datetime.now().timestamp()
    if user.id not in FLOOD_TRACK:
        FLOOD_TRACK[user.id] = []
    FLOOD_TRACK[user.id].append(now)
    # Mantener solo mensajes de los últimos 10 segundos
    FLOOD_TRACK[user.id] = [t for t in FLOOD_TRACK[user.id] if now - t < 10]
    if len(FLOOD_TRACK[user.id]) > 5:  # Más de 5 mensajes en 10s
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id,
                user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=datetime.now() + timedelta(minutes=5)
            )
            await update.message.reply_text(f"El mortal {user.mention_html()} ha sido silenciado por flood (5 min).", parse_mode=ParseMode.HTML)
            return  # No procesar más
        except Exception as e:
            logger.error(f"Error anti-flood: {e}")

    # Detección de reenvíos
    forward_info = ""
    if hasattr(update.message, 'forward_origin') and update.message.forward_origin:
        origin = update.message.forward_origin
        if hasattr(origin, 'sender_user') and origin.sender_user:
            fwd_user = origin.sender_user
            fwd_rep = get_user_reputation(fwd_user.id)
            fwd_reputacion = fwd_rep["reputation"] if fwd_rep else 50
            fwd_edad = estimar_fecha_creacion(fwd_user.id)
            forward_info = f"El mensaje es un reenvío de {fwd_user.first_name} (ID: {fwd_user.id}, Edad: {fwd_edad}, Reputación: {fwd_reputacion}/100)."
        elif hasattr(origin, 'chat') and origin.chat:
            fwd_chat = origin.chat
            forward_info = f"El mensaje es un reenvío del chat '{fwd_chat.title}' (ID: {fwd_chat.id})."
        elif hasattr(origin, 'sender_name') and origin.sender_name:
            forward_info = f"El mensaje es un reenvío de '{origin.sender_name}' (usuario oculto)."
    # Fallback para API antigua (si existe)
    elif hasattr(update.message, 'forward_from') and update.message.forward_from:
        fwd_user = update.message.forward_from
        fwd_rep = get_user_reputation(fwd_user.id)
        fwd_reputacion = fwd_rep["reputation"] if fwd_rep else 50
        fwd_edad = estimar_fecha_creacion(fwd_user.id)
        forward_info = f"El mensaje es un reenvío de {fwd_user.first_name} (ID: {fwd_user.id}, Edad: {fwd_edad}, Reputación: {fwd_reputacion}/100)."
    elif hasattr(update.message, 'forward_from_chat') and update.message.forward_from_chat:
        fwd_chat = update.message.forward_from_chat
        forward_info = f"El mensaje es un reenvío del chat '{fwd_chat.title}' (ID: {fwd_chat.id})."
    elif hasattr(update.message, 'forward_sender_name') and update.message.forward_sender_name:
        forward_info = f"El mensaje es un reenvío de '{update.message.forward_sender_name}' (usuario oculto)."
    
    # Identificar si el usuario es Kai (el padre de Mashi)
    es_kai = user.id == OWNER_ID
    nombre_usuario = "Kai (tu padre/creador)" if es_kai else user.first_name
    
    # ============== SISTEMA DE DETECCIÓN DE HOSTILIDAD / NSFW / ELOGIOS ==============
    es_hostil, insulto_detectado = detectar_hostilidad(msg_text)
    es_nsfw, nsfw_detectado = detectar_nsfw(msg_text) if not es_hostil else (False, "")
    elogio_detectado = detectar_elogio(msg_text) if not es_hostil else False
    user_rep_data = get_user_reputation(user.id)
    reputacion_actual = user_rep_data["reputation"] if user_rep_data else 50
    roleplay_permitido = es_nsfw and reputacion_actual >= 40 and not es_hostil

    # ============== DETECCIÓN DE RETOS/CONFRONTACIONES ==============
    retos_patterns = [
        r'\b(échame|sácame|expúlsame|báname|kick|ban)\b',
        r'\b(hazlo|atrévete|prueba|inténtalo)\b.*\b(expuls|ban|kick|sac)\b',
        r'\b(no.*puedes?|cobarde?|débil?)\b.*\b(expuls|ban)\b'
    ]
    es_reto = False
    for pattern in retos_patterns:
        if re.search(pattern, msg_text, re.IGNORECASE):
            es_reto = True
            break
    
    # Si es hostil y NO es Kai, actualizar reputación
    if es_hostil and not es_kai:
        reputacion_actual = update_user_reputation(
            user.id,
            user.username or user.first_name,
            delta=-10,  # Penalización por insulto
            insulto=insulto_detectado
        )
        logger.info(f"🔥 Hostilidad detectada de {user.first_name}: '{insulto_detectado}'")

        # Si además es reto y reputación muy baja, advertir
        if es_reto and reputacion_actual < 30:
            warnings_count, was_banned = add_warning(user.id, user.username or user.first_name, f"Insulto + reto: {insulto_detectado}")
            if was_banned:
                # Banear temporalmente
                try:
                    await context.bot.ban_chat_member(update.effective_chat.id, user.id, until_date=datetime.now() + timedelta(hours=3))
                    await update.message.reply_text(f"El mortal {user.mention_html()} ha sido exiliado temporalmente por comportamiento inadecuado. Regresará en 3 horas.", parse_mode=ParseMode.HTML)
                    db_safe_run("INSERT INTO mod_logs (action, target_id, timestamp) VALUES (?, ?, ?)", ("exilio_temporal", user.id, datetime.now().isoformat()), commit=True)
                except Exception as e:
                    logger.error(f"Error baneando: {e}")
            else:
                await update.message.reply_text(f"⚠️ Advertencia {warnings_count}/3 para {user.mention_html()}. Comportamiento inadecuado.", parse_mode=ParseMode.HTML)

    elif not es_hostil and not es_kai:
        # Mensaje normal = pequeña mejora de reputación
        if random.random() < 0.3:  # 30% de chance de mejorar rep
            update_user_reputation(user.id, user.username or user.first_name, delta=1)
    
    CHAT_CONTEXT.append(f"{nombre_usuario}: {msg_text}")

    if not es_hostil and es_saludo_hola_leon(msg_text):
        texto_saludo = construir_saludo_hola_leon(user, reputacion_actual)
        CHAT_CONTEXT.append(f"Mashi: {texto_saludo}")
        await update.message.reply_text(texto_saludo, parse_mode=ParseMode.HTML)
        return

    is_reply = (update.message.reply_to_message and
                update.message.reply_to_message.from_user.id == context.bot.id)
    is_mentioned = re.search(r"(mashi|guardián|león|mamoru)", msg_text, re.IGNORECASE)
    is_from_kai = es_kai  # Siempre responder a Kai
    is_hostile_trigger = es_hostil  # Siempre responder a insultos
    is_nsfw_trigger = es_nsfw
    is_praise_trigger = elogio_detectado and reputacion_actual >= 60
    random_threshold = 0.02 if reputacion_actual >= 60 else 0.005
    random_chance = random.random() < random_threshold

    if is_reply or is_mentioned or is_from_kai or is_hostile_trigger or is_nsfw_trigger or is_praise_trigger or random_chance:
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
            # Usuario normal - ajustar tono según reputación y contexto
            if is_praise_trigger:
                prompt_sistema += "\n\nEl mortal acaba de rendirte un elogio sincero. Responde con gratitud templada, sin perder tu aura divina."
            elif reputacion_actual < 30:
                prompt_sistema += f"\n\nNOTA: Este usuario ({user.first_name}) tiene mala reputación ({reputacion_actual}/100). Sé frío y distante con él."
            elif reputacion_actual > 70:
                prompt_sistema += f"\n\nNOTA: Este usuario ({user.first_name}) tiene buena reputación ({reputacion_actual}/100). Puedes ser más amable."

        if roleplay_permitido:
            prompt_sistema += NSFW_ROLEPLAY_PROMPT
        elif es_nsfw and not es_hostil:
            prompt_sistema += "\n\nADVERTENCIA: El usuario solicita contenido sensual sin la confianza suficiente. Recuerda las reglas del templo y responde con firmeza sin describir escenas íntimas."
        
        prompt_usuario = f"HISTORIAL DE CHAT:\n{historial}\n\n"
        if forward_info:
            prompt_usuario += f"INFORMACIÓN ADICIONAL: {forward_info}\n\n"
        if roleplay_permitido:
            prompt_usuario += f"El mortal desea roleplay sensual y mencionó '{nsfw_detectado}'. Mantén elegancia insinuante.\n\n"
        elif es_nsfw and not es_hostil:
            prompt_usuario += "El mortal insinúa contenido adulto sin suficiente confianza. Recuérdale las reglas con firmeza.\n\n"
        prompt_usuario += "Responde al último mensaje como Mashi:"
        
        if ia_disponible:
            respuesta = await consultar_ia(prompt_sistema, prompt_usuario)
            if respuesta:
                CHAT_CONTEXT.append(f"Mashi: {respuesta}")
                await update.message.reply_text(respuesta)
                return
        
        fallback = construir_respuesta_fallback(es_kai, es_hostil, reputacion_actual, insulto_detectado, es_nsfw, nsfw_detectado, user)
        CHAT_CONTEXT.append(f"Mashi: {fallback}")
        await update.message.reply_text(fallback)
        return

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id not in ALLOWED_CHATS: return
    new_members = update.message.new_chat_members
    chat_id = update.effective_chat.id
    adder = update.message.from_user

    admin_lookup_failed = False
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
    except Exception as e:
        admin_lookup_failed = True
        admin_ids = []
        logger.warning(f"No pude obtener admins del chat {chat_id}: {e}")

    for member in new_members:
        if member.is_bot and member.id != context.bot.id:
            if adder.id == OWNER_ID or adder.id in admin_ids or admin_lookup_failed:
                await context.bot.send_message(chat_id, f"Acepto al autómata {member.mention_html()} por orden de la autoridad.", parse_mode=ParseMode.HTML)
            else:
                try:
                    await context.bot.ban_chat_member(chat_id, member.id)
                    await context.bot.send_message(chat_id, f"{random.choice(FRASES_ANTI_BOT)} ({member.mention_html()})", parse_mode=ParseMode.HTML)
                except: pass
        elif not member.is_bot:
            await ensure_user(member)
            edad_estimada = estimar_fecha_creacion(member.id)
            kb = [[InlineKeyboardButton("Soy Mayor de 18", callback_data=f"age_yes:{member.id}")],
                  [InlineKeyboardButton("Soy Menor", callback_data=f"age_no:{member.id}")]]
            await context.bot.send_message(chat_id, f"Mortal {member.mention_html()} (Cuenta: {edad_estimada}), confirma tu edad (+18) para permanecer en el templo.", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

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
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("purificar", purificar))
    application.add_handler(CommandHandler("exilio", exilio))
    application.add_handler(CommandHandler("reputacion", reputacion))
    application.add_handler(CommandHandler("debug", debug))
    application.add_handler(CommandHandler("advertir", advertir))
    application.add_handler(CommandHandler("silenciar", silenciar))
    application.add_handler(CommandHandler("expulsar", expulsar))
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    application.add_handler(CallbackQueryHandler(age_verification_handler, pattern="^age_"))
    
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), conversacion_natural))
    application.add_handler(MessageHandler(filters.ALL, handle_bot_messages))

    logger.info("Mashi está en línea.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()