#!venv/bin/python

from dotenv import dotenv_values
secrets = dotenv_values(".env")
assert(secrets["API_KEY"])

if "USER_PW" not in secrets or len(secrets["USER_PW"]) == 0:
    print ("WARN: No 'USER_PW' given. Allowing everyone!")
else:
    print (f"Userpassword: '{secrets['USER_PW']}'")

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

class User:
    def __init__(self):
        self.resolution = Printer.Image.DD_8
        self.last_printed_user_id = None
        self.print_user_changes = True

class Globals:
    printer : Printer = None
    sock_timeout_s : int = 5
    users : dict = {}
    has_password : bool = "USER_PW" in secrets and len(secrets["USER_PW"]) > 0

not_connected = 'Printer is not connected.'
not_registered = "You are not registered.\nUse `/start [pw]`"

def getUser(id : int) -> User:
    if id in Globals.users:
        return Globals.users[id]
    else:
        return None

def getParameters(text : str):
    return [param for param in text.split() if not "/" in param]

def maybeConnect() -> str:
    if Globals.printer:
        try:
            msg = ""
            stati = Globals.printer.getStatus([Printer.Paper])
            if stati[Printer.Paper].isNearEnd():
                msg += f"Notice: Paper is near end\n"
            if stati[Printer.Paper].isPresent():
                msg += f"Warn: Printer reports no paper\n"
            return msg
        except Exception as e:
            print (f"Could not get printer status: {e}.")
            print (f"trying re-connect")
            Globals.printer = None

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

def printAndUpdateIfNewUser(user: User, message):
    sender = message.chat
    time = message.date

    if hasattr(message, 'forward_origin') and message.forward_origin:
        time = message.forward_origin.date
        if hasattr(message.forward_origin, "sender_user"):
            sender = message.forward_origin.sender_user
        elif hasattr(message.forward_origin, "sender_user_name"):
            class AnonUser:
                def __init__(self, name):
                    self.first_name = name
                    self.last_name = None
                    self.id = hash(name)

            sender = AnonUser(message.forward_origin.sender_user_name)
    elif hasattr(message, 'from_user') and message.from_user:
        sender = message.from_user

    id = sender.id

    if not user.last_printed_user_id or user.last_printed_user_id != id:
        name = str(sender.first_name)
        if sender.last_name:
            name += " " + str(sender.last_name)
        printNewUser(name, time)
        user.last_printed_user_id = id

def printNewUser(name, date):
    if Globals.printer:
        Globals.printer.println(Just.RIGHT, BIGFONT, name)
        Globals.printer.println(SMALLFONT, date.strftime("%Y-%m-%d %H:%M:%S"))
        Globals.printer.print(Just.LEFT)
        Globals.printer.feed(mm= 2)

async def setUserEcho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getUser(update.message.chat.id)
    if not user:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=not_registered)
        return

    message = ""
    if "on" in update.message.text:
        user.print_user_changes = True
    elif "off" in update.message.text:
        user.print_user_changes = False
    else:
        message += f"Neither 'on' nor 'off' read.\nIgnoring your rumblings about '{update.message.text}'\n"

    state = "on" if user.print_user_changes else "off"
    message += f"Printing user names: {state}"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getUser(update.message.chat.id)
    message = ""
    if user:
        message = f"You are already registered"
    else:
        may_log_in = not Globals.has_password
        if Globals.has_password:
            passwd = getParameters(update.message.text)
            if len(passwd) == 0:
                message = f"No password given. No cookies."
            elif passwd[0] != secrets["USER_PW"]:
                message = f"Invalid password given"
            else:
                may_log_in = True

        if may_log_in:
            Globals.users[update.message.chat.id] = User()
            message = f"Successfully registered."

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def cut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getUser(update.message.chat.id)
    if not user:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=not_registered)
        return

    message = maybeConnect() or ""
    if Globals.printer:
        Globals.printer.print(defaultCut.FEED_CUT())
        message += "k (ut)"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = "You have never been registered, lol"
    user = getUser(update.message.chat.id)
    if user:
        del Globals.users[update.message.chat.id]
        message = "You have been successfully removed from list"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


