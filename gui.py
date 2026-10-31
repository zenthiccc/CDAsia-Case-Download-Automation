"""Desktop UI for the CDAsia downloader (CustomTkinter).

  .venv/bin/python gui.py

The download itself runs cdasia_fetch.py in a child process, so the window stays responsive
and Stop can end it.
"""
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
import yaml

import cdasia_fetch as engine

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

PAD = 16
MONO = ("SF Mono", 12)
OTHER = "Browse for a file..."


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CDAsia Case Downloader")
        self.geometry("820x720")
        self.minsize(680, 600)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.settings = engine.load_settings()
        self.proc = None
        self.lines = queue.Queue()
        self.total = 0
        self.done = 0

        # Header
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(PAD, 4))
        ctk.CTkLabel(head, text="CDAsia Case Downloader", font=ctk.CTkFont(size=22, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(head, text="Downloads every case in a syllabus yaml, with separate opinions, "
                                "into <folder>/cases.", text_color=("gray40", "gray65")).pack(anchor="w")

        # Inputs card
        card = ctk.CTkFrame(self, corner_radius=12)
        card.grid(row=1, column=0, sticky="ew", padx=PAD, pady=8)
        card.grid_columnconfigure(1, weight=1)

        self.yaml_var = ctk.StringVar()
        self.parent_var = ctk.StringVar(value=self.settings.get("parent", str(engine.HERE.parent)))
        self.name_var = ctk.StringVar()
        self.only_var = ctk.StringVar()

        self._label(card, "Syllabus yaml", 0)
        self.yaml_menu = ctk.CTkOptionMenu(card, variable=self.yaml_var, command=self._yaml_picked, dynamic_resizing=False)
        self.yaml_menu.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=(PAD, 4))
        self.count_label = ctk.CTkLabel(card, text="", width=80, text_color=("gray40", "gray65"))
        self.count_label.grid(row=0, column=2, padx=(0, PAD), pady=(PAD, 4))

        self._label(card, "Create in", 1)
        ctk.CTkEntry(card, textvariable=self.parent_var).grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=4)
        ctk.CTkButton(card, text="Choose...", width=80, command=self._pick_parent).grid(row=1, column=2, padx=(0, PAD), pady=4)

        self._label(card, "Folder name", 2)
        ctk.CTkEntry(card, textvariable=self.name_var, placeholder_text="e.g. consti-art7-sec16to17").grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(0, PAD), pady=4)

        self._label(card, "Only (optional)", 3)
        ctk.CTkEntry(card, textvariable=self.only_var, placeholder_text="download just cases whose name contains this").grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=(0, PAD), pady=4)

        self.preview = ctk.CTkLabel(card, text="", anchor="w", justify="left", text_color=("gray40", "gray65"))
        self.preview.grid(row=4, column=0, columnspan=3, sticky="ew", padx=PAD, pady=(4, PAD))
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

        # Log
        self.log = ctk.CTkTextbox(self, corner_radius=12, font=MONO, wrap="word")
        self.log.grid(row=3, column=0, sticky="nsew", padx=PAD, pady=(8, PAD))
        self.log.tag_config("ok", foreground="#2ecc71")
        self.log.tag_config("bad", foreground="#e74c3c")
        self.log.tag_config("note", foreground="#f39c12")
        self.log.configure(state="disabled")

        self._load_yamls()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain)

    def _label(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, anchor="w", width=120).grid(
            row=row, column=0, sticky="w", padx=PAD, pady=(PAD if row == 0 else 4, 4))

    # --- inputs -------------------------------------------------------------
    def _load_yamls(self):
        self.yaml_paths = {p.name: p for p in sorted(engine.SYLLABI.glob("*.y*ml"))}
        last = Path(self.settings.get("yaml", ""))
        if last.is_file():
            self.yaml_paths.setdefault(last.name, last)
        self.yaml_menu.configure(values=[*self.yaml_paths, OTHER])
        first = last.name if last.name in self.yaml_paths else next(iter(self.yaml_paths), "")
        if first:
            self.yaml_var.set(first)
            self._yaml_picked(first)

    def _yaml_picked(self, choice):
        if choice == OTHER:
            path = filedialog.askopenfilename(title="Syllabus yaml", initialdir=engine.SYLLABI,
                                              filetypes=[("YAML", "*.yaml *.yml")])
            if not path:
                self.yaml_var.set(next(iter(self.yaml_paths), ""))
                return
            path = Path(path)
            self.yaml_paths[path.name] = path
            self.yaml_menu.configure(values=[*self.yaml_paths, OTHER])
            self.yaml_var.set(choice := path.name)
        try:
            cases = yaml.safe_load(self.yaml_paths[choice].read_text()) or []
            self.count_label.configure(text=f"{len(cases)} cases")
        except Exception as e:
            self.count_label.configure(text="invalid")
            self._write(f"Could not read {choice}: {e}\n", "bad")
        self.name_var.set(self.yaml_paths[choice].stem)

    def _pick_parent(self):
        path = filedialog.askdirectory(title="Create the section folder in", initialdir=self.parent_var.get())
        if path:
            self.parent_var.set(path)

    def _dest(self):
        name = engine.safe_filename(self.name_var.get())
        return Path(self.parent_var.get()).expanduser() / name if name else None

    def _update_preview(self):
        dest = self._dest()
        self.preview.configure(text=f"→  {dest}/cases   ·   {dest}/digest" if dest else "Enter a folder name")

    # --- running ------------------------------------------------------------
    def _run(self):
        cases_yaml, dest = self.yaml_paths.get(self.yaml_var.get()), self._dest()
        if not cases_yaml or not dest:
            self.status.configure(text="Pick a yaml and enter a folder name")
            return
        if not dest.parent.is_dir():
            self.status.configure(text=f"Folder not found: {dest.parent}")
            return
        only = self.only_var.get().strip()
        cases = yaml.safe_load(cases_yaml.read_text()) or []
        self.total = sum(1 for c in cases if not only or only.lower() in c["name"].lower()) or 1
        self.done = 0
        self.dest = dest
        engine.save_settings(parent=str(dest.parent), yaml=str(cases_yaml))

        cmd = [sys.executable, "-u", str(engine.HERE / "cdasia_fetch.py"), "--cases", str(cases_yaml), "--dest", str(dest)]
        if only:
            cmd += ["--only", only]
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
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
        subprocess.run(["open", str(target)])

    def _close(self):
        self._stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
