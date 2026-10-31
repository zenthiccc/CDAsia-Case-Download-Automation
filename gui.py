"""Desktop UI for the CDAsia downloader (CustomTkinter).

  .venv/bin/python gui.py

Pick a syllabus .md; its case list is turned into yaml and shown for checking/editing. Download then
runs cdasia_fetch.py in a child process, so the window stays responsive and Stop can end it.
"""
import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import cdasia_fetch as engine
import syllabus_parser

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

PAD = 16
MONO = ("Menlo" if sys.platform == "darwin" else "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono", 12)
OTHER = "Browse for a file..."
MUTED = ("gray40", "gray65")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CDAsia Case Downloader")
        self.geometry("880x820")
        self.minsize(700, 640)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.settings = engine.load_settings()
        self.proc = None
        self.lines = queue.Queue()
        self.total = 0
        self.done = 0
        self.check_job = None

        # Header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, 4))
        ctk.CTkLabel(head, text="CDAsia Case Downloader", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(head, text="Pick a syllabus, check the cases found in it, then download them "
                                "(with separate opinions) into <folder>/cases.", text_color=MUTED).pack(anchor="w")

        # Inputs card
        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=1, column=0, sticky="ew", padx=PAD, pady=8)
        card.grid_columnconfigure(1, weight=1)

        self.syllabus_var = ctk.StringVar()
        self.parent_var = ctk.StringVar(value=self.settings.get("parent", str(engine.HERE.parent)))
        self.name_var = ctk.StringVar()

        self._label(card, "Syllabus (.md)", 0)
        self.syllabus_menu = ctk.CTkOptionMenu(card, variable=self.syllabus_var, command=self._syllabus_picked,
                                               dynamic_resizing=False)
        self.syllabus_menu.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(0, PAD), pady=(PAD, 4))

        self._label(card, "Create in", 1)
        ctk.CTkEntry(card, textvariable=self.parent_var).grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=4)
        ctk.CTkButton(card, text="Choose...", width=80, command=self._pick_parent).grid(row=1, column=2, padx=(0, PAD), pady=4)

        self._label(card, "Folder name", 2)
        ctk.CTkEntry(card, textvariable=self.name_var, placeholder_text="e.g. consti-art7-sec16to17").grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(0, PAD), pady=4)

        self.preview = ctk.CTkLabel(card, text="", anchor="w", justify="left", text_color=MUTED)
        self.preview.grid(row=3, column=0, columnspan=3, sticky="ew", padx=PAD, pady=(4, PAD))
        for v in (self.parent_var, self.name_var):
            v.trace_add("write", lambda *_: self._update_preview())

        # Actions + progress
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=PAD, pady=4)
        bar.grid_columnconfigure(3, weight=1)
        self.run_btn = ctk.CTkButton(bar, text="Download", width=130, height=36,
                                     font=ctk.CTkFont(weight="bold"), command=self._run)
        self.run_btn.grid(row=0, column=0, padx=(0, 8))
        self.stop_btn = ctk.CTkButton(bar, text="Stop", width=80, height=36, state="disabled",
                                      fg_color=("#c0392b", "#a93226"), hover_color=("#a93226", "#922b21"),
                                      command=self._stop)
        self.stop_btn.grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(bar, text="Open folder", width=110, height=36, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=self._open_folder).grid(row=0, column=2, padx=(0, 12))
        prog = ctk.CTkFrame(bar, fg_color="transparent")
        prog.grid(row=0, column=3, sticky="ew")
        self.status = ctk.CTkLabel(prog, text="Ready", anchor="w")
        self.status.pack(fill="x")
        self.progress = ctk.CTkProgressBar(prog)
        self.progress.set(0)
        self.progress.pack(fill="x")

        # Tabs: the editable case list, and the download log
        self.tabs = ctk.CTkTabview(self, corner_radius=12)
        self.tabs.grid(row=3, column=0, sticky="nsew", padx=PAD, pady=(0, PAD))
        review, log = self.tabs.add("Review cases"), self.tabs.add("Log")
        for tab in (review, log):
            tab.grid_columnconfigure(0, weight=1)
        review.grid_rowconfigure(1, weight=1)
        log.grid_rowconfigure(0, weight=1)

        tools = ctk.CTkFrame(review, fg_color="transparent")
        tools.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        tools.grid_columnconfigure(0, weight=1)
        self.check_label = ctk.CTkLabel(tools, text="", anchor="w", justify="left", wraplength=640)
        self.check_label.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(tools, text="Regenerate from syllabus", width=170, fg_color="transparent", border_width=1,
                      text_color=("gray10", "gray90"), command=lambda: self._load_cases(fresh=True)).grid(row=0, column=1)
        self.editor = ctk.CTkTextbox(review, font=MONO, wrap="none", undo=True)
        self.editor.grid(row=1, column=0, sticky="nsew")
        self.editor.bind("<KeyRelease>", lambda _: self._schedule_check())

        self.log = ctk.CTkTextbox(log, font=MONO, wrap="word")
        self.log.grid(row=0, column=0, sticky="nsew")
        self.log.tag_config("ok", foreground="#2ecc71")
        self.log.tag_config("bad", foreground="#e74c3c")
        self.log.tag_config("note", foreground="#f39c12")
        self.log.configure(state="disabled")

        self._load_syllabi()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain)

    def _label(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, anchor="w", width=120).grid(
            row=row, column=0, sticky="w", padx=PAD, pady=(PAD if row == 0 else 4, 4))

    # --- inputs -------------------------------------------------------------
    def _load_syllabi(self):
        self.syllabus_paths = {p.name: p for p in sorted(engine.SYLLABI.glob("*.md"))}
        last = Path(self.settings.get("syllabus", ""))
        if last.is_file():
            self.syllabus_paths.setdefault(last.name, last)
        self.syllabus_menu.configure(values=[*self.syllabus_paths, OTHER])
        first = last.name if last.name in self.syllabus_paths else next(iter(self.syllabus_paths), "")
        if first:
            self.syllabus_var.set(first)
            self._syllabus_picked(first)
        else:
            self.syllabus_var.set(OTHER)
            self.check_label.configure(text="Pick your syllabus .md above.", text_color=MUTED)

    def _syllabus_picked(self, choice):
        if choice == OTHER:
            path = filedialog.askopenfilename(title="Syllabus", initialdir=engine.SYLLABI,
                                              filetypes=[("Markdown / text", "*.md *.txt"), ("All files", "*")])
            if not path:
                self.syllabus_var.set(next(iter(self.syllabus_paths), ""))
                return
            path = Path(path)
            self.syllabus_paths[path.name] = path
            self.syllabus_menu.configure(values=[*self.syllabus_paths, OTHER])
            self.syllabus_var.set(choice := path.name)
        self.name_var.set(engine.safe_filename(self.syllabus_paths[choice].stem))
        self._load_cases()

    def _load_cases(self, fresh=False):
        syllabus, dest = self.syllabus_paths.get(self.syllabus_var.get()), self._dest()
        if not syllabus:
            return
        if fresh:
            text, saved = syllabus_parser.to_yaml(syllabus.read_text(), syllabus.name), False
        else:
            text, saved = engine.draft_cases(syllabus, dest or Path("/nonexistent"))
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self.editor.edit_reset()
        self.tabs.set("Review cases")
        self._check(f"Loaded your saved cases.yaml from {dest.name}. " if saved else "")

    def _schedule_check(self):
        if self.check_job:
            self.after_cancel(self.check_job)
        self.check_job = self.after(400, self._check)

    def _check(self, prefix=""):
        """Validate the editor's yaml and say so; returns the case list or None."""
        self.check_job = None
        text = self.editor.get("1.0", "end")
        try:
            cases = syllabus_parser.validate(text)
        except ValueError as e:
            self.check_label.configure(text=f"✗ {e}", text_color=("#c0392b", "#e74c3c"))
            return None
        checks = text.count("# CHECK:")
        msg = f"{prefix}✓ {len(cases)} cases. Check names, citations and match words, edit if needed, then Download."
        if checks:
            msg += f"  {checks} guess(es) marked #\u00a0CHECK."
        self.check_label.configure(text=msg, text_color=("#1e8449", "#2ecc71"))
        return cases

    def _pick_parent(self):
        path = filedialog.askdirectory(title="Create the section folder in", initialdir=self.parent_var.get())
        if path:
            self.parent_var.set(path)

    def _dest(self):
        name = engine.safe_filename(self.name_var.get())
        return Path(self.parent_var.get()).expanduser() / name if name else None

    def _update_preview(self):
        dest = self._dest()
        if dest:
            home = str(Path.home())
            shown = "~" + str(dest)[len(home):] if str(dest).startswith(home) else str(dest)
            self.preview.configure(text=f"→  {shown}/  cases · digests · cases.yaml · syllabus.md · PROMPT.md")
        else:
            self.preview.configure(text="Enter a folder name")

    # --- running ------------------------------------------------------------
    def _run(self):
        syllabus, dest = self.syllabus_paths.get(self.syllabus_var.get()), self._dest()
        if not syllabus or not dest:
            self.status.configure(text="Pick a syllabus and enter a folder name")
            return
        if not dest.parent.is_dir():
            self.status.configure(text=f"Folder not found: {dest.parent}")
            return
        cases = self._check()
        if cases is None:
            self.tabs.set("Review cases")
            self.status.configure(text="Fix the case list first")
            return
        self.total = len(cases)
        self.done = 0
        self.dest = engine.prepare_section(dest, self.editor.get("1.0", "end-1c"), syllabus)
        engine.save_settings(parent=str(dest.parent), syllabus=str(syllabus))

        cmd = [sys.executable, "-u", str(engine.HERE / "cdasia_fetch.py"), "--dest", str(dest),
               "--cases", str(dest / "cases.yaml"), "--syllabus", str(syllabus)]
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.tabs.set("Log")
        self.progress.set(0)
        self.status.configure(text="Opening browser...")
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.proc = subprocess.Popen(cmd, cwd=engine.HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

    def _read(self, proc):
        for line in proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def _drain(self):
        try:
            while True:
                line = self.lines.get_nowait()
                if line is None:
                    self._finished()
                else:
                    self._handle(line)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _handle(self, line):
        low = line.lower()
        tag = ("bad" if ("not found" in low or "failed" in low or "error" in low) else
               "ok" if ("saved" in low or "skipping" in low) else
               "note" if line.startswith(">>>") else None)
        self._write(line, tag)
        if line.startswith(">>> Please log in"):
            self.status.configure(text="Log in to CDAsia in the browser window")
        m = re.match(r"\[(\d+)\] (.+?):", line)
        if m:
            self.done += 1
            self.progress.set(min(self.done / self.total, 1))
            self.status.configure(text=f"{self.done}/{self.total}  {m.group(2)}")

    def _write(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text, tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _finished(self):
        code = self.proc.wait() if self.proc else 0
        self.proc = None
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        if code == 0:
            self.progress.set(1)
            self.status.configure(text="Done. All cases downloaded")
        elif code < 0:
            self.status.configure(text="Stopped")
        else:
            self.status.configure(text="Done. Some cases need attention (see log / report.csv)")

    def _stop(self):
        if self.proc:
            self.proc.terminate()

    def _open_folder(self):
        dest = getattr(self, "dest", None) or self._dest()
        target = dest if dest and dest.exists() else Path(self.parent_var.get()).expanduser()
        if sys.platform == "win32":
            os.startfile(target)
        else:
            subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", str(target)])

    def _close(self):
        self._stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
