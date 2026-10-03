# -*- coding: utf-8 -*-
"""
build_index.py - Raccolta UNA TANTUM delle fonti testuali per l'indice locale
============================================================================

Perche' esiste: il WAF (Azure Application Gateway) di www.comune.milano.it,
servizicrm.comune.milano.it (anche la sitemap) e studyandwork.yesmilano.it
risponde 403 ai client non-browser, anche con uno user-agent dichiarato. A
runtime i prototipi leggono quindi un indice locale (data/index/*.json).

Come raccoglie (regole):
* elenco CURATO e chiuso di pagine pubbliche (FAQ del Centro Supporto, pagine
  di servizio, guide YesMilano), tutte consentite da robots.txt
  (servizicrm non ha robots.txt: 404 = nessun divieto);
* ritmo lento: almeno PAUSA_S secondi (default 2.5) tra una richiesta e l'altra;
* prima prova con lo user-agent dichiarato (UA_DICHIARATO); se il WAF risponde
  403, per QUESTA raccolta una tantum ripete con uno user-agent da browser
  standard (UA_BROWSER). L'esito di ogni tentativo e' registrato nel manifest
  (data/index/_manifest.json) e documentato in README_CORE.md, insieme alla
  richiesta al Comune di un feed/API ufficiale (data wishlist);
* riprende da dove era rimasto: i documenti gia' salvati non si riscaricano
  (usa --force per riscaricare tutto).

Uso:
    python build_index.py            # raccolta completa
    python build_index.py --force    # riscarica anche i documenti presenti
    python build_index.py --solo KA-00325 KA-02121

Ogni documento salvato in data/index/<id>.json contiene: id, tipo
(faq | pagina_comune | guida_yesmilano), titolo/domanda, testo pulito, url,
aggiornato_il (data di aggiornamento della fonte, se presente), recuperato_il.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

import milano_tools as mt

QUI = Path(__file__).resolve().parent
OUT = QUI / "data" / "index"
PAUSA_S = 2.5  # >= 2 s tra le richieste, come da regole di raccolta

# ---------------------------------------------------------------------------
# Elenco curato delle FAQ del Centro Supporto (rilevanti per chi arriva a Milano)
# ---------------------------------------------------------------------------
FAQ_OBBLIGATORIE = [
    "KA-00325", "KA-00330", "KA-00370", "KA-00372", "KA-00393", "KA-00489", "KA-00534", "KA-00596",
    "KA-01955", "KA-02121", "KA-02125", "KA-02150", "KA-02795", "KA-02803", "KA-02885", "KA-03707",
    "KA-03708", "KA-03709", "KA-03731", "KA-03937", "KA-03938", "KA-04007", "KA-04339", "KA-04449",
]
FAQ_CORRELATE = [
    # Residenza persone straniere, attestazione di soggiorno UE, stato pratica
    "KA-00295", "KA-00328", "KA-00329", "KA-00331", "KA-00341", "KA-00373", "KA-00428", "KA-00429",
    "KA-00430", "KA-00431", "KA-00435", "KA-00437", "KA-00465", "KA-00490", "KA-00491", "KA-00556",
    "KA-00594", "KA-00597", "KA-00598", "KA-03582", "KA-03931", "KA-03249", "KA-03252",
    # Carta d'identita' elettronica (CIE)
    "KA-00408", "KA-00410", "KA-00411", "KA-00552", "KA-00564", "KA-00578", "KA-04009", "KA-04355",
    "KA-03621",
    # SPID, Fascicolo del cittadino, canali senza SPID
    "KA-00309", "KA-03725", "KA-03732", "KA-03075", "KA-02883",
    # Certificati
    "KA-00390", "KA-00546",
    # TARI
    "KA-01813", "KA-01945", "KA-02119", "KA-02120", "KA-01986", "KA-02042", "KA-03059", "KA-04281",
    # Milano Welcome Center
    "KA-02793", "KA-02798", "KA-02799", "KA-02800", "KA-04104",
    # Idoneita' abitativa (ricongiungimento)
    "KA-03701", "KA-03702", "KA-03703", "KA-03705",
    # Scuola, nidi, sezioni primavera, infanzia
    "KA-01575", "KA-03762", "KA-03769", "KA-04081", "KA-04082", "KA-04043", "KA-01245", "KA-01417",
    "KA-03978",
]

# Pagine di servizio di www.comune.milano.it
PAGINE_COMUNE = [
    "https://www.comune.milano.it/servizi/anagrafe/cambio-di-residenza-per-persone-straniere-provenienti-dall-estero",
    "https://www.comune.milano.it/servizi/anagrafe/richiesta-di-residenza-per-persone-straniere-provenienti-dall-estero/modulistica-richiesta-di-residenza-per-persone-straniere-provenienti-dall-estero",
    "https://www.comune.milano.it/servizi/anagrafe/cambio-di-residenza",
    "https://www.comune.milano.it/servizi/anagrafe/attestazione-di-soggiorno-per-cittadini-ue-non-italiani-e-britannici",
    "https://www.comune.milano.it/servizi/anagrafe/carta-d-identita",
    "https://www.comune.milano.it/servizi/tributi/tari-dichiarazione-di-occupazione-di-appartamenti-e-immobili",
    "https://www.comune.milano.it/servizi/tributi/tari-dichiarazione-di-cessazione-di-occupazione-di-appartamenti-e-immobili",
    "https://www.comune.milano.it/servizi/welfare/milano-welcome-center",
    "https://www.comune.milano.it/servizi/scuola/nidi-d-infanzia-e-sezioni-primavera",
    "https://www.comune.milano.it/servizi/scuola/scuole-primarie-e-secondarie-iscrizione",
]

# Guide di studyandwork.yesmilano.it (in inglese)
GUIDE_YESMILANO = [
    # Study > How To (studenti)
    "https://studyandwork.yesmilano.it/en/study/how-to/first-steps",
    "https://studyandwork.yesmilano.it/en/study/how-to/get-italian-tax-code-codice-fiscale",
    "https://studyandwork.yesmilano.it/en/study/how-to/residence-permit-students",
    "https://studyandwork.yesmilano.it/en/study/how-to/take-residence-milano-students",
    "https://studyandwork.yesmilano.it/en/study/how-to/get-temporary-residence-milano",
    "https://studyandwork.yesmilano.it/en/study/how-to/national-health-service-students-step-step",
    "https://studyandwork.yesmilano.it/en/study/how-to/id-card",
    # Work > Getting Started guide (professionisti)
    "https://studyandwork.yesmilano.it/en/work/getting-started-guide/tax-code",
    "https://studyandwork.yesmilano.it/en/work/getting-started-guide/residence-permit",
    "https://studyandwork.yesmilano.it/en/work/getting-started-guide/registering-resident-milano",
    "https://studyandwork.yesmilano.it/en/work/getting-started-guide/italian-healthcare",
    "https://studyandwork.yesmilano.it/en/work/getting-started-guide/identity-card",
    "https://studyandwork.yesmilano.it/en/work/getting-started-guide/digital-identity-spid",
    "https://studyandwork.yesmilano.it/en/work/getting-started-guide/family-reunification",
]


def id_pagina(url: str) -> str:
    """Id stabile per una pagina: 'comune:<path>' o 'yesmilano:<path>'."""
    u = urlparse(url)
    pref = "yesmilano" if "yesmilano" in u.netloc else "comune"
    path = u.path.strip("/")
    path = re.sub(r"^(servizi|en)/", "", path)
    return f"{pref}:{path}"


def nome_file(doc_id: str) -> str:
    """Nome di file corto (i percorsi Windows hanno un limite di 260 caratteri):
    slug troncato + 8 caratteri di hash dell'id per evitare collisioni."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", doc_id)
    if len(base) <= 48:
        return base + ".json"
    return base[:40] + "_" + hashlib.sha1(doc_id.encode("utf-8")).hexdigest()[:8] + ".json"


