#!/usr/bin/env python3
r"""gui.py - MvC2 Mix Converter, graphical front-end (Tkinter, stdlib only).

A one-window app for non-technical users. It's a thin shell over the same engine
the terminal menu uses (install.py); every long-running job runs on a worker
thread and streams its progress= output into the log at the bottom, so the window
never freezes.

Run from source:  py mixconv\gui.py
Frozen:           double-click MixConverter.exe
"""
import os, sys, queue, threading, traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config
import install

APP_TITLE = "Marvel vs. Capcom 2  -  Mix Converter"


class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()          # worker -> UI progress messages
        self.busy = False
        self._action_widgets = []       # buttons disabled while a job runs

        root.title(APP_TITLE)
        root.geometry("760x620")
        root.minsize(700, 560)
        try:
            root.call("tk", "scaling", 1.2)
        except tk.TclError:
            pass

        self._build_header()
        self._build_tabs()
        self._build_log()
        self._build_statusbar()

        self.refresh_status()
        self.root.after(100, self._drain_queue)

    # ---------------------------------------------------------------- layout
    def _build_header(self):
        top = ttk.Frame(self.root, padding=(14, 12, 14, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Marvel vs. Capcom 2 — Mix Converter",
                  font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(top, text="Move your mods between a Dreamcast disc and the Steam "
                            "Fighting Collection.",
                  foreground="#555").pack(anchor="w")
        self.status_lbl = ttk.Label(top, text="", font=("Segoe UI", 9))
        self.status_lbl.pack(anchor="w", pady=(6, 0))

    def _build_tabs(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="x", padx=14, pady=(6, 4))
        self.nb = nb
        self._tab_setup(nb)
        self._tab_install(nb)
        self._tab_build(nb)
        self._tab_restore(nb)

    def _build_log(self):
        frm = ttk.LabelFrame(self.root, text="Progress", padding=6)
        frm.pack(fill="both", expand=True, padx=14, pady=(4, 4))
        self.log = scrolledtext.ScrolledText(frm, height=12, wrap="word",
                                             state="disabled",
                                             font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

    def _build_statusbar(self):
        bar = ttk.Frame(self.root, padding=(14, 2, 14, 8))
        bar.pack(fill="x")
        self.pbar = ttk.Progressbar(bar, mode="indeterminate", length=160)
        self.pbar.pack(side="right")
        self.busy_lbl = ttk.Label(bar, text="", foreground="#555")
        self.busy_lbl.pack(side="right", padx=(0, 10))

    # ------------------------------------------------------------- setup tab
    def _tab_setup(self, nb):
        t = ttk.Frame(nb, padding=14); nb.add(t, text="1. Setup")
        ttk.Label(t, text="First-time setup", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        msg = ("This tool ships with no game files, so it needs a copy of your Steam\n"
               "game to work from. That copy is also your backup to restore later.\n\n"
               "Click the button below to copy your game exactly as it is now.\n\n"
               "Tip: if you'd like a clean, unmodified backup to fall back on, verify\n"
               "the game in Steam first (right-click the game → Properties → Installed\n"
               "Files → Verify integrity of game files), then build the backup.")
        ttk.Label(t, text=msg, justify="left").pack(anchor="w", pady=(4, 10))
        self.steam_lbl = ttk.Label(t, text="", foreground="#333",
                                   wraplength=690, justify="left")
        self.steam_lbl.pack(anchor="w", pady=(0, 2))
        ch = ttk.Button(t, text="Change Steam folder…", command=self.on_set_steam)
        ch.pack(anchor="w", pady=(0, 10))
        self._action_widgets.append(ch)
        b1 = ttk.Button(t, text="Build initial backup from Steam",
                        command=self.on_copy_stock)
        b1.pack(anchor="w")
        self._action_widgets.append(b1)

        ttk.Separator(t, orient="horizontal").pack(fill="x", pady=14)
        ttk.Label(t, text="Optional — only needed to BUILD Dreamcast discs (Steam → DC):",
                  foreground="#555").pack(anchor="w")
        self.dc_lbl = ttk.Label(t, text="", foreground="#333")
        self.dc_lbl.pack(anchor="w", pady=(2, 6))
        b2 = ttk.Button(t, text="Add a stock Dreamcast disc (.cdi)…",
                        command=self.on_set_dc)
        b2.pack(anchor="w")
        self._action_widgets.append(b2)

    # ----------------------------------------------------------- install tab
    def _tab_install(self, nb):
        t = ttk.Frame(nb, padding=14); nb.add(t, text="2. Install into Steam")
        ttk.Label(t, text="Install a Dreamcast mix into Steam  (DC → Steam)",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(t, justify="left", text=(
            "Pick a Dreamcast mix (.cdi, or a .zip containing one). Your current Steam\n"
            "files are backed up automatically, then the mix's stages, palettes,\n"
            "HUD/effects and music are installed.")).pack(anchor="w", pady=(4, 10))
        row = ttk.Frame(t); row.pack(fill="x")
        self.mix_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.mix_var).pack(side="left", fill="x", expand=True)
        bb = ttk.Button(row, text="Browse…", command=self.on_browse_mix)
        bb.pack(side="left", padx=(6, 0))
        self._action_widgets.append(bb)
        go = ttk.Button(t, text="Convert & Install", command=self.on_install)
        go.pack(anchor="w", pady=(12, 0))
        self._action_widgets.append(go)
        ttk.Label(t, foreground="#555", text=(
            "After it finishes, fully quit and relaunch Steam to play.")
        ).pack(anchor="w", pady=(10, 0))

    # ------------------------------------------------------------- build tab
    def _tab_build(self, nb):
        t = ttk.Frame(nb, padding=14); nb.add(t, text="3. Build a Disc")
        ttk.Label(t, text="Build a Dreamcast disc from Steam  (Steam → DC)",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(t, justify="left", text=(
            "Patches your stages, palettes, HUD/effects and music from Steam into a\n"
            "Dreamcast .cdi you can load in Flycast or burn to DVD-R.")).pack(
            anchor="w", pady=(4, 10))

        ttk.Label(t, text="Base disc to patch onto:").pack(anchor="w")
        row = ttk.Frame(t); row.pack(fill="x")
        self.base_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.base_var).pack(side="left", fill="x", expand=True)
        bb = ttk.Button(row, text="Browse…", command=self.on_browse_base)
        bb.pack(side="left", padx=(6, 0))
        self._action_widgets.append(bb)
        ttk.Label(t, foreground="#555", text=(
            "Leave blank to build on a fresh STOCK disc, or pick an existing modded\n"
            ".cdi to keep its mods and add yours on top.")
        ).pack(anchor="w", pady=(2, 8))

        cf = ttk.LabelFrame(t, text="If the base disc and Steam changed the same file", padding=8)
        cf.pack(fill="x", pady=(0, 8))
        self.conflict_var = tk.StringVar(value="steam")
        ttk.Radiobutton(cf, text="Use my Steam version (recommended)",
                        variable=self.conflict_var, value="steam").pack(anchor="w")
        ttk.Radiobutton(cf, text="Keep the base disc's version",
                        variable=self.conflict_var, value="disc").pack(anchor="w")
        ttk.Label(cf, foreground="#a15", text=(
            "Note: mixes that add EXTRA palette slots (more colors per character)\n"
            "relocate palette data — your Steam colors may only partly apply there.")
        ).pack(anchor="w", pady=(4, 0))

        orow = ttk.Frame(t); orow.pack(fill="x", pady=(2, 0))
        ttk.Label(orow, text="Output name:").pack(side="left")
        self.out_var = tk.StringVar(value="MVC2_from_steam.cdi")
        ttk.Entry(orow, textvariable=self.out_var, width=28).pack(side="left", padx=(6, 0))
        go = ttk.Button(t, text="Build Disc", command=self.on_build)
        go.pack(anchor="w", pady=(12, 0))
        self._action_widgets.append(go)

    # ----------------------------------------------------------- restore tab
    def _tab_restore(self, nb):
        t = ttk.Frame(nb, padding=14); nb.add(t, text="4. Restore / Reset")
        ttk.Label(t, text="Undo changes to your Steam install",
                  font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(t, text="Restore a backup made when you installed a mix:").pack(
            anchor="w", pady=(8, 2))
        row = ttk.Frame(t); row.pack(fill="x")
        self.backup_var = tk.StringVar()
        self.backup_combo = ttk.Combobox(row, textvariable=self.backup_var,
                                         state="readonly", width=42)
        self.backup_combo.pack(side="left")
        rb = ttk.Button(row, text="Refresh", command=self.refresh_backups)
        rb.pack(side="left", padx=(6, 0))
        self._action_widgets.append(rb)
        rs = ttk.Button(t, text="Restore selected backup", command=self.on_restore)
        rs.pack(anchor="w", pady=(8, 0))
        self._action_widgets.append(rs)

        ttk.Separator(t, orient="horizontal").pack(fill="x", pady=14)
        ttk.Label(t, text="Or wipe all mods and return to the clean baseline:").pack(anchor="w")
        rz = ttk.Button(t, text="Reset Steam to stock", command=self.on_reset)
        rz.pack(anchor="w", pady=(6, 0))
        self._action_widgets.append(rz)

    # ------------------------------------------------------------- status/log
    def refresh_status(self):
        root = config.steam_root()
        self.steam_lbl.config(
            text=("Steam install: " + root) if root
            else "Steam install: NOT FOUND (is the Fighting Collection installed?)")
        self.dc_lbl.config(
            text=("Stock Dreamcast disc: present" if os.path.exists(config.STOCK_DC_CDI)
                  else "Stock Dreamcast disc: not set (disc-building disabled)"))
        ok, _ = config.check()
        if ok:
            self.status_lbl.config(text="✓ Ready to install mixes into Steam.",
                                   foreground="#177245")
        else:
            self.status_lbl.config(
                text="⚠ Setup needed — open the “1. Setup” tab to build your backup from Steam.",
                foreground="#b00")
        self.refresh_backups()

    def refresh_backups(self):
        bdir = os.path.join(config.OUTPUT, "backups")
        items = []
        if os.path.isdir(bdir):
            items = sorted((d for d in os.listdir(bdir)
                            if d.startswith("steam_")
                            and os.path.isdir(os.path.join(bdir, d))), reverse=True)
        self.backup_combo["values"] = items
        if items:
            self.backup_combo.current(0)
        else:
            self.backup_var.set("")

    def logln(self, msg=""):
        self.log.config(state="normal")
        self.log.insert("end", str(msg) + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ------------------------------------------------------------- job runner
    def _set_busy(self, on, label=""):
        self.busy = on
        for w in self._action_widgets:
            w.config(state="disabled" if on else "normal")
        if on:
            self.pbar.start(12); self.busy_lbl.config(text=label)
        else:
            self.pbar.stop(); self.busy_lbl.config(text="")

    def run_job(self, title, fn, *args, **kwargs):
        """Run fn(*args, progress=<queued>, **kwargs) on a worker thread."""
        if self.busy:
            return
        self.logln("\n" + "=" * 56)
        self.logln(title)
        self.logln("=" * 56)
        self._set_busy(True, title)

        def worker():
            def prog(m):
                self.q.put(("log", m))
            try:
                fn(*args, progress=prog, **kwargs)
                self.q.put(("done", None))
            except Exception as e:
                self.q.put(("log", "\nERROR: " + str(e)))
                self.q.put(("log", traceback.format_exc()))
                self.q.put(("fail", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.logln(payload)
                elif kind == "done":
                    self._set_busy(False)
                    self.logln("\n✓ Finished.")
                    self.refresh_status()
                elif kind == "fail":
                    self._set_busy(False)
                    messagebox.showerror("Something went wrong", payload)
                    self.refresh_status()
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    # --------------------------------------------------------------- actions
    def on_copy_stock(self):
        if not config.steam_root():
            messagebox.showerror(
                "Steam not found",
                "The Fighting Collection Steam install wasn't found.\n\n"
                "Use “Change Steam folder…” to point at it.")
            return
        if not messagebox.askyesno(
                "Build backup",
                "Copy your current Steam game files to use as your backup?\n\n"
                "Tip: for a clean baseline to restore, verify the game in Steam first."):
            return
        self.run_job("Building initial backup from Steam", install.copy_stock_from_steam)

    def on_set_steam(self):
        d = filedialog.askdirectory(
            title="Select your MARVEL vs. CAPCOM Fighting Collection folder")
        if not d:
            return
        arc = config.steam_arc(d)
        if not arc or not os.path.exists(arc):
            if not messagebox.askyesno(
                    "Doesn't look right",
                    "That folder doesn't contain the expected game file\n"
                    "(nativeDX11x64\\arc\\pc\\game_50.arc).\n\nUse it anyway?"):
                return
        config.set_steam_root(d)
        self.logln("Steam folder set to: " + d)
        self.refresh_status()

    def on_set_dc(self):
        p = filedialog.askopenfilename(title="Select a stock Dreamcast MvC2 disc",
                                       filetypes=[("Dreamcast disc", "*.cdi"),
                                                  ("All files", "*.*")])
        if p:
            self.run_job("Adding stock Dreamcast disc", install.set_stock_dc, p)

    def on_browse_mix(self):
        p = filedialog.askopenfilename(
            title="Select a Dreamcast mix",
            initialdir=config.MIXES if os.path.isdir(config.MIXES) else None,
            filetypes=[("Mix (.cdi or .zip)", "*.cdi *.zip"), ("All files", "*.*")])
        if p:
            self.mix_var.set(p)

    def on_install(self):
        mix = self.mix_var.get().strip().strip('"')
        if not mix or not os.path.exists(mix):
            messagebox.showerror("Pick a mix", "Choose a .cdi or .zip mix first.")
            return
        ok, problems = config.check()
        if not ok:
            messagebox.showerror("Setup needed",
                                 "Finish Setup first:\n\n" + "\n".join(problems))
            return
        if not messagebox.askyesno(
                "Install mix",
                "Install this mix into Steam?\n\n" + os.path.basename(mix) +
                "\n\nYour current files are backed up automatically."):
            return
        self.run_job("Installing mix into Steam", install.install_dc_to_steam, mix)

    def on_browse_base(self):
        p = filedialog.askopenfilename(title="Select a base Dreamcast .cdi",
                                       filetypes=[("Dreamcast disc", "*.cdi"),
                                                  ("All files", "*.*")])
        if p:
            self.base_var.set(p)

    def on_build(self):
        if not os.path.exists(config.STOCK_DC_CDI) and not self.base_var.get().strip():
            messagebox.showerror(
                "No base disc",
                "Building a disc needs a stock Dreamcast .cdi.\n\n"
                "Add one under Setup, or pick a base .cdi to patch onto.")
            return
        base = self.base_var.get().strip().strip('"') or None
        if base and not os.path.exists(base):
            messagebox.showerror("Base not found", "That base .cdi doesn't exist.")
            return
        name = os.path.basename(self.out_var.get().strip().strip('"') or "MVC2_from_steam")
        if not name.lower().endswith(".cdi"):
            name += ".cdi"
        out = os.path.join(config.OUTPUT, name)
        os.makedirs(config.OUTPUT, exist_ok=True)
        if base and not messagebox.askyesno(
                "Patch onto modded disc?",
                "You're patching onto an existing modded disc. Extra-palette mixes "
                "may only partly apply your Steam colors.\n\nContinue?"):
            return
        self.run_job("Building Dreamcast disc: " + name,
                     install.build_dc_from_steam, out,
                     base_cdi=base, conflict_mode=self.conflict_var.get())

    def on_restore(self):
        sel = self.backup_var.get().strip()
        if not sel:
            messagebox.showinfo("No backup", "No backups to restore.")
            return
        bdir = os.path.join(config.OUTPUT, "backups", sel)
        if not messagebox.askyesno("Restore backup",
                                   "Restore these files over your live Steam install?\n\n" + sel):
            return
        self.run_job("Restoring backup: " + sel, install.restore_steam, bdir)

    def on_reset(self):
        if not messagebox.askyesno(
                "Reset to stock",
                "Overwrite your live Steam game + music with the clean stock "
                "baseline?\n\nThis removes any installed mix."):
            return
        self.run_job("Resetting Steam to stock", install.reset_to_stock)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")     # nicer on Windows; falls back if absent
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
