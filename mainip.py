import ast
import keyword
import os
import queue
import re
import sys
import threading
import traceback
from collections import UserList
from collections.abc import Iterable
from html import escape
from time import time, sleep
import customIPython
import IPython
import requests
import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import matplotlib_backend

'''
    TODO:
    - use inspect module to improve inspector
'''


def my_exec(script, g=None, l=None):
    """Execute a script and return the value of the last expression"""
    stmts = list(ast.iter_child_nodes(ast.parse(script)))
    if not stmts:
        return None
    if isinstance(stmts[-1], ast.Expr):
        if len(stmts) > 1:
            exec(compile(ast.Module(body=stmts[:-1]), filename="<ast>", mode="exec"), g, l)
        return eval(compile(ast.Expression(body=stmts[-1].value), filename="<ast>", mode="eval"), g, l)
    else:
        return exec(script, g, l)


def looseSend(chat_id, msg):
    s = str(msg)
    if s and not s.isspace():
        bot.send_message(chat_id=chat_id, text=msg, parse_mode=telegram.ParseMode.HTML)


def apiRequest(command, params=None):
    pth = 'https://api.telegram.org/bot1268314054:AAHFugw_rOq1LbOUrrwDA23EGCp4tr4f4jI'
    return requests.get('%s/%s' % (pth, command), params=params)


class KThread(threading.Thread):
    """A subclass of threading.Thread, with a kill() method.
    https://web.archive.org/web/20130503082442/http://mail.python.org/pipermail/python-list/2004-May/281943.html"""

    def __init__(self, *args, **keywords):
        threading.Thread.__init__(self, *args, **keywords)
        self.killed = False

    def start(self):
        """Start the thread."""
        self.__run_backup = self.run
        self.run = self.__run  # Force the Thread to install our trace.
        threading.Thread.start(self)

    def __run(self):
        """Hacked run function, which installs the
trace."""
        sys.settrace(self.globaltrace)
        self.__run_backup()
        self.run = self.__run_backup

    def globaltrace(self, frame, why, arg):
        if why == 'call':
            return self.localtrace
        else:
            return None

    def localtrace(self, frame, why, arg):
        if self.killed:
            if why == 'line':
                raise SystemExit()
        return self.localtrace

    def kill(self):
        self.killed = True


