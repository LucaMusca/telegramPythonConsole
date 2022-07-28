import threading
import os
import telegram
from matplotlib.backend_bases import Gcf
from matplotlib.backends.backend_agg import FigureCanvasAgg
import mainip

FigureCanvas = FigureCanvasAgg

manager, myChatID, bot = None, None, None  # those objects are initialized by mainip


def show(*args, **kwargs):
    for num, figmanager in enumerate(Gcf.get_all_fig_managers()):
        pid = threading.get_ident()
        try:
            consoleID = manager.threads[pid].chatID
        except KeyError:
            consoleID = myChatID
        filename = '%s.png' % consoleID
        figmanager.canvas.figure.savefig(filename)
        sendPhoto(consoleID, filename)
        os.remove(filename)


def sendPhoto(chatID, filename):
    console = manager.data[chatID]
    console.history.index = 0
    try:
        bot.edit_message_reply_markup(chat_id=console.lastMessage.chat_id, message_id=console.lastMessage.message_id)
    except (telegram.error.BadRequest, AttributeError):
        pass
    reply_markup = console.history()
    console.lastMessage = bot.send_photo(chat_id=chatID, photo=open(filename, 'rb'),reply_markup=reply_markup)
