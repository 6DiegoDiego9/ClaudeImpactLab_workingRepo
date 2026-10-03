# -*- coding: utf-8 -*-
"""
date_utils.py - Calcolo DETERMINISTICO delle scadenze (niente LLM qui)
=====================================================================

Le date le calcola il codice, non Claude: Claude sceglie la regola e cita la
fonte, questo modulo fa l'aritmetica.

* giorni di calendario e giorni lavorativi (esclusi sabato, domenica, festivi
  nazionali italiani 2026-2027 e, a Milano, Sant'Ambrogio 7 dicembre);
* quando la fonte e' ambigua ("entro 8 giorni" senza dire di che tipo)
  scadenza_ambigua() restituisce ENTRAMBE le interpretazioni e indica la piu'
  prudente (la data piu' vicina).

Regole di conteggio (convenzione usata, dichiarata in ogni risultato):
* il giorno dell'evento (es. ingresso in Italia, trasferimento) NON si conta:
  si parte dal giorno successivo (dies a quo non computatur);
* giorni lavorativi: si contano solo i giorni lavorativi successivi;
* giorni di calendario: se l'ultimo giorno cade di sabato/domenica/festivo la
  data "prorogata" al primo giorno lavorativo e' riportata a parte (regola
  generale dell'art. 2963 c.c. e art. 155 c.p.c.): non tutti i procedimenti la
  applicano, quindi la data prudente resta quella non prorogata.

Esempi verificati nelle fonti (vedi CORREZIONI_VERIFICATE.md):
* kit del permesso di soggiorno: "otto giorni lavorativi" dall'ingresso
  (art. 5, c. 2, D.Lgs. 286/1998) -> scadenza(ingresso, 8, "lavorativi");
* residenza: 20 giorni dal trasferimento (KA-00534) -> calendario;
* TARI nuova occupazione: 90 giorni dall'inizio dell'occupazione (KA-02121).
"""
from __future__ import annotations

from datetime import date, timedelta

GIORNI_SETTIMANA = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
        "ottobre", "novembre", "dicembre"]