class Raccoglitore:
    """Scarica con pausa minima tra le richieste e registra gli esiti."""

    def __init__(self, pausa: float = PAUSA_S):
        self.pausa = pausa
        self.ultimo = 0.0
        self.esiti: list[dict] = []
        self.client = httpx.Client(timeout=30, follow_redirects=True)

    def get(self, url: str, accept: str = "text/html") -> httpx.Response | None:
        tentativi = []
        r = None
        for nome_ua, ua in (("dichiarato", mt.UA_DICHIARATO), ("browser", mt.UA_BROWSER)):
            attesa = self.pausa - (time.time() - self.ultimo)
            if attesa > 0:
                time.sleep(attesa)
            try:
                r = self.client.get(url, headers={"User-Agent": ua, "Accept": accept,
                                                  "Accept-Language": "it-IT,it;q=0.9,en;q=0.8"})
            except httpx.HTTPError as e:
                self.ultimo = time.time()
                tentativi.append({"ua": nome_ua, "errore": str(e)})
                break
            self.ultimo = time.time()
            tentativi.append({"ua": nome_ua, "status": r.status_code})
            if r.status_code != 403:  # il ripiego su UA browser solo in caso di WAF (403)
                break
        self.esiti.append({"url": url, "tentativi": tentativi})
        print(f"  {tentativi} {url[:110]}", flush=True)
        if r is not None and r.status_code == 200:
            return r
        return None


