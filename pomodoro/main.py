"""桌面番茄钟 — 专注 / 短休息 / 长休息"""

import json
import os
import sys
import winsound
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
STATS_PATH = APP_DIR / "stats.json"

DEFAULT_CONFIG = {
    "work_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "pomodoros_before_long_break": 4,
    "always_on_top": False,
    "sound_enabled": True,
}

MODES = {
    "work": {"label": "专注", "color": "#E74C3C", "key": "work_minutes"},
    "short_break": {"label": "短休息", "color": "#27AE60", "key": "short_break_minutes"},
    "long_break": {"label": "长休息", "color": "#3498DB", "key": "long_break_minutes"},
}


def load_json(path: Path, default: dict) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return {**default, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            pass
    return default.copy()


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def show_toast(title: str, message: str) -> None:
    """Windows 10+ 原生通知"""
    safe_title = title.replace("'", "''").replace('"', '`"')
    safe_msg = message.replace("'", "''").replace('"', '`"')
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, "
        "Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
        "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
        "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
        "$x = [xml]$t.GetXml(); "
        f"$x.toast.GetElementsByTagName('text')[0].AppendChild($x.CreateTextNode('{safe_title}')) | Out-Null; "
        f"$x.toast.GetElementsByTagName('text')[1].AppendChild($x.CreateTextNode('{safe_msg}')) | Out-Null; "
        "$n = [Windows.UI.Notifications.ToastNotification]::new($x); "
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Pomodoro').Show($n)"
    )
    os.system(f'powershell -WindowStyle Hidden -Command "{script}"')