def pasqua(anno: int) -> date:
    """Domenica di Pasqua (algoritmo gregoriano anonimo / Meeus)."""
    a = anno % 19
    b, c = divmod(anno, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = ((h + l - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


def festivi_nazionali(anno: int) -> dict[date, str]:
    """Festivi nazionali italiani dell'anno. Dal 2026 e' di nuovo festa
    nazionale anche il 4 ottobre (San Francesco d'Assisi e Santa Caterina da
    Siena), reintrodotta dalla legge approvata dal Parlamento nell'ottobre 2025."""
    p = pasqua(anno)
    f = {
        date(anno, 1, 1): "Capodanno",
        date(anno, 1, 6): "Epifania",
        p: "Pasqua",
        p + timedelta(days=1): "Lunedì dell'Angelo (Pasquetta)",
        date(anno, 4, 25): "Festa della Liberazione",
        date(anno, 5, 1): "Festa del Lavoro",
        date(anno, 6, 2): "Festa della Repubblica",
        date(anno, 8, 15): "Ferragosto (Assunzione)",
        date(anno, 11, 1): "Ognissanti",
        date(anno, 12, 8): "Immacolata Concezione",
        date(anno, 12, 25): "Natale",
        date(anno, 12, 26): "Santo Stefano",
    }
    if anno >= 2026:
        f[date(anno, 10, 4)] = "San Francesco d'Assisi e Santa Caterina da Siena"
    return f


def festivi_locali_milano(anno: int) -> dict[date, str]:
    """Festivo locale di Milano: Sant'Ambrogio, patrono (7 dicembre)."""
    return {date(anno, 12, 7): "Sant'Ambrogio (patrono di Milano)"}


#: Tabella esplicita 2026-2027 (nazionali + locale Milano), utile anche per la UI.
FESTIVI_2026_2027: dict[date, str] = {}
for _a in (2026, 2027):
    FESTIVI_2026_2027.update(festivi_nazionali(_a))
    FESTIVI_2026_2027.update(festivi_locali_milano(_a))


def nome_festivo(d: date, milano: bool = True) -> str | None:
    """Nome del festivo se d e' festivo (nazionale o, con milano=True, Sant'Ambrogio)."""
    n = festivi_nazionali(d.year).get(d)
    if n is None and milano:
        n = festivi_locali_milano(d.year).get(d)
    return n


def is_lavorativo(d: date, milano: bool = True) -> bool:
    """True se d non e' sabato, domenica o festivo."""
    return d.weekday() < 5 and nome_festivo(d, milano) is None


def primo_lavorativo_da(d: date, milano: bool = True) -> date:
    """d stesso se lavorativo, altrimenti il primo giorno lavorativo successivo."""
    while not is_lavorativo(d, milano):
        d += timedelta(days=1)
    return d


def aggiungi_giorni_calendario(inizio: date, n: int) -> date:
    """inizio + n giorni di calendario (il giorno di inizio non si conta)."""
    return inizio + timedelta(days=n)


def aggiungi_giorni_lavorativi(inizio: date, n: int, milano: bool = True) -> date:
    """n-esimo giorno lavorativo DOPO inizio (inizio non si conta)."""
    if n < 0:
        raise ValueError("n deve essere >= 0")
    d, contati = inizio, 0
    while contati < n:
        d += timedelta(days=1)
        if is_lavorativo(d, milano):
            contati += 1
    return d


def giorni_lavorativi_tra(a: date, b: date, milano: bool = True) -> int:
    """Numero di giorni lavorativi in (a, b] (a escluso, b incluso)."""
    if b <= a:
        return 0
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if is_lavorativo(d, milano):
            n += 1
    return n


def data_estesa(d: date) -> str:
    """'lunedì 12 ottobre 2026'."""
    return f"{GIORNI_SETTIMANA[d.weekday()]} {d.day} {MESI[d.month - 1]} {d.year}"


def _descrivi(d: date, milano: bool) -> dict:
    return {"data": d.isoformat(), "data_estesa": data_estesa(d), "lavorativo": is_lavorativo(d, milano),
            "festivo": nome_festivo(d, milano), "weekend": d.weekday() >= 5}


def scadenza(inizio: date, n: int, tipo: str = "calendario", milano: bool = True, oggi: date | None = None) -> dict:
    """Scadenza a n giorni da 'inizio'. tipo: 'calendario' o 'lavorativi'.
    Restituisce {tipo, n, inizio, scadenza (+ data_estesa), prorogata (solo
    calendario, se cade in giorno non lavorativo), giorni_rimanenti, regola}."""
    if tipo not in ("calendario", "lavorativi"):
        raise ValueError("tipo deve essere 'calendario' o 'lavorativi'")
    if tipo == "calendario":
        s = aggiungi_giorni_calendario(inizio, n)
        regola = (f"{n} giorni di calendario dal giorno successivo a {inizio.isoformat()} "
                  "(il giorno iniziale non si conta).")
    else:
        s = aggiungi_giorni_lavorativi(inizio, n, milano)
        regola = (f"{n} giorni lavorativi dopo {inizio.isoformat()}: esclusi sabato, domenica e festivi nazionali"
                  + (", e Sant'Ambrogio (7 dicembre) a Milano." if milano else "."))
    out = {"tipo": tipo, "n": n, "inizio": inizio.isoformat(), "scadenza": _descrivi(s, milano), "regola": regola,
           "prorogata": None}
    if tipo == "calendario" and not is_lavorativo(s, milano):
        p = primo_lavorativo_da(s, milano)
        out["prorogata"] = {**_descrivi(p, milano),
                            "nota": ("La scadenza cade in un giorno non lavorativo: per la regola generale "
                                     "(art. 2963 c.c.) slitta al primo giorno lavorativo, ma verifica se vale "
                                     "per questo procedimento; la data prudente resta quella non prorogata.")}
    if oggi is not None:
        out["giorni_rimanenti"] = (s - oggi).days
    return out


def scadenza_ambigua(inizio: date, n: int, milano: bool = True, oggi: date | None = None) -> dict:
    """Per fonti ambigue ('entro n giorni' senza specificare): restituisce
    entrambe le interpretazioni (calendario e lavorativi) e indica come
    prudente la data piu' vicina."""
    cal = scadenza(inizio, n, "calendario", milano, oggi)
    lav = scadenza(inizio, n, "lavorativi", milano, oggi)
    prudente = "calendario" if cal["scadenza"]["data"] <= lav["scadenza"]["data"] else "lavorativi"
    return {
        "inizio": inizio.isoformat(), "n": n, "calendario": cal, "lavorativi": lav,
        "prudente": prudente,
        "differenza_giorni": (date.fromisoformat(lav["scadenza"]["data"]) - date.fromisoformat(cal["scadenza"]["data"])).days,
        "nota": ("La fonte non dice se i giorni sono di calendario o lavorativi: mostro entrambe le date. "
                 f"Per sicurezza considera la data piu' vicina ({prudente})."),
    }


if __name__ == "__main__":  # pragma: no cover - prova veloce
    import json
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print(json.dumps(scadenza(date(2026, 12, 3), 8, "lavorativi"), ensure_ascii=False, indent=1))
    print(json.dumps(scadenza_ambigua(date(2026, 10, 3), 20), ensure_ascii=False, indent=1))
