# -*- coding: utf-8 -*-
"""Tools that Claude can call while building the personal checklist.

Every tool is read-only: nothing is ever written to City systems.
All tool definitions are strict (additionalProperties: false, all params required).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CORE = Path(__file__).resolve().parent / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import date_utils  # noqa: E402  (shared core, Italian comments kept as-is)
import local_index  # noqa: E402
import milano_tools as mt  # noqa: E402

DATA = ROOT / "data"
FIXTURES = ROOT / "fixtures"

# Point the shared core at this project's index and cache (not the scratch folder).
mt.configure(cache_dir=DATA / "cache", index_dir=DATA / "index")

# Languages offered in the UI: code -> (name in Italian, endonym, BCP-47 for speech)
LINGUE: dict[str, dict[str, str]] = {
    "tl": {"nome_it": "tagalog", "nome": "Tagalog", "bcp47": "fil-PH", "dir": "ltr"},
    "ar": {"nome_it": "arabo", "nome": "العربية", "bcp47": "ar-EG", "dir": "rtl"},
    "en": {"nome_it": "inglese", "nome": "English", "bcp47": "en-GB", "dir": "ltr"},
    "zh": {"nome_it": "cinese", "nome": "中文", "bcp47": "zh-CN", "dir": "ltr"},
    "es": {"nome_it": "spagnolo", "nome": "Español", "bcp47": "es-ES", "dir": "ltr"},
    "si": {"nome_it": "singalese", "nome": "සිංහල", "bcp47": "si-LK", "dir": "ltr"},
    "bn": {"nome_it": "bengalese", "nome": "বাংলা", "bcp47": "bn-BD", "dir": "ltr"},
    "uk": {"nome_it": "ucraino", "nome": "Українська", "bcp47": "uk-UA", "dir": "ltr"},
}


@lru_cache(maxsize=None)
def _load(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def oggi() -> date:
    """Today's date (overridable with env LEGGIMI_OGGI=YYYY-MM-DD for reproducible demos)."""
    import os
    v = os.environ.get("LEGGIMI_OGGI", "").strip()
    return date.fromisoformat(v) if v else date.today()


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def get_percorso(caso_allegato_a: int) -> dict:
    """Curated path graph (with sources) plus the Allegato A checklist for one case (0 = all cases)."""
    perc = _load("percorso.json")
    all_a = _load("allegato_a_extraue.json")
    casi = all_a["casi"] if caso_allegato_a not in (1, 2, 3, 4) else [c for c in all_a["casi"] if c["caso"] == caso_allegato_a]
    return {"percorso": perc, "allegato_a": {k: all_a[k] for k in ("titolo", "url", "recuperato_il", "nota_recupero")},
            "casi_allegato_a": casi}


def search_comune_faq(query_it: str) -> dict:
    """Search the City's FAQ (local index saved 3/10/2026). Query must be Italian."""
    risultati = mt.search_comune_faq(query_it, top=5)
    pagine = mt.search_fonti(query_it, top=3, tipo="pagina_comune")
    return {"query_it": query_it, "faq": risultati, "pagine_comune": pagine,
            "nota": "Indice locale delle FAQ e pagine pubbliche del Comune, recuperate il 3/10/2026 "
                    "(il WAF del Comune blocca i client automatici: vedi README)."}


def leggi_faq(ka: str) -> dict:
    d = mt.get_faq_article(ka)
    if d is None:
        raise LookupError(f"FAQ {ka} non presente nell'indice locale.")
    return {k: d.get(k) for k in ("ka", "domanda", "risposta", "aggiornato_il", "recuperato_il", "url", "categoria")}


def leggi_pagina(id: str) -> dict:  # noqa: A002 - name matches the tool schema
    d = local_index.get_doc(id)
    if d is None:
        raise LookupError(f"Documento {id} non trovato nell'indice locale.")
    return {k: d.get(k) for k in ("id", "tipo", "titolo", "testo", "url", "aggiornato_il", "recuperato_il")}


def calcola_scadenza(data_inizio: str, giorni: int, tipo: str) -> dict:
    """Deterministic deadline (calendar or working days, Milan holidays)."""
    inizio = date.fromisoformat(data_inizio)
    return date_utils.scadenza(inizio, int(giorni), tipo, milano=True, oggi=oggi())


def sedi_anagrafiche() -> dict:
    """ds549 registry offices (live CKAN with cache fallback, then the fixture captured today)."""
    try:
        r = mt.sedi_anagrafiche()
    except Exception as e:  # noqa: BLE001 - fall back to the fixture captured live on 3/10/2026
        fx = json.loads((FIXTURES / "sedi_anagrafiche_ds549.json").read_text(encoding="utf-8"))
        r = {"sedi": fx["sedi"], "fonte": "https://dati.comune.milano.it/dataset/ds549-sedi-dei-servizi-anagrafici",
             "recuperato_il": fx.get("catturato_il"), "da_cache": True, "avviso": f"CKAN non raggiungibile ({e})"}
    sedi = [{k: s.get(k) for k in ("municipio", "indirizzo", "orari", "note", "nil")} for s in r["sedi"]]
    return {"sedi": sedi, "fonte": r["fonte"], "periodo": "risorse aggiornate il 28/01/2026",
            "recuperato_il": r.get("recuperato_il"), "da_cache": r.get("da_cache"), "avviso": r.get("avviso"),
            "uso": "Le sedi anagrafiche lavorano su appuntamento e servono per i PASSI SUCCESSIVI (CIE, certificati). "
                   "NON per la domanda di residenza dall'estero, che si fa solo online (KA-00330).",
            "incoerenza": _load("percorso.json")["conflitti_tra_fonti"][0]["dettaglio"]}


def contatti_aiuto() -> dict:
    return _load("aiuto_persone.json")


def glossario(termine: str) -> dict:
    g = _load("glossario.json")
    t = (termine or "").strip().lower()
    trovati = [x for x in g["termini"] if t and (t in x["termine"].lower() or x["termine"].lower() in t)]
    return {"termini": trovati or g["termini"], "nota": g["_descrizione"]}


def confronto_ricerca_comune(lingua: str) -> dict:
    """What the City's own FAQ search returned for a question in the user's language (captured live 3/10/2026)."""
    return confronto_per_lingua(lingua)


def confronto_per_lingua(lingua: str) -> dict:
    fx = json.loads((FIXTURES / "ricerca_comune_confronto.json").read_text(encoding="utf-8"))
    chiave = {"tl": "residenza_tl", "ar": "residenza_ar", "en": "residenza_en"}.get(lingua)
    base = {"catturato_il": fx["catturato_il"], "endpoint": fx["endpoint"], "nota": fx["nota"],
            "riferimento_it": _sintesi_cattura(fx["risultati"]["residenza_it"])}
    if not chiave:
        return {**base, "disponibile": False,
                "messaggio": f"Nessuna cattura della ricerca del Comune in {LINGUE.get(lingua, {}).get('nome_it', lingua)} "
                             "il 3/10/2026: confronto non disponibile per questa lingua."}
    return {**base, "disponibile": True, "cattura": _sintesi_cattura(fx["risultati"][chiave])}


def _sintesi_cattura(r: dict) -> dict:
    return {"domanda": r["domanda"], "lingua": r["lingua"], "ka_attesi": r["ka_attesi"],
            "trovato_atteso": r["trovato_atteso"], "posizione_atteso": r["posizione_atteso"],
            "risultati": [{"ka": x["ka"], "domanda": x["domanda"], "url": x["url"]} for x in r["risultati"]]}


# ---------------------------------------------------------------------------
# Strict tool definitions for Claude
# ---------------------------------------------------------------------------

def _schema(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


TOOL_DEFS: list[dict] = [
    {"name": "get_percorso", "strict": True,
     "description": ("Restituisce il percorso curato dei primi passi (ingresso, Sportello Unico e codice fiscale, kit "
                     "postale, residenza online, stato pratica, TARI, CIE, SPID, SSN da verificare) con fonti e date, "
                     "e la lista documenti dell'Allegato A per il caso indicato (1 permesso valido, 2 in rinnovo, "
                     "3 in attesa del primo permesso per lavoro subordinato, 4 ricongiungimento; 0 = tutti i casi). "
                     "Chiamalo SEMPRE prima di decidere il prossimo passo."),
     "input_schema": _schema({"caso_allegato_a": {"type": "integer", "enum": [0, 1, 2, 3, 4]}})},
    {"name": "search_comune_faq", "strict": True,
     "description": ("Cerca nelle FAQ ufficiali del Centro Supporto del Comune di Milano (e nelle pagine di servizio) "
                     "salvate il 3/10/2026. Scrivi la query SEMPRE IN ITALIANO con parole da sportello, anche se la "
                     "persona scrive in un'altra lingua (es. 'residenza stranieri provenienti dall'estero', "
                     "'documenti residenza in attesa del permesso di soggiorno'). Ogni risultato ha KA, url e data: "
                     "cita quelli pertinenti e scarta gli altri dicendo perche'."),
     "input_schema": _schema({"query_it": {"type": "string", "description": "Domanda riformulata in italiano"}})},
    {"name": "leggi_faq", "strict": True,
     "description": "Testo completo e data di aggiornamento di una FAQ del Comune dato il codice KA (es. 'KA-00534').",
     "input_schema": _schema({"ka": {"type": "string"}})},
    {"name": "leggi_pagina", "strict": True,
     "description": "Testo completo di una pagina di servizio del Comune dall'indice locale, dato il suo id (es. 'comune:anagrafe/cambio-di-residenza-per-persone-straniere-provenienti-dall-estero').",
     "input_schema": _schema({"id": {"type": "string"}})},
    {"name": "calcola_scadenza", "strict": True,
     "description": ("Calcola in modo deterministico una scadenza: data di inizio (YYYY-MM-DD), numero di giorni e tipo "
                     "('calendario' o 'lavorativi', festivi nazionali e Sant'Ambrogio esclusi). Usalo per ogni data: "
                     "non calcolare le date a mente."),
     "input_schema": _schema({"data_inizio": {"type": "string", "description": "YYYY-MM-DD"},
                              "giorni": {"type": "integer"},
                              "tipo": {"type": "string", "enum": ["calendario", "lavorativi"]}})},
    {"name": "sedi_anagrafiche", "strict": True,
     "description": ("Sedi dei servizi anagrafici (open data ds549, dal vivo con cache): indirizzo, orari, note "
                     "d'ingresso. Servono per i passi successivi su appuntamento, NON per la domanda di residenza "
                     "dall'estero."),
     "input_schema": _schema({})},
    {"name": "contatti_aiuto", "strict": True,
     "description": "Canali umani: Milano Welcome Center (indirizzo, orari, email) e Contact Center 020202, con fonte.",
     "input_schema": _schema({})},
    {"name": "glossario", "strict": True,
     "description": ("Glossario dei termini a rischio e dei falsi amici (es. 'attestazione di soggiorno' tradotta dal "
                     "sito come 'Residence permit'). Passa il termine o '' per averli tutti."),
     "input_schema": _schema({"termine": {"type": "string"}})},
    {"name": "confronto_ricerca_comune", "strict": True,
     "description": ("Mostra cosa ha restituito la ricerca FAQ del sito del Comune per una domanda sulla residenza "
                     "scritta nella lingua della persona (catturata dal vivo il 3/10/2026). Serve a spiegare perche' "
                     "Leggimi riformula in italiano."),
     "input_schema": _schema({"lingua": {"type": "string", "enum": list(LINGUE)}})},
]

TOOL_IMPLS: dict[str, Callable[[dict], Any]] = {
    "get_percorso": lambda i: get_percorso(int(i.get("caso_allegato_a", 0))),
    "search_comune_faq": lambda i: search_comune_faq(i["query_it"]),
    "leggi_faq": lambda i: leggi_faq(i["ka"]),
    "leggi_pagina": lambda i: leggi_pagina(i["id"]),
    "calcola_scadenza": lambda i: calcola_scadenza(i["data_inizio"], i["giorni"], i["tipo"]),
    "sedi_anagrafiche": lambda i: sedi_anagrafiche(),
    "contatti_aiuto": lambda i: contatti_aiuto(),
    "glossario": lambda i: glossario(i.get("termine", "")),
    "confronto_ricerca_comune": lambda i: confronto_ricerca_comune(i["lingua"]),
}