class Console:
    activityTimeout = 1200
    commandTimeout = 2400

    def __init__(self, ID, manager):
        self.l = self.g = self.history = self.settings = self.inspector = self.lastQuery = self.result = None
        self.outBuffer = []
        self.terminator = Terminator(self)
        self.reader = Reader()
        self.manager = manager
        self.chatID = ID
        self.subProcess = None
        self.lastMessage = None
        self.lastActivity = time()
        self.initialize()

    def initialize(self):
        self.l = {'console': self}
        self.g = self.l  # crucial bit
        self.ip = customIPython.myIPython(user_ns=self.l)
        self.history = History(self)

        self.settings = Settings(self)
        self.settings.initialize()

        self.inspector = Inspector(self)

        self.ip.run_cell(startup_script)
        self.write('Session started')

    def receive(self, message_id, text: str):
        self.lastActivity = time()
        if text.startswith('@pythonConsole_bot '):
            text = text[19:]
        if text == '/start':
            self.initialize()
        elif text == '/stop':
            self.write('Your session has been terminated', markup=False)
            self.manager.remove(self)
        elif text == '/settings':
            self.settings.initialize()
        elif text == '/inspect':
            self.inspector.initialize()
        elif text == '/terminate':
            self.terminator.terminateCommand()
        elif self.reader.lock.locked():
            self.reader.line = text
            self.reader.lock.release()
        else:
            if self.subProcess and self.subProcess.is_alive():
                self.write(emojis['shushing'] + 'Previous command is still running. Use /terminate to kill it.')
            else:
                self.subProcess = KThread(target=self.run,
                                          args=(text,), daemon=True)  # create process for executing the command
                self.subProcess.start()
                self.manager.threads[self.subProcess.ident] = self

                if self.settings['Markup'] == 'ON':
                    bot.delete_message(chat_id=self.chatID, message_id=message_id)
                    self.write(Console.markup(text), e=False)

    def run(self, script, startup=False):  # secondary thread
        if not startup:
            self.history.append(script)
            self.lastQuery = script
            self.history.updateReplyMarkup()
        try:
            result = self.ip.run_cell(script)
            if result.success:
                self.result = result.result
            else:
                if result.error_before_exec:
                    raise result.error_before_exec
                raise result.error_in_exec
            if self.result is not None:
                self.l['_'] = self.result
            else:
                self.history.updateReplyMarkup()
        except SyntaxError as s:
            self.write(emojis['angryFace'] + bold % escape(str(s).replace('<unknown>', '<console>')), e=False)
        except ImportError as i:
            msg = '\nIf you want module %s to be available in this console, contact @lucaMuscarella' % i.name
            if self.settings.getSetting('Traceback') == 'ON':
                track = self.ip.getTB()
                self.write(emojis['redCross'] + (bold % escape(track)) + msg, e=False)
            else:
                self.write(emojis['redCross'] + (bold % escape(str(i)) + msg), e=False)
        except Exception as e:
            if self.settings.getSetting('Traceback') == 'ON':
                track = self.ip.getTB()
                self.write(emojis['redCross'] + bold % escape(track), e=False)
            else:
                self.write(emojis['redCross'] + bold % escape(str(e)), e=False)

        self.lastActivity = time()
        self.history.terminable = False
        self.history.updateReplyMarkup()

        del self.manager.threads[self.subProcess.ident]

    @classmethod
    def markup(cls, text):
        chunks = re.split(r'(\s+)', text)
        for x, c in enumerate(chunks):
            if c in keyword.kwlist:
                chunks[x] = bold % c
        return ''.join(chunks)

    def checkMyState(self):
        if time() - self.lastActivity > 1 and self.isRunning():
            self.history.terminable = True
            self.history.updateReplyMarkup()
        if time() - self.lastActivity > Console.activityTimeout:
            if not self.isRunning():
                self.write('Your console has been shut down due to inactivity', markup=False)
                self.manager.remove(self)
            else:
                if time() - self.lastActivity > Console.commandTimeout:
                    self.write('The command is taking too long and will be terminated', markup=False)
                    self.terminator.terminateCommand()
                    self.lastActivity = time()

    def isRunning(self) -> bool:
        return self.subProcess and self.subProcess.is_alive()

    def callbackHandler(self, data: str, callback_id):
        obj = getattr(self, data.split()[0])
        obj.callbackHandler(' '.join(data.split()[1:]))

        apiRequest('answerCallbackQuery', params={'callback_query_id': callback_id})

    def write(self, message, **kwargs):
        self.manager.inout.queue.put((self.chatID, message, kwargs))

    def send(self, message, e=True, markup=True, **kwargs):  # to be called by inout thread
        if re.compile(r'Out\[\d+\]:').match(message):
            self.outBuffer.append(message)
            return
        if self.outBuffer:
            self._writeCore(bold % ''.join(self.outBuffer) + ' ' + escape(message), False, markup, **kwargs)
            self.outBuffer.clear()
        else:
            self._writeCore(customIPython.escape_ansi(message), e, markup, **kwargs)

    def _writeCore(self, message, e=True, markup=True, **kwargs):
        if markup:
            reply_markup = self.history()
        else:
            reply_markup = None
        self.history.index = 0
        s = str(message)
        first, second = s[:4092], s[4092:]
        if first and not first.isspace():
            try:
                bot.edit_message_reply_markup(chat_id=self.lastMessage.chat_id, message_id=self.lastMessage.message_id)
            except (telegram.error.BadRequest, AttributeError):
                pass

            if e:
                self.lastMessage = bot.send_message(chat_id=self.chatID, text=escape(first),
                                                    parse_mode=telegram.ParseMode.HTML, **kwargs,
                                                    reply_markup=reply_markup)
            else:
                self.lastMessage = bot.send_message(chat_id=self.chatID, text=first, parse_mode=telegram.ParseMode.HTML,
                                                    **kwargs, reply_markup=reply_markup)

        if second:
            self._writeCore(second, e, markup, **kwargs)

    def flush(self):  # duck typing
        pass

    def __exit__(self):
        self.terminator.terminateCommand(hard=True)
        self.settings.__exit__()
        self.inspector.__exit__()


