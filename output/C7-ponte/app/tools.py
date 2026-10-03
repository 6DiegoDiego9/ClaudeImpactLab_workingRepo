# -*- coding: utf-8 -*-
"""Tools that Claude calls at runtime to ground the case card in City of Milan sources.

Text sources (FAQ of the Centro Supporto, comune.milano.it service pages) come from the local
index saved on 3/10/2026, because the City's WAF answers 403 to automated clients. Open data
(dati.comune.milano.it CKAN) is queried live, with a file cache as fallback.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from . import config
from .config import local_index, mt

DS549 = "ds549"
DS550 = "ds550"
# Read-only allowlist of datastore resources Claude may query.
DATASTORE_ALLOWLIST = {
    DS549: mt.DS549_RESOURCE_ID if hasattr(mt, "DS549_RESOURCE_ID") else "48b24517-765e-4f6f-8b30-9094a212eb85",
    DS550: "4f541e96-b984-469e-91b3-0291031cad44",
}

_EXTERNAL: dict[str, dict] | None = None


def external_sources() -> dict[str, dict]:
    global _EXTERNAL
    if _EXTERNAL is None:
        raw = json.loads((config.DATA_DIR / "fonti_esterne.json").read_text(encoding="utf-8"))
        _EXTERNAL = {f["id"]: f for f in raw["fonti"]}
    return _EXTERNAL


def _schema(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


TOOL_DEFS: list[dict] = [
    {
        "name": "search_comune_faq",
        "strict": True,
        "description": (
            "Cerca nelle fonti ufficiali del Comune di Milano salvate il 3/10/2026 (FAQ KA del Centro Supporto, "
            "pagine di servizio di comune.milano.it, guide YesMilano). Scrivi la query IN ITALIANO con parole "
            "da sportello (es. 'residenza permesso di soggiorno in rinnovo', 'prima carta d'identita extra UE', "
            "'idoneita abitativa documenti', 'Milano Welcome Center orari'). Restituisce id, titolo, estratto, "
            "url, data di aggiornamento della fonte (aggiornato_il) e data di recupero. Fai piu' ricerche in "
            "parallelo nello stesso turno quando le procedure sono piu' di una."),
        "input_schema": _schema({
            "query": {"type": "string", "description": "Domanda riformulata in italiano"},
            "tipo": {"type": "string", "enum": ["tutti", "faq", "pagina_comune", "guida_yesmilano"],
                     "description": "Filtra per tipo di fonte; 'tutti' per cercare ovunque"},
        }),
    },
    {
        "name": "get_faq_article",
        "strict": True,
        "description": (
            "Legge il testo completo di una FAQ (codice KA, es. 'KA-00370') o di un documento dell'indice "
            "(id restituito da search_comune_faq, es. 'comune:anagrafe/...'). Usalo prima di citare una regola: "
            "la scheda deve riportare cio' che la fonte dice davvero, con la sua data di aggiornamento."),
        "input_schema": _schema({"id": {"type": "string", "description": "Codice KA o id del documento"}}),
    },
    {
        "name": "get_fonte_esterna",
        "strict": True,
        "description": (
            "Legge una fonte non comunale verificata il 3/10/2026: 'dpr394-art45' (Normattiva: iscrizione "
            "scolastica dei minori stranieri in qualunque periodo dell'anno), 'prefettura-ricongiungimento' "
            "(nulla osta al ricongiungimento online sul portale del Ministero dell'Interno con SPID, con "
            "l'assistenza di sindacati e associazioni), 'allegato-a-extraue' (nota di lettura dell'Allegato A del "
            "Comune: documenti per la residenza dall'estero, asterischi di obbligatorieta', codice fiscale)."),
        "input_schema": _schema({"id": {"type": "string",
                                        "enum": ["dpr394-art45", "prefettura-ricongiungimento", "allegato-a-extraue"]}}),
    },
    {
        "name": "sedi_anagrafiche",
        "strict": True,
        "description": (
            "Sedi dei servizi anagrafici del Comune (open data ds549, dal vivo da dati.comune.milano.it): "
            "municipio, indirizzo, orari, note di accesso. Il campo orari e' testo libero."),
        "input_schema": _schema({}),
    },
    {
        "name": "ckan_dataset_meta",
        "strict": True,
        "description": (
            "Metadati di un dataset del portale open data del Comune (dal vivo): titolo, periodo coperto "
            "(temporal_start/temporal_end), frequenza di aggiornamento e un avviso di freschezza se il dato e' "
            "vecchio o fermo. Usalo per ds550 (patronati e sindacati) e ds549 (sedi anagrafiche) prima di "
            "proporli: se c'e' avviso_freschezza scrivi 'verifica prima di andare'."),
        "input_schema": _schema({"slug": {"type": "string", "description": "Es. 'ds550' o 'ds549'"}}),
    },
    {
        "name": "ckan_datastore_search",
        "strict": True,
        "description": (
            "Cerca righe in un dataset aperto del Comune (dal vivo, sola lettura). dataset='ds550' per le sedi "
            "di patronati e sindacati (dato del 2018: segnalalo sempre), dataset='ds549' per le sedi anagrafiche. "
            "q e' un testo libero (es. 'CGIL', 'ACLI', 'Padova'); municipio filtra per numero di municipio "
            "(1-9), 0 per non filtrare. Restituisce al massimo 8 righe."),
        "input_schema": _schema({
            "dataset": {"type": "string", "enum": [DS550, DS549]},
            "q": {"type": "string", "description": "Testo libero, stringa vuota per nessun filtro"},
            "municipio": {"type": "integer", "description": "Numero del municipio 1-9, oppure 0"},
        }),
    },
]


def _search(inp: dict) -> list[dict]:
    tipo = inp.get("tipo") or "tutti"
    res = mt.search_fonti(inp["query"], top=6, tipo=None if tipo == "tutti" else tipo)
    return [{k: r.get(k) for k in ("id", "tipo", "titolo", "estratto", "url", "aggiornato_il", "recuperato_il")}
            for r in res]


def _get_article(inp: dict) -> dict:
    ident = (inp.get("id") or "").strip()
    d = None
    if ident.upper().startswith("KA"):
        d = mt.get_faq_article(ident)
        if d is not None:
            return {"id": d.get("ka"), "tipo": "faq", "titolo": d.get("domanda"), "testo": d.get("risposta"),
                    "url": d.get("url"), "aggiornato_il": d.get("aggiornato_il"),
                    "recuperato_il": d.get("recuperato_il"), "categoria": d.get("categoria"),
                    "link_servizio": d.get("link_servizio")}
    d = local_index.get_doc(ident)
    if d is None:
        raise LookupError(f"Documento {ident} non presente nell'indice locale del 3/10/2026: "
                          "non citarlo come fonte e segnalalo come 'da verificare'.")
    return {k: d.get(k) for k in ("id", "tipo", "titolo", "testo", "url", "aggiornato_il", "recuperato_il")}


def _external(inp: dict) -> dict:
    f = external_sources().get(inp["id"])
    if f is None:
        raise LookupError(f"Fonte esterna {inp['id']} sconosciuta.")
    return f


def _sedi(_: dict) -> dict:
    out = mt.sedi_anagrafiche()
    out["dataset"] = "ds549-sedi-dei-servizi-anagrafici"
    return out


def _meta(inp: dict) -> dict:
    m = mt.ckan_dataset_meta(inp["slug"])
    keep = ("slug", "identificativo", "titolo", "temporal_start", "temporal_end", "frequency", "modified",
            "avviso_freschezza", "url_pagina", "recuperato_il", "da_cache")
    out = {k: m.get(k) for k in keep}
    out["descrizione"] = (m.get("descrizione") or "")[:400]
    return out


_DS550_FIELDS = ("Patronati", "Indirizzo", "tel", "indirizzo web", "CAP", "MUNICIPIO", "NIL")


def _datastore(inp: dict) -> dict:
    ds = inp["dataset"]
    rid = DATASTORE_ALLOWLIST[ds]
    filters = {}
    mun = int(inp.get("municipio") or 0)
    if ds == DS550 and 1 <= mun <= 9:
        filters["MUNICIPIO"] = mun
    q = (inp.get("q") or "").strip() or None
    r = mt.ckan_datastore_search(rid, filters=filters or None, q=q, limit=8, allowlist=list(DATASTORE_ALLOWLIST.values()))
    rows = r.get("righe") or []
    if ds == DS550:
        rows = [{k: row.get(k) for k in _DS550_FIELDS} for row in rows]
        avviso = ("ds550 copre il 10-11/03/2018 (frequenza NEVER, risorse modificate il 25/11/2020): "
                  "indirizzi e telefoni possono essere cambiati, verifica prima di andare.")
    else:
        rows = [{k: v for k, v in row.items() if k not in ("_id", "Location")} for row in rows]
        avviso = None
    return {"dataset": ds, "resource_id": rid, "righe": rows, "totale": r.get("totale"),
            "recuperato_il": r.get("recuperato_il"), "da_cache": r.get("da_cache"),
            "avviso_freschezza": avviso, "avviso_rete": r.get("avviso")}


TOOL_IMPLS: dict[str, Callable[[dict], Any]] = {
    "search_comune_faq": _search,
    "get_faq_article": _get_article,
    "get_fonte_esterna": _external,
    "sedi_anagrafiche": _sedi,
    "ckan_dataset_meta": _meta,
    "ckan_datastore_search": _datastore,
}

# Short Italian labels shown in the UI while Claude works.
TOOL_LABELS = {
    "search_comune_faq": "Cerco nelle FAQ e pagine del Comune",
    "get_faq_article": "Leggo la fonte",
    "get_fonte_esterna": "Leggo la fonte esterna",
    "sedi_anagrafiche": "Consulto le sedi anagrafiche (ds549, dal vivo)",
    "ckan_dataset_meta": "Controllo la freschezza del dataset",
    "ckan_datastore_search": "Cerco nel dataset aperto",
}