class PomodoroApp(ctk.CTk):
    CANVAS_SIZE = 260
    RING_WIDTH = 12

    def __init__(self) -> None:
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.config = load_json(CONFIG_PATH, DEFAULT_CONFIG)
        self.stats = load_json(
            STATS_PATH,
            {"today": datetime.now().strftime("%Y-%m-%d"), "completed_today": 0, "total_completed": 0},
        )
        self._sync_today_stats()

        self.title("番茄钟")
        self.geometry("420x580")
        self.minsize(380, 520)
        self.resizable(False, False)
        self.attributes("-topmost", self.config["always_on_top"])

        self.mode = "work"
        self.remaining_seconds = self._mode_seconds("work")
        self.total_seconds = self.remaining_seconds
        self.running = False
        self.completed_pomodoros = 0
        self._timer_id: str | None = None

        self._build_ui()
        self._refresh_display()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _sync_today_stats(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if self.stats.get("today") != today:
            self.stats["today"] = today
            self.stats["completed_today"] = 0
            save_json(STATS_PATH, self.stats)

    def _mode_seconds(self, mode: str) -> int:
        return int(self.config[MODES[mode]["key"]]) * 60

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, padx=24, pady=(20, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        self.mode_label = ctk.CTkLabel(
            header,
            text=MODES[self.mode]["label"],
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=MODES[self.mode]["color"],
        )
        self.mode_label.grid(row=0, column=0, sticky="w")

        self.settings_btn = ctk.CTkButton(
            header,
            text="⚙",
            width=36,
            height=36,
            font=ctk.CTkFont(size=18),
            command=self._open_settings,
        )
        self.settings_btn.grid(row=0, column=1, sticky="e")

        self.canvas = ctk.CTkCanvas(
            self,
            width=self.CANVAS_SIZE,
            height=self.CANVAS_SIZE,
            bg="#1a1a1a",
            highlightthickness=0,
        )
        self.canvas.grid(row=1, column=0, pady=(8, 4))

        self.time_label = ctk.CTkLabel(
            self,
            text="25:00",
            font=ctk.CTkFont(family="Consolas", size=56, weight="bold"),
        )
        self.time_label.place(relx=0.5, rely=0.38, anchor="center")

        self.sub_label = ctk.CTkLabel(
            self,
            text="准备开始专注",
            font=ctk.CTkFont(size=14),
            text_color="#888888",
        )
        self.sub_label.grid(row=2, column=0, pady=(0, 12))

        mode_bar = ctk.CTkFrame(self, fg_color="transparent")
        mode_bar.grid(row=3, column=0, padx=24, pady=4, sticky="ew")
        mode_bar.grid_columnconfigure((0, 1, 2), weight=1)

        self.mode_buttons: dict[str, ctk.CTkButton] = {}
        for i, (key, info) in enumerate(MODES.items()):
            btn = ctk.CTkButton(
                mode_bar,
                text=info["label"],
                height=34,
                fg_color=info["color"] if key == self.mode else "#333333",
                hover_color=info["color"],
                command=lambda k=key: self._switch_mode(k),
            )
            btn.grid(row=0, column=i, padx=4, sticky="ew")
            self.mode_buttons[key] = btn

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=4, column=0, padx=24, pady=16, sticky="ew")
        controls.grid_columnconfigure((0, 1, 2), weight=1)

        self.start_btn = ctk.CTkButton(
            controls,
            text="开始",
            height=44,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#E74C3C",
            hover_color="#C0392B",
            command=self._toggle_timer,
        )
        self.start_btn.grid(row=0, column=0, padx=4, sticky="ew")

        self.reset_btn = ctk.CTkButton(
            controls,
            text="重置",
            height=44,
            fg_color="#444444",
            hover_color="#555555",
            command=self._reset_timer,
        )
        self.reset_btn.grid(row=0, column=1, padx=4, sticky="ew")

        self.skip_btn = ctk.CTkButton(
            controls,
            text="跳过",
            height=44,
            fg_color="#444444",
            hover_color="#555555",
            command=self._skip_timer,
        )
        self.skip_btn.grid(row=0, column=2, padx=4, sticky="ew")

        stats_frame = ctk.CTkFrame(self, corner_radius=12)
        stats_frame.grid(row=5, column=0, padx=24, pady=(4, 20), sticky="ew")
        stats_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(
            stats_frame,
            text="今日完成",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        ).grid(row=0, column=0, pady=(12, 0))
        ctk.CTkLabel(
            stats_frame,
            text="累计完成",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        ).grid(row=0, column=1, pady=(12, 0))

        self.today_stat = ctk.CTkLabel(
            stats_frame,
            text=str(self.stats["completed_today"]),
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color="#E74C3C",
        )
        self.today_stat.grid(row=1, column=0, pady=(0, 12))

        self.total_stat = ctk.CTkLabel(
            stats_frame,
            text=str(self.stats["total_completed"]),
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color="#3498DB",
        )
        self.total_stat.grid(row=1, column=1, pady=(0, 12))

        self.session_label = ctk.CTkLabel(
            self,
            text=self._session_text(),
            font=ctk.CTkFont(size=12),
            text_color="#666666",
        )
        self.session_label.grid(row=6, column=0, pady=(0, 16))

    def _session_text(self) -> str:
        n = self.config["pomodoros_before_long_break"]
        return f"当前轮次：{self.completed_pomodoros % n}/{n}  ·  完成后进入长休息"

    def _format_time(self, seconds: int) -> str:
        m, s = divmod(max(0, seconds), 60)
        return f"{m:02d}:{s:02d}"

    def _draw_ring(self) -> None:
        self.canvas.delete("all")
        cx = cy = self.CANVAS_SIZE // 2
        r = cx - self.RING_WIDTH - 8
        color = MODES[self.mode]["color"]
        bg = "#2a2a2a"

        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=bg, width=self.RING_WIDTH,
        )

        if self.total_seconds > 0:
            progress = 1 - self.remaining_seconds / self.total_seconds
            extent = max(0.5, 360 * progress)
            self.canvas.create_arc(
                cx - r, cy - r, cx + r, cy + r,
                start=90, extent=-extent,
                outline=color, width=self.RING_WIDTH, style="arc",
            )

    def _refresh_display(self) -> None:
        self.time_label.configure(text=self._format_time(self.remaining_seconds))
        self.mode_label.configure(text=MODES[self.mode]["label"], text_color=MODES[self.mode]["color"])
        self.sub_label.configure(
            text="计时中..." if self.running else "已暂停" if self.remaining_seconds < self.total_seconds else "准备开始"
        )
        self.session_label.configure(text=self._session_text())
        self.today_stat.configure(text=str(self.stats["completed_today"]))
        self.total_stat.configure(text=str(self.stats["total_completed"]))

        for key, btn in self.mode_buttons.items():
            btn.configure(fg_color=MODES[key]["color"] if key == self.mode else "#333333")

        self.start_btn.configure(text="暂停" if self.running else "开始")
        self._draw_ring()

    def _switch_mode(self, mode: str) -> None:
        if self.running:
            return
        self.mode = mode
        self.remaining_seconds = self._mode_seconds(mode)
        self.total_seconds = self.remaining_seconds
        self._refresh_display()

    def _toggle_timer(self) -> None:
        if self.running:
            self._pause_timer()
        else:
            self._start_timer()

    def _start_timer(self) -> None:
        self.running = True
        self._tick()

    def _pause_timer(self) -> None:
        self.running = False
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None
        self._refresh_display()

    def _reset_timer(self) -> None:
        self._pause_timer()
        self.remaining_seconds = self._mode_seconds(self.mode)
        self.total_seconds = self.remaining_seconds
        self._refresh_display()

    def _skip_timer(self) -> None:
        self._pause_timer()
        self._on_timer_complete(skipped=True)

    def _tick(self) -> None:
        if not self.running:
            return

        if self.remaining_seconds <= 0:
            self._on_timer_complete()
            return

        self.remaining_seconds -= 1
        self._refresh_display()
        self._timer_id = self.after(1000, self._tick)

    def _on_timer_complete(self, skipped: bool = False) -> None:
        self.running = False
        if self._timer_id:
            self.after_cancel(self._timer_id)
            self._timer_id = None

        if not skipped:
            self._notify_complete()

        if self.mode == "work" and not skipped:
            self.completed_pomodoros += 1
            self.stats["completed_today"] += 1
            self.stats["total_completed"] += 1
            save_json(STATS_PATH, self.stats)

        self._advance_mode()
        self._refresh_display()

    def _notify_complete(self) -> None:
        mode_info = MODES[self.mode]
        if self.mode == "work":
            title, msg = "专注完成！", "休息一下吧 🍅"
        elif self.mode == "short_break":
            title, msg = "短休息结束", "继续专注！"
        else:
            title, msg = "长休息结束", "新一轮专注开始！"

        if self.config["sound_enabled"]:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)

        show_toast(title, msg)
        self.sub_label.configure(text=msg)

    def _advance_mode(self) -> None:
        if self.mode == "work":
            n = self.config["pomodoros_before_long_break"]
            if self.completed_pomodoros > 0 and self.completed_pomodoros % n == 0:
                self.mode = "long_break"
            else:
                self.mode = "short_break"
        else:
            self.mode = "work"

        self.remaining_seconds = self._mode_seconds(self.mode)
        self.total_seconds = self.remaining_seconds

    def _open_settings(self) -> None:
        if self.running:
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("设置")
        dialog.geometry("340x420")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        entries: dict[str, ctk.CTkEntry] = {}
        labels = [
            ("work_minutes", "专注时长（分钟）"),
            ("short_break_minutes", "短休息（分钟）"),
            ("long_break_minutes", "长休息（分钟）"),
            ("pomodoros_before_long_break", "几轮后长休息"),
        ]

        for i, (key, label) in enumerate(labels):
            ctk.CTkLabel(dialog, text=label, anchor="w").grid(
                row=i, column=0, padx=20, pady=(16 if i == 0 else 8, 0), sticky="ew"
            )
            entry = ctk.CTkEntry(dialog, width=120)
            entry.insert(0, str(self.config[key]))
            entry.grid(row=i, column=1, padx=20, pady=(16 if i == 0 else 8, 0))
            entries[key] = entry

        top_var = ctk.BooleanVar(value=self.config["always_on_top"])
        sound_var = ctk.BooleanVar(value=self.config["sound_enabled"])

        ctk.CTkCheckBox(dialog, text="窗口置顶", variable=top_var).grid(
            row=len(labels), column=0, columnspan=2, padx=20, pady=16, sticky="w"
        )
        ctk.CTkCheckBox(dialog, text="完成时播放提示音", variable=sound_var).grid(
            row=len(labels) + 1, column=0, columnspan=2, padx=20, pady=4, sticky="w"
        )

        def save_settings() -> None:
            try:
                for key, entry in entries.items():
                    val = int(entry.get())
                    if val <= 0:
                        raise ValueError
                    self.config[key] = val
            except ValueError:
                self.sub_label.configure(text="请输入有效的正整数")
                return

            self.config["always_on_top"] = top_var.get()
            self.config["sound_enabled"] = sound_var.get()
            save_json(CONFIG_PATH, self.config)
            self.attributes("-topmost", self.config["always_on_top"])

            if not self.running:
                self.remaining_seconds = self._mode_seconds(self.mode)
                self.total_seconds = self.remaining_seconds
                self._refresh_display()

            dialog.destroy()

        ctk.CTkButton(dialog, text="保存", command=save_settings, fg_color="#E74C3C").grid(
            row=len(labels) + 2, column=0, columnspan=2, pady=24
        )

    def _on_close(self) -> None:
        save_json(CONFIG_PATH, self.config)
        save_json(STATS_PATH, self.stats)
        self.destroy()


def main() -> None:
    app = PomodoroApp()
    app.mainloop()


if __name__ == "__main__":
    main()