class Reader:
    def __init__(self):
        self.lock = threading.Lock()
        self.line = None

    def readline(self):
        self.lock.acquire()
        self.lock.acquire()
        line = self.line
        self.lock.release()
        return line


class Inspector:
    def __init__(self, console):
        self.console = console
        self.message = None

    def initialize(self):
        self.frames = []
        if self.message:
            try:
                bot.edit_message_reply_markup(chat_id=self.message.chat_id, message_id=self.message.message_id)
            except telegram.error.BadRequest:
                pass
        self.message = None
        frame = InspectorFrame(self.console.lastQuery, self.console.result)
        self.frames.append(frame)
        self.display()

    def display(self):
        frame = self.frames[-1]
        frameList = frame()
        if len(self.frames) > 1:
            btext = emojis['left']
            backward = InlineKeyboardButton(btext, callback_data='inspector <-')
            replyMU = InlineKeyboardMarkup([[backward]] + frameList)
        else:
            replyMU = InlineKeyboardMarkup(frameList)

        if not self.message:
            self.message = bot.send_message(chat_id=self.console.chatID, text='Inspecting %s' % frame.name,
                                            parse_mode=telegram.ParseMode.HTML, reply_markup=replyMU)
        else:
            try:
                bot.edit_message_reply_markup(chat_id=self.message.chat_id, message_id=self.message.message_id,
                                              reply_markup=replyMU)
            except telegram.error.BadRequest:
                pass

    def callbackHandler(self, data):
        if data == '<-':
            self.frames.pop()
        else:
            self.frames.append(self.frames[-1].next(int(data)))
        self.display()

    def __exit__(self):
        if self.message:
            try:
                bot.edit_message_reply_markup(chat_id=self.message.chat_id, message_id=self.message.message_id)
            except telegram.error.BadRequest:
                pass


class InspectorFrame:
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.message = None

    @classmethod
    def inspectable(cls, value):
        return hasattr(value, '__dict__') or (
                isinstance(value, Iterable) and not isinstance(value, str) and len(value) > 0)

    def __call__(self):
        items = []  # prefer list on dict to maintain order
        value = self.value
        if hasattr(value, '__dict__'):
            items = [('{}.{}'.format(self.name, a), getattr(value, a)) for a in value.__dict__]
        elif isinstance(value, Iterable) and not isinstance(value, str):
            if isinstance(value, list) or isinstance(value, tuple):
                items = [('{}[{}]'.format(self.name, x), a) for (x, a) in enumerate(value)]
            elif isinstance(value, set):
                items = [('item', a) for a in value]
            elif isinstance(value, dict):
                items = [('{}'.format(k), value[k]) for k in value]

        self.items = items
        buttons = []
        for index, (k, v) in enumerate(items):
            if InspectorFrame.inspectable(v):
                buttons.append([InlineKeyboardButton('{}: {}'.format(k, v), callback_data='inspector %s' % str(index))])
            else:
                buttons.append([InlineKeyboardButton('{}: {}'.format(k, v), switch_inline_query_current_chat=str(k))])
        return buttons

    def next(self, index):
        return InspectorFrame(*self.items[index])


class Settings:
    def __init__(self, console):
        self.console = console
        self.data = {'Traceback': ['OFF', 'ON'], 'History': ['{}{}'.format(emojis['left'], emojis['right']), 'LIST'],
                     'Markup': ['OFF', 'ON']}
        self.value = {x: 0 for x in self.data}
        self.message = None

    def initialize(self):
        if self.message:
            bot.edit_message_reply_markup(chat_id=self.message.chat_id, message_id=self.message.message_id)
        self.message = bot.send_message(chat_id=self.console.chatID, text='Settings',
                                        parse_mode=telegram.ParseMode.HTML, reply_markup=self())

    def callbackHandler(self, data):
        key, value = data.split()
        self.value[key] += 1
        self.value[key] %= len(self.data[key])

        if key == 'History':
            self.console.history.updateReplyMarkup()

        self.updateReplyMarkup()

    def updateReplyMarkup(self):
        bot.edit_message_reply_markup(chat_id=self.message.chat_id, message_id=self.message.message_id,
                                      reply_markup=self())

    def getSetting(self, key):
        return self.data[key][self.value[key]]

    def __getitem__(self, key):
        return self.getSetting(key)

    def __call__(self):
        buttons = []
        for key in self.data:
            value = self.getSetting(key)
            buttons.append(
                [InlineKeyboardButton('{} {}'.format(key, value), callback_data='settings {} {}'.format(key, value))])
        return InlineKeyboardMarkup(buttons)

    def __exit__(self):
        if self.message:
            bot.edit_message_reply_markup(chat_id=self.message.chat_id, message_id=self.message.message_id)


