#!venv/bin/python

from dotenv import dotenv_values
secrets = dotenv_values(".env")
assert(secrets["API_KEY"])

from py_epos.printer import *
import socket

HOST = secrets["IP"]
PORT = 9100  # The port used by the server


import logging
from telegram import Update
from telegram.ext import filters, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler

import string
import unicodedata
from unidecode import unidecode

def deEmojify(inputString):
    returnString = ""

    for character in inputString:
        try:
            character.encode("ascii")
            returnString += character
        except UnicodeEncodeError:
            replaced = unidecode(str(character))
            if replaced != '':
                returnString += replaced
            else:
                try:
                     returnString += "[" + unicodedata.name(character) + "]"
                except ValueError:
                     returnString += "[x]"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

class Globals:
    printerSocket = None
    printer = None

not_connected = 'Printer is not connected.'


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = "Connection was already set up."
    if not Globals.printerSocket:
        try:
            Globals.printerSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            Globals.printerSocket.connect((HOST, PORT))
            Globals.printer = Printer(Globals.printerSocket)
            message = f"Connected to printer."

            user = update.message.chat
            firstline = f"{user.first_name} {user.last_name}"
            Globals.printer.println(BIGFONT, Just.CENTER, firstline)
            Globals.printer.println(SMALLFONT, update.message.date.strftime("%Y-%m-%d %H:%M:%S"))
            Globals.printer.print(Just.LEFT)
            Globals.printer.feed(2)

        except socket.error as e:
            message = str(e)
            Globals.printerSocket = None

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = not_connected
    if Globals.printerSocket:
        # TODO: Make feed optional.
        Globals.printer.print(defaultCut.FEED_CUT())
        Globals.printerSocket.close()
        message = "Successfully closed connection."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = not_connected
    if Globals.printerSocket:
        message = 'k'
        mm = 1
        if "mm" in update.message.text:
            try:
                mm = int(update.message.text.strip(string.ascii_letters))
            except:
                message = f"Could not parse {update.message.text} as int."
        Globals.printer.feed(mm=mm)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def regularMessage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = not_connected
    if Globals.printerSocket:
        message = 'k'
        # TODO: De-emojify
        try:
            Globals.printer.println(update.message.text)
        except UnicodeEncodeError as e:
            message = f"{e}: Pls don't use that garbage here"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


if __name__ == '__main__':
    application = ApplicationBuilder().token(secrets["API_KEY"]).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('end', end))
    application.add_handler(CommandHandler('feed', feed))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), regularMessage))

    application.run_polling()

"""
Update(
    message=Message(
        channel_chat_created=False,
        chat=Chat(
            first_name='Pascal',
            id=170554685,
            last_name='(optional)',
            type=<ChatType.PRIVATE>,
            username='Urinator'),
        date=datetime.datetime(2025, 1, 30, 19, 40, 49, tzinfo=datetime.timezone.utc),
        delete_chat_photo=False,
        entities=(
            MessageEntity(length=9, offset=0, type=<MessageEntityType.ITALIC>),
            MessageEntity(length=3, offset=10, type=<MessageEntityType.BOLD>)),
        from_user=User(
            first_name='Pascal',
            id=170554685,
            is_bot=False,
            language_code='en',
            last_name='(optional)',
            username='Urinator'),
        group_chat_created=False,
        message_id=17,
        supergroup_chat_created=False,
        text='formatted BOB'),
    update_id=225771877)
"""