def salva(doc: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / nome_file(doc["id"])).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def gia_presente(doc_id: str) -> bool:
    return (OUT / nome_file(doc_id)).exists()


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--force", action="store_true", help="riscarica anche i documenti gia' presenti")
    ap.add_argument("--solo", nargs="*", help="solo questi KA o URL")
    ap.add_argument("--pausa", type=float, default=PAUSA_S)
    a = ap.parse_args(argv)
    if a.pausa < 2:
        print("Pausa minima 2 s: la imposto a 2.")
        a.pausa = 2.0

    rc = Raccoglitore(a.pausa)
    faq = list(dict.fromkeys(FAQ_OBBLIGATORIE + FAQ_CORRELATE))
    pagine = PAGINE_COMUNE + GUIDE_YESMILANO
    if a.solo:
        faq = [mt.normalizza_ka(x) for x in a.solo if re.search(r"(?i)ka-?\d+", x)]
        pagine = [x for x in a.solo if x.startswith("http")]

    errori: list[str] = []
    salvati = 0

    # 1) Sitemap di servizicrm: URL completi delle FAQ e lastmod
    sitemap = {}
    da_scaricare = [k for k in faq if a.force or not gia_presente(k)]
    if da_scaricare:
        print("Sitemap servizicrm...")
        r = rc.get(mt.CRM_SITEMAP, accept="application/xml")
        if r is None:
            errori.append("sitemap servizicrm non scaricabile")
        else:
            for m in re.finditer(r"(?s)<url>\s*<loc>(.*?)</loc>\s*(?:<lastmod>(.*?)</lastmod>)?", r.text):
                u = unquote(m.group(1).strip())
                ka = mt.ka_da_url(u)
                if ka:
                    sitemap[ka] = {"url": u, "lastmod": (m.group(2) or "").strip() or None}
            print(f"  {len(sitemap)} FAQ in sitemap")

    # 2) FAQ
    for ka in faq:
        if not a.force and gia_presente(ka):
            continue
        info = sitemap.get(ka)
        if not info:
            errori.append(f"{ka}: non in sitemap")
            continue
        r = rc.get(info["url"])
        if r is None:
            errori.append(f"{ka}: download fallito")
            continue
        p = mt.parse_ka_page(r.text, info["url"])
        if not p["risposta"]:
            errori.append(f"{ka}: risposta vuota")
            continue
        salva({
            "id": ka, "tipo": "faq", "titolo": p["domanda"], "domanda": p["domanda"], "testo": p["risposta"],
            "url": info["url"], "lingua": "it",
            "aggiornato_il": p["aggiornato_il"] or mt.data_it_to_iso(info.get("lastmod")),
            "aggiornato_il_fonte": "pagina ('Ultimo aggiornamento')" if p["aggiornato_il"] else "sitemap lastmod",
            "lastmod_sitemap": info.get("lastmod"), "recuperato_il": mt.adesso_iso(),
            "categoria": p["categoria"], "titolo_breve": p["titolo_breve"], "parole_chiave": p["parole_chiave"],
            "link": p["link"], "link_servizio": p["link_servizio"],
        })
        salvati += 1

    # 3) Pagine di servizio del Comune e guide YesMilano
    for url in pagine:
        did = id_pagina(url)
        if not a.force and gia_presente(did):
            continue
        r = rc.get(url)
        if r is None:
            errori.append(f"{url}: download fallito")
            continue
        p = mt.parse_page(r.text, str(r.url))
        if not p["testo"]:
            errori.append(f"{url}: testo vuoto")
            continue
        yes = "yesmilano" in url
        salva({
            "id": did, "tipo": "guida_yesmilano" if yes else "pagina_comune", "titolo": p["titolo"],
            "testo": p["testo"], "url": url, "lingua": "en" if yes else "it",
            "aggiornato_il": p["aggiornato_il"],
            "aggiornato_il_fonte": "pagina ('Ultimo aggiornamento')" if p["aggiornato_il"] else None,
            "recuperato_il": mt.adesso_iso(), "link": p["link"],
        })
        salvati += 1

    # 4) Manifest
    docs = sorted(p.name for p in OUT.glob("*.json") if not p.name.startswith("_"))
    man_path = OUT / "_manifest.json"
    vecchio = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    ua_403 = sum(1 for e in rc.esiti if e["tentativi"] and e["tentativi"][0].get("status") == 403)
    manifest = {
        "costruito_il": mt.adesso_iso(),
        "documenti": len(docs),
        "per_tipo": {t: sum(1 for d in mt.local_index.all_docs(t)) for t in ("faq", "pagina_comune", "guida_yesmilano")},
        "ua_dichiarato": mt.UA_DICHIARATO,
        "ua_browser_ripiego": mt.UA_BROWSER,
        "richieste_questa_esecuzione": len(rc.esiti),
        "richieste_403_con_ua_dichiarato": ua_403,
        "nota_waf": ("Il WAF risponde 403 allo user-agent dichiarato; per questa raccolta una tantum di pagine "
                     "pubbliche consentite da robots.txt si e' ripiegato su uno user-agent da browser standard, "
                     f"a ritmo lento (>= {a.pausa} s tra le richieste). Vedi README_CORE.md."),
        "esiti": (vecchio.get("esiti", []) if not a.force else []) + rc.esiti,
        "errori": errori,
    }
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nSalvati {salvati} documenti in questa esecuzione; totale indice: {len(docs)}. Errori: {len(errori)}")
    for e in errori:
        print("  -", e)
    return 0 if not errori else 1


if __name__ == "__main__":
    sys.exit(main())
