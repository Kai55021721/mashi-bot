import os
import random
from datetime import datetime, timedelta, timezone
from functools import wraps
from dotenv import load_dotenv
from telegram import Update, ChatPermissions
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Carga las variables del archivo .env al entorno
load_dotenv()

# --- Configuración de Mashi (Modo Seguro con .env) ---
# Leemos el token que cargamos desde el archivo .env
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("No se encontró la variable de entorno TELEGRAM_TOKEN. ¿Creaste el archivo .env?")

OWNER_ID = 1890046858  # Reemplaza con tu ID de USUARIO
CHANNEL_ID = -1001537357564  # Reemplaza con tu ID de CANAL

# --- Biblioteca de Stickers de Mashi ¡Completa! ---
STICKERS_MASHI = {
    "bienvenida": ["CAACAgEAAxkBAAMhaH8vXP5TK2wCm6Rhswjd4YGvQ3kAAiEAA_VzPiGC-sUZ3K6fQDYE", "CAACAgEAAxkBAAMjaH8vkoAUsEI9cElXQkWSV0GeTmwAAjkEAAJDxwFFaFCJcG9PQ0w2BA", "CAACAgEAAxkBAAMlaH8v27LaeG_OqeDCzzY9uYzpSJ0AAh4BAALuPvQTufVLeDk2skA2BA"],
    "pregunta": ["CAACAgQAAxkBAAMnaH8wCMNQtvhqMpnoRku8okncdX0AApMJAAK6hJUJZP319e21ll02BA", "CAACAgEAAxkBAAMpaH8wPYZ4WpTUv6Q3GpI6STfo7pIAAgaCAAKvGWIHkyHlYkubVQU2BA", "CAACAgEAAxkBAAMraH8wuInCUvb-O3H6UOTeD5gD51YAAoACAALNOylG8TYmulCY2mY2BA"],
    "entrometido": ["CAACAgEAAxkBAAMtaH8w7goEQPqdkqfkhegjwcM49h0AAj4CAAI6OC4FtWwnrTDY_bk2BA", "CAACAgEAAxkBAAMvaH8xKajPj479j93fwsNDVvEU09EAAiACAAKGCvlEiEEpL64JXIs2BA", "CAACAgEAAxkBAAMzaH8zIxNxghb4GqG5QgEaCLhIefgAAnMAA0T71wOTgPPcE1LiYDYE"],
    "rugido": "CAACAgUAAxkBAAM1aH80YqFYWuboCHmRQbSUlFDBZgMAAq4GAAJq0coFCIV7sNzZaeo2BA",
    "chiste": "CAACAgEAAxkBAAM4aH80xYMRhBbf7PH12Y6sK6JC1ncAAnwCAALfJAABRX8K5zfE-EumNgQ",
    "enfadado": "CAACAgQAAxkBAAMPaH8uQ8ooKLoYuO-XpQWNBixlCYcAAicBAAIFMywQjEwAAX_WsOGnNgQ"
}

# --- Listas de Respuestas de Texto ---
FRASES_BIENVENIDA = ["¡Silencio! Un nuevo cachorro ha entrado en mi territorio. Soy Mashi, el guardián. No rompas nada.", "Detecto un nuevo aroma... Ah, eres tú. Pórtate bien y no tendrás que conocer mis garras.", "He sentido una perturbación en el templo. Ah, solo eres tú. Me llamo Mashi. No toques nada valioso.", "¿Otro más? Esto parece un desfile. Bueno, mientras traigas chismes interesantes, puedes quedarte. Te observo.", "En nombre del gran Kai, te permito la entrada a este sagrado lugar. Pero que sepas que mis ojos no se apartarán de ti."]
CHISTES_MASHI = ["¿Qué le dice un león a otro? ¿Vamos a la carnicería o esperamos el delivery de gacelas?", "¿Por qué cruzó el león la carretera? ¡Para demostrar que tenía agallas!", "¿Qué hace una abeja en el gimnasio? ¡Zumba!"]