class IOhandler:
    def __init__(self, manager):
        self.manager = manager
        self.queue = queue.Queue()
        self.thread = threading.Thread(target=self.wait, daemon=True)
        self.thread.start()

    def write(self, text):  # called by running thread
        pid = threading.get_ident()
        try:
            consoleID = self.manager.threads[pid].chatID
        except KeyError:
            consoleID = myChatID
        self.manager.data[consoleID].write(text)

    def flush(self):
        pass

    def readline(self):
        pid = threading.get_ident()
        try:
            consoleID = self.manager.threads[pid].chatID
        except KeyError:
            consoleID = myChatID
        return self.manager.data[consoleID].reader.readline()

    def close(self):
        pass

    def wait(self):
        looseSend(myChatID, 'wait started')
        while True:
            chatId, message, kwargs = self.queue.get()
            self.manager.data[chatId].send(message, **{'e': True, 'markup': True, **kwargs})


class Terminator:
    def __init__(self, console):
        self.console = console

    @classmethod
    def button(cls):
        return [InlineKeyboardButton(emojis['redDot'] + 'Terminate', callback_data='terminator ON')]

    def callbackHandler(self, data):  # do not remove parameter data
        self.terminateCommand()

    def terminateCommand(self, hard=False):
        console = self.console
        if console.reader.lock.locked():
            console.reader.lock.release()
        if console.isRunning():
            console.subProcess.kill()
            # sleep(0.2)
            if console.isRunning():
                if not hard:
                    print("Unfortunately, I couldn't kill the command as it is a blocking call(such as time.sleep)."
                          " You need to wait for the command to terminate or use /stop (and lose your variables).")
            else:
                console.history.terminable = False
                console.write('Command terminated')
        if not console.isRunning and not hard:
            console.write('There is no process to kill')
        print('terminator called')


class History:
    def __init__(self, console):
        self.console = console
        self.historyList = HistoryList()
        self.index = 0
        self.terminable = False

    def append(self, item):
        self.historyList.append(item)

    def __call__(self):

        if self.console.settings.getSetting('History') == 'LIST':
            return self.historyList.createList()
        else:
            ll = []
            if self.historyList:
                btext = emojis['left'] if self.index < len(self.historyList) - 1 else '   '
                backward = InlineKeyboardButton(btext, callback_data='history <-')

                ftext = emojis['right'] if self.index > 0 else '   '
                forward = InlineKeyboardButton(ftext, callback_data='history ->')

                h = [InlineKeyboardButton(self.historyList[-self.index - 1],
                                          switch_inline_query_current_chat=self.historyList[-self.index - 1])]

                if ftext == btext == '   ':
                    ll.append(h)
                else:
                    ll.append([backward, forward])
                    ll.append(h)
            else:
                ll.append([])

            if self.terminable:
                ll.append(Terminator.button())
            return InlineKeyboardMarkup(ll)

    def callbackHandler(self, data):
        if data == '<-' and self.index < len(self.historyList) - 1:
            self.index += 1
            self.updateReplyMarkup()
        elif data == '->' and self.index > 0:
            self.index -= 1
            self.updateReplyMarkup()

    def updateReplyMarkup(self):
        if self.console.lastMessage:
            message = self.console.lastMessage
            try:
                bot.edit_message_reply_markup(chat_id=message.chat_id, message_id=message.message_id,
                                              reply_markup=self())
            except telegram.error.BadRequest:
                pass


