import curses
import sys
import argparse
import re
from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class Buffer:
    lines: tuple
    filename: Optional[str] = None
    modified: bool = False

    @staticmethod
    def from_file(filename):
        with open(filename) as f:
            return Buffer(tuple(f.read().splitlines()), filename, modified=False)

    def __len__(self):
        return len(self.lines)

    def __getitem__(self, index):
        return self.lines[index]

    @property
    def bottom(self):
        return len(self) - 1

    def insert(self, cursor, string):
        row, col = cursor.row, cursor.col
        current = self.lines[row]
        new_line = current[:col] + string + current[col:]
        new_lines = list(self.lines)
        new_lines[row] = new_line
        return replace(self, lines=tuple(new_lines), modified=True)

    def split(self, cursor):
        row, col = cursor.row, cursor.col
        current = self.lines[row]
        new_lines = list(self.lines)
        new_lines[row] = current[:col]
        new_lines.insert(row + 1, current[col:])
        return replace(self, lines=tuple(new_lines), modified=True)

    def delete(self, cursor):
        row, col = cursor.row, cursor.col
        if (row, col) < (self.bottom, len(self[row])):
            current = self.lines[row]
            new_lines = list(self.lines)
            if col < len(current):
                new_lines[row] = current[:col] + current[col + 1:]
            else:
                next_line = self.lines[row + 1]
                new_lines[row] = current + next_line
                new_lines.pop(row + 1)
            return replace(self, lines=tuple(new_lines), modified=True)
        return self

    def save(self):
        if self.filename:
            with open(self.filename, 'w') as f:
                f.write('\n'.join(self.lines))
                if self.lines:
                    f.write('\n')
        return replace(self, modified=False)


@dataclass(frozen=True)
class Window:
    nrows: int
    ncols: int
    row: int = 0
    col: int = 0

    @property
    def bottom(self):
        return self.row + self.nrows - 1

    def up(self, cursor):
        if cursor.row == self.row - 1 and self.row > 0:
            return replace(self, row=self.row - 1)
        return self

    def down(self, buffer, cursor):
        if cursor.row == self.bottom + 1 and self.bottom < buffer.bottom:
            return replace(self, row=self.row + 1)
        return self

    def translate(self, cursor):
        return cursor.row - self.row, cursor.col - self.col

    def horizontal_scroll(self, cursor, left_margin=5, right_margin=2):
        n_pages = cursor.col // (self.ncols - right_margin)
        new_col = max(n_pages * self.ncols - right_margin - left_margin, 0)
        if new_col != self.col:
            return replace(self, col=new_col)
        return self

    def page_up(self, buffer, cursor):
        new_cursor = replace(cursor, row=max(0, cursor.row - self.nrows))
        new_cursor = new_cursor.clamp_col(buffer)
        new_window = self
        if new_cursor.row < self.row:
            new_window = replace(self, row=max(0, self.row - self.nrows))
        return new_window, new_cursor

    def page_down(self, buffer, cursor):
        new_cursor = replace(cursor, row=min(buffer.bottom, cursor.row + self.nrows))
        new_cursor = new_cursor.clamp_col(buffer)
        new_window = self
        if new_cursor.row > self.bottom:
            new_window = replace(self, row=min(buffer.bottom - self.nrows + 1, self.row + self.nrows))
        return new_window, new_cursor


@dataclass(frozen=True)
class Cursor:
    row: int = 0
    col: int = 0
    col_hint: Optional[int] = None

    def __post_init__(self):
        if self.col_hint is None:
            object.__setattr__(self, 'col_hint', self.col)

    def set_col(self, col):
        return replace(self, col=col, col_hint=col)

    def up(self, buffer):
        if self.row > 0:
            new_cursor = replace(self, row=self.row - 1)
            return new_cursor.clamp_col(buffer)
        return self

    def down(self, buffer):
        if self.row < buffer.bottom:
            new_cursor = replace(self, row=self.row + 1)
            return new_cursor.clamp_col(buffer)
        return self

    def left(self, buffer):
        if self.col > 0:
            return self.set_col(self.col - 1)
        elif self.row > 0:
            new_row = self.row - 1
            new_col = len(buffer[new_row])
            return replace(self, row=new_row, col=new_col, col_hint=new_col)
        return self

    def right(self, buffer):
        if self.col < len(buffer[self.row]):
            return self.set_col(self.col + 1)
        elif self.row < buffer.bottom:
            return replace(self, row=self.row + 1, col=0, col_hint=0)
        return self

    def word_left(self, buffer):
        line = buffer[self.row]
        col = self.col

        # Skip whitespace
        while col > 0 and line[col - 1].isspace():
            col -= 1

        # Skip word characters
        if col > 0 and re.match(r'\w', line[col - 1]):
            while col > 0 and re.match(r'\w', line[col - 1]):
                col -= 1
        # Skip non-word, non-whitespace characters
        elif col > 0:
            while col > 0 and not line[col - 1].isspace() and not re.match(r'\w', line[col - 1]):
                col -= 1

        return self.set_col(col)

    def word_right(self, buffer):
        line = buffer[self.row]
        col = self.col

        # Skip whitespace
        while col < len(line) and line[col].isspace():
            col += 1

        # Skip word characters
        if col < len(line) and re.match(r'\w', line[col]):
            while col < len(line) and re.match(r'\w', line[col]):
                col += 1
        # Skip non-word, non-whitespace characters
        elif col < len(line):
            while col < len(line) and not line[col].isspace() and not re.match(r'\w', line[col]):
                col += 1

        return self.set_col(col)

    def beginning_of_line(self):
        return self.set_col(0)

    def end_of_line(self, buffer):
        return self.set_col(len(buffer[self.row]))

    def clamp_col(self, buffer):
        new_col = min(self.col_hint, len(buffer[self.row]))
        if new_col != self.col:
            return replace(self, col=new_col)
        return self


