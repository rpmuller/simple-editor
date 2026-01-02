import curses
import sys
import argparse

# TODO:
# Remap cursor movement to Ctrl-p (up), Ctrl-n (down), Ctrl-b (left), and Ctrl-f (right).
#    Also emacs commands Ctrl-a, Ctrl-e, Ctrl-d (delte)
#    Remap q to Ctrl-q or Command-q
# Add page up and page down commands.
# Add a command to save the buffer to a file.
# Rewrite horizontal scrolling to move the entire window rather than only the current line.
# Add a status line to the bottom of the window that displays the name of the file being edited and the current cursor position.
# Add commands to move one word left or right.
# If the buffer is modified and not yet saved, print a message in the status line and don’t let the user exit. Add a force exit command as well.
# Rewrite the application so that there’s no mutable state. I’ve found dataclasses with the dataclass.replace function a convenient way to write applications around immutable objects.


def right(window, buffer, cursor):
    cursor.right(buffer)
    window.down(buffer, cursor)
    window.horizontal_scroll(cursor)


def left(window, buffer, cursor):
    cursor.left(buffer)
    window.up(cursor)
    window.horizontal_scroll(cursor)


def main(stdscr):
    parser = argparse.ArgumentParser()
    parser.add_argument("filename")
    args = parser.parse_args()

    with open(args.filename) as f:
        buffer = Buffer(f.read().splitlines())

    window = Window(curses.LINES - 1, curses.COLS - 1)
    cursor = Cursor()

    while True:
        stdscr.erase()
        for row, line in enumerate(buffer[window.row : window.row + window.nrows]):
            if row == cursor.row - window.row and window.col > 0:
                line = "«" + line[window.col + 1 :]
            if len(line) > window.ncols:
                line = line[: window.ncols - 1] + "»"
            stdscr.addstr(row, 0, line[: window.ncols])
        stdscr.move(*window.translate(cursor))

        k = stdscr.getkey()
        if k == "q":
            sys.exit(0)
        elif k == "KEY_UP":
            cursor.up(buffer)
            window.up(cursor)
            window.horizontal_scroll(cursor)
        elif k == "KEY_DOWN":
            cursor.down(buffer)
            window.down(buffer, cursor)
            window.horizontal_scroll(cursor)
        elif k == "KEY_LEFT":
            left(window, buffer, cursor)
        elif k == "KEY_RIGHT":
            right(window, buffer, cursor)
        elif k == "\n":
            buffer.split(cursor)
            right(window, buffer, cursor)
        elif k in ("KEY_DELETE", "\x04"):
            buffer.delete(cursor)
        elif k in ("KEY_BACKSPACE", "\x7f"):
            if (cursor.row, cursor.col) > (0, 0):
                left(window, buffer, cursor)
                buffer.delete(cursor)
        else:
            buffer.insert(cursor, k)
            for _ in k:
                right(window, buffer, cursor)


class Buffer:
    def __init__(self, lines):
        self.lines = lines

    def __len__(self):
        return len(self.lines)

    def __getitem__(self, index):
        return self.lines[index]

    @property
    def bottom(self):
        return len(self) - 1

    def insert(self, cursor, string):
        row, col = cursor.row, cursor.col
        current = self.lines.pop(row)
        new = current[:col] + string + current[col:]
        self.lines.insert(row, new)

    def split(self, cursor):
        row, col = cursor.row, cursor.col
        current = self.lines.pop(row)
        self.lines.insert(row, current[:col])
        self.lines.insert(row + 1, current[col:])

    def delete(self, cursor):
        row, col = cursor.row, cursor.col
        if (row, col) < (self.bottom, len(self[row])):
            current = self.lines.pop(row)
            if col < len(self[row]):
                new = current[:col] + current[col + 1 :]
                self.lines.insert(row, new)
            else:
                next = self.lines.pop(row)
                new = current + next
                self.lines.insert(row, new)


class Window:
    def __init__(self, nrows, ncols, row=0, col=0):
        self.nrows = nrows
        self.ncols = ncols
        self.row = row
        self.col = col
        return

    @property
    def bottom(self):
        return self.row + self.nrows - 1

    def up(self, cursor):
        if cursor.row == self.row - 1 and self.row > 0:
            self.row -= 1

    def down(self, buffer, cursor):
        if cursor.row == self.bottom + 1 and self.bottom < buffer.bottom:
            self.row += 1

    def translate(self, cursor):
        return cursor.row - self.row, cursor.col - self.col

    def horizontal_scroll(self, cursor, left_margin=5, right_margin=2):
        n_pages = cursor.col // (self.ncols - right_margin)
        self.col = max(n_pages * self.ncols - right_margin - left_margin, 0)


class Cursor:
    def __init__(self, row=0, col=0, col_hint=None):
        self.row = row
        self._col = col
        self._col_hint = col if col_hint is None else col_hint
        return

    @property
    def col(self):
        return self._col

    @col.setter
    def col(self, col):
        self._col = col
        self._col_hint = col

    def up(self, buffer):
        if self.row > 0:
            self.row -= 1
            self._clamp_col(buffer)

    def down(self, buffer):
        if self.row < buffer.bottom:
            self.row += 1
            self._clamp_col(buffer)

    def left(self, buffer):
        if self.col > 0:
            self.col -= 1
        elif self.row > 0:
            self.row -= 1
            self.col = len(buffer[self.row])

    def right(self, buffer):
        if self.col < len(buffer[self.row]):
            self.col += 1
        elif self.row < buffer.bottom:
            self.row += 1
            self.col = 0

    def _clamp_col(self, buffer):
        self._col = min(self._col_hint, len(buffer[self.row]))


if __name__ == "__main__":
    curses.initscr()
    curses.wrapper(main)