# --- Cerebro Local de Mashi ---
RESPUESTAS_LOCALES = {
    "saludo": ["¿Qué quieres, {salutation}?", "Estaba ocupado vigilando. Sé breve, {salutation}.", "Un saludo. Espero que no sea una tontería."],
    "despedida": ["Ya era hora. Vuelve a tus asuntos, {salutation}.", "Adiós. El templo estará más tranquilo sin ti.", "Bien, menos ruido."],
    "estado": ["Estoy perfectamente, {salutation}. Mi vigilancia es impecable, como siempre.", "Ocupado. Protegiendo el templo de gamberros como tú.", "Funcionando a la perfección, gracias por tu inútil pregunta."],
    "agradecimiento": ["Como debe ser.", "El reconocimiento es aceptable.", "No necesito tu gratitud, solo tu obediencia."],
    "lore": ["Mi historia es demasiado grandiosa para tu mente de gamberro. Basta con saber que sirvo a Kai.", "Soy el guardián de este templo y el protector de Kai. Es todo lo que necesitas saber.", "Soy Mashi. Proteger a mi padre Kai es mi única misión. Fin de la historia."],
    "desconocido": ["No he entendido esa estupidez. Intenta hablar con más claridad, gamberro.", "Hmm... fascinante. Sigue, quiero ver a dónde lleva esta tontería.", "¿Me estás hablando a mí? Porque no me interesa."]
}

# --- Función Ayudante para Respuestas Inteligentes ---
async def reply_or_send(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs):
    try:
        if update.message and update.message.sender_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, **kwargs)
        else:
            await update.message.reply_text(text=text, **kwargs)
    except Exception as e:
        print(f"Error al enviar/responder mensaje: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, **kwargs)

# --- Decorador de Seguridad para Kai ---
def owner_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        sender_chat_id = update.message.sender_chat.id if update.message.sender_chat else None
        if user_id == OWNER_ID or sender_chat_id == CHANNEL_ID:
            return await func(update, context, *args, **kwargs)
        else:
            await reply_or_send(update, context, "¿Un mortal dándome órdenes a mí? ¡Insolente! Solo obedezco al gran Kai Shitsumon.")
            return
    return wrapped

# --- Funciones de Comandos ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_or_send(update, context, "He llegado. Soy Mashi, el guardián. Llámame por mi nombre si necesitas algo, gamberro.")

async def ayudamashi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto_ayuda = "Rugidos y órdenes de Mashi:\n/quiensoy - Te diré cuál es mi sagrada misión.\n/rugir - Escucha mi poderoso rugido.\n/chiste - Te contaré un chiste tan malo que te reirás.\n/proteger - Anunciaré que el templo está bajo mi protección."
    user_id = update.effective_user.id
    sender_chat_id = update.message.sender_chat.id if update.message.sender_chat else None
    if user_id == OWNER_ID or sender_chat_id == CHANNEL_ID:
        texto_ayuda += "\n\n--- Órdenes de Kai ---\n/informe - Mi reporte, maestro.\n/anuncio <texto> - Publicaré un anuncio.\n/callate - Entraré en modo silencioso.\n/despierta - Reanudaré mi vigilancia activa."
    await reply_or_send(update, context, texto_ayuda)

async def quiensoy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_or_send(update, context, "Soy Mashi, el león amarillo. Mi única misión es proteger el sagrado Templo de Kai Shitsumon. Mi vida es la devoción, mi pasatiempo es la irreverencia.")

async def rugir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_or_send(update, context, "¡¡¡GRRRRRRAAAAAAAUUUUURRRR!!!")
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKERS_MASHI["rugido"])

async def chiste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_or_send(update, context, random.choice(CHISTES_MASHI))
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKERS_MASHI["chiste"])

async def proteger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_or_send(update, context, "¡A mi lado! Me pongo en modo guardián. Nadie pasará mientras Mashi vigile.")

# --- Comandos solo para el Propietario ---
@owner_only
async def informe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_or_send(update, context, "A tus órdenes, Kai. El templo está en calma. Sin intrusos. Todo en orden.")

@owner_only
async def anuncio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    texto_anuncio = " ".join(context.args)
    if not texto_anuncio:
        await reply_or_send(update, context, "Dime qué debo anunciar, maestro. Usa: /anuncio <tu mensaje>")
        return
    mensaje_final = f"¡ATENCIÓN, GAMBERROS! 📢\n\nOrden del maestro Kai:\n\n*\"{texto_anuncio}\"*"
    await reply_or_send(update, context, mensaje_final, parse_mode='Markdown')

