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
from io import BytesIO
import asyncio

import string
import unicodedata
from unidecode import unidecode

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARN
)

class Globals:
    printer : Printer = None
    default_resolution = Printer.Image.DD_8
    last_user_id = None
    print_user_changes = True
    sock_timeout_s = 5

not_connected = 'Printer is not connected.'

def maybeConnect() -> str:
    if not Globals.printer:
        try:
            newsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            newsock.settimeout(Globals.sock_timeout_s)
            newsock.connect((HOST, PORT))
            Globals.printer = Printer(newsock)
            return f"Connected to printer."

        except socket.error as e:
            Globals.printer = None
            return str(e)
    return None

def printAndUpdateIfNewUser(message):
    user = message.chat
    time = message.date

    # import pdb; pdb.set_trace()

    if hasattr(message, 'forward_origin') and message.forward_origin:
        if hasattr(message.forward_origin, "sender_user"):
            user = message.forward_origin.sender_user
        elif hasattr(message.forward_origin, "sender_user_name"):
            class AnonUser:
                def __init__(self, name):
                    self.first_name = name
                    self.last_name = None
                    self.id = hash(name)

            user = AnonUser(message.forward_origin.sender_user_name)
    elif hasattr(message, 'from_user') and message.from_user:
        user = message.from_user

    id = user.id
    name = str(user.first_name)
    if user.last_name:
        name += " " + str(user.last_name)

    if not Globals.last_user_id or Globals.last_user_id != id:
        printNewUser(name, time)
        Globals.last_user_id = id

def printNewUser(name, date):
    if Globals.printer:
        Globals.printer.println(Just.RIGHT, BIGFONT, name)
        Globals.printer.println(SMALLFONT, date.strftime("%Y-%m-%d %H:%M:%S"))
        Globals.printer.print(Just.LEFT)
        Globals.printer.feed(mm= 2)

async def setUserEcho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    Globals.print_user_changes = "on" in update.message.text
    state = "on" if Globals.print_user_changes else "off"
    message = f"Set printing user names to {Globals.print_user_changes}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = maybeConnect() or "Connection was already set up."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def cut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = maybeConnect() or ""
    if Globals.printer:
        Globals.printer.print(defaultCut.FEED_CUT())
        message += "k (ut)"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = not_connected
    if Globals.printer:
        Globals.printer.socket.close()
        Globals.printer = None
        message = "Successfully closed connection."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def setLog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = ""
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


async def feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = maybeConnect() or ""
    if Globals.printer:
        mm = 1
        command = update.message.text.replace('/feed', '')
        if len(command) > 1:
            try:
                mm = int(command.strip(string.ascii_letters))
            except:
                message = f"Could not parse {update.message.text} as int."
                message += f"\n{update}"
        message = f'Advancing {mm}mm'
        Globals.printer.feed(mm=mm)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


def deEmojify(inputString):
    returnString = ""

    encoding = 'ascii'
    if Globals.printer:
        encoding = Globals.printer.encoding

    for character in inputString:
        try:
            character.encode(encoding)
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

    return returnString

async def regularMessage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = maybeConnect() or ""
    if Globals.printer:
        try:
            printAndUpdateIfNewUser(update.message)
        except Exception as e:
            message += f"Could not print new user.\n{update.message}\n{e}"

        # TODO: use entities (italic, bold, etc)
        text = deEmojify(update.message.text)

        try:
            Globals.printer.println(BIGFONT, text)
            Globals.printer.feed(2)
            message += f'k: {update.message.message_id}'
        except UnicodeEncodeError as e:
            message += f"{e} in {text}: Pls don't use that garbage here"
        except Exception as e:
            message += f"{e} in {text}, ehmm?"
    else:
        # not connected.
        message += f"Perhaps this helps:\n{update}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


resolutions = {
    "sd_8" : Printer.Image.SD_8,
    "dd_8" : Printer.Image.DD_8,
    "sd_24" : Printer.Image.SD_24,
    "dd_24" : Printer.Image.DD_24,
}

async def setRes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    command = update.message.text.replace('/setres', '').strip()
    message = ""
    if command in resolutions.keys():
        Globals.default_resolution = resolutions[command]
        message = f"Successfully set default resolution.\n"
    else:
        message += f"Invalid resolution {command}.\n"
        message += f"Use one of '{[k for k in resolutions.keys()]}'\n"

    message += f"Current default resolution: {Globals.default_resolution}"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = maybeConnect() or ""

    if Globals.printer:
        resolution = Globals.default_resolution
        message = ""
        caption = ""

        message += f"Using resolution {resolution} (change that with /setres ..)\n"

        download = await context.bot.get_file(update.message.photo[-1].file_id)
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text=f"got file {download}, downloading...")

        print (str(download))

        rawImage = await download.download_as_bytearray()
        image = Printer.Image(BytesIO(rawImage), resolution=resolution)
        message += f"Printing...."
        Globals.printer.printImage(image, ugly_workaround=resolution.bits_per_line != 8)
        if len(caption) > 0:
            Globals.printer.println(SMALLFONT, Just.LEFT, caption)

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = f"one of\n"
    message += "\n".join(['start', 'end', 'feed', 'setres', 'setUserEcho', 'cut', 'help', 'status'])
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = ""
    for name in dir(Globals):
        if "__" in name:
            continue
        message += f"{name}: {getattr(Globals, name)}\n"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

if __name__ == '__main__':
    application = ApplicationBuilder().token(secrets["API_KEY"]).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('end', end))
    application.add_handler(CommandHandler('feed', feed))
    application.add_handler(CommandHandler('setres', setRes))
    application.add_handler(CommandHandler('setUserEcho', setUserEcho))
    application.add_handler(CommandHandler('cut', cut))
    application.add_handler(CommandHandler('help', help))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), regularMessage))
    application.add_handler(MessageHandler(filters.PHOTO, photo))

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

"""
TODO: Auto connect and disconnect:

def callback_auto_message(context):
    context.bot.send_message(chat_id='12345678', text='Automatic message!')


def start_auto_messaging(update, context):
    chat_id = update.message.chat_id
    context.job_queue.run_repeating(callback_auto_message, 10, context=chat_id, name=str(chat_id))
    # context.job_queue.run_once(callback_auto_message, 3600, context=chat_id)
    # context.job_queue.run_daily(callback_auto_message, time=datetime.time(hour=9, minute=22), days=(0, 1, 2, 3, 4, 5, 6), context=chat_id)


def stop_notify(update, context):
    chat_id = update.message.chat_id
    context.bot.send_message(chat_id=chat_id, text='Stopping automatic messages!')
    job = context.job_queue.get_jobs_by_name(str(chat_id))
    job[0].schedule_removal()
"""