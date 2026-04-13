import customtkinter as ctk
import tkinter as tk
import threading
import time
import ctypes
import json
import os
from pynput.mouse import Listener, Button

# ============================================================
#  ФАЙЛ НАЛАШТУВАНЬ
# ============================================================
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "macro_settings.json")

DEFAULT_SETTINGS = {
    "sensitivity":   3.30,
    "resolution_x":  3440,
    "resolution_y":  1440,
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                for k, v in DEFAULT_SETTINGS.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ============================================================
#  БАЗОВИЙ ПАТЕРН (1920x1080 / sens 1.0)
#
#  ЛОГІКА КОМПЕНСАЦІЇ:
#  Гра тягне приціл ВГОРУ при стрільбі (recoil іде вгору на екрані)
#  тому мишка має рухатись ВНИЗ (позитивний Y) щоб компенсувати
#
#  Але гра також тягне вліво/вправо — і ось тут дзеркально:
#  коли recoil іде ВПРАВО — мишка тягне ВЛІВО (від'ємний X)
#  коли recoil іде ВЛІВО  — мишка тягне ВПРАВО (позитивний X)
#
#  На гіфці показано РУХ МИШКИ (компенсація), не сам recoil:
#  1. Вниз (компенсуємо підйом вгору)
#  2. Петля вліво (спрей пішов вправо — тягнемо вліво)
#  3. Петля вправо, ширша (спрей пішов різко вліво — тягнемо вправо)
# ============================================================
_RAW_PATTERN = [
    # Кулі 1-9: ВНИЗ — компенсуємо підйом прицілу
    (  0,  85),
    (  0,  90),
    (  0,  92),
    (  0,  90),
    (  0,  85),
    (  0,  78),
    (  0,  68),
    (  0,  55),
    (  0,  40),

    # Кулі 10-13: починає тягнути вправо — тягнемо мишку ВЛІВО + трохи вниз
    (-10,  25),
    (-20,  12),
    (-26,   4),
    (-24,   0),

    # Кулі 14-16: пік лівої петлі — повертаємось
    (-18,  -4),
    ( -8,  -4),
    (  4,  -2),

    # Кулі 17-23: спрей іде різко вліво — тягнемо мишку ВПРАВО (ширша петля)
    ( 16,   0),
    ( 28,   2),
    ( 38,   2),
    ( 44,   0),
    ( 42,  -2),
    ( 34,  -2),
    ( 22,  -2),

    # Кулі 24-27: повернення назад вліво
    (  8,   0),
    ( -6,   2),
    (-18,   2),
    (-26,   0),

    # Кулі 28-30: затухання
    (-20,   0),
    (-12,   0),
    ( -4,   0),
]

DELAY        = 0.0875
SMOOTH_STEPS = 15
BASE_RES_Y   = 1080
BASE_SENS    = 1.0


def compute_scale(sensitivity, resolution_y):
    return (BASE_SENS / sensitivity) * (BASE_RES_Y / resolution_y)

def build_pattern(scale):
    return [(round(dx * scale), round(dy * scale)) for dx, dy in _RAW_PATTERN]


# ============================================================
#  ВІКНО НАЛАШТУВАНЬ
# ============================================================
class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, settings, on_save):
        super().__init__(parent)
        self.title("Налаштування")
        self.geometry("340x340")
        self.resizable(False, False)
        self.grab_set()

        self.settings = settings.copy()
        self.on_save  = on_save

        ctk.CTkLabel(self, text="Налаштування макросу",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(20, 16))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(padx=30, fill="x")

        ctk.CTkLabel(form, text="Сенситивність в грі:", anchor="w").pack(fill="x")
        self.entry_sens = ctk.CTkEntry(form, placeholder_text="напр. 3.30")
        self.entry_sens.insert(0, str(self.settings["sensitivity"]))
        self.entry_sens.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(form, text="Ширина екрану (px):", anchor="w").pack(fill="x")
        self.entry_resx = ctk.CTkEntry(form, placeholder_text="напр. 3440")
        self.entry_resx.insert(0, str(self.settings["resolution_x"]))
        self.entry_resx.pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(form, text="Висота екрану (px):", anchor="w").pack(fill="x")
        self.entry_resy = ctk.CTkEntry(form, placeholder_text="напр. 1440")
        self.entry_resy.insert(0, str(self.settings["resolution_y"]))
        self.entry_resy.pack(fill="x", pady=(2, 16))

        ctk.CTkLabel(self,
                     text="Після збереження — одразу діє,\nперезапуск не потрібен.",
                     font=ctk.CTkFont(size=11), text_color="gray").pack()

        self.label_error = ctk.CTkLabel(self, text="", text_color="#E24B4A",
                                        font=ctk.CTkFont(size=11))
        self.label_error.pack(pady=(4, 0))

        ctk.CTkButton(self, text="Зберегти і застосувати",
                      command=self._save, height=36).pack(pady=(8, 20), padx=30, fill="x")

    def _save(self):
        try:
            sens  = float(self.entry_sens.get().replace(",", "."))
            res_x = int(self.entry_resx.get())
            res_y = int(self.entry_resy.get())
            if sens <= 0 or res_x <= 0 or res_y <= 0:
                raise ValueError
            new_settings = {"sensitivity": sens, "resolution_x": res_x, "resolution_y": res_y}
            save_settings(new_settings)
            self.on_save(new_settings)
            self.destroy()
        except ValueError:
            self.label_error.configure(text="Перевір введені значення!")


