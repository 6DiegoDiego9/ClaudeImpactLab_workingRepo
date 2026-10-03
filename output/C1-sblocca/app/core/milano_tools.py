# -*- coding: utf-8 -*-
"""
milano_tools.py - Strumenti sulle fonti pubbliche del Comune di Milano
=======================================================================

Nucleo condiviso dei prototipi Claude Impact Lab Milano (Track 01, accoglienza
dei nuovi arrivati). Verificato dal vivo il 03/10/2026.

Architettura delle fonti (vedi README_CORE.md):

* FAQ del Centro Supporto e pagine di servizio (comune.milano.it,
  servizicrm.comune.milano.it, studyandwork.yesmilano.it): il WAF (Azure
  Application Gateway) risponde 403 ai client non-browser. A RUNTIME la fonte
  primaria e' quindi l'INDICE LOCALE (data/index/*.json, costruito una tantum
  da build_index.py). La ricerca live del Comune resta opzionale (LIVE_FAQ=1).
* CKAN (dati.comune.milano.it) e SPARQL (virtuoso-prod.comune.milano.it)
  rispondono senza problemi: si interrogano dal vivo, con cache su file e
  fallback alla cache quando la rete fallisce.

Configurazione (variabili d'ambiente o configure()):

* MILANO_CACHE_DIR   cartella della cache (default: <cwd>/data/cache)
* MILANO_INDEX_DIR   cartella dell'indice locale (default: accanto a local_index.py)
* MILANO_CACHE_TTL   secondi in cui una risposta in cache vale senza rete (default 0)
* LIVE_FAQ=1         abilita la ricerca semantica live delle FAQ del Comune
* MILANO_UA_BROWSER=1  consente il ripiego su uno user-agent da browser quando il
                     WAF risponde 403 (default 0: a runtime si usa SOLO lo
                     user-agent dichiarato; il ripiego e' pensato per la raccolta
                     una tantum, vedi README_CORE.md)

Ogni funzione pubblica ha una docstring scritta per essere riusata come
descrizione di tool per Claude.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
import time
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx

import local_index

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

#: User-agent dichiarato e onesto, usato per tutte le richieste di default.
UA_DICHIARATO = (
    "ClaudeImpactLab-Milano-prototipo/0.1 (hackathon Claude Impact Lab Milano, "
    "Track 01; uso non commerciale; +https://github.com/Claude-Milano/impact-lab-oct-2026)"
)
#: User-agent da browser standard: SOLO per la raccolta una tantum (build_index.py)
#: e le catture di confronto, quando il WAF risponde 403 allo UA dichiarato.
UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

CKAN_BASE = "https://dati.comune.milano.it/api/3/action/"
SPARQL_ENDPOINT = "https://virtuoso-prod.comune.milano.it/sparql"
FAQ_SEARCH_URL = "https://www.comune.milano.it/o/crmsearch-service/knowledgeArticles"
CRM_BASE = "https://servizicrm.comune.milano.it"
CRM_SITEMAP = CRM_BASE + "/sitemap.xml"

#: ds549 "Sedi dei servizi anagrafici": resource_id della risorsa CSV con
#: datastore attivo, verificato dal vivo il 03/10/2026 (13 righe, dataset
#: modificato il 28-01-2026).
DS549_SLUG = "ds549-sedi-dei-servizi-anagrafici"
DS549_RESOURCE_ID = "48b24517-765e-4f6f-8b30-9094a212eb85"

#: Host consentiti per fetch_page_snapshot e percorsi vietati da robots.txt
#: (letti il 03/10/2026; servizicrm non ha robots.txt -> 404 -> tutto consentito).
HOST_CONSENTITI = {
    "www.comune.milano.it": ["/fascicolo-del-cittadino/", "/accesso-civico/", "/scrivi/"],
    "servizicrm.comune.milano.it": [],
    "studyandwork.yesmilano.it": ["/core/", "/profiles/", "/admin/", "/search/", "/user/",
                                  "/node/add/", "/comment/reply/", "/filter/tips",
                                  "/index.php/", "/media/oembed"],
}

#: Timeout brevi (secondi). SPARQL ha il suo (15 s) come da specifica.
TIMEOUT_DEFAULT = 10.0
TIMEOUT_SPARQL = 15.0

_CONFIG: dict[str, Any] = {"cache_dir": None}


def configure(cache_dir: str | os.PathLike | None = None,
              index_dir: str | os.PathLike | None = None) -> None:
    """Imposta la cartella della cache e/o dell'indice locale (in alternativa
    alle variabili d'ambiente MILANO_CACHE_DIR / MILANO_INDEX_DIR)."""
    if cache_dir is not None:
        _CONFIG["cache_dir"] = Path(cache_dir)
    if index_dir is not None:
        local_index.set_index_dir(index_dir)


def cache_dir() -> Path:
    """Cartella della cache su file (creata se manca)."""
    d = _CONFIG["cache_dir"] or os.environ.get("MILANO_CACHE_DIR") or (Path.cwd() / "data" / "cache")
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _flag(nome: str) -> bool:
    return os.environ.get(nome, "0").strip().lower() in ("1", "true", "si", "sì", "yes", "on")


def live_faq_attiva() -> bool:
    """True se la ricerca live delle FAQ del Comune e' abilitata (env LIVE_FAQ=1)."""
    return _flag("LIVE_FAQ")


def adesso_iso() -> str:
    """Timestamp locale ISO 8601 con fuso, al secondo."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class FonteNonDisponibile(RuntimeError):
    """La fonte non risponde e non c'e' una copia in cache."""


# ---------------------------------------------------------------------------
# HTTP con user-agent dichiarato, ripiego opzionale e cache su file
# ---------------------------------------------------------------------------

def http_get(url: str, params: dict | None = None, timeout: float = TIMEOUT_DEFAULT,
             accept: str | None = None, consenti_ua_browser: bool | None = None) -> tuple[httpx.Response, list[dict]]:
    """GET con user-agent dichiarato. Se il server risponde 403 (WAF) e il
    ripiego e' consentito (argomento o env MILANO_UA_BROWSER=1), ripete UNA
    volta con uno user-agent da browser. Restituisce (risposta, tentativi)."""
    if consenti_ua_browser is None:
        consenti_ua_browser = _flag("MILANO_UA_BROWSER")
    headers = {"User-Agent": UA_DICHIARATO, "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"}
    if accept:
        headers["Accept"] = accept
    tentativi: list[dict] = []
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        r = c.get(url, params=params, headers=headers)
        tentativi.append({"ua": "dichiarato", "status": r.status_code})
        if r.status_code == 403 and consenti_ua_browser:
            headers["User-Agent"] = UA_BROWSER
            if not accept:
                headers["Accept"] = "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"
            r = c.get(url, params=params, headers=headers)
            tentativi.append({"ua": "browser", "status": r.status_code})
    return r, tentativi


def _chiave_cache(url: str, params: dict | None) -> str:
    raw = url + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cached_fetch(tipo: str, url: str, params: dict | None = None, *, timeout: float = TIMEOUT_DEFAULT,
                 formato: str = "json", accept: str | None = None,
                 consenti_ua_browser: bool | None = None, ttl: float | None = None) -> dict:
    """Scarica url (JSON o testo) salvando in cache risposta + timestamp di
    recupero. Se la rete fallisce (errore, timeout, HTTP >= 400) restituisce la
    copia in cache con un avviso. Solleva FonteNonDisponibile se non c'e' copia.

    Restituisce {contenuto, recuperato_il, da_cache, avviso, http_status, tentativi}.
    """
    f = cache_dir() / tipo / (_chiave_cache(url, params) + ".json")
    if ttl is None:
        ttl = float(os.environ.get("MILANO_CACHE_TTL", "0") or 0)
    cached = None
    if f.exists():
        try:
            cached = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
    if cached and ttl > 0 and (time.time() - cached.get("_ts", 0)) < ttl:
        return {"contenuto": cached["contenuto"], "recuperato_il": cached["recuperato_il"],
                "da_cache": True, "avviso": None, "http_status": cached.get("http_status"), "tentativi": []}

    errore = None
    tentativi: list[dict] = []
    status = None
    try:
        r, tentativi = http_get(url, params=params, timeout=timeout, accept=accept,
                                consenti_ua_browser=consenti_ua_browser)
        status = r.status_code
        if r.status_code < 400:
            contenuto = r.json() if formato == "json" else r.text
            rec = adesso_iso()
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({"url": url, "params": params, "recuperato_il": rec, "_ts": time.time(),
                                     "http_status": status, "contenuto": contenuto}, ensure_ascii=False),
                         encoding="utf-8")
            return {"contenuto": contenuto, "recuperato_il": rec, "da_cache": False, "avviso": None,
                    "http_status": status, "tentativi": tentativi}
        errore = f"HTTP {r.status_code}" + (" (bloccato dal WAF)" if r.status_code == 403 else "")
    except (httpx.HTTPError, ValueError) as e:
        errore = f"{type(e).__name__}: {e}"

    if cached:
        return {"contenuto": cached["contenuto"], "recuperato_il": cached["recuperato_il"], "da_cache": True,
                "avviso": f"Fonte non raggiungibile ora ({errore}): uso la copia salvata il {cached['recuperato_il']}.",
                "http_status": status, "tentativi": tentativi}
    raise FonteNonDisponibile(f"{url}: {errore}; nessuna copia in cache.")


# ---------------------------------------------------------------------------
# Pulizia HTML -> testo e parser delle pagine
# ---------------------------------------------------------------------------

def html_to_text(s: str) -> str:
    """Converte un frammento HTML in testo pulito (elenchi come '- ', a capo
    sui blocchi, entita' decodificate, spazi compattati)."""
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style|noscript|svg|nav|form|button|select|template)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?is)<!--.*?-->", " ", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = re.sub(r"(?i)<(br|/p|/div|/h[1-6]|/li|/tr|/ul|/ol|/table|/section|h[1-6])\b[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s).replace("\xa0", " ").replace("​", "")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n(- )?\n+", "\n", s)
    s = re.sub(r"\n{2,}", "\n", s)
    return s.strip()


def data_it_to_iso(s: str | None) -> str | None:
    """'23/08/2025' -> '2025-08-23'; '28-01-2026' -> '2026-01-28'; ISO resta ISO."""
    if not s:
        return None
    s = s.strip()
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


def _estrai_link(frammento: str, base: str, max_link: int = 40) -> list[dict]:
    out, visti = [], set()
    for m in re.finditer(r'(?is)<a\b[^>]*href="([^"#][^"]*)"[^>]*>(.*?)</a>', frammento):
        href = _html.unescape(m.group(1)).strip().replace("\\", "/").split()[0]  # HTML malformato: 'url target='
        if not href:
            continue
        if href.startswith(("javascript:", "mailto:", "tel:")):
            continue
        url = urljoin(base, href)
        testo = html_to_text(m.group(2)).replace("\n", " ").strip()
        if not testo or url in visti:
            continue
        if re.search(r"facebook|instagram|linkedin|youtube|twitter|x\.com|wa\.me|whatsapp", url):
            continue
        visti.add(url)
        out.append({"testo": testo[:120], "url": url})
        if len(out) >= max_link:
            break
    return out


def ka_da_url(url: str) -> str | None:
    """Ricava il numero KA dal link (es. .../centro-supporto/KA-00325/... -> 'KA-00325')."""
    m = re.search(r"(KA-\d{5})", unquote(url or ""), re.I)
    return m.group(1).upper() if m else None