class HistoryList(UserList):
    def __init__(self):
        super().__init__()
        self.halfSize = 3

    def append(self, item) -> None:
        if item in self:
            self.remove(item)
        super().append(item)

    def createButton(self, num):
        try:
            text = self[-num - 1]
        except:
            text = ''
        return InlineKeyboardButton(text, switch_inline_query_current_chat=text)

    def createList(self):
        buttons = [self.createButton(x) for x in reversed(range(self.halfSize * 2))]
        return InlineKeyboardMarkup([buttons[-self.halfSize * 2:-self.halfSize], buttons[-self.halfSize:]])


class ConsolesManager:
    def __init__(self):
        self.data = {}
        self.threads = {}
        bot.delete_webhook()  # deleteWebhook
        try:
            self.offset = apiRequest('getUpdates').json()['result'][-1]['update_id'] + 1
        except:
            self.offset = 0
        apiRequest('getUpdates', params={'offset': self.offset}).json()
        self.inout = IOhandler(self)
        sys.stdout = self.inout
        sys.stdin = self.inout

    def put(self, console):
        self.data[console.chatID] = console

    def remove(self, console, hard=False):
        console.__exit__()
        self.data.pop(console.chatID)

    def poll(self):
        while self.data:
            updates = apiRequest('getUpdates', params={'offset': self.offset}).json()['result']
            if updates:
                self.offset = updates[-1]['update_id'] + 1
                if 'message' in updates[-1]:
                    message = updates[-1]['message']
                    chat_id = int(message['chat']['id'])
                    text = message['text'] if 'entities' not in message else self.parseMessage(message)

                    self.getUpdate(chat_id, text, message['message_id'])
                if 'callback_query' in updates[-1]:
                    callback = updates[-1]['callback_query']
                    chat_id = int(callback['from']['id'])
                    self.data[chat_id].callbackHandler(callback['data'], callback['id'])

            for c in list(self.data.values()):
                c.checkMyState()

    def getUpdate(self, chat_id, text, message_id):
        if chat_id not in self.data:
            if text == '/stop':
                looseSend(chat_id, 'The console is not running. Use /start to start it')
            elif text == '/start':
                self.put(Console(chat_id, self))
            else:
                looseSend(chat_id, 'Command not found, use /start to start a session')
        else:
            self.data[chat_id].receive(message_id, text)

    def parseMessage(self, message):
        text = list(message['text'])

        marks = []
        for entity in message['entities']:
            if entity['type'] in markdown:
                t = markdown[entity['type']]
                o = entity['offset']
                l = entity['length']
                marks.append((o, t))
                marks.append((o + l, t))

        marks.sort(key=lambda a: a[0])
        off = 0
        for p, t in marks:
            text[p + off:p + off] = list(t)
            off += 2

        return ''.join(text)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        apiRequest('getUpdates', params={'offset': self.offset + 1}).json()
        hook = 'https://lm857.user.srcf.net/pythonConsole_bot/root.php'
        apiRequest('setWebhook', params={'url': hook})
        looseSend(chatId, 'Webhook restored')


Token = #add here your bot's token
bot = telegram.Bot(token=Token)

path = 'https://api.telegram.org/bot%s' % Token
bold = '<b>%s</b>'

startup_script = '''
from time import sleep
import sys
import matplotlib
matplotlib.use('module://matplotlib_backend')
'''

emojis = {'shushing': '🤫', 'right': '➡️', 'left': '⬅️', 'redCross': '❌', 'angryFace': '😡', 'redDot': '🔴'}

markdown = {'italic': '__', 'bold': '**'}


def bootstrap():
    t = threading.Thread(target=main, args=(myChatID, '/start'), daemon=True)
    t.start()


def main(chatId, message):
    try:
        if message in ['/stop', '/settings', '/inspect']:
            looseSend(chatId, 'The console is not running. Use /start to start it')
            return
        if message != '/start':
            looseSend(chatId, 'Command not found, use /start to start a session')
            return

        with ConsolesManager() as manager:
            matplotlib_backend.manager, matplotlib_backend.myChatID, matplotlib_backend.bot = manager, myChatID, bot
            manager.getUpdate(chatId, message, 0)
            manager.poll()

    except Exception:
        track = traceback.format_exc()
        looseSend(chatId, escape(track))


if __name__ == "__main__":
    chatId = int(sys.argv[1])
    message = sys.argv[2]
    main(chatId, message)