@owner_only
async def callate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data['is_silent'] = True
    await reply_or_send(update, context, "Entendido, Kai. Vigilancia silenciosa activada.")

@owner_only
async def despierta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data['is_silent'] = False
    await reply_or_send(update, context, "¡GRRR! Vigilancia activa reanudada.")

# --- Funciones de Comportamiento ---
async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_who_added = update.message.from_user
    chat_id = update.effective_chat.id
    admins = await context.bot.get_chat_administrators(chat_id)
    admin_ids = {admin.user.id for admin in admins}
    for new_member in update.message.new_chat_members:
        if new_member.is_bot:
            if new_member.id == context.bot.id: continue
            if user_who_added.id not in admin_ids:
                try:
                    await context.bot.send_sticker(chat_id=chat_id, sticker=STICKERS_MASHI["enfadado"])
                    await context.bot.ban_chat_member(chat_id=chat_id, user_id=new_member.id)
                    await reply_or_send(update, context, f"¡¿CÓMO TE ATREVES, {user_who_added.first_name}?! ¡Has intentado profanar este templo con esta basura de spam! Odio a estos bots con todo mi ser. ¡Intruso desterrado!")
                    restriction_end_time = datetime.now(timezone.utc) + timedelta(hours=1)
                    permissions = ChatPermissions(can_send_messages=False)
                    await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_who_added.id, permissions=permissions, until_date=restriction_end_time)
                except BadRequest:
                    await reply_or_send(update, context, f"¡He detectado un bot intruso (@{new_member.username}), pero no tengo permisos para desterrarlo! ¡Administradores, ayudadme a purgar esta escoria!")
            else:
                await reply_or_send(update, context, f"Un administrador ha traído a esta máquina, @{new_member.username}. Supongo que tendré que tolerarlo. Pero te estaré vigilando.")
        else:
            await reply_or_send(update, context, random.choice(FRASES_BIENVENIDA))
            await context.bot.send_sticker(chat_id=chat_id, sticker=random.choice(STICKERS_MASHI["bienvenida"]))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or update.message.text.startswith('/'): return

    text = update.message.text.lower()

    if 'mashi' not in text:
        return

    if context.bot_data.get('is_silent', False):
        return

    user_id = update.effective_user.id
    sender_chat_id = update.message.sender_chat.id if update.message.sender_chat else None
    is_kai = (user_id == OWNER_ID or sender_chat_id == CHANNEL_ID)
    salutation = "maestro Kai" if is_kai else "gamberro"

    response_key = "desconocido"
    if any(word in text for word in ["hola", "buenas", "hey", "qué tal"]):
        response_key = "saludo"
    elif any(word in text for word in ["adiós", "chao", "hasta luego", "nos vemos"]):
        response_key = "despedida"
    elif any(word in text for word in ["cómo estás", "qué haces", "todo bien"]):
        response_key = "estado"
    elif any(word in text for word in ["gracias", "genial", "buen bot"]):
        response_key = "agradecimiento"
    elif any(word in text for word in ["quién es kai", "tu misión", "tu padre", "cuéntame de ti"]):
        response_key = "lore"

    if 'negro' in text:
        await reply_or_send(update, context, "Con un rayo podemos arreglar eso.")
        return

    response_text = random.choice(RESPUESTAS_LOCALES[response_key]).format(salutation=salutation)
    await reply_or_send(update, context, response_text)

# --- Función Principal ---
def main() -> None:
    """Inicia el bot."""
    application = Application.builder().token(TOKEN).build()
    application.bot_data['is_silent'] = False

    # Comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ayudamashi", ayudamashi))
    application.add_handler(CommandHandler("quiensoy", quiensoy))
    application.add_handler(CommandHandler("rugir", rugir))
    application.add_handler(CommandHandler("chiste", chiste))
    application.add_handler(CommandHandler("proteger", proteger))
    application.add_handler(CommandHandler("informe", informe))
    application.add_handler(CommandHandler("anuncio", anuncio))
    application.add_handler(CommandHandler("callate", callate))
    application.add_handler(CommandHandler("despierta", despierta))

    # Comportamientos
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("El bot Mashi está funcionando...")
    application.run_polling()

if __name__ == "__main__":
    main()
