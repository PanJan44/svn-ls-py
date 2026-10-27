#!/usr/bin/env python3
"""A lazy, keyboard-driven browser for remote SVN repositories."""

import curses
import os
import shutil
import subprocess
import sys
from urllib.parse import quote


def child_url(parent, name):
    is_dir = name.endswith("/")
    segment = quote(name.rstrip("/"), safe="!$&'()*+,;=:@-._~")
    return parent.rstrip("/") + "/" + segment + ("/" if is_dir else "")


def list_dir(url, revision=None):
    cmd = ["svn", "ls"]
    if revision:
        cmd += ["-r", revision]

    # Trailing @ prevents SVN from interpreting URL characters
    # as a peg revision delimiter.
    cmd.append(url + "@")

    result = subprocess.run(
        cmd, text=True, capture_output=True
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "svn ls failed")

    return sorted(
        result.stdout.splitlines(),
        key=lambda s: (not s.endswith("/"), s.lower()),
    )


def copy_text(value):
    commands = []
    if sys.platform == "darwin":
        commands = [["pbcopy"]]
    elif os.name == "nt":
        commands = [["clip"]]
    else:
        for executable in ("wl-copy", "xclip", "xsel"):
            if shutil.which(executable):
                if executable == "xclip":
                    commands.append([executable, "-selection", "clipboard"])
                elif executable == "xsel":
                    commands.append([executable, "--clipboard", "--input"])
                else:
                    commands.append([executable])
                break

    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, input=value, text=True, capture_output=True,
                timeout=2
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    return False


def browse(stdscr, root, revision=None):
    curses.curs_set(0)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_CYAN, -1)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    curses.init_pair(3, curses.COLOR_YELLOW, -1)

    cache = {}
    current = root.rstrip("/")
    if not current:
        current = root

    stack = []
    selected = 0
    message = "Enter: open  Backspace: up  /: filter  c: copy URL  q: quit"

    def get_entries(url):
        if url not in cache:
            cache[url] = list_dir(url, revision)
        return cache[url]

    while True:
        try:
            entries = get_entries(current)
            error = ""
        except RuntimeError as exc:
            entries = []
            error = str(exc)

        query = ""
        visible = entries

        while True:
            height, width = stdscr.getmaxyx()
            stdscr.erase()

            title = f" SVN: {current}"
            stdscr.addnstr(0, 0, title, width - 1, curses.A_BOLD)

            if revision:
                stdscr.addnstr(1, 0, f" Revision: {revision}", width - 1)

            if error:
                stdscr.addnstr(2, 0, error, width - 1,
                               curses.color_pair(3))
            else:
                stdscr.addnstr(
                    2, 0, f" {len(visible)} entries"
                    + (f" | filter: {query}" if query else ""),
                    width - 1,
                )

            start = max(0, min(
                selected - (height - 5),
                max(0, selected - (height - 5) // 2)
            ))
            start = min(start, max(0, len(visible) - (height - 5)))

            for row, name in enumerate(
                visible[start:start + max(0, height - 5)], start=3
            ):
                entry = visible[row - 3 + start]
                # Directory entries end in /
                is_dir = entry.endswith("/")
                label = ("[D] " if is_dir else "    ") + entry
                attr = curses.color_pair(1) if is_dir else curses.A_NORMAL
                if row - 3 + start == selected:
                    attr |= curses.A_REVERSE
                stdscr.addnstr(row, 0, label, width - 1, attr)

            stdscr.addnstr(height - 2, 0, message, width - 1)
            stdscr.addnstr(height - 1, 0, " ↑/↓ navigate  →/Enter open  ←/Backspace up",
                           width - 1, curses.A_DIM)
            stdscr.refresh()

            key = stdscr.getch()

            if key in (ord("q"), 27):
                return

            if key in (curses.KEY_UP, ord("k")):
                selected = max(0, selected - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                selected = min(max(0, len(visible) - 1), selected + 1)
            elif key in (curses.KEY_RIGHT, 10, 13, curses.KEY_ENTER, ord("l")):
                if visible and visible[selected].endswith("/"):
                    name = visible[selected]
                    stack.append((current, selected))
                    current = child_url(current, name)
                    selected = 0
                    break
                elif visible:
                    url = child_url(current, visible[selected])
                    message = "Selected: " + url
            elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 8, 127, ord("h")):
                if stack:
                    current, selected = stack.pop()
                    break
            elif key == ord("r"):
                cache.pop(current, None)
                break
            elif key == ord("c"):
                if visible:
                    url = child_url(current, visible[selected])
                    message = (
                        "Copied: " + url if copy_text(url)
                        else "Clipboard unavailable. Selected URL: " + url
                    )
            # elif key == ord("/"):
            #     curses.echo()
            #     curses.curs_set(1)
            #     stdscr.addstr(height - 1, 0, "/")
            #     raw = stdscr.getstr(height - 1, 1, max(1, width - 2))
            #     curses.noecho()
            #     curses.curs_set(0)
            #     query = raw.decode(errors="replace").strip().lower()
            #     visible = [e for e in entries if query in e.lower()]
            #     selected = 0
            # elif key in (curses.KEY_HOME, ord("g")):
            #     selected = 0
            # elif key in (curses.KEY_END, ord("G")):
            #     selected = max(0, len(visible) - 1)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} REPOSITORY_URL [-r REVISION]")
        sys.exit(2)

    url = sys.argv[1].rstrip("/")
    revision = None
    if len(sys.argv) >= 4 and sys.argv[2] in ("-r", "--revision"):
        revision = sys.argv[3]

    try:
        curses.wrapper(browse, url, revision)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
