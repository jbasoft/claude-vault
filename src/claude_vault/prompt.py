"""Credential prompting.

The whole point of this module: the value the user types must never reach the
agent that asked for it. So the prompt is drawn by *this* process -- a native
dialog when there is a desktop, a terminal prompt when there is a TTY -- and the
value goes straight into the vault.

Order of preference:
  1. --stdin            explicit, for CI and headless servers
  2. native GUI dialog  tkinter (all platforms), with RTL-aware layout
  3. terminal prompt     getpass on a TTY
  4. hard error          never silently skip, never echo
"""

from __future__ import annotations

import os
import sys

from .i18n import current


class PromptError(RuntimeError):
    pass


class PromptCancelled(RuntimeError):
    pass


def gui_available() -> bool:
    if os.environ.get("VAULT_NO_GUI"):
        return False
    if sys.platform not in ("win32", "darwin") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return False
    try:
        import tkinter  # noqa: F401
    except Exception:
        return False
    return True


def _gui_prompt(name: str, *, want_username: bool, note: str) -> tuple[str, str]:
    import tkinter as tk

    t = current()
    result: dict[str, str] = {}

    root = tk.Tk()
    root.title(t("dialog.title"))
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass

    anchor = "e" if t.rtl else "w"
    justify = "right" if t.rtl else "left"
    pad = {"padx": 16, "pady": 4}

    tk.Label(root, text=t("dialog.heading"), font=("TkDefaultFont", 11, "bold"),
             anchor=anchor, justify=justify).grid(row=0, column=0, sticky="ew",
                                                  padx=16, pady=(14, 2))
    tk.Label(root, text=t("dialog.subtitle", name=name), anchor=anchor,
             justify=justify, wraplength=380, fg="#555").grid(
        row=1, column=0, sticky="ew", **pad)
    if note:
        tk.Label(root, text=note, anchor=anchor, justify=justify, wraplength=380,
                 fg="#777").grid(row=2, column=0, sticky="ew", **pad)

    frame = tk.Frame(root)
    frame.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 4))
    frame.columnconfigure(1, weight=1)

    row = 0
    user_var = tk.StringVar()
    if want_username:
        tk.Label(frame, text=t("dialog.username"), anchor=anchor).grid(
            row=row, column=0, sticky=anchor, pady=3)
        user_entry = tk.Entry(frame, textvariable=user_var, width=34,
                              justify=justify)
        user_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1

    secret_var = tk.StringVar()
    tk.Label(frame, text=t("dialog.secret"), anchor=anchor).grid(
        row=row, column=0, sticky=anchor, pady=3)
    secret_entry = tk.Entry(frame, textvariable=secret_var, show="•",
                            width=34, justify=justify)
    secret_entry.grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
    row += 1

    show_var = tk.BooleanVar(value=False)

    def toggle() -> None:
        secret_entry.config(show="" if show_var.get() else "•")

    tk.Checkbutton(frame, text=t("dialog.show"), variable=show_var,
                   command=toggle, anchor=anchor).grid(
        row=row, column=1, sticky=anchor, padx=(8, 0))

    error = tk.Label(root, text="", fg="#c00", anchor=anchor, justify=justify)
    error.grid(row=4, column=0, sticky="ew", padx=16)

    def submit(_event=None) -> None:
        if not secret_var.get():
            error.config(text=t("dialog.empty"))
            return
        result["secret"] = secret_var.get()
        result["username"] = user_var.get()
        root.destroy()

    def cancel(_event=None) -> None:
        root.destroy()

    buttons = tk.Frame(root)
    buttons.grid(row=5, column=0, sticky="ew", padx=16, pady=(6, 14))
    buttons.columnconfigure(0, weight=1)
    order = [(t("dialog.cancel"), cancel), (t("dialog.save"), submit)]
    if t.rtl:
        order.reverse()
    for col, (label, cmd) in enumerate(order, start=1):
        tk.Button(buttons, text=label, command=cmd, width=11).grid(
            row=0, column=col, padx=4)

    tk.Label(root, text=t("dialog.footer"), fg="#888", anchor=anchor,
             justify=justify, wraplength=380, font=("TkDefaultFont", 8)).grid(
        row=6, column=0, sticky="ew", padx=16, pady=(0, 12))

    root.bind("<Return>", submit)
    root.bind("<Escape>", cancel)
    (user_entry if want_username else secret_entry).focus_force()
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    root.mainloop()

    if "secret" not in result:
        raise PromptCancelled(t("error.cancelled"))
    return result["secret"], result["username"]


def _tty_prompt(name: str, *, want_username: bool) -> tuple[str, str]:
    import getpass

    t = current()
    print(t("dialog.heading"), file=sys.stderr)
    print(t("dialog.subtitle", name=name), file=sys.stderr)
    username = ""
    if want_username:
        username = input(t("dialog.username") + " ").strip()
    value = getpass.getpass(t("dialog.secret") + " ")
    if not value:
        raise PromptCancelled(t("error.cancelled"))
    confirm = getpass.getpass(t("dialog.confirm") + " ")
    if confirm != value:
        raise PromptError(t("error.mismatch"))
    return value, username


def ask(name: str, *, want_username: bool = False, note: str = "",
        from_stdin: bool = False, force_tty: bool = False) -> tuple[str, str]:
    """Return (secret, username). Raises rather than returning an empty secret."""
    t = current()
    if from_stdin:
        value = sys.stdin.read().strip("\r\n")
        if not value:
            raise PromptError(t("error.empty_stdin"))
        return value, ""
    if not force_tty and gui_available():
        try:
            return _gui_prompt(name, want_username=want_username, note=note)
        except PromptCancelled:
            raise
        except Exception:
            pass  # a broken display should fall back, not crash
    if sys.stdin.isatty():
        return _tty_prompt(name, want_username=want_username)
    raise PromptError(t("error.no_prompt"))