@dataclass(frozen=True)
class State:
    buffer: Buffer
    window: Window
    cursor: Cursor


def right(state):
    cursor = state.cursor.right(state.buffer)
    window = state.window.down(state.buffer, cursor)
    window = window.horizontal_scroll(cursor)
    return replace(state, cursor=cursor, window=window)


def left(state):
    cursor = state.cursor.left(state.buffer)
    window = state.window.up(cursor)
    window = window.horizontal_scroll(cursor)
    return replace(state, cursor=cursor, window=window)


def render(stdscr, state):
    stdscr.erase()

    # Render buffer lines
    display_rows = state.window.nrows - 1  # Reserve last line for status
    for row, line in enumerate(state.buffer[state.window.row : state.window.row + display_rows]):
        if len(line) > state.window.col:
            line = line[state.window.col:]
        else:
            line = ""

        if len(line) > state.window.ncols:
            line = line[:state.window.ncols - 1] + "»"

        if row < display_rows:
            stdscr.addstr(row, 0, line[:state.window.ncols])

    # Render status line
    status = f" {state.buffer.filename or 'unnamed'} | Line {state.cursor.row + 1}, Col {state.cursor.col + 1}"
    if state.buffer.modified:
        status += " [Modified]"
    status = status[:state.window.ncols]

    try:
        stdscr.addstr(state.window.nrows - 1, 0, status, curses.A_REVERSE)
    except curses.error:
        pass

    # Move cursor to correct position
    screen_row, screen_col = state.window.translate(state.cursor)
    stdscr.move(screen_row, screen_col)


def main(stdscr):
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()

    buffer = Buffer.from_file(args.filename)
    window = Window(curses.LINES, curses.COLS)
    cursor = Cursor()

    state = State(buffer=buffer, window=window, cursor=cursor)

    while True:
        render(stdscr, state)

        k = stdscr.getkey()
        if k == "\x11":  # Ctrl-q
            if state.buffer.modified:
                # Don't exit if modified
                continue
            sys.exit(0)
        elif k == "\x18":  # Ctrl-x (force quit)
            sys.exit(0)
        elif k in ("KEY_UP", "\x10"):  # Arrow up or Ctrl-p
            cursor = state.cursor.up(state.buffer)
            window = state.window.up(cursor)
            window = window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k in ("KEY_DOWN", "\x0e"):  # Arrow down or Ctrl-n
            cursor = state.cursor.down(state.buffer)
            window = state.window.down(state.buffer, cursor)
            window = window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k in ("KEY_LEFT", "\x02"):  # Arrow left or Ctrl-b
            state = left(state)
        elif k in ("KEY_RIGHT", "\x06"):  # Arrow right or Ctrl-f
            state = right(state)
        elif k == "\x1b[1;5D":  # Ctrl-Left (word left)
            cursor = state.cursor.word_left(state.buffer)
            window = state.window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k == "\x1b[1;5C":  # Ctrl-Right (word right)
            cursor = state.cursor.word_right(state.buffer)
            window = state.window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k == "\x17":  # Ctrl-w (word left, Emacs-style)
            cursor = state.cursor.word_left(state.buffer)
            window = state.window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k == "\x1a":  # Ctrl-z (word right, using Meta-f mapping)
            cursor = state.cursor.word_right(state.buffer)
            window = state.window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k == "\x01":  # Ctrl-a (beginning of line)
            cursor = state.cursor.beginning_of_line()
            window = state.window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k == "\x05":  # Ctrl-e (end of line)
            cursor = state.cursor.end_of_line(state.buffer)
            window = state.window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k == "\x13":  # Ctrl-s (save)
            buffer = state.buffer.save()
            state = replace(state, buffer=buffer)
        elif k == "KEY_PPAGE":  # Page Up
            window, cursor = state.window.page_up(state.buffer, state.cursor)
            window = window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k == "KEY_NPAGE":  # Page Down
            window, cursor = state.window.page_down(state.buffer, state.cursor)
            window = window.horizontal_scroll(cursor)
            state = replace(state, cursor=cursor, window=window)
        elif k == "\n":
            buffer = state.buffer.split(state.cursor)
            state = replace(state, buffer=buffer)
            state = right(state)
        elif k in ("KEY_DELETE", "\x04"):  # Delete or Ctrl-d
            buffer = state.buffer.delete(state.cursor)
            state = replace(state, buffer=buffer)
        elif k in ("KEY_BACKSPACE", "\x7f"):
            if (state.cursor.row, state.cursor.col) > (0, 0):
                state = left(state)
                buffer = state.buffer.delete(state.cursor)
                state = replace(state, buffer=buffer)
        else:
            buffer = state.buffer.insert(state.cursor, k)
            state = replace(state, buffer=buffer)
            for _ in k:
                state = right(state)


if __name__ == "__main__":
    curses.initscr()
    curses.wrapper(main)
