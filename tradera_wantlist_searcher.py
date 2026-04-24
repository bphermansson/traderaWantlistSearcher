#!/usr/bin/env python3
"""
Tradera Wantlist Searcher
GUI-applikation för Ubuntu som läser en Discogs wantlist (CSV)
och söker efter skivorna på Tradera via web scraping.
Visar separata flikar för HITTADE och SAKNADE skivor.
"""

import csv
import json
import os
import re
import threading
import tkinter as tk
import urllib.parse
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import List, Dict, Optional
import webbrowser

import requests

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wantlist_cache.json")

# ============================================================
# Tradera Web Scraping
# ============================================================
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
})


def _get_attr(item: Dict, attr_name: str) -> str:
    """Hämta första värdet ur attributes-arrayen för givet namn."""
    for attr in item.get("attributes", []):
        if attr.get("name") == attr_name:
            vals = attr.get("values", [])
            if vals:
                return str(vals[0])
    return ""


def tradera_search(query: str, max_results: int = 10) -> List[Dict]:
    """
    Sök på Tradera via web scraping av sökresultatsidan.
    Returnerar lista med dict: {item_id, title, price, url, bids, end_date, format}
    """
    results: List[Dict] = []
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://www.tradera.com/search?q={encoded}"
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()

        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            resp.text,
            re.DOTALL,
        )
        if not m:
            return results

        data = json.loads(m.group(1))
        discover = data.get("props", {}).get("pageProps", {}).get("initialState", {}).get("discover", {})
        items = discover.get("items", [])

        for item in items[:max_results]:
            item_id = item.get("itemId")
            title = item.get("shortDescription", "")
            price = item.get("price")
            item_url = item.get("itemUrl", "")
            bids = item.get("totalBids")
            end_date = item.get("endDate")
            fmt = _get_attr(item, "music_format")

            if not item_id or not title:
                continue

            if not item_url:
                item_url = f"https://www.tradera.com/item/{item_id}"

            results.append({
                "item_id": item_id,
                "title": str(title).strip(),
                "price": price,
                "url": str(item_url).strip(),
                "bids": bids,
                "end_date": end_date,
                "format": fmt,
            })

    except Exception as exc:
        print(f"Sökfel för '{query}': {exc}")

    return results


# ============================================================
# Discogs CSV-parser
# ============================================================
def _extract_format(format_str: str) -> str:
    """Extrahera huvudformat ur Discogs Format-sträng, t.ex. 'LP, Album' → 'LP'."""
    if not format_str:
        return ""
    # Ta första delen före kommatecknet, rensa citat och whitespace
    fmt = format_str.split(",")[0].strip().strip('"').strip()
    return fmt


def parse_discogs_wantlist(filepath: str) -> List[Dict]:
    """Läs Discogs wantlist CSV och returnera lista med dict."""
    items: List[Dict] = []
    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            artist = row.get("Artist", "").strip()
            title = row.get("Title", "").strip()
            fmt_raw = row.get("Format", "").strip()
            if artist and title:
                items.append({
                    "artist": artist,
                    "title": title,
                    "format": _extract_format(fmt_raw),
                    "search_query": f"{artist} {title}",
                })
    return items


# ============================================================
# GUI-Applikation
# ============================================================
class TraderaWantlistApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Tradera Wantlist Sökare")
        self.root.geometry("1200x900")
        self.root.minsize(950, 650)

        self.wantlist_items: List[Dict] = []
        self.search_results: List[Dict] = []
        self.stop_search = False
        self.search_thread: Optional[threading.Thread] = None

        self._build_ui()
        self._setup_autosave()
        self.root.after(100, self._load_cache)

    def _setup_autosave(self):
        """Spara cache när fönstret stängs."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Hantera fönsterstängning – spara cache och avsluta."""
        self._save_cache()
        self.root.destroy()

    def _save_cache(self):
        """Spara wantlist och resultat till JSON-cache."""
        if not self.wantlist_items and not self.search_results:
            return
        try:
            cache = {
                "file_path": self.file_var.get(),
                "wantlist_items": self.wantlist_items,
                "search_results": self.search_results,
            }
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"Kunde inte spara cache: {exc}")

    def _load_cache(self):
        """Ladda wantlist och resultat från JSON-cache vid uppstart."""
        if not os.path.exists(CACHE_FILE):
            return
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)

            wantlist = cache.get("wantlist_items", [])
            results = cache.get("search_results", [])

            if not wantlist:
                return

            if messagebox.askyesno(
                "Återställ session",
                f"Vill du återställa föregående session?\n"
                f"({len(wantlist)} skivor, {sum(1 for r in results if r.get('hits'))} hittade)"
            ):
                self.file_var.set(cache.get("file_path", ""))
                self.wantlist_items = wantlist
                self.search_results = results
                self.preview_var.set(f"Återställde {len(wantlist)} skivor")
                self._restore_results_to_gui()
        except Exception as exc:
            print(f"Kunde inte ladda cache: {exc}")

    def _restore_results_to_gui(self):
        """Återställ tidigare sökresultat till GUI."""
        self.tree_found.delete(*self.tree_found.get_children())
        self.tree_missing.delete(*self.tree_missing.get_children())

        for idx, result in enumerate(self.search_results, 1):
            hits = result.get("hits", [])
            artist_title = f"{result['artist']} – {result['title']}"
            tag = str(idx - 1)

            if hits:
                best = hits[0]
                best_title = best["title"]
                price = f"{best['price']:,} kr".replace(",", " ") if best["price"] else "–"
                self.tree_found.insert(
                    "", tk.END, values=(artist_title, len(hits), best_title, price), tags=(tag,)
                )
            else:
                self.tree_missing.insert(
                    "", tk.END, values=(artist_title,), tags=(tag,)
                )

        total = len(self.search_results)
        found = sum(1 for r in self.search_results if r.get("hits"))
        missing = total - found
        self.status_var.set(f"Återställd: {found}/{total} skivor hade träffar.")
        self.summary_var.set(f"🎯 Hittade: {found}  |  ❌ Saknade: {missing}  |  📀 Totalt: {total}")
        self.notebook.tab(0, text=f"🎯 Hittade skivor ({found})")
        self.notebook.tab(1, text=f"❌ Saknade skivor ({missing})")

    # ---------- UI-bygge ----------
    def _build_ui(self):
        # Övre ram – fil + knappar
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill=tk.X)

        ttk.Label(
            top_frame,
            text="Discogs Wantlist (CSV):",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky=tk.W)
        self.file_var = tk.StringVar()
        ttk.Entry(top_frame, textvariable=self.file_var, width=60).grid(row=0, column=1, padx=5)
        ttk.Button(top_frame, text="Välj fil…", command=self._choose_file).grid(row=0, column=2)
        ttk.Button(top_frame, text="Ladda", command=self._load_wantlist).grid(row=0, column=3, padx=(5, 0))

        self.preview_var = tk.StringVar(value="Inga skivor laddade")
        ttk.Label(top_frame, textvariable=self.preview_var, font=("Segoe UI", 9, "italic")).grid(
            row=1, column=0, columnspan=4, sticky=tk.W, pady=(5, 0)
        )

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=5)

        # Kontrollram
        ctrl_frame = ttk.Frame(self.root, padding=10)
        ctrl_frame.pack(fill=tk.X)

        self.search_btn = ttk.Button(
            ctrl_frame, text="🔍 Sök på Tradera", command=self._start_search
        )
        self.search_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(
            ctrl_frame, text="⏹ Stoppa", command=self._stop_search, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(10, 0))

        self.progress = ttk.Progressbar(
            ctrl_frame, mode="determinate", length=300
        )
        self.progress.pack(side=tk.LEFT, padx=(20, 0))

        self.status_var = tk.StringVar(value="Klar")
        ttk.Label(ctrl_frame, textvariable=self.status_var, font=("Segoe UI", 10)).pack(
            side=tk.LEFT, padx=(15, 0)
        )

        # Summering – hittade / saknade
        self.summary_var = tk.StringVar(value="")
        self.summary_label = ttk.Label(
            ctrl_frame, textvariable=self.summary_var,
            font=("Segoe UI", 10, "bold"), foreground="#2e7d32"
        )
        self.summary_label.pack(side=tk.RIGHT, padx=(0, 10))

        # Notebook med två flikar: Hittade & Saknade
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # --- Flik 1: Hittade skivor ---
        found_frame = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(found_frame, text="🎯 Hittade skivor")

        found_cols = (
            "artist_title", "hits", "best_title", "price"
        )
        self.tree_found = ttk.Treeview(
            found_frame, columns=found_cols, show="headings", selectmode="browse"
        )
        self.tree_found.heading("artist_title", text="Artist – Title")
        self.tree_found.heading("hits", text="Träffar")
        self.tree_found.heading("best_title", text="Bästa träff")
        self.tree_found.heading("price", text="Pris")

        self.tree_found.column("artist_title", width=350, minwidth=150)
        self.tree_found.column("hits", width=60, anchor=tk.CENTER)
        self.tree_found.column("best_title", width=450, minwidth=200)
        self.tree_found.column("price", width=90, anchor=tk.E)

        vsb1 = ttk.Scrollbar(found_frame, orient=tk.VERTICAL, command=self.tree_found.yview)
        hsb1 = ttk.Scrollbar(found_frame, orient=tk.HORIZONTAL, command=self.tree_found.xview)
        self.tree_found.configure(yscrollcommand=vsb1.set, xscrollcommand=hsb1.set)

        self.tree_found.grid(row=0, column=0, sticky="nsew")
        vsb1.grid(row=0, column=1, sticky="ns")
        hsb1.grid(row=1, column=0, sticky="ew")
        found_frame.grid_rowconfigure(0, weight=1)
        found_frame.grid_columnconfigure(0, weight=1)

        self.tree_found.bind("<Double-1>", self._on_found_double_click)
        self.tree_found.bind("<<TreeviewSelect>>", self._on_found_select)

        # --- Flik 2: Saknade skivor ---
        missing_frame = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(missing_frame, text="❌ Saknade skivor")

        missing_cols = ("artist_title",)
        self.tree_missing = ttk.Treeview(
            missing_frame, columns=missing_cols, show="headings", selectmode="browse"
        )
        self.tree_missing.heading("artist_title", text="Artist – Title")
        self.tree_missing.column("artist_title", width=600, minwidth=300)

        vsb2 = ttk.Scrollbar(missing_frame, orient=tk.VERTICAL, command=self.tree_missing.yview)
        hsb2 = ttk.Scrollbar(missing_frame, orient=tk.HORIZONTAL, command=self.tree_missing.xview)
        self.tree_missing.configure(yscrollcommand=vsb2.set, xscrollcommand=hsb2.set)

        self.tree_missing.grid(row=0, column=0, sticky="nsew")
        vsb2.grid(row=0, column=1, sticky="ns")
        hsb2.grid(row=1, column=0, sticky="ew")
        missing_frame.grid_rowconfigure(0, weight=1)
        missing_frame.grid_columnconfigure(0, weight=1)

        self.tree_missing.bind("<<TreeviewSelect>>", self._on_missing_select)

        # Detaljpanel (nedre)
        detail_frame = ttk.LabelFrame(self.root, text="Detaljer", padding=10)
        detail_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)

        self.detail_text = scrolledtext.ScrolledText(
            detail_frame, height=8, wrap=tk.WORD, font=("Consolas", 10)
        )
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        self.detail_text.config(state=tk.DISABLED)

        # Konfigurera länk-taggar i detaljtexten
        self.detail_text.tag_config("link", foreground="blue", underline=True)
        self.detail_text.tag_bind("link", "<Enter>", lambda e: self.detail_text.config(cursor="hand2"))
        self.detail_text.tag_bind("link", "<Leave>", lambda e: self.detail_text.config(cursor=""))

        # Håll reda på unika länk-taggar för rensning
        self._link_tags: List[str] = []

    # ---------- Händelsehanterare ----------
    def _choose_file(self):
        path = filedialog.askopenfilename(
            title="Välj Discogs wantlist CSV",
            filetypes=[("CSV-filer", "*.csv"), ("Alla filer", "*.*")],
        )
        if path:
            self.file_var.set(path)

    def _load_wantlist(self):
        path = self.file_var.get().strip()
        if not path:
            messagebox.showwarning("Ingen fil", "Välj en CSV-fil först.")
            return
        try:
            self.wantlist_items = parse_discogs_wantlist(path)
            count = len(self.wantlist_items)
            self.preview_var.set(f"Laddade {count} skivor")
            self.status_var.set(f"Laddade {count} skivor")
            messagebox.showinfo("Klart", f"Laddade {count} skivor från wantlisten.")
        except Exception as exc:
            messagebox.showerror("Fel", f"Kunde inte läsa filen:\n{exc}")

    def _stop_search(self):
        self.stop_search = True
        self.status_var.set("Stoppar…")

    def _start_search(self):
        if not self.wantlist_items:
            messagebox.showwarning("Tom wantlist", "Ladda en wantlist först.")
            return
        if self.search_thread and self.search_thread.is_alive():
            messagebox.showinfo("Pågår", "En sökning pågår redan.")
            return

        self.stop_search = False
        self.search_results = []
        self.tree_found.delete(*self.tree_found.get_children())
        self.tree_missing.delete(*self.tree_missing.get_children())
        self.search_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress["maximum"] = len(self.wantlist_items)
        self.progress["value"] = 0
        self.summary_var.set("")
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)
        self.detail_text.config(state=tk.DISABLED)

        self.search_thread = threading.Thread(
            target=self._search_worker, daemon=True
        )
        self.search_thread.start()

    def _search_worker(self):
        total = len(self.wantlist_items)
        for idx, item in enumerate(self.wantlist_items, 1):
            if self.stop_search:
                break

            query = item["search_query"]
            self.root.after(
                0,
                lambda q=query, i=idx, t=total: self.status_var.set(
                    f"Söker ({i}/{t}): {q[:45]}…"
                ),
            )

            try:
                hits = tradera_search(query, max_results=10)
            except Exception as exc:
                hits = []
                print(f"Fel vid sökning '{query}': {exc}")

            # Filtrera träffar efter format om format anges i wantlist
            want_fmt = item.get("format", "")
            if want_fmt and hits:
                filtered = [h for h in hits if h.get("format", "").upper() == want_fmt.upper()]
                # Om vi har filtrerade träffar, använd dem; annars behåll alla
                if filtered:
                    hits = filtered

            result = {
                "artist": item["artist"],
                "title": item["title"],
                "format": want_fmt,
                "query": query,
                "hits": hits,
            }
            self.search_results.append(result)

            self.root.after(0, lambda r=result, i=idx: self._insert_result(r, i))
            self.root.after(0, lambda v=idx: self.progress.config(value=v))

        self.root.after(0, self._search_done)

    def _insert_result(self, result: Dict, index: int):
        hits = result["hits"]
        artist_title = f"{result['artist']} – {result['title']}"
        tag = str(index - 1)

        if hits:
            best = hits[0]
            best_title = best["title"]
            price = f"{best['price']:,} kr".replace(",", " ") if best["price"] else "–"

            iid = self.tree_found.insert(
                "", tk.END, values=(artist_title, len(hits), best_title, price)
            )
            self.tree_found.item(iid, tags=(tag,))
        else:
            iid = self.tree_missing.insert(
                "", tk.END, values=(artist_title,)
            )
            self.tree_missing.item(iid, tags=(tag,))

    def _search_done(self):
        self.search_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        total = len(self.search_results)
        found = sum(1 for r in self.search_results if r["hits"])
        missing = total - found

        self.status_var.set(f"Klar! {found}/{total} skivor hade träffar.")
        self.summary_var.set(f"🎯 Hittade: {found}  |  ❌ Saknade: {missing}  |  📀 Totalt: {total}")

        # Uppdatera flik-texter
        self.notebook.tab(0, text=f"🎯 Hittade skivor ({found})")
        self.notebook.tab(1, text=f"❌ Saknade skivor ({missing})")

        messagebox.showinfo(
            "Sökning klar",
            f"{found} av {total} skivor hade träffar på Tradera.\n"
            f"{missing} skivor saknades.",
        )

    def _get_result_by_tag(self, tags) -> Optional[Dict]:
        if not tags:
            return None
        try:
            idx = int(tags[0])
        except ValueError:
            return None
        if 0 <= idx < len(self.search_results):
            return self.search_results[idx]
        return None

    def _show_details(self, result: Dict):
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete("1.0", tk.END)

        # Rensa gamla länk-taggar
        for tag in self._link_tags:
            self.detail_text.tag_delete(tag)
        self._link_tags.clear()

        self.detail_text.insert(
            tk.END, f"🎵 {result['artist']} – {result['title']}\n"
        )
        self.detail_text.insert(tk.END, f"Sökning: {result['query']}\n")

        # YouTube Music-länk
        yt_query = urllib.parse.quote(f"{result['artist']} {result['title']}")
        yt_url = f"https://music.youtube.com/search?q={yt_query}"
        self.detail_text.insert(tk.END, "🎧 ")
        yt_start = self.detail_text.index(tk.INSERT)
        self.detail_text.insert(tk.END, "Lyssna på YouTube Music  |  ")
        yt_end = self.detail_text.index(tk.INSERT)
        yt_tag = "yt_music"
        self._link_tags.append(yt_tag)
        self.detail_text.tag_add(yt_tag, yt_start, yt_end)
        self.detail_text.tag_config(yt_tag, foreground="red", underline=True)
        self.detail_text.tag_bind(
            yt_tag, "<Button-1>",
            lambda e, url=yt_url: webbrowser.open(url)
        )
        self.detail_text.tag_bind(
            yt_tag, "<Enter>",
            lambda e: self.detail_text.config(cursor="hand2")
        )
        self.detail_text.tag_bind(
            yt_tag, "<Leave>",
            lambda e: self.detail_text.config(cursor="")
        )

        # Spotify-länk
        sp_query = urllib.parse.quote(f"{result['artist']} {result['title']}")
        sp_url = f"https://open.spotify.com/search/{sp_query}"
        self.detail_text.insert(tk.END, "🟢 ")
        sp_start = self.detail_text.index(tk.INSERT)
        self.detail_text.insert(tk.END, "Öppna i Spotify\n")
        sp_end = self.detail_text.index(tk.INSERT)
        sp_tag = "spotify"
        self._link_tags.append(sp_tag)
        self.detail_text.tag_add(sp_tag, sp_start, sp_end)
        self.detail_text.tag_config(sp_tag, foreground="#1DB954", underline=True)
        self.detail_text.tag_bind(
            sp_tag, "<Button-1>",
            lambda e, url=sp_url: webbrowser.open(url)
        )
        self.detail_text.tag_bind(
            sp_tag, "<Enter>",
            lambda e: self.detail_text.config(cursor="hand2")
        )
        self.detail_text.tag_bind(
            sp_tag, "<Leave>",
            lambda e: self.detail_text.config(cursor="")
        )

        self.detail_text.insert(tk.END, "-" * 60 + "\n")

        if result["hits"]:
            for rank, h in enumerate(result["hits"], 1):
                fmt = h.get("format", "")
                fmt_str = f" [{fmt}]" if fmt else ""
                self.detail_text.insert(tk.END, f"\n  #{rank} {h['title']}{fmt_str}\n")
                price_str = (
                    f"{h['price']:,} kr".replace(",", " ")
                    if h["price"] is not None
                    else "Pris ej tillgängligt"
                )
                self.detail_text.insert(tk.END, f"    💰 {price_str}\n")
                if h["bids"] is not None:
                    self.detail_text.insert(tk.END, f"    🏷️ {h['bids']} bud\n")

                # Skriv länk-prefix och sedan själva URL:en som en klickbar länk
                self.detail_text.insert(tk.END, "    🔗 ")
                url_start = self.detail_text.index(tk.INSERT)
                self.detail_text.insert(tk.END, f"{h['url']}\n")
                url_end = self.detail_text.index(tk.INSERT)

                # Skapa unik tagg för denna länk
                link_tag = f"link_{rank}"
                self._link_tags.append(link_tag)
                self.detail_text.tag_add(link_tag, url_start, url_end)
                self.detail_text.tag_config(link_tag, foreground="blue", underline=True)
                self.detail_text.tag_bind(
                    link_tag, "<Button-1>",
                    lambda e, url=h["url"]: webbrowser.open(url)
                )
                self.detail_text.tag_bind(
                    link_tag, "<Enter>",
                    lambda e: self.detail_text.config(cursor="hand2")
                )
                self.detail_text.tag_bind(
                    link_tag, "<Leave>",
                    lambda e: self.detail_text.config(cursor="")
                )
        else:
            self.detail_text.insert(tk.END, "\n  ❌ Inga träffar hittades på Tradera.\n")

        self.detail_text.config(state=tk.DISABLED)

    def _on_found_select(self, event=None):
        result = self._get_result_by_tag(self.tree_found.item(self.tree_found.selection()[0], "tags") if self.tree_found.selection() else None)
        if result:
            self._show_details(result)

    def _on_missing_select(self, event=None):
        result = self._get_result_by_tag(self.tree_missing.item(self.tree_missing.selection()[0], "tags") if self.tree_missing.selection() else None)
        if result:
            self._show_details(result)

    def _on_found_double_click(self, event):
        region = self.tree_found.identify("region", event.x, event.y)
        if region != "cell":
            return
        iid = self.tree_found.identify_row(event.y)
        if not iid:
            return
        tags = self.tree_found.item(iid, "tags")
        result = self._get_result_by_tag(tags)
        if result and result["hits"]:
            webbrowser.open(result["hits"][0]["url"])


def main():
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    app = TraderaWantlistApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
