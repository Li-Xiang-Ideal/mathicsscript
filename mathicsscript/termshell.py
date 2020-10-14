import atexit
import os
import os.path as osp
import locale
import pathlib
import sys
import re
from mathics.core.expression import strip_context

from pygments import highlight
from pygments.lexers import MathematicaLexer
mma_lexer = MathematicaLexer()

from pygments.styles import get_style_by_name
from pygments.formatters.terminal import TERMINAL_COLORS
from pygments.formatters import Terminal256Formatter

from pygments.token import (
    # Comment,
    # Generic,
    # Keyword,
    Name,
    Literal,
    # Operator,
    # String,
    Token,
)

color_scheme = TERMINAL_COLORS.copy()
color_scheme[Token.Name] = "yellow"
color_scheme[Name.Function] = "green"
color_scheme[Name.NameSpace] = "brown"
color_scheme[Literal.Number] = "blue"

dark_terminal_formatter = Terminal256Formatter(bg="dark")
dark_terminal_formatter.colorscheme = color_scheme

light_terminal_formatter = Terminal256Formatter(bg="light")
light_terminal_formatter.colorscheme = color_scheme

from colorama import init as colorama_init
from mathicsscript.term_background import is_dark_background

from readline import (
    read_history_file,
    read_init_file,
    set_completer,
    set_completer_delims,
    set_history_length,
    write_history_file,
    # parse_and_bind,
)

try:
    HISTSIZE = int(os.environ.get("MATHICSSCRIPT_HISTSIZE", 50))
except:
    HISTSIZE = 50

HISTFILE = osp.expanduser("~/.mathicsscript_hist")



from mathics.core.parser import LineFeeder, FileLineFeeder
class TerminalShell(LineFeeder):
    def __init__(
        self, definitions, style: str, want_readline: bool, want_completion: bool
    ):
        super(TerminalShell, self).__init__("<stdin>")
        self.input_encoding = locale.getpreferredencoding()
        self.lineno = 0
        self.terminal_formatter = None
        self.history_length = definitions.get_config_value('$HistoryLength', HISTSIZE)

        # Try importing readline to enable arrow keys support etc.
        self.using_readline = False
        try:
            if want_readline:

                self.using_readline = sys.stdin.isatty() and sys.stdout.isatty()
                self.ansi_color_re = re.compile("\033\\[[0-9;]+m")
                if want_completion:
                    set_completer(
                        lambda text, state: self.complete_symbol_name(text, state)
                    )

                    # Make _ a delimiter, but not $ or `
                    set_completer_delims(
                        " \t\n_~!@#%^&*()-=+[{]}\\|;:'\",<>/?"
                    )

                    inputrc = pathlib.Path(__file__).parent.absolute() / "inputrc"
                    read_init_file(inputrc)
                    # parse_and_bind('"\ep\e": "\u03C0"')
                    # parse_and_bind("tab: complete")
                    self.completion_candidates = []

                # History
                try:
                    read_history_file(HISTFILE)
                except IOError:
                    pass
                except:
                    # PyPy read_history_file fails
                    return
                set_history_length(self.history_length)
                atexit.register(self.user_write_history_file)
                pass

        except ImportError:
            pass

        colorama_init()
        if style is None:
            if is_dark_background():
                style = "DARKBG"
                self.terminal_formatter = dark_terminal_formatter
            else:
                style = "LIGHTBG"
                self.terminal_formatter = light_terminal_formatter
        else:
            ustyle = style.upper()
            if ustyle == "DARKBG":
                self.terminal_formatter = dark_terminal_formatter
            elif ustyle == "LIGHTBG":
                self.terminal_formatter = light_terminal_formatter

        color_schemes = {
            "NOCOLOR": (["", "", "", ""], ["", "", "", ""]),
            "DARKBG": (
                ["\033[32m", "\033[1m", "\033[22m", "\033[39m"],
                ["\033[31m", "\033[1m", "\033[22m", "\033[39m"],
            ),
            "LIGHTBG": (
                ["\033[34m", "\033[1m", "\033[22m", "\033[39m"],
                ["\033[31m", "\033[1m", "\033[22m", "\033[39m"],
            ),
        }

        # Handle any case by using .upper()
        term_colors = color_schemes.get(style.upper())
        if term_colors is None:
            out_msg = f"The 'style' {style} argument must be {repr(list(color_schemes.keys()))} or None"
            quit(out_msg)

        self.incolors, self.outcolors = term_colors
        self.definitions = definitions

    def get_last_line_number(self):
        return self.definitions.get_line_no()

    def get_in_prompt(self):
        next_line_number = self.get_last_line_number() + 1
        if self.lineno > 0:
            return " " * len("In[{0}]:= ".format(next_line_number))
        else:
            return "{1}In[{2}{0}{3}]:= {4}".format(next_line_number, *self.incolors)

    def get_out_prompt(self):
        line_number = self.get_last_line_number()
        return "{1}Out[{2}{0}{3}]= {4}".format(line_number, *self.outcolors)

    def to_output(self, text):
        line_number = self.get_last_line_number()
        newline = "\n" + " " * len("Out[{0}]= ".format(line_number))
        return newline.join(text.splitlines())

    def out_callback(self, out):
        print(self.to_output(str(out)))

    def read_line(self, prompt):
        if self.using_readline:
            return self.rl_read_line(prompt)
        return input(prompt)

    def print_result(self, result):
        if result is not None and result.result is not None:
            out_str = str(result.result)
            if self.terminal_formatter:  # pygmentize
                # from pygments import lex
                # print(list(lex(out_str, mma_lexer)))
                out_str = highlight(out_str, mma_lexer, self.terminal_formatter)
            output = self.to_output(out_str)
            print(self.get_out_prompt() + output + "\n")

    def rl_read_line(self, prompt):
        # Wrap ANSI colour sequences in \001 and \002, so readline
        # knows that they're nonprinting.
        prompt = self.ansi_color_re.sub(lambda m: "\001" + m.group(0) + "\002", prompt)

        return input(prompt)

    def complete_symbol_name(self, text, state):
        try:
            return self._complete_symbol_name(text, state)
        except Exception:
            # any exception thrown inside the completer gets silently
            # thrown away otherwise
            print("Unhandled error in readline completion")

    def _complete_symbol_name(self, text, state):
        # The readline module calls this function repeatedly,
        # increasing 'state' each time and expecting one string to be
        # returned per call.

        if state == 0:
            self.completion_candidates = self.get_completion_candidates(text)

        try:
            return self.completion_candidates[state]
        except IndexError:
            return None

    def get_completion_candidates(self, text):
        matches = self.definitions.get_matching_names(text + "*")
        if "`" not in text:
            matches = [strip_context(m) for m in matches]
        return matches

    def reset_lineno(self):
        self.lineno = 0

    def feed(self):
        result = self.read_line(self.get_in_prompt()) + "\n"
        if result == "\n":
            return ""  # end of input
        self.lineno += 1
        return result

    def empty(self):
        return False

    def user_write_history_file(self):
        try:
            set_history_length(self.history_length)
            write_history_file(HISTFILE)
        except:
            pass
