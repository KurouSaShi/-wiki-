import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog, ttk
import urllib.request
import urllib.error
import json
import re
import os


def fetch_sheetdb(api_url: str) -> list[dict]:
    req = urllib.request.Request(api_url, headers={
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} {e.reason}\n{body}") from e


def apply_template_segments(template: str, row: dict) -> list[tuple[str, str]]:
    segments: list[tuple[str, str]] = []
    last = 0
    for m in re.finditer(r"<<(.+?)>>", template):
        if m.start() > last:
            segments.append((template[last:m.start()], "normal"))
        inner = m.group(1)
        if "|" in inner:
            key, fallback = inner.split("|", 1)
            key = key.strip()
            if key in row and row[key] != "":
                segments.append((str(row[key]), "normal"))
            else:
                segments.append((fallback, "unresolved"))
        else:
            key = inner.strip()
            if key in row and row[key] != "":
                segments.append((str(row[key]), "normal"))
            else:
                segments.append((f"<<{key}>>", "unresolved"))
        last = m.end()
    if last < len(template):
        segments.append((template[last:], "normal"))
    return segments


def segments_to_text(segments: list[tuple[str, str]]) -> str:
    """保存用: タグなしのプレーンテキストに変換"""
    return "".join(text for text, _ in segments)
WIKI_EDITOR = dict(
    bg="#ffffff",
    fg="#24292f",
    insertbackground="#0969da",
    selectbackground="#b3d4ff",
    font=("Courier", 10),
)

OUTPUT_AREA = dict(
    bg="#ffffff",
    fg="#24292f",
    insertbackground="#0969da",
    selectbackground="#b3d4ff",
    font=("Courier", 10),
)
    ##tk
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WikiWiki ジェネレーター")
        self.geometry("1200x800")
        self.configure(bg="#f0f0f0")

        self.rows: list[dict] = []
        self.current: int = 0
        self._api_visible = False      # API URL 表示/非表示

        self._build()



    def _build(self):

        top = tk.Frame(self, bg="#f0f0f0")
        top.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(top, text="API URL:", bg="#f0f0f0").pack(side="left")
        link = tk.Label(top, text="SheetDB", fg="#0969da", bg="#f0f0f0",
                        cursor="hand2", font=("Helvetica", 9, "underline"))
        link.pack(side="left", padx=(2, 6))
        link.bind("<Button-1>", lambda _: __import__("webbrowser").open("https://sheetdb.io/"))
        self.api_var = tk.StringVar(value="https://sheetdb.io/api/v1/XXXXXXXX")
        self.api_entry = tk.Entry(top, textvariable=self.api_var, width=40, show="●")
        self.api_entry.pack(side="left", padx=(4, 2))
        self.eye_btn = tk.Button(top, text="表示", width=4,
                                 command=self._toggle_api_visible)
        self.eye_btn.pack(side="left", padx=(0, 6))
        tk.Button(top, text="取得", width=6, command=self._fetch).pack(side="left")
        self.info_lbl = tk.Label(top, text="", bg="#f0f0f0", fg="gray", width=14, anchor="w")
        self.info_lbl.pack(side="left", padx=8)


        pg = tk.Frame(top, bg="#f0f0f0")
        pg.pack(side="right")
        tk.Button(pg, text="◀", width=2, command=self._prev).pack(side="left")
        self.page_lbl = tk.Label(pg, text="－ / －", bg="#f0f0f0", fg="gray", width=8)
        self.page_lbl.pack(side="left", padx=4)
        tk.Button(pg, text="▶", width=2, command=self._next).pack(side="left")


        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        tab_tpl = tk.Frame(nb, bg="#ffffff")
        tab_out = tk.Frame(nb, bg="#ffffff")

        nb.add(tab_tpl, text="  📝 テンプレート  ")
        nb.add(tab_out, text="  ⚙ 生成結果  ")

        self._build_tpl_tab(tab_tpl)
        self._build_out_tab(tab_out)


        bot = tk.Frame(self, bg="#f0f0f0")
        bot.pack(fill="x", padx=10, pady=(0, 8))

        tk.Button(bot, text="テンプレートを保存",
                  command=self._save_template).pack(side="left", padx=(0, 6))
        tk.Button(bot, text="生成結果を保存（現在のページ）",
                  command=lambda: self._save_result(bulk=False)).pack(side="left", padx=(0, 6))
        tk.Button(bot, text="生成結果を一括保存（全ページ）",
                  command=lambda: self._save_result(bulk=True)).pack(side="left", padx=(0, 6))
        tk.Button(bot, text="コピー",
                  command=self._copy).pack(side="right")


    def _build_tpl_tab(self, parent):
        hint = tk.Label(parent,
                        text="  <<ヘッダー名>>  /  <<ヘッダー名|代替文字>>",
                        bg="#ffffff", fg="#888888",
                        font=("Courier", 9), anchor="w")
        hint.pack(fill="x", pady=(4, 0))

        self.tpl = scrolledtext.ScrolledText(
            parent, wrap="word", relief="flat",
            **WIKI_EDITOR,
        )
        self.tpl.pack(fill="both", expand=True, padx=2, pady=2)
        self.tpl.insert("1.0",
            "*<<曲名>>*\n"
            "----\n"
            "|項目|内容|\n"
            "|アーティスト|<<アーティスト>>|\n"
            "|BPM|<<BPM>>|\n"
            "|難易度|<<難易度>>|\n"
            "----\n"
            "<<コメント>>\n"
        )
        self.tpl.tag_configure("tpl_valid",   foreground="#0969da")  # 青: ヘッダー存在
        self.tpl.tag_configure("tpl_invalid", foreground="#ff6b6b")  # 赤: ヘッダー不在
        self.tpl.bind("<KeyRelease>", self._on_tpl_edit)
        self._highlight_template()


    def _build_out_tab(self, parent):
        self.out = scrolledtext.ScrolledText(
            parent, wrap="word", relief="flat",
            state="disabled",
            **OUTPUT_AREA,
        )
        self.out.pack(fill="both", expand=True, padx=2, pady=2)
        self.out.tag_configure("unresolved",
                               foreground="#ff6b6b")


    def _on_tpl_edit(self, _=None):
        self._highlight_template()
        self._render()

    def _toggle_api_visible(self):
        self._api_visible = not self._api_visible
        self.api_entry.config(show="" if self._api_visible else "●")
        self.eye_btn.config(text="隠す" if self._api_visible else "表示")

    def _fetch(self):
        url = self.api_var.get().strip()
        try:
            data = fetch_sheetdb(url)
            if not data:
                raise ValueError("データが空です")
            self.rows = data
            self.current = 0
            self.info_lbl.config(text=f"✓ {len(data)} 行取得", fg="green")
            self._highlight_template()
            self._render()
        except Exception as e:
            self.info_lbl.config(text="✗ 取得失敗", fg="red")
            messagebox.showerror("エラー", str(e))

    def _prev(self):
        if self.current > 0:
            self.current -= 1
            self._render()

    def _next(self):
        if self.current < len(self.rows) - 1:
            self.current += 1
            self._render()

    def _copy(self):
        text = self.out.get("1.0", "end-1c")
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)


    def _highlight_template(self):

        known = set(self.rows[0].keys()) if self.rows else set()

        self.tpl.tag_remove("tpl_valid",   "1.0", "end")
        self.tpl.tag_remove("tpl_invalid", "1.0", "end")

        content = self.tpl.get("1.0", "end-1c")
        for m in re.finditer(r"<<(.+?)>>", content):
            inner = m.group(1)
            key = inner.split("|")[0].strip()
            if known:
                tag = "tpl_valid" if key in known else "tpl_invalid"
            else:
                tag = "tpl_invalid"
            self.tpl.tag_add(tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")


    def _render(self):
        if not self.rows:
            return
        row = self.rows[self.current]
        tpl = self.tpl.get("1.0", "end-1c")
        segments = apply_template_segments(tpl, row)
        self.page_lbl.config(text=f"{self.current + 1} / {len(self.rows)}")

        self.out.config(state="normal")
        self.out.delete("1.0", "end")
        for text, tag in segments:
            if tag == "normal":
                self.out.insert("end", text)
            else:
                self.out.insert("end", text, tag)
        self.out.config(state="disabled")


    def _save_template(self):
        path = filedialog.asksaveasfilename(
            title="テンプレートを保存",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            initialfile="template.txt",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.tpl.get("1.0", "end-1c"))

    def _save_result(self, bulk: bool):
        if not self.rows:
            messagebox.showwarning("データなし", "先にデータを取得してください")
            return
        tpl = self.tpl.get("1.0", "end-1c")

        if not bulk:
            path = filedialog.asksaveasfilename(
                title="生成結果を保存",
                defaultextension=".txt",
                filetypes=[("Text", "*.txt"), ("All", "*.*")],
                initialfile=f"result_{self.current + 1}.txt",
            )
            if not path:
                return
            with open(path, "w", encoding="utf-8") as f:
                f.write(segments_to_text(apply_template_segments(tpl, self.rows[self.current])))
        else:
            # 全ページをフォルダに一括保存
            folder = filedialog.askdirectory(title="保存先フォルダを選択")
            if not folder:
                return
            first_key = list(self.rows[0].keys())[0] if self.rows else None
            for i, row in enumerate(self.rows):
                name = str(row.get(first_key, i + 1)) if first_key else str(i + 1)
                # ファイル名に使えない文字を除去
                safe_name = re.sub(r'[\\/:*?"<>|]', "_", name)
                path = os.path.join(folder, f"{i+1:03}_{safe_name}.txt")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(segments_to_text(apply_template_segments(tpl, row)))
            messagebox.showinfo("完了", f"{len(self.rows)} ファイルを保存しました\n{folder}")


if __name__ == "__main__":
    App().mainloop()
