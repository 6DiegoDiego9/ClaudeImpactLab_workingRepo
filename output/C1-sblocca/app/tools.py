"""Tools that Claude calls at runtime, plus deterministic helpers (graph, deadlines, citation guard).

Sources:
- prerequisite graph: data/prerequisiti.json (hand-written, verified 3/10/2026)
- FAQ / pages / YesMilano guides: local dated index in data/index (WAF blocks automated access, see README)
- ds549 registry offices: CKAN datastore, LIVE (with file cache fallback)
Dates are computed here (app/core/date_utils.py), never by the model.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
CORE = Path(__file__).resolve().parent / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

import date_utils  # noqa: E402
import ics as ics_mod  # noqa: E402
import local_index  # noqa: E402
import milano_tools as mt  # noqa: E402

local_index.set_index_dir(ROOT / "data" / "index")
mt.configure(cache_dir=ROOT / "data" / "cache")

GRAPH_PATH = ROOT / "data" / "prerequisiti.json"
TODAY_DEFAULT = date(2026, 10, 3)


def load_graph() -> dict:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def today() -> date:
    """Demo date is fixed to the event day so recorded fixtures stay consistent; override with SBLOCCA_TODAY."""
    import os
    v = os.environ.get("SBLOCCA_TODAY", "").strip()
    if v:
        try:
            return date.fromisoformat(v)
        except ValueError:
            pass
    return TODAY_DEFAULT


# ---------------------------------------------------------------------------
# Deterministic deadlines
# ---------------------------------------------------------------------------

def _parse(d: str | None) -> date | None:
    if not d:
        return None
    try:
        return date.fromisoformat(d.strip()[:10])
    except ValueError:
        return None


def compute_deadlines(data_arrivo: str = "", data_inizio_alloggio: str = "", node_ids: list[str] | None = None) -> dict:
    """Compute every deadline of the graph from the case dates (code, not model).

    Returns {nodo_id: {...}} with the date, the rule and, for the residence permit, both readings
    (calendar = prudent, working days = the law)."""
    g = load_graph()
    arr = _parse(data_arrivo)
    alloggio = _parse(data_inizio_alloggio)
    oggi = today()
    out: dict[str, Any] = {}
    for n in g["nodi"]:
        rule = n.get("scadenza")
        if not rule or (node_ids and n["id"] not in node_ids):
            continue
        start = arr if rule["da"] == "data_arrivo" else (alloggio or arr)
        start_label = rule["da"] if (rule["da"] == "data_arrivo" or alloggio) else "data_arrivo (data alloggio non nota)"
        if start is None:
            out[n["id"]] = {"calcolabile": False, "motivo": f"Manca la data di partenza ({rule['da']}).",
                            "regola": f"{rule['giorni']} giorni {rule['tipo']} da {rule['da']} ({rule['fonte']})"}
            continue
        main = date_utils.scadenza(start, rule["giorni"], rule["tipo"], milano=True, oggi=oggi)
        entry = {
            "calcolabile": True,
            "da": start_label,
            "inizio": start.isoformat(),
            "giorni": rule["giorni"],
            "tipo": rule["tipo"],
            "data": main["scadenza"]["data"],
            "data_estesa": main["scadenza"]["data_estesa"],
            "giorni_rimanenti": main.get("giorni_rimanenti"),
            "scaduta": (main.get("giorni_rimanenti") or 0) < 0,
            "regola": main["regola"],
            "fonte": rule["fonte"],
            "nota": rule.get("nota", ""),
            "prorogata": main.get("prorogata"),
        }
        if rule["tipo"] == "lavorativi":
            cal = date_utils.scadenza(start, rule["giorni"], "calendario", milano=True, oggi=oggi)
            entry["data_prudente"] = cal["scadenza"]["data"]
            entry["data_prudente_estesa"] = cal["scadenza"]["data_estesa"]
            entry["nota_prudente"] = (f"Se si contano {rule['giorni']} giorni di calendario (come semplifica Poste) "
                                      f"la data e' {cal['scadenza']['data_estesa']}: e' la scelta prudente.")
        out[n["id"]] = entry
    return {"oggi": oggi.isoformat(), "oggi_esteso": date_utils.data_estesa(oggi), "scadenze": out,
            "nota": "Date calcolate dal codice (date_utils.py): giorno iniziale escluso; lavorativi senza sabati, domeniche, festivi nazionali e 7 dicembre."}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_get_prerequisite_graph(inp: dict) -> dict:
    g = load_graph()
    return {"grafo": g, "oggi": today().isoformat(),
            "nota": "Grafo verificato il 3/10/2026. Decidi tu quali nodi valgono per il caso, in che ordine e cosa e' fattibile oggi."}


def tool_search_comune_faq(inp: dict) -> dict:
    tipo = inp.get("tipo") or "tutti"
    res = mt.search_fonti(inp["query"], top=6, tipo=None if tipo == "tutti" else tipo)
    return {"risultati": res, "fonte": "indice locale datato (raccolto il 3/10/2026)",
            "nota": "Cita id/KA, url e aggiornato_il. Le guide YesMilano non hanno data di aggiornamento: usa la data di recupero."}


def tool_get_faq_article(inp: dict) -> dict:
    d = mt.get_faq_article(inp["ka"])
    if d is None:
        raise LookupError(f"FAQ {inp['ka']} non presente nell'indice locale (raccolto il 3/10/2026).")
    d = dict(d)
    d.pop("link_servizio", None)
    return d


def tool_get_page(inp: dict) -> dict:
    key = (inp.get("id_o_url") or "").strip()
    d = local_index.get_doc(key) or local_index.get_doc_by_url(key)
    if d is None:
        raise LookupError(f"Pagina '{key}' non trovata nell'indice locale. Usa search_comune_faq per trovare l'id.")
    testo = d.get("testo") or ""
    return {"id": d.get("id"), "tipo": d.get("tipo"), "titolo": d.get("titolo"), "url": d.get("url"),
            "aggiornato_il": d.get("aggiornato_il"), "recuperato_il": d.get("recuperato_il"),
            "testo": testo[:9000], "link": (d.get("link") or [])[:25],
            "nota": "Copia dell'indice locale; la pagina pubblica e' la fonte di verita'."}


def tool_sedi_anagrafiche(inp: dict) -> dict:
    res = mt.sedi_anagrafiche()
    filtro = (inp.get("municipio") or "").strip().lower()
    if filtro:
        num = "".join(ch for ch in filtro if ch.isdigit())
        sedi = [s for s in res["sedi"] if (num and (s.get("municipio") or "").strip().lower().endswith(" " + num))
                or (not num and filtro in json.dumps(s, ensure_ascii=False).lower())]
        if sedi:
            res = {**res, "sedi": sedi}
    res["dataset"] = "ds549-sedi-dei-servizi-anagrafici (aggiornato al 28/01/2026)"
    return res


def tool_calcola_scadenze(inp: dict) -> dict:
    return compute_deadlines(inp.get("data_arrivo", ""), inp.get("data_inizio_alloggio", ""))


def _schema(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


TOOL_DEFS: list[dict] = [
    {"name": "get_prerequisite_graph", "strict": True,
     "description": ("Returns the verified prerequisite graph (data/prerequisiti.json): nodes with requires, si_applica_a, "
                     "deadline rule, richiede_spid, official no-SPID channels and dated sources; plus the list of VERIFIED "
                     "source conflicts and of things that are NOT conflicts. Call it once at the start of every case."),
     "input_schema": _schema({})},
    {"name": "search_comune_faq", "strict": True,
     "description": ("Search the dated local index of official sources: Comune di Milano support FAQs (KA codes), "
                     "comune.milano.it service pages and YesMilano guides (English). Write the query IN ITALIAN with "
                     "office words (e.g. 'stato pratica residenza senza SPID', 'dichiarazione TARI senza SPID')."),
     "input_schema": _schema({"query": {"type": "string", "description": "Query in Italian"},
                              "tipo": {"type": "string", "enum": ["tutti", "faq", "pagina_comune", "guida_yesmilano"]}})},
    {"name": "get_faq_article", "strict": True,
     "description": "Full text of one official FAQ by KA code (e.g. 'KA-00325'), with 'Ultimo aggiornamento' date and URL.",
     "input_schema": _schema({"ka": {"type": "string"}})},
    {"name": "get_page", "strict": True,
     "description": ("Full text of a comune.milano.it service page or YesMilano guide from the local index, by id "
                     "(e.g. 'comune:welfare/milano-welcome-center') or by public URL."),
     "input_schema": _schema({"id_o_url": {"type": "string"}})},
    {"name": "sedi_anagrafiche", "strict": True,
     "description": ("LIVE open data ds549: registry offices of the Comune (address, hours, booking notes). "
                     "Optional filter by municipio number (e.g. '2'); empty string for all."),
     "input_schema": _schema({"municipio": {"type": "string"}})},
    {"name": "calcola_scadenze", "strict": True,
     "description": ("Deterministic deadline calculator (code, not model). Pass ISO dates (YYYY-MM-DD) or empty strings. "
                     "Returns every graph deadline with date, remaining days and rule. Use these dates, never compute dates yourself."),
     "input_schema": _schema({"data_arrivo": {"type": "string"}, "data_inizio_alloggio": {"type": "string"}})},
]

TOOL_IMPLS: dict[str, Callable[[dict], Any]] = {
    "get_prerequisite_graph": tool_get_prerequisite_graph,
    "search_comune_faq": tool_search_comune_faq,
    "get_faq_article": tool_get_faq_article,
    "get_page": tool_get_page,
    "sedi_anagrafiche": tool_sedi_anagrafiche,
    "calcola_scadenze": tool_calcola_scadenze,
}


# ---------------------------------------------------------------------------
# Citation guard
# ---------------------------------------------------------------------------

def known_sources() -> tuple[set[str], set[str]]:
    """KA codes and URLs that exist in the graph or in the local index (what a tool could have returned)."""
    kas: set[str] = set()
    urls: set[str] = set()
    g = load_graph()
    blob = json.dumps(g, ensure_ascii=False)
    import re
    kas.update(re.findall(r"KA-\d{5}", blob))
    urls.update(re.findall(r"https?://[^\s\"']+", blob))
    for d in local_index.all_docs():
        if d.get("url"):
            urls.add(d["url"])
        if str(d.get("id", "")).startswith("KA-"):
            kas.add(d["id"])
    urls.add("https://dati.comune.milano.it/dataset/ds549-sedi-dei-servizi-anagrafici")
    return kas, urls


def _norm_url(u: str) -> str:
    return (u or "").strip().rstrip("/").replace("http://", "https://")


def check_citations(nodi: list[dict], seen_text: str) -> list[dict]:
    """Mark each cited source as verified only if it appeared in a tool result of this session
    (seen_text = concatenated tool outputs). Unverified citations are flagged, not hidden."""
    seen = seen_text.replace("http://", "https://")
    for n in nodi:
        for f in n.get("fonti", []):
            ka = (f.get("ka") or "").strip().upper()
            url = _norm_url(f.get("url", ""))
            ok = bool((ka and ka in seen) or (url and url in seen) or (url and url.split("?")[0] in seen))
            f["verificata"] = ok
    return nodi


def ics_for(deadlines: dict, titles: dict[str, str], lang_note: str = "") -> bytes:
    events = []
    for nid, d in (deadlines.get("scadenze") or {}).items():
        if not d.get("calcolabile"):
            continue
        events.append({"titolo": f"Scadenza: {titles.get(nid, nid)}", "data": d["data"],
                       "descrizione": f"{d['regola']} Fonte: {d['fonte']}. {d.get('nota', '')} "
                                      "Promemoria generato da Sblocca (prototipo non ufficiale): verifica con il Comune.",
                       "url": ""})
        if d.get("data_prudente") and d["data_prudente"] != d["data"]:
            events.append({"titolo": f"Data prudente: {titles.get(nid, nid)}", "data": d["data_prudente"],
                           "descrizione": d.get("nota_prudente", ""), "url": ""})
    return ics_mod.ics_bytes(events, nome_calendario="Sblocca - scadenze (prototipo)", allarme_minuti=1440)