async def feed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = maybeConnect() or ""
    if Globals.printer:
        mm = 1
        commands = getParameters(update.message.text)
        if len(commands) != 1:
            message += f"Invalid number of parameters. Got {len(commands)}"
        else:
            command  = commands[0]
            try:
                mm = int(command.strip(string.ascii_letters))
            except:
                message += f"Could not parse {update.message.text} as int."
                message += f"\n{update}"
            message += f'Advancing {mm}mm'
        try:
            Globals.printer.feed(mm=mm)
        except Exception as e:
            message += f"\nCould not feed forward:\n{e}"
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
    user = getUser(update.message.chat.id)
    if not user:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=not_registered)
        return

    message = maybeConnect() or ""
    if len(message) > 1:
        message += "\n" # dirty

    if Globals.printer:
        try:
            printAndUpdateIfNewUser(user, update.message)
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
    user = getUser(update.message.chat.id)
    if not user:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=not_registered)
        return

    message = ""
    commands = getParameters(update.message.text)
    if len(commands) != 1:
        message = f"Invalid number of commands. Expected: 1, got: {len(commands)}"
    elif commands[0] in resolutions.keys():
        user.resolution = resolutions[commands[0]]
        message = f"Successfully set default resolution."
    else:
        message += f"Invalid resolution {commands[0]}.\n"
        message += f"Use one of '{[k for k in resolutions.keys()]}'"

    message += f"\nCurrent resolution: {user.resolution}"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getUser(update.message.chat.id)
    if not user:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=not_registered)
        return

    message = maybeConnect() or ""

    if Globals.printer:
        resolution = user.resolution
        caption = update.message.caption or ""

        message += f"Using resolution {resolution} (change that with /setres ..)\n"

        download = await context.bot.get_file(update.message.photo[-1].file_id)
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                           text=f"got file {download}, downloading...")

        print (str(download))

        rawImage = await download.download_as_bytearray()
        image = Printer.Image(BytesIO(rawImage), resolution=resolution)
        message += f"Printing...."
        try:
            Globals.printer.printImage(image, ugly_workaround=resolution.bits_per_line != 8)
            if len(caption) > 0:
                Globals.printer.println(SMALLFONT, Just.LEFT, caption)
        except BrokenPipeError as e:
            message += f"\nSocket error during printing. Probably just timed out. TODO: Reconnect.\n{e}"
        except Exception as e:
            message += f"\nError during printing.\n{e}"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = f"one of\n"
    message += "\n".join([
        '/start',
        '/end',
        '/feed',
        '/setRes',
        '/setUserEcho',
        '/cut',
        '/help',
        '/status'
    ])
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = getUser(update.message.chat.id)
    if not user:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=not_registered)
        return

    message = "User settings:"

    for name in dir(user):
        if "__" in name:
            continue
        message += f"\n  {name}: {getattr(user, name)}"

    message += "\nGlobal Settings: "
    for name in dir(Globals):
        if "__" in name:
            continue
        message += f"\n  {name}: {getattr(Globals, name)}"

    message += "\n"
    message += maybeConnect() or ""

    message += "\nPrinter Status: "
    try:
        stati = Globals.printer.getStatus()
        for status in stati.values():
            message += f"\n  {str(status)}"
    except Exception as e:
        message += f"Error. Disconnected? {e}"
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
Message(
    api_kwargs={
        'forward_date': 1736339977,
        'forward_from': {
            'id': 608950592,
            'is_bot': False,
            'first_name': 'Lukers',
            'username': 'Keesebrot'
            }
    },
    channel_chat_created=False
    chat=Chat(
        first_name='Pascal',
        id=170554685,
        last_name='(optional)',
        type=<ChatType.PRIVATE>,
        username='Urinator'),
    date=datetime.datetime(2025, 2, 2, 16, 21, 14, tzinfo=datetime.timezone.utc),
    delete_chat_photo=False,
    entities=(MessageEntity(length=53, offset=242, type=<MessageEntityType.URL>),),
    forward_origin=MessageOriginUser(
        date=datetime.datetime(2025, 1, 8, 12, 39, 37, tzinfo=datetime.timezone.utc),
        sender_user=User(
            first_name='Lukers',
            id=608950592,
            is_bot=False,
            username='Keesebrot'),
        type=<MessageOriginType.USER>),0
        from_user=User(
            first_name='Pascal',
            id=170554685,
            is_bot=False,0
            language_code='de',
            last_name='(optional)',
            username='Urinator'),
        group_chat_created=False,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        message_id=890,
        supergroup_chat_created=False,
        text='Emma und ich...'
)
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