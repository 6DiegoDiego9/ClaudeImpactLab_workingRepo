# -*- coding: utf-8 -*-
"""
local_index.py - Indice locale delle fonti testuali (FAQ e pagine pubbliche)
============================================================================

A runtime e' la fonte PRIMARIA dei prototipi: il WAF del Comune e di YesMilano
blocca i client non-browser, quindi FAQ e pagine sono state salvate una tantum
da build_index.py in data/index/*.json (un file per documento).

Ricerca: BM25 semplice in puro Python (nessuna dipendenza), con
tokenizzazione italiana minima: minuscole, accenti normalizzati, apostrofi
separati, stopword, "stemming" leggerissimo (toglie la vocale finale per
unificare singolare/plurale: stranieri/straniero/straniera -> stranier).
Il titolo/domanda pesa di piu' del corpo del testo.

API:
    search_local(query, top=5, tipo=None) -> [{id, tipo, titolo, estratto, url,
                                               aggiornato_il, recuperato_il, punteggio}]
    get_doc(id) -> dict | None
    get_doc_by_url(url) -> dict | None
    all_docs(tipo=None) -> list[dict]
    set_index_dir(path)
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

_INDEX_DIR: Path | None = None
_CACHE: dict = {"firma": None, "docs": {}, "bm25": None}

# Stopword minime italiane e inglesi (le guide YesMilano sono in inglese).
STOPWORD = set("""
a ad al alla alle allo agli ai all anche che chi ci col come con cosa cui da dal dalla dalle dagli dai dall
de del della delle dello degli dei dell di do e ed era essere gli ha hai hanno ho i il in io la le lo l
loro lui ma mi mia mio ne nei nel nella nelle nello negli nell no noi non o per piu poi puo quale quali
quando quanto quella quelle quello questa queste questo se sei si sia sono su sua sue suo sul sulla sulle
sui sull ti tra tu tua tuo un una uno uni vi voi devo posso come dove ecc
the of and or to in on for with by is are be as at an it its this that from your you can will do does
""".split())

# Espansioni di dominio (query -> termini aggiunti con peso ridotto).
ESPANSIONI = {
    "cie": "carta identita elettronica",
    "identita": "cie",
    "tari": "tassa rifiuti",
    "rifiuti": "tari",
    "iscrizione": "residenza",
    "anagrafica": "residenza",
    "residenza": "iscrizione anagrafica",
    "extra": "extracomunitari",
    "spid": "identita digitale",
    "nido": "nidi primavera",
    "asilo": "nido nidi",
    "permesso": "soggiorno",
    "alloggiativa": "abitativa",
    "alloggio": "abitativa",
}


def set_index_dir(path: str | os.PathLike) -> None:
    """Cambia la cartella dell'indice (default: data/index accanto a questo file
    o env MILANO_INDEX_DIR)."""
    global _INDEX_DIR
    _INDEX_DIR = Path(path)
    _CACHE["firma"] = None


def index_dir() -> Path:
    if _INDEX_DIR is not None:
        return _INDEX_DIR
    env = os.environ.get("MILANO_INDEX_DIR")
    return Path(env) if env else Path(__file__).resolve().parent / "data" / "index"


def normalizza(testo: str) -> str:
    """Minuscole e accenti tolti ('identità' -> 'identita')."""
    t = unicodedata.normalize("NFKD", testo or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower()


def _stem(tok: str) -> str:
    if tok.isdigit() or len(tok) <= 4:
        return tok
    if tok.endswith(("zioni", "zione")):
        return tok[:-1]  # iscrizione/iscrizioni -> iscrizion
    if tok[-1] in "aeiou":
        return tok[:-1]
    if tok.endswith("s") and len(tok) > 5:  # inglese: permits -> permit
        return tok[:-1]
    return tok


def tokenizza(testo: str) -> list[str]:
    """Tokenizzazione minima: normalizza, separa su non-alfanumerici
    (l'apostrofo divide: dall'estero -> dall, estero), toglie stopword, stem."""
    toks = re.split(r"[^a-z0-9]+", normalizza(testo))
    return [_stem(t) for t in toks if t and t not in STOPWORD and len(t) > 1]


def _firma(d: Path) -> tuple:
    try:
        files = sorted(p for p in d.glob("*.json") if not p.name.startswith("_"))
        return (str(d), len(files), max((p.stat().st_mtime for p in files), default=0))
    except OSError:
        return (str(d), 0, 0)


class _BM25:
    def __init__(self, docs: dict[str, dict], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.ids: list[str] = []
        self.tf: list[Counter] = []
        self.len: list[int] = []
        df: Counter = Counter()
        for did, d in docs.items():
            titolo = " ".join(filter(None, [d.get("titolo"), d.get("domanda"), d.get("titolo_breve")]))
            extra = " ".join(d.get("parole_chiave") or []) + " " + (d.get("categoria") or "")
            # Il titolo pesa 3 volte, parole chiave e categoria 1 volta, il corpo 1 volta
            toks = tokenizza(titolo) * 3 + tokenizza(extra) + tokenizza(d.get("testo", ""))
            c = Counter(toks)
            self.ids.append(did)
            self.tf.append(c)
            self.len.append(len(toks))
            df.update(c.keys())
        n = max(len(self.ids), 1)
        self.avgdl = (sum(self.len) / n) if self.len else 1
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, q: dict[str, float]) -> list[tuple[str, float]]:
        out = []
        for i, did in enumerate(self.ids):
            tf, dl, s = self.tf[i], self.len[i], 0.0
            for t, w in q.items():
                f = tf.get(t)
                if f:
                    s += w * self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            if s > 0:
                out.append((did, s))
        out.sort(key=lambda x: -x[1])
        return out


def _carica() -> dict[str, dict]:
    d = index_dir()
    f = _firma(d)
    if _CACHE["firma"] == f:
        return _CACHE["docs"]
    docs = {}
    for p in sorted(d.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if doc.get("id") and doc.get("testo"):
            docs[doc["id"]] = doc
    _CACHE.update(firma=f, docs=docs, bm25=_BM25(docs) if docs else None)
    return docs


def all_docs(tipo: str | None = None) -> list[dict]:
    """Tutti i documenti dell'indice (filtrabili per tipo)."""
    return [d for d in _carica().values() if tipo is None or d.get("tipo") == tipo]


def _query_pesata(query: str) -> dict[str, float]:
    q: dict[str, float] = {}
    for t in tokenizza(query):
        q[t] = q.get(t, 0) + 1.0
    base = list(q)
    for t in base:
        for k, esp in ESPANSIONI.items():
            if _stem(k) == t:
                for e in tokenizza(esp):
                    if e not in q:
                        q[e] = 0.4
    return q


def _snippet(testo: str, termini: set[str], n: int = 400) -> str:
    frasi = re.split(r"(?<=[.!?])\s+|\n", testo or "")
    migliore, best = "", 0
    for fr in frasi:
        s = len(set(tokenizza(fr)) & termini)
        if s > best:
            migliore, best = fr, s
    out = migliore if best else (testo or "")[:n]
    out = re.sub(r"\s+", " ", out).strip()
    return out if len(out) <= n else out[: n - 1] + "…"


def search_local(query: str, top: int = 5, tipo: str | None = None) -> list[dict]:
    """Cerca nell'indice locale con BM25. tipo: 'faq', 'pagina_comune',
    'guida_yesmilano' o None (tutti). Restituisce i migliori 'top' documenti
    con estratto, URL, data di aggiornamento della fonte e data di recupero."""
    docs = _carica()
    bm = _CACHE["bm25"]
    if not bm or not query.strip():
        return []
    q = _query_pesata(query)
    out = []
    for did, s in bm.score(q):
        d = docs[did]
        if tipo and d.get("tipo") != tipo:
            continue
        out.append({"id": did, "tipo": d.get("tipo"), "titolo": d.get("domanda") or d.get("titolo"),
                    "estratto": _snippet(d.get("testo", ""), set(q)), "url": d.get("url"),
                    "aggiornato_il": d.get("aggiornato_il"), "recuperato_il": d.get("recuperato_il"),
                    "punteggio": round(s, 3)})
        if len(out) >= top:
            break
    return out


def get_doc(doc_id: str) -> dict | None:
    """Documento completo dato l'id ('KA-00325', 'comune:...', 'yesmilano:...').
    Gli id KA si accettano anche come 'ka-325'."""
    docs = _carica()
    if doc_id in docs:
        return docs[doc_id]
    m = re.fullmatch(r"(?i)\s*ka-?(\d+)\s*", doc_id or "")
    if m:
        return docs.get(f"KA-{int(m.group(1)):05d}")
    return None


def get_doc_by_url(url: str) -> dict | None:
    """Documento dato l'URL (confronto senza slash finale e senza query)."""
    def norm(u: str) -> str:
        return (u or "").split("?")[0].split("#")[0].rstrip("/").lower()
    target = norm(url)
    for d in _carica().values():
        if norm(d.get("url")) == target:
            return d
    return None


if __name__ == "__main__":  # piccola prova da riga di comando
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    q = " ".join(sys.argv[1:]) or "iscrizione anagrafica dall'estero"
    for r in search_local(q, top=8):
        print(f"{r['punteggio']:7.2f}  {r['id']:<55} {r['titolo'][:70]}")
