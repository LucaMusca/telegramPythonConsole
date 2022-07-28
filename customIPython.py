import re
import IPython


def escape_ansi(s):
    return re.compile(r'''
        \x1B  # ESC
        (?:   # 7-bit C1 Fe (except CSI)
            [@-Z\\-_]
        |     # or [ for CSI, followed by a control sequence
            \[
            [0-?]*  # Parameter bytes
            [ -/]*  # Intermediate bytes
            [@-~]   # Final byte
        )
    ''', re.VERBOSE).sub('', s)


def myIPython(*args, **kwargs):
    def escape_ansi(s):
        return re.compile(r'''
            \x1B  # ESC
            (?:   # 7-bit C1 Fe (except CSI)
                [@-Z\\-_]
            |     # or [ for CSI, followed by a control sequence
                \[
                [0-?]*  # Parameter bytes
                [ -/]*  # Intermediate bytes
                [@-~]   # Final byte
            )
        ''', re.VERBOSE).sub('', s)

    def exception_handler(exception_type, exception, traceback):
        nonlocal myTB
        tb = '\n'.join(escape_ansi(l) for l in traceback)
        myTB = "%s" % tb

    def getTB():
        nonlocal myTB
        return myTB

    ip = IPython.InteractiveShell(*args, **kwargs)
    ip._showtraceback = exception_handler
    ip.getTB = getTB
    myTB = None

    return ip
