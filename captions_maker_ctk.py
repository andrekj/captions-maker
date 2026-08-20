from pathlib import Path
import json, queue, shutil, subprocess, threading, uuid
import customtkinter as ctk
from tkinter import filedialog, messagebox

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "caption_projects"
PROJECTS.mkdir(exist_ok=True)
import captions_maker_server as engine

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

BG = "#0b1014"
PANEL = "#131a20"
PANEL_2 = "#19232a"
BORDER = "#27343d"
MUTED = "#84939d"
MINT = "#47dfbf"
AMBER = "#ffc45b"


class CaptionsMaker(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Captions Maker")
        self.geometry("1120x720")
        self.minsize(920, 620)
        self.configure(fg_color=BG)
        self.file_path = None
        self.project = None
        self.events = queue.Queue()
        self.font_var = ctk.StringVar(value="Georgia")
        self.size_var = ctk.IntVar(value=100)
        self.color_var = ctk.StringVar(value="Kuning")
        self.words_var = ctk.IntVar(value=1)
        self.pos_var = ctk.IntVar(value=50)
        self._build_ui()
        self.after(100, self._drain_events)

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color="#0f151a")
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)

        ctk.CTkLabel(side, text="C  CAPTIONS", text_color=MINT,
                     font=ctk.CTkFont(size=17, weight="bold")).pack(anchor="w", padx=22, pady=(28, 2))
        ctk.CTkLabel(side, text="Local caption studio", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=22)

        ctk.CTkLabel(side, text="PROJECT", text_color=MUTED,
                     font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=22, pady=(38, 8))
        self.project_label = ctk.CTkLabel(side, text="No video selected", text_color="#d9e2e6",
                                          anchor="w", wraplength=165)
        self.project_label.pack(fill="x", padx=22)

        ctk.CTkLabel(side, text="STEPS", text_color=MUTED,
                     font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=22, pady=(35, 8))
        self.step_labels = []
        for number, text in [("01", "Upload"), ("02", "Review"), ("03", "Style & export")]:
            row = ctk.CTkFrame(side, fg_color="transparent", height=34)
            row.pack(fill="x", padx=17, pady=2)
            badge = ctk.CTkLabel(row, text=number, width=28, height=24, corner_radius=7,
                                 fg_color=PANEL_2, text_color=MUTED,
                                 font=ctk.CTkFont(size=10, weight="bold"))
            badge.pack(side="left")
            label = ctk.CTkLabel(row, text=text, text_color="#aebbc2", anchor="w")
            label.pack(side="left", padx=9)
            self.step_labels.append((badge, label))

        ctk.CTkFrame(side, height=1, fg_color=BORDER).pack(fill="x", padx=22, pady=(35, 18))
        ctk.CTkLabel(side, text="PROCESSING", text_color=MUTED,
                     font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=22)
        ctk.CTkLabel(side, text="Whisper small\nCPU int8 · FFmpeg", text_color=MINT,
                     justify="left", anchor="w", font=ctk.CTkFont(size=11)).pack(anchor="w", padx=22, pady=(7, 0))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=30, pady=26)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text="Create captions", text_color="#f0f5f6",
                     font=ctk.CTkFont(size=27, weight="bold")).grid(row=0, column=0, sticky="w")
        self.status = ctk.CTkLabel(top, text="Upload a video to get started", text_color=MUTED,
                                   font=ctk.CTkFont(size=12))
        self.status.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ctk.CTkButton(top, text="New video", width=105, height=34, fg_color=PANEL_2,
                      hover_color="#25343c", command=self.choose_file).grid(row=0, column=1, rowspan=2, sticky="e")

        self.tabs = ctk.CTkSegmentedButton(main, values=["Upload", "Review", "Style & export"],
                                           command=self._tab_changed, height=38,
                                           selected_color=MINT, selected_hover_color="#38b99e",
                                           text_color="#06120f")
        self.tabs.grid(row=1, column=0, sticky="w", pady=(22, 18))
        self.tabs.set("Upload")

        self.content = ctk.CTkFrame(main, fg_color="transparent")
        self.content.grid(row=2, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self._show_upload()

    def _clear_content(self):
        for child in self.content.winfo_children():
            child.destroy()

    def _show_upload(self):
        self._clear_content()
        self._set_step(0)
        card = ctk.CTkFrame(self.content, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=14)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        zone = ctk.CTkFrame(card, fg_color="#101b1d", border_color="#2e7467", border_width=1, corner_radius=12)
        zone.grid(row=0, column=0, padx=28, pady=28, sticky="nsew")
        ctk.CTkLabel(zone, text="＋", text_color=MINT, font=ctk.CTkFont(size=40)).pack(pady=(70, 3))
        ctk.CTkLabel(zone, text="Upload your voiceover video", text_color="#edf4f4",
                     font=ctk.CTkFont(size=19, weight="bold")).pack()
        ctk.CTkLabel(zone, text="MP4, MOV, MKV or WebM · processing stays on this computer",
                     text_color=MUTED).pack(pady=(7, 20))
        ctk.CTkButton(zone, text="Choose video", width=150, height=40, fg_color=MINT,
                      text_color="#06120f", command=self.choose_file).pack(pady=(0, 70))

    def _show_review(self):
        self._clear_content()
        self._set_step(1)
        card = ctk.CTkFrame(self.content, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=14)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 12))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="Review transcription", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text="Edit any word before rendering. Timing stays attached to the voiceover.", text_color=MUTED).grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.review = ctk.CTkTextbox(card, fg_color="#0d1317", border_color=BORDER, border_width=1,
                                     corner_radius=9, font=ctk.CTkFont(size=13))
        self.review.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 16))
        if self.project:
            for i, seg in enumerate(self.project.get("segments", [])):
                self.review.insert("end", f"[{i}] {seg['start']:.2f}s  {seg['text']}\n")
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 18))
        ctk.CTkButton(bottom, text="Transcribe again", width=130, command=self.transcribe).pack(side="left")
        ctk.CTkButton(bottom, text="Continue to style  →", width=160, fg_color=MINT,
                      text_color="#06120f", command=lambda: self.tabs.set("Style & export")).pack(side="right")

    def _show_style(self):
        self._clear_content()
        self._set_step(2)
        wrap = ctk.CTkFrame(self.content, fg_color="transparent")
        wrap.grid(row=0, column=0, sticky="nsew")
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)
        left = ctk.CTkFrame(wrap, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        ctk.CTkLabel(left, text="Caption style", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(left, text="Defaults are tuned for Shorts", text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 14))
        self._option(left, "Font", self.font_var, ["Georgia", "Arial Black", "Impact", "Trebuchet MS", "Courier New"])
        self._slider(left, "Font size", self.size_var, 24, 110)
        self._option(left, "Text color", self.color_var, ["Kuning", "Putih", "Mint"])
        self._slider(left, "Vertical position", self.pos_var, 15, 80)
        self._option(left, "Words per caption", self.words_var, [1, 2, 3])
        right = ctk.CTkFrame(wrap, fg_color=PANEL, border_color=BORDER, border_width=1, corner_radius=14)
        right.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        ctk.CTkLabel(right, text="Ready to render", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=20, pady=(18, 2))
        ctk.CTkLabel(right, text="Caption will be burned into a new MP4", text_color=MUTED).pack(anchor="w", padx=20, pady=(0, 28))
        summary = ctk.CTkFrame(right, fg_color="#10181d", corner_radius=9)
        summary.pack(fill="x", padx=20)
        for label, value in [("Font", "Georgia"), ("Size", "100 px"), ("Color", "Kuning"), ("Position", "Center")]:
            row = ctk.CTkFrame(summary, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=8)
            ctk.CTkLabel(row, text=label, text_color=MUTED).pack(side="left")
            ctk.CTkLabel(row, text=value, text_color="#e9f0f1").pack(side="right")
        self.render_button = ctk.CTkButton(right, text="Render & download MP4", height=46, fg_color=MINT,
                                            text_color="#06120f", command=self.render)
        self.render_button.pack(fill="x", padx=20, pady=(28, 10))
        ctk.CTkLabel(right, text="Output is saved in caption_projects", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).pack()

    def _option(self, parent, label, variable, values):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=7)
        ctk.CTkLabel(row, text=label, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(row, variable=variable, values=[str(v) for v in values], width=155).pack(side="right")

    def _slider(self, parent, label, variable, low, high):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=7)
        ctk.CTkLabel(row, text=label, anchor="w").pack(side="left")
        ctk.CTkSlider(row, variable=variable, from_=low, to=high, number_of_steps=high-low, width=155).pack(side="right")

    def _tab_changed(self, value):
        if value == "Upload": self._show_upload()
        elif value == "Review":
            if not self.project:
                messagebox.showinfo("Review", "Upload and transcribe a video first.")
                self.tabs.set("Upload")
            else: self._show_review()
        else:
            if not self.project:
                messagebox.showinfo("Style", "Upload and transcribe a video first.")
                self.tabs.set("Upload")
            else: self._show_style()

    def _set_step(self, active):
        for i, (badge, label) in enumerate(self.step_labels):
            badge.configure(fg_color="#17483f" if i == active else PANEL_2,
                            text_color=MINT if i == active else MUTED)
            label.configure(text_color="#edf4f4" if i == active else "#aebbc2")

    def choose_file(self):
        p = filedialog.askopenfilename(title="Choose voiceover video",
                                       filetypes=[("Video", "*.mp4 *.mov *.mkv *.webm"), ("All files", "*.*")])
        if p:
            self.file_path = Path(p)
            self.project = None
            self.project_label.configure(text=self.file_path.name)
            self.status.configure(text=f"Selected: {self.file_path.name}")
            self.tabs.set("Upload")
            self._show_upload()
            # Start the expected one-click flow immediately after file selection.
            self.after(150, self.transcribe)

    def transcribe(self):
        if not self.file_path:
            messagebox.showwarning("Upload video", "Choose a video first.")
            return
        self.status.configure(text="Transcribing locally… first run may take longer")
        self._run_async(self._transcribe_worker)

    def _transcribe_worker(self):
        try:
            pid = uuid.uuid4().hex[:12]
            folder = PROJECTS / pid
            folder.mkdir()
            dst = folder / self.file_path.name
            shutil.copy2(self.file_path, dst)
            data = engine.transcribe(dst, "auto")
            data.update(project_id=pid, filename=self.file_path.name)
            (folder / "transcript.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf8")
            self.events.put(("transcribed", data))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _collect_review(self):
        if not self.project or not hasattr(self, "review"):
            return
        lines = self.review.get("1.0", "end").splitlines()
        segments = self.project.get("segments", [])
        for line in lines:
            if not line.startswith("[") or "]" not in line:
                continue
            try:
                index = int(line.split("]", 1)[0][1:])
                text = line.split("]", 1)[1].strip().split("s  ", 1)[-1]
            except (ValueError, IndexError):
                continue
            if index >= len(segments):
                continue
            segment = segments[index]
            segment["text"] = text
            words = text.split()
            old = segment.get("words", [])
            if len(words) == len(old):
                for word, edited in zip(old, words):
                    word["word"] = edited
            elif words:
                start, end = float(segment["start"]), float(segment["end"])
                step = (end - start) / len(words)
                segment["words"] = [{"word": word, "start": start + j * step,
                                     "end": start + (j + 1) * step, "confidence": 1}
                                    for j, word in enumerate(words)]

    def render(self):
        self._collect_review()
        if not self.project:
            messagebox.showwarning("Transcription", "Generate captions first.")
            return
        self.status.configure(text="Rendering with FFmpeg…")
        self._run_async(self._render_worker)

    def _render_worker(self):
        try:
            pid = self.project["project_id"]
            folder = PROJECTS / pid
            video = folder / self.project["filename"]
            colors = {"Kuning": "&H0000FFFF", "Putih": "&H00FFFFFF", "Mint": "&H00BFFFD8"}
            style = {"font": self.font_var.get(), "size": int(float(self.size_var.get())),
                     "color": colors[self.color_var.get()], "accent": "&H0000BFFF", "align": 5,
                     "y": round(1920 * (1 - int(float(self.pos_var.get())) / 100)),
                     "words_per_caption": int(self.words_var.get())}
            ass = folder / "captions.ass"
            ass.write_text(engine.make_ass(self.project, style), encoding="utf8")
            output = folder / "captioned_output.mp4"
            cmd = ["ffmpeg", "-y", "-i", str(video), "-vf", "ass=captions.ass", "-c:v", "libx264",
                   "-preset", "veryfast", "-crf", "20", "-c:a", "copy", "-movflags", "+faststart", str(output)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, cwd=str(folder))
            if result.returncode:
                raise RuntimeError(result.stderr[-2500:])
            self.events.put(("rendered", output))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _run_async(self, function):
        threading.Thread(target=function, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "transcribed":
                    self.project = data
                    self.status.configure(text=f"Transcription ready · {len(data.get('segments', []))} segments")
                    self.tabs.set("Review")
                    self._show_review()
                elif kind == "rendered":
                    self.status.configure(text=f"Render complete · {data.name}")
                    messagebox.showinfo("Render complete", f"Captioned video created:\n{data}")
                else:
                    self.status.configure(text="Something went wrong")
                    messagebox.showerror("Error", data)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)


if __name__ == "__main__":
    app = CaptionsMaker()
    app.mainloop()
