# Telegram Python console
You can use this bot to run a Python console from your Telegram!

## Setup
Just begin a chat with [`@pythonConsole_bot`](https://telegram.me/pythonConsole_bot "PythonConsole") and you are all set :)

 ![img](https://i.imgur.com/BTKe5L1.png)

## Features
  * IPython support: the console internally uses the IPython interactive shell, so all the IPython "magics" work as expected.
  * Matplotlib support: the bot implements a `matplotlib` backend, so calling `matplotlib.pyplot.show` (or related methods) will send a picture of the plot to the chat.
 ![img](https://i.imgur.com/wfFRNe0.png)
  * History: the console remembers previous commands, and can fill the textbox with them. You can choose between two styles of history, ARROWS or LIST. The only difference is user interface. 
  * Traceback: toggle between short error message or full traceback. 
  * Variables: inspect the variables of the interpreter using Telegram interactive inline buttons(beta).

## Caveats
Telegram uses a Markdown dialect to markup messages. The syntax for *italic* is to add two leading and two trailing underscores (e.g. \_\_word\_\_). Unfortunately, the same syntax is commonly used in Python, as it identifies "magic" methods. Since it is not possible to modify how Telegram renders messages sent by users, the text `a.__dict__` will be displayed as <code>a.*dict*</code>.  
Don't worry, the console understands what you mean :)