def normalizza_ka(ka: str) -> str:
    """'ka-325', 'KA-00325', '00325' -> 'KA-00325'."""
    m = re.search(r"(\d+)", ka or "")
    if not m:
        raise ValueError(f"Codice FAQ non valido: {ka!r} (atteso es. 'KA-00325')")
    return f"KA-{int(m.group(1)):05d}"


def parse_ka_page(page: str, url: str) -> dict:
    """Estrae da una pagina pubblica del Centro Supporto (servizicrm) domanda,
    risposta in testo, data 'Ultimo aggiornamento', breadcrumb e link."""
    # Domanda: <h2 id="faqtitle"> oppure JSON-LD FAQPage
    domanda = None
    m = re.search(r'(?is)<h2[^>]*id="faqtitle"[^>]*>(.*?)</h2>', page)
    if m:
        domanda = html_to_text(m.group(1))
    risposta_ld = None
    for ld in re.findall(r'(?is)<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page):
        try:
            j = json.loads(ld)
        except ValueError:
            continue
        if isinstance(j, dict) and j.get("@type") == "FAQPage":
            q = (j.get("mainEntity") or [{}])[0]
            domanda = domanda or (q.get("name") or "").strip()
            risposta_ld = html_to_text((q.get("acceptedAnswer") or {}).get("text") or "")
    # Risposta: blocco #faqcontent fino a #faqlastmodified
    risposta, link = None, []
    a = page.find('id="faqcontent"')
    if a >= 0:
        a = page.find(">", a) + 1
        b = page.find('id="faqlastmodified"', a)
        frammento = page[a:b if b > 0 else a + 50000]
        frammento = frammento[: frammento.rfind("<div")] if b > 0 else frammento
        risposta = html_to_text(frammento)
        link = _estrai_link(frammento, CRM_BASE)
    risposta = risposta or risposta_ld or ""
    # Data di aggiornamento visibile sulla pagina
    m = re.search(r"Ultimo aggiornamento:\s*(\d{1,2}/\d{1,2}/\d{4})", page)
    aggiornato = data_it_to_iso(m.group(1)) if m else None
    # Breadcrumb (area / servizio / titolo breve)
    briciole = []
    m = re.search(r'(?is)<ul class="breadcrumb">(.*?)</ul>', page)
    if m:
        for li in re.findall(r'(?is)<li[^>]*>(.*?)</li>', m.group(1)):
            t = html_to_text(re.sub(r'(?is)<span class="separator">.*?</span>', "", li))
            if t and t.lower() != "home":
                briciole.append(t)
    # Servizi collegati ("Vai al servizio")
    servizi = []
    for sm in re.finditer(r'(?is)<h5[^>]*>(.*?)</h5>.*?data-link="([^"]+)"', page[page.find('id="faqservices"'):] if 'id="faqservices"' in page else ""):
        servizi.append({"titolo": html_to_text(sm.group(1)), "url": urljoin(CRM_BASE, _html.unescape(sm.group(2)))})
    kw = re.search(r'<meta name="keywords" content="([^"]*)"', page)
    return {
        "ka": ka_da_url(url) or (re.search(r'id="ArticlePublicNumber" value="(KA-\d+)"', page) or [None, None])[1],
        "domanda": domanda,
        "risposta": risposta,
        "aggiornato_il": aggiornato,
        "categoria": " / ".join(briciole[:-1]) if len(briciole) > 1 else (briciole[0] if briciole else None),
        "titolo_breve": briciole[-1] if briciole else None,
        "link": link,
        "link_servizio": servizi,
        "parole_chiave": [k.strip() for k in kw.group(1).split(",") if k.strip()] if kw else [],
        "url": url,
    }


def parse_comune_page(page: str, url: str) -> dict:
    """Estrae titolo, testo principale, 'Ultimo aggiornamento' e link da una
    pagina di servizio di www.comune.milano.it (Liferay)."""
    t = re.search(r"(?is)<title>(.*?)</title>", page)
    titolo = html_to_text(t.group(1)).replace(" - Comune di Milano", "").strip() if t else None
    a = page.find('id="main-content"')
    a = page.find(">", a) + 1 if a >= 0 else 0
    b = page.find("<footer", a)
    frammento = page[a:b if b > 0 else len(page)]
    testo = html_to_text(frammento)
    m = re.search(r"Ultimo aggiornamento:\s*(\d{1,2}/\d{1,2}/\d{4})", page)
    return {"titolo": titolo, "testo": testo, "aggiornato_il": data_it_to_iso(m.group(1)) if m else None,
            "link": _estrai_link(frammento, "https://www.comune.milano.it"), "url": url}


def parse_yesmilano_page(page: str, url: str) -> dict:
    """Estrae titolo, testo principale, data (se presente) e link da una guida
    di studyandwork.yesmilano.it (Drupal)."""
    t = re.search(r"(?is)<title>(.*?)</title>", page)
    titolo = html_to_text(t.group(1)).split("|")[0].strip() if t else None
    a = page.find('role="main"')
    a = page.find(">", a) + 1 if a >= 0 else 0
    b = page.find("<footer", a)
    frammento = page[a:b if b > 0 else len(page)]
    testo = html_to_text(frammento)
    # Righe di servizio della UI da togliere
    testo = "\n".join(r for r in testo.split("\n") if r not in ("Icons", "-->", "Video", "Contacts"))
    agg = None
    for pat in (r'article:modified_time" content="([^"]+)"', r'dateModified"\s*:\s*"([^"]+)"',
                r'<time[^>]*datetime="([^"]+)"'):
        m = re.search(pat, page)
        if m:
            agg = data_it_to_iso(m.group(1))
            break
    return {"titolo": titolo, "testo": testo, "aggiornato_il": agg,
            "link": _estrai_link(frammento, "https://studyandwork.yesmilano.it"), "url": url}


def parse_page(page: str, url: str) -> dict:
    """Sceglie il parser giusto in base all'host."""
    host = urlparse(url).netloc
    if host == "servizicrm.comune.milano.it":
        d = parse_ka_page(page, url)
        return {"titolo": d["domanda"], "testo": d["risposta"], "aggiornato_il": d["aggiornato_il"],
                "link": d["link"], "url": url, "ka": d["ka"]}
    if host.endswith("yesmilano.it"):
        return parse_yesmilano_page(page, url)
    return parse_comune_page(page, url)


# ---------------------------------------------------------------------------
# FAQ e pagine: indice locale (fonte primaria) + live opzionale
# ---------------------------------------------------------------------------

def _estratto(testo: str, n: int = 600) -> str:
    testo = re.sub(r"\s+", " ", testo or "").strip()
    return testo if len(testo) <= n else testo[: n - 1].rsplit(" ", 1)[0] + "…"


def search_comune_faq(text: str, top: int = 5) -> list[dict]:
    """Cerca tra le FAQ ufficiali del Centro Supporto del Comune di Milano
    (indice locale salvato il 03/10/2026, con data di aggiornamento della
    fonte). Scrivi la domanda IN ITALIANO con parole da sportello (es.
    'iscrizione anagrafica dall'estero', 'dichiarazione TARI nuova occupazione').
    Restituisce [{ka, domanda, estratto_risposta, url, categoria, aggiornato_il,
    recuperato_il, punteggio}]. Con LIVE_FAQ=1 prova prima la ricerca live del
    Comune e, se fallisce, ripiega sull'indice locale."""
    if live_faq_attiva():
        try:
            return search_comune_faq_live(text, top)
        except Exception:  # noqa: BLE001 - qualsiasi errore -> indice locale
            pass
    out = []
    for r in local_index.search_local(text, top=top, tipo="faq"):
        d = local_index.get_doc(r["id"]) or {}
        out.append({"ka": r["id"], "domanda": d.get("domanda") or r["titolo"],
                    "estratto_risposta": _estratto(d.get("testo", ""), 600), "url": r["url"],
                    "categoria": d.get("categoria"), "aggiornato_il": d.get("aggiornato_il"),
                    "recuperato_il": d.get("recuperato_il"), "punteggio": r["punteggio"],
                    "fonte": "indice_locale"})
    return out


def search_fonti(text: str, top: int = 5, tipo: str | None = None) -> list[dict]:
    """Cerca in tutte le fonti ufficiali salvate nell'indice locale: FAQ del
    Comune ('faq'), pagine di servizio di comune.milano.it ('pagina_comune') e
    guide YesMilano per studenti e professionisti, in inglese
    ('guida_yesmilano'). tipo=None cerca ovunque. Restituisce
    [{id, tipo, titolo, estratto, url, aggiornato_il, recuperato_il, punteggio}]."""
    return local_index.search_local(text, top=top, tipo=tipo)


def search_comune_faq_live(text: str, top: int = 5, *, forza: bool = False,
                           consenti_ua_browser: bool | None = None) -> list[dict]:
    """Ricerca semantica LIVE nelle FAQ del Comune di Milano (endpoint usato dal
    sito). Attiva solo con LIVE_FAQ=1 (o forza=True per catture una tantum).
    Parametri esatti: top, searchType=semantic, formatInput=true, category=
    (vuoto), textSearch. ATTENZIONE: con il parametro 'q' l'endpoint restituisce
    una lista generica sbagliata. Restituisce [{ka, domanda, estratto_risposta,
    url, categoria}]. Solleva FonteNonDisponibile se il WAF blocca e non c'e' cache."""
    if not (forza or live_faq_attiva()):
        raise RuntimeError("Ricerca live disattivata: imposta LIVE_FAQ=1 oppure usa search_comune_faq (indice locale).")
    params = {"top": str(int(top)), "searchType": "semantic", "formatInput": "true",
              "category": "", "textSearch": text}
    res = cached_fetch("faq_live", FAQ_SEARCH_URL, params, formato="json", accept="application/json",
                       consenti_ua_browser=consenti_ua_browser)
    out = []
    for it in res["contenuto"] or []:
        link = it.get("link") or ""
        out.append({
            "ka": ka_da_url(link),
            "domanda": (it.get("question") or "").strip(),
            "estratto_risposta": _estratto(html_to_text(it.get("answer") or ""), 600),
            "url": link,
            "categoria": it.get("category"),
            "recuperato_il": res["recuperato_il"],
            "da_cache": res["da_cache"],
            "fonte": "live_comune",
        })
    return out


def _sitemap_crm(consenti_ua_browser: bool | None = None) -> dict[str, dict]:
    """Mappa KA -> {url, lastmod} dalla sitemap di servizicrm (in cache)."""
    res = cached_fetch("sitemap", CRM_SITEMAP, formato="text", accept="application/xml",
                       consenti_ua_browser=consenti_ua_browser, timeout=30)
    out = {}
    for m in re.finditer(r"(?s)<url>\s*<loc>(.*?)</loc>\s*(?:<lastmod>(.*?)</lastmod>)?", res["contenuto"]):
        u = unquote(m.group(1).strip())
        ka = ka_da_url(u)
        if ka:
            out[ka] = {"url": u, "lastmod": (m.group(2) or "").strip() or None}
    return out


def get_faq_article(ka: str) -> dict | None:
    """Legge una FAQ ufficiale del Comune di Milano dato il codice (es.
    'KA-00325'): domanda, risposta completa in testo, data di aggiornamento
    della fonte, data di recupero, categoria, URL pubblico e servizi collegati.
    Legge dall'indice locale; se la FAQ non c'e' e LIVE_FAQ=1 la scarica dalla
    pagina pubblica (URL trovato via sitemap). Restituisce None se non trovata."""
    ka = normalizza_ka(ka)
    d = local_index.get_doc(ka)
    if d:
        return {"ka": ka, "domanda": d.get("domanda") or d.get("titolo"), "risposta": d.get("testo"),
                "aggiornato_il": d.get("aggiornato_il"), "lastmod_sitemap": d.get("lastmod_sitemap"),
                "recuperato_il": d.get("recuperato_il"), "categoria": d.get("categoria"),
                "url": d.get("url"), "link": d.get("link", []), "link_servizio": d.get("link_servizio", []),
                "fonte": "indice_locale"}
    if not live_faq_attiva():
        return None
    sm = _sitemap_crm()
    info = sm.get(ka)
    if not info:
        return None
    res = cached_fetch("faq_pagine", info["url"], formato="text", accept="text/html")
    p = parse_ka_page(res["contenuto"], info["url"])
    return {"ka": ka, "domanda": p["domanda"], "risposta": p["risposta"],
            "aggiornato_il": p["aggiornato_il"] or data_it_to_iso(info.get("lastmod")),
            "lastmod_sitemap": info.get("lastmod"), "recuperato_il": res["recuperato_il"],
            "categoria": p["categoria"], "url": info["url"], "link": p["link"],
            "link_servizio": p["link_servizio"], "fonte": "live_cache" if res["da_cache"] else "live"}


def _robots_consente(url: str) -> bool:
    u = urlparse(url)
    vietati = HOST_CONSENTITI.get(u.netloc)
    if vietati is None:
        return False
    return not any(u.path.startswith(p) for p in vietati)


def fetch_page_snapshot(url: str, consenti_ua_browser: bool | None = None) -> dict:
    """Scarica una pagina pubblica del Comune (www.comune.milano.it/servizi/...,
    servizicrm) o di YesMilano (studyandwork.yesmilano.it/...), ne estrae il
    testo principale e salva uno snapshot datato. Se il WAF blocca (403) o la
    rete fallisce, restituisce l'ultimo snapshot in cache o la copia
    dell'indice locale, con la sua data e il flag waf_bloccato.
    Restituisce {url, titolo, testo, aggiornato_il, recuperato_il, fonte
    ('live'|'cache'|'indice_locale'), waf_bloccato, avviso}."""
    if not _robots_consente(url):
        raise ValueError(f"URL non consentito (host fuori allowlist o vietato da robots.txt): {url}")
    snap = cache_dir() / "snapshots" / (_chiave_cache(url, None) + ".json")
    status, errore, tentativi = None, None, []
    try:
        r, tentativi = http_get(url, accept="text/html", consenti_ua_browser=consenti_ua_browser)
        status = r.status_code
        if r.status_code < 400:
            p = parse_page(r.text, str(r.url))
            out = {"url": url, "titolo": p["titolo"], "testo": p["testo"], "aggiornato_il": p["aggiornato_il"],
                   "link": p.get("link", []), "recuperato_il": adesso_iso(), "fonte": "live",
                   "waf_bloccato": False, "avviso": None, "tentativi": tentativi}
            snap.parent.mkdir(parents=True, exist_ok=True)
            snap.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
            return out
        errore = f"HTTP {r.status_code}"
    except httpx.HTTPError as e:
        errore = f"{type(e).__name__}: {e}"
    waf = status == 403
    motivo = ("il sito ha bloccato la richiesta automatica (403, WAF)" if waf else f"fonte non raggiungibile ({errore})")
    if snap.exists():
        out = json.loads(snap.read_text(encoding="utf-8"))
        out.update({"fonte": "cache", "waf_bloccato": waf, "tentativi": tentativi,
                    "avviso": f"Copia salvata il {out.get('recuperato_il')}: {motivo}."})
        return out
    d = local_index.get_doc_by_url(url)
    if d:
        return {"url": url, "titolo": d.get("titolo"), "testo": d.get("testo"), "aggiornato_il": d.get("aggiornato_il"),
                "link": d.get("link", []), "recuperato_il": d.get("recuperato_il"), "fonte": "indice_locale",
                "waf_bloccato": waf, "tentativi": tentativi,
                "avviso": f"Copia dell'indice locale salvata il {d.get('recuperato_il')}: {motivo}."}
    raise FonteNonDisponibile(f"{url}: {motivo}; nessuno snapshot salvato.")


# ---------------------------------------------------------------------------
# CKAN (dati.comune.milano.it) - dal vivo
# ---------------------------------------------------------------------------

def ckan_action(azione: str, params: dict | None = None, timeout: float = TIMEOUT_DEFAULT) -> dict:
    """Chiama un'azione dell'API CKAN e restituisce {result, recuperato_il, da_cache, avviso}."""
    res = cached_fetch("ckan", CKAN_BASE + azione, params, timeout=timeout, formato="json")
    body = res["contenuto"]
    if not body.get("success", False):
        raise FonteNonDisponibile(f"CKAN {azione}: {json.dumps(body.get('error'), ensure_ascii=False)[:300]}")
    return {"result": body["result"], "recuperato_il": res["recuperato_il"], "da_cache": res["da_cache"],
            "avviso": res["avviso"]}


def risolvi_dataset(slug: str) -> str:
    """'ds549' -> 'ds549-sedi-dei-servizi-anagrafici' (cerca per campo identifier).
    Uno slug completo o un id CKAN restano invariati."""
    s = slug.strip()
    if re.fullmatch(r"(?i)ds\d+", s):
        r = ckan_action("package_search", {"fq": f'identifier:"{s.upper()}"', "rows": 1})
        res = r["result"]["results"]
        if not res:
            raise FonteNonDisponibile(f"Dataset {s} non trovato su CKAN")
        return res[0]["name"]
    return s


def ckan_search(q: str, rows: int = 10) -> list[dict]:
    """Cerca dataset nel catalogo open data del Comune di Milano
    (dati.comune.milano.it). Restituisce [{slug, titolo, descrizione,
    metadata_modified, frequency, n_risorse}]."""
    r = ckan_action("package_search", {"q": q, "rows": max(1, min(int(rows), 50))})
    out = []
    for p in r["result"]["results"]:
        out.append({"slug": p["name"], "titolo": p.get("title"), "descrizione": _estratto(p.get("notes") or "", 240),
                    "metadata_modified": p.get("metadata_modified"), "frequency": p.get("frequency"),
                    "n_risorse": p.get("num_resources"), "recuperato_il": r["recuperato_il"]})
    return out


def _copertura_temporale(p: dict) -> tuple[str | None, str | None]:
    start, end = p.get("temporal_start"), p.get("temporal_end")
    tc = p.get("temporal_coverage")
    if tc and not (start or end):
        try:
            lst = json.loads(tc) if isinstance(tc, str) else tc
            starts = [x.get("temporal_start") for x in lst if x.get("temporal_start")]
            ends = [x.get("temporal_end") for x in lst if x.get("temporal_end")]
            start = min(starts) if starts else None
            end = max(ends) if ends else None
        except (ValueError, AttributeError, TypeError):
            pass
    return start, end


def ckan_dataset_meta(slug: str) -> dict:
    """Metadati di un dataset open data del Comune (accetta 'ds549' o lo slug
    completo): titolo, risorse [{id, nome, formato, url, datastore_active,
    last_modified}], copertura temporale, frequenza di aggiornamento, data di
    modifica e un avviso di freschezza se il dato e' vecchio (fine copertura
    oltre 2 anni fa) o non viene aggiornato (frequency NEVER)."""
    nome = risolvi_dataset(slug)
    r = ckan_action("package_show", {"id": nome})
    p = r["result"]
    start, end = _copertura_temporale(p)
    freq = p.get("frequency")
    avvisi = []
    if end:
        try:
            fine = date.fromisoformat(end[:10])
            oggi = date.today()
            if (oggi - fine).days > 730:
                avvisi.append(f"Copertura temporale ferma al {fine.isoformat()} (oltre 2 anni fa): dato vecchio.")
        except ValueError:
            pass
    else:
        avvisi.append("Copertura temporale non indicata nei metadati.")
    if (freq or "").upper() == "NEVER":
        avvisi.append("Frequenza di aggiornamento NEVER: il dataset non viene aggiornato (va bene per dati "
                      "storici o indagini una tantum, non per informazioni operative come sedi e orari).")
    return {
        "slug": p["name"], "identificativo": p.get("identifier"), "id_ckan": p["id"], "titolo": p.get("title"),
        "descrizione": _estratto(p.get("notes") or "", 400),
        "risorse": [{"id": x["id"], "nome": x.get("name"), "formato": x.get("format"), "url": x.get("url"),
                     "datastore_active": bool(x.get("datastore_active")), "last_modified": x.get("last_modified")}
                    for x in p.get("resources", [])],
        "temporal_start": start, "temporal_end": end, "frequency": freq,
        "modified": data_it_to_iso(p.get("modified")) if p.get("modified") else None,
        "metadata_modified": p.get("metadata_modified"),
        "avviso_freschezza": " ".join(avvisi) or None,
        "url_pagina": f"https://dati.comune.milano.it/dataset/{p['name']}",
        "recuperato_il": r["recuperato_il"], "da_cache": r["da_cache"],
    }


_SQL_VIETATE = re.compile(r"(?i)\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|into|"
                          r"execute|call|vacuum|pg_sleep|pg_read_file|set|reset|lock|comment)\b")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def valida_sql(sql: str, allowlist: list[str] | set[str], limite_max: int = 200) -> str:
    """Valida e normalizza una query per datastore_search_sql: solo SELECT, una
    sola istruzione, niente commenti, solo resource_id dell'allowlist, LIMIT
    obbligatorio (aggiunto se manca, ridotto a limite_max se superiore).
    Restituisce la SQL pronta; solleva ValueError con messaggio in italiano."""
    if not allowlist:
        raise ValueError("Serve un'allowlist di resource_id: nessuna tabella e' consentita.")
    s = (sql or "").strip()
    s = re.sub(r";\s*$", "", s)
    if ";" in s:
        raise ValueError("Una sola istruzione SQL per volta (trovato ';').")
    if "--" in s or "/*" in s:
        raise ValueError("Commenti SQL non ammessi.")
    if not re.match(r"(?is)^select\b", s):
        raise ValueError("Sono ammesse solo query SELECT.")
    # Le parole vietate si cercano fuori dalle stringhe/identificatori quotati
    nudo = re.sub(r'"[^"]*"|\'[^\']*\'', " ", s)
    m = _SQL_VIETATE.search(nudo)
    if m:
        raise ValueError(f"Parola chiave non ammessa: {m.group(1).upper()}.")
    ids = {x.lower() for x in _UUID.findall(s)}
    consentiti = {x.lower() for x in allowlist}
    if not ids:
        raise ValueError('Indica la tabella con il resource_id tra virgolette, es. FROM "48b24517-...".')
    fuori = ids - consentiti
    if fuori:
        raise ValueError(f"resource_id non in allowlist: {', '.join(sorted(fuori))}.")
    m = re.search(r"(?is)\blimit\s+(\d+)(\s+offset\s+\d+)?\s*$", s)
    if m:
        n = int(m.group(1))
        if n > limite_max:
            s = s[: m.start(1)] + str(limite_max) + s[m.end(1):]
    else:
        if re.search(r"(?i)\blimit\b", nudo):
            raise ValueError("LIMIT deve stare in fondo alla query (es. ... LIMIT 50).")
        s = f"{s} LIMIT {limite_max}"
    return s


def ckan_sql(sql: str, allowlist: list[str] | set[str], timeout: float = 15.0) -> dict:
    """Esegue una query SQL di sola lettura su una o piu' tabelle del datastore
    open data del Comune (datastore_search_sql). Regole: solo SELECT, una sola
    istruzione, la tabella e' il resource_id tra virgolette doppie e deve essere
    nell'allowlist, LIMIT massimo 200 (aggiunto se manca). I nomi di colonna con
    spazi o maiuscole vanno tra virgolette doppie.
    Restituisce {sql_eseguita, campi, righe, recuperato_il, da_cache}."""
    s = valida_sql(sql, allowlist)
    r = ckan_action("datastore_search_sql", {"sql": s}, timeout=timeout)
    res = r["result"]
    return {"sql_eseguita": s, "campi": [f["id"] for f in res.get("fields", [])], "righe": res.get("records", []),
            "recuperato_il": r["recuperato_il"], "da_cache": r["da_cache"], "avviso": r["avviso"]}


def ckan_datastore_search(resource_id: str, filters: dict | None = None, q: str | None = None,
                          limit: int = 50, allowlist: list[str] | set[str] | None = None) -> dict:
    """Legge righe da una risorsa del datastore open data del Comune, con filtri
    esatti per campo (filters={'campo': 'valore'}) e/o ricerca full-text (q).
    limit massimo 200. Restituisce {campi, righe, totale, recuperato_il, da_cache}."""
    if allowlist is not None and resource_id.lower() not in {x.lower() for x in allowlist}:
        raise ValueError(f"resource_id non in allowlist: {resource_id}")
    params: dict[str, Any] = {"resource_id": resource_id, "limit": max(1, min(int(limit), 200))}
    if filters:
        params["filters"] = json.dumps(filters, ensure_ascii=False)
    if q:
        params["q"] = q
    r = ckan_action("datastore_search", params)
    res = r["result"]
    return {"campi": [f["id"] for f in res.get("fields", [])], "righe": res.get("records", []),
            "totale": res.get("total"), "recuperato_il": r["recuperato_il"], "da_cache": r["da_cache"],
            "avviso": r["avviso"]}


def sedi_anagrafiche() -> dict:
    """Elenco delle sedi dei servizi anagrafici del Comune di Milano (open data
    ds549, aggiornato al 28/01/2026): municipio, indirizzo, telefono, orari, note
    (es. 'solo su appuntamento'), quartiere NIL e coordinate.
    Nota verificata: le note di ds549 dicono che la prenotazione e' possibile
    'sia con SPID che senza registrazione', ma il link di prenotazione della
    pagina 'Cambio di residenza' porta al login SPID/CIE/eIDAS: incoerenza tra
    fonti da segnalare. Restituisce {sedi: [...], fonte, recuperato_il, da_cache}."""
    r = ckan_datastore_search(DS549_RESOURCE_ID, limit=100)
    sedi = []
    for x in r["righe"]:
        sedi.append({"municipio": x.get("titolo"), "indirizzo": x.get("Indirizzo"), "telefono": x.get("telefono"),
                     "orari": x.get("orari"), "note": x.get("Note"), "nil": x.get("NIL"),
                     "lat": x.get("LAT_Y_4326"), "lon": x.get("LONG_X_4326")})
    return {"sedi": sedi, "fonte": f"https://dati.comune.milano.it/dataset/{DS549_SLUG}",
            "resource_id": DS549_RESOURCE_ID, "recuperato_il": r["recuperato_il"], "da_cache": r["da_cache"],
            "avviso": r["avviso"]}


# ---------------------------------------------------------------------------
# SPARQL (virtuoso-prod.comune.milano.it) - dal vivo
# ---------------------------------------------------------------------------

_SPARQL_VIETATE = re.compile(r"(?i)\b(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|COPY|MOVE|ADD|SERVICE)\b")


def valida_sparql(query: str, limite_max: int = 200) -> str:
    """Guardie SPARQL: deve contenere GRAPH <https://dati.comune.milano.it/data/...>
    e un LIMIT <= limite_max; niente update ne' SERVICE. Solleva ValueError."""
    q = (query or "").strip()
    if not re.search(r"GRAPH\s*<https://dati\.comune\.milano\.it/data/[^>\s]+>", q):
        raise ValueError("La query deve contenere GRAPH <https://dati.comune.milano.it/data/...>.")
    nudo = re.sub(r'"[^"]*"|\'[^\']*\'|<[^>\s]*>', " ", q)
    m = _SPARQL_VIETATE.search(nudo)
    if m:
        raise ValueError(f"Operazione SPARQL non ammessa: {m.group(1).upper()}.")
    lim = re.findall(r"(?i)\bLIMIT\s+(\d+)", nudo)
    if not lim:
        raise ValueError("La query deve avere un LIMIT (massimo 200).")
    if int(lim[-1]) > limite_max:
        raise ValueError(f"LIMIT {lim[-1]} troppo alto: massimo {limite_max}.")
    return q


def sparql(query: str, timeout: float = TIMEOUT_SPARQL) -> dict:
    """Interroga i Linked Open Data del Comune di Milano (endpoint SPARQL
    Virtuoso). La query deve indicare il grafo con GRAPH
    <https://dati.comune.milano.it/data/...> (es. atti-pubblici, biblioteche,
    scuole) e avere LIMIT <= 200. Nei filtri sui letterali usa STR(), es.
    FILTER(STR(?label) = "ISCRIZIONE ANAGRAFICA PER IMMIGRAZIONE").
    Restituisce {variabili, righe: [{var: valore}], recuperato_il, da_cache}."""
    q = valida_sparql(query)
    res = cached_fetch("sparql", SPARQL_ENDPOINT, {"query": q, "format": "application/sparql-results+json"},
                       timeout=timeout, formato="json", accept="application/sparql-results+json")
    body = res["contenuto"]
    righe = [{k: v.get("value") for k, v in b.items()} for b in body.get("results", {}).get("bindings", [])]
    return {"variabili": body.get("head", {}).get("vars", []), "righe": righe,
            "recuperato_il": res["recuperato_il"], "da_cache": res["da_cache"], "avviso": res["avviso"]}


#: Query SPARQL d'esempio verificate dal vivo il 03/10/2026.
SPARQL_ESEMPI = {
    # Pratiche (non persone) di iscrizione anagrafica per immigrazione, per anno.
    # Comprendono anche chi arriva da altri comuni italiani. 2025 = 50.777.
    "iscrizioni_immigrazione_per_anno": """
PREFIX ap: <https://dati.comune.milano.it/atti-pubblici/onto/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?anno (SUM(xsd:integer(?n)) AS ?pratiche)
WHERE {
  GRAPH <https://dati.comune.milano.it/data/atti-pubblici> {
    ?s a ap:TotaleDocumentiRilasciatiPerMese ;
       ap:tipologiaAttoPubblico ?t ; ap:anno ?anno ; ap:numeroDocumenti ?n .
    ?t rdfs:label ?tl .
    FILTER(STR(?tl) = "ISCRIZIONE ANAGRAFICA PER IMMIGRAZIONE")
  }
}
GROUP BY ?anno ORDER BY ?anno LIMIT 50""".strip(),
    # Biblioteche comunali con indirizzo, municipio, orari e note di accesso.
    "biblioteche_con_orari": """
PREFIX bo: <https://dati.comune.milano.it/biblioteche/onto/>
PREFIX om: <https://dati.comune.milano.it/ontomi/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?nome ?indirizzo ?municipio ?orari ?note
WHERE {
  GRAPH <https://dati.comune.milano.it/data/biblioteche> {
    ?a a bo:BibliotecaAnagrafica ; om:nome ?nome ; bo:orarioBiblioteca ?orari ; om:haIndirizzo ?i .
    ?i om:indirizzoCompleto ?indirizzo .
    OPTIONAL { ?i om:haMunicipio ?m . BIND(REPLACE(STR(?m), "^.*/", "") AS ?municipio) }
    OPTIONAL { ?a rdfs:comment ?note }
  }
}
ORDER BY ?nome LIMIT 50""".strip(),
}


# ---------------------------------------------------------------------------
# Definizioni di tool pronte per Claude (strict) e implementazioni
# ---------------------------------------------------------------------------

def _schema(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required if required is not None else list(props),
            "additionalProperties": False}


TOOL_DEFS: list[dict] = [
    {"name": "cerca_fonti_comune", "strict": True,
     "description": ("Cerca nelle fonti ufficiali salvate (FAQ del Centro Supporto del Comune di Milano, pagine di "
                     "servizio di comune.milano.it, guide YesMilano in inglese). Scrivi la query IN ITALIANO con "
                     "parole da sportello (es. 'iscrizione anagrafica dall'estero', 'dichiarazione TARI nuova "
                     "occupazione', 'carta d'identita cittadino extra UE'). Ogni risultato ha id, url e data di "
                     "aggiornamento della fonte: citali sempre."),
     "input_schema": _schema({"query": {"type": "string", "description": "Domanda riformulata in italiano"},
                              "tipo": {"type": "string", "enum": ["tutti", "faq", "pagina_comune", "guida_yesmilano"],
                                       "description": "Filtra per tipo di fonte; 'tutti' per cercare ovunque"}})},
    {"name": "leggi_faq", "strict": True,
     "description": "Legge il testo completo di una FAQ ufficiale del Comune dato il codice KA (es. 'KA-00489').",
     "input_schema": _schema({"ka": {"type": "string", "description": "Codice FAQ, es. KA-00489"}})},
    {"name": "leggi_documento", "strict": True,
     "description": "Legge il testo completo di un documento dell'indice locale dato il suo id (restituito da cerca_fonti_comune).",
     "input_schema": _schema({"id": {"type": "string"}})},
    {"name": "sedi_anagrafiche", "strict": True,
     "description": "Elenco delle sedi anagrafiche del Comune (open data ds549): indirizzo, orari, note di accesso.",
     "input_schema": _schema({})},
]


def _tool_cerca(inp: dict) -> list[dict]:
    tipo = inp.get("tipo") or "tutti"
    return search_fonti(inp["query"], top=5, tipo=None if tipo == "tutti" else tipo)


def _tool_leggi_faq(inp: dict) -> dict:
    d = get_faq_article(inp["ka"])
    if d is None:
        raise LookupError(f"FAQ {inp['ka']} non presente nell'indice locale.")
    return d


def _tool_leggi_doc(inp: dict) -> dict:
    d = local_index.get_doc(inp["id"])
    if d is None:
        raise LookupError(f"Documento {inp['id']} non trovato.")
    return {k: d.get(k) for k in ("id", "tipo", "titolo", "testo", "url", "aggiornato_il", "recuperato_il", "link")}


TOOL_IMPLS: dict[str, Callable[[dict], Any]] = {
    "cerca_fonti_comune": _tool_cerca,
    "leggi_faq": _tool_leggi_faq,
    "leggi_documento": _tool_leggi_doc,
    "sedi_anagrafiche": lambda inp: sedi_anagrafiche(),
}


def slug_testo(s: str, n: int = 60) -> str:
    """Slug ASCII per nomi di file."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:n] or hashlib.sha1(s.encode()).hexdigest()[:10]


__all__ = [n for n in dir() if not n.startswith("_") and n not in ("annotations",)]