# ============================================================
#  ГОЛОВНЕ ВІКНО
# ============================================================
class MacroApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("AK-47 Recoil Macro")
        self.geometry("640x560")
        self.resizable(False, False)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.settings      = load_settings()
        self.scale         = compute_scale(self.settings["sensitivity"],
                                           self.settings["resolution_y"])
        self.pattern       = build_pattern(self.scale)

        self.macro_enabled = False
        self.is_firing     = False
        self.listener      = None
        self._settings_win = None

        self._setup_ui()
        self._start_mouse_listener()

    # ------------------------------------------------------------------ UI ---

    def _setup_ui(self):
        self.frame_left = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.frame_left.pack(side="left", fill="y")
        self.frame_left.pack_propagate(False)

        ctk.CTkLabel(self.frame_left, text="AK-47 MACRO",
                     font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(24, 4))
        ctk.CTkLabel(self.frame_left, text="CS2 / Rust",
                     font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 16))

        self.switch_macro = ctk.CTkSwitch(
            self.frame_left, text="Увімкнути макрос",
            command=self._toggle_macro, font=ctk.CTkFont(size=13),
        )
        self.switch_macro.pack(pady=8, padx=20)

        ctk.CTkButton(self.frame_left, text="▶  Показати анімацію",
                      command=self._play_animation, height=36
                      ).pack(pady=8, padx=20, fill="x")

        ctk.CTkButton(self.frame_left, text="✕  Очистити",
                      command=self._clear_canvas,
                      fg_color="transparent", border_width=1, height=32
                      ).pack(pady=4, padx=20, fill="x")

        ctk.CTkButton(self.frame_left, text="⚙  Налаштування",
                      command=self._open_settings,
                      fg_color="#2b4a6f", hover_color="#1e3a5f", height=32
                      ).pack(pady=(12, 4), padx=20, fill="x")

        ctk.CTkFrame(self.frame_left, height=1, fg_color="gray30").pack(
            fill="x", padx=16, pady=12)

        self.info_frame = ctk.CTkFrame(self.frame_left, fg_color="transparent")
        self.info_frame.pack(padx=20, fill="x")
        self._build_info_rows()

        self.label_status = ctk.CTkLabel(
            self.frame_left, text="● ВИМКНЕНО",
            text_color="#E24B4A", font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.label_status.pack(side="bottom", pady=20)

        # ── Права панель — канвас ────────────────────────────────────────────
        self.frame_right = ctk.CTkFrame(self, corner_radius=0, fg_color="#2a2a2a")
        self.frame_right.pack(side="right", fill="both", expand=True)

        ctk.CTkLabel(self.frame_right,
                     text="Рух мишки (компенсація віддачі)",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(pady=(8, 0))

        self.canvas = tk.Canvas(self.frame_right, bg="#333333", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        # Хрестик — початкова позиція прицілу
        self._start_x, self._start_y = 200, 80
        self._draw_start_dot()

    def _build_info_rows(self):
        for w in self.info_frame.winfo_children():
            w.destroy()
        rows = [
            ("Розширення:",    f"{self.settings['resolution_x']}×{self.settings['resolution_y']}"),
            ("Сенситивність:", f"{self.settings['sensitivity']}"),
            ("Масштаб:",       f"{self.scale:.3f}"),
            ("Затримка:",      f"{DELAY*1000:.1f} мс"),
            ("Плавність:",     f"{SMOOTH_STEPS} кроків"),
            ("Куль:",          "30"),
        ]
        for label, val in rows:
            row = ctk.CTkFrame(self.info_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11),
                         text_color="gray").pack(side="left")
            ctk.CTkLabel(row, text=val, font=ctk.CTkFont(size=11, weight="bold")
                         ).pack(side="right")

    def _draw_start_dot(self):
        x, y = self._start_x, self._start_y
        self.canvas.create_oval(x-6, y-6, x+6, y+6,
                                fill="#4CAF50", outline="#4CAF50", tags="start")
        self.canvas.create_text(x + 14, y, text="старт",
                                fill="gray", font=("Arial", 8), tags="start")

    # ---------------------------------------------------------------- Logic --

    def _toggle_macro(self):
        self.macro_enabled = bool(self.switch_macro.get())
        if self.macro_enabled:
            self.label_status.configure(text="● УВІМКНЕНО", text_color="#4CAF50")
        else:
            self.label_status.configure(text="● ВИМКНЕНО",  text_color="#E24B4A")

    def _clear_canvas(self):
        self.canvas.delete("all")
        self._draw_start_dot()

    def _play_animation(self):
        self._clear_canvas()
        threading.Thread(target=self._draw_pattern, daemon=True).start()

    def _open_settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.focus()
            return
        self._settings_win = SettingsWindow(self, self.settings, self._apply_settings)

    def _apply_settings(self, new_settings):
        self.settings = new_settings
        self.scale    = compute_scale(new_settings["sensitivity"],
                                      new_settings["resolution_y"])
        self.pattern  = build_pattern(self.scale)
        self._build_info_rows()
        self._clear_canvas()

    def _draw_pattern(self):
        # Канвас показує рух мишки — масштабуємо щоб влізло
        CANVAS_SCALE = 1.6
        cx, cy = self._start_x, self._start_y

        colors = (
            ["#E24B4A"] * 9  +   # червоний — вниз
            ["#EF9F27"] * 7  +   # жовтий   — ліва петля
            ["#3B8BD4"] * 7  +   # синій    — права петля
            ["#888888"] * 7      # сірий    — повернення/затухання
        )

        for i, (dx, dy) in enumerate(_RAW_PATTERN):
            vdx = round(dx * CANVAS_SCALE / 10)
            vdy = round(dy * CANVAS_SCALE / 10)
            nx, ny = cx + vdx, cy + vdy
            color  = colors[i] if i < len(colors) else "#888888"

            self.canvas.create_line(cx, cy, nx, ny,
                                    fill=color, width=2, smooth=True, tags="line")
            self.canvas.create_oval(nx-3, ny-3, nx+3, ny+3,
                                    fill=color, outline="", tags="dot")
            if (i + 1) % 5 == 0 or i == 0:
                self.canvas.create_text(nx + 10, ny, text=str(i+1),
                                        fill="white", font=("Arial", 8), tags="num")
            cx, cy = nx, ny
            time.sleep(DELAY)

    # ──────────────────────────────────────── Mouse macro ──────────────────

    def _start_mouse_listener(self):
        self.listener = Listener(on_click=self._on_click)
        self.listener.daemon = True
        self.listener.start()

    def _on_click(self, x, y, button, pressed):
        if button == Button.left and self.macro_enabled:
            if pressed:
                self.is_firing = True
                threading.Thread(target=self._move_mouse, daemon=True).start()
            else:
                self.is_firing = False

    def _move_mouse(self):
        sleep_time = DELAY / SMOOTH_STEPS

        for dx, dy in self.pattern:
            if not self.is_firing:
                break

            step_x = dx / SMOOTH_STEPS
            step_y = dy / SMOOTH_STEPS
            rem_x  = 0.0
            rem_y  = 0.0

            for _ in range(SMOOTH_STEPS):
                if not self.is_firing:
                    break

                rem_x += step_x
                rem_y += step_y

                mx = int(rem_x)
                my = int(rem_y)

                if mx != 0 or my != 0:
                    ctypes.windll.user32.mouse_event(0x0001, mx, my, 0, 0)
                    rem_x -= mx
                    rem_y -= my

                time.sleep(sleep_time)

    # ────────────────────────────────────────────────────── Lifecycle ──────

    def on_closing(self):
        if self.listener:
            self.listener.stop()
        self.destroy()


if __name__ == "__main__":
    app = MacroApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
