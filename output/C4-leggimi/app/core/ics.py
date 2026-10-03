# -*- coding: utf-8 -*-
"""
ics.py - Generazione di file calendario .ics (RFC 5545)
======================================================

* UTF-8, righe terminate da CRLF, righe piu' lunghe di 75 ottetti "piegate"
  (folding) senza spezzare i caratteri multibyte;
* testo con escape di \\ ; , e a capo;
* eventi di giornata intera (data) o con orario (datetime: se "naive" e'
  ora locale di Milano con TZID=Europe/Rome, se con fuso viene convertito in UTC);
* promemoria VALARM opzionale (es. 1 giorno prima).

Uso:
    from ics import genera_ics, salva_ics
    testo = genera_ics([{"titolo": "Dichiarazione TARI", "data": date(2026, 12, 30),
                         "descrizione": "Entro 90 giorni (KA-02121)", "url": "https://..."}],
                       allarme_minuti=24*60)
    salva_ics("scadenze.ics", testo)
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PRODID = "-//Claude Impact Lab Milano//Track 01 Accoglienza//IT"

# Definizione minima del fuso Europe/Rome (regole UE dal 1996), per i client
# che non conoscono il TZID.
VTIMEZONE_ROMA = [
    "BEGIN:VTIMEZONE", "TZID:Europe/Rome",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
    "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
    "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
    "END:VTIMEZONE",
]


def escape_testo(s: str) -> str:
    """Escape dei valori TEXT (RFC 5545, 3.3.11)."""
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,") \
        .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def piega_riga(riga: str, limite: int = 75) -> str:
    """Piega una riga a 'limite' ottetti UTF-8 (continuazione con CRLF + spazio)."""
    b = riga.encode("utf-8")
    if len(b) <= limite:
        return riga
    parti, corrente, lung, primo = [], "", 0, True
    for ch in riga:
        n = len(ch.encode("utf-8"))
        max_ = limite if primo else limite - 1  # le righe di continuazione iniziano con uno spazio
        if lung + n > max_:
            parti.append(corrente)
            corrente, lung, primo = ch, n, False
        else:
            corrente += ch
            lung += n
    parti.append(corrente)
    return "\r\n ".join(parti)


def _fmt_dt(v: date | datetime) -> tuple[str, str]:
    """Restituisce (parametri, valore) per DTSTART/DTEND."""
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            return "", v.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return ";TZID=Europe/Rome", v.strftime("%Y%m%dT%H%M%S")
    return ";VALUE=DATE", v.strftime("%Y%m%d")


def _a_data(v) -> date | datetime:
    if isinstance(v, (date, datetime)):
        return v
    s = str(v).strip()
    if "T" in s or " " in s:
        return datetime.fromisoformat(s.replace(" ", "T"))
    return date.fromisoformat(s)


def genera_ics(eventi: list[dict], nome_calendario: str = "Scadenze Milano",
               allarme_minuti: int | None = None, durata_minuti: int = 30,
               dtstamp: datetime | None = None) -> str:
    """Genera il testo .ics da una lista di {titolo, data, descrizione, url}.

    * data: date / datetime / stringa ISO ('2026-12-30' o '2026-12-30T09:00');
    * allarme_minuti: se indicato aggiunge un VALARM che suona N minuti prima
      (es. 1440 = un giorno prima);
    * dtstamp: per output deterministico nei test (default: adesso UTC).
    Restituisce una stringa con terminatori CRLF (scrivila con salva_ics)."""
    stamp = (dtstamp or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    righe = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{escape_testo(nome_calendario)}", "X-WR-TIMEZONE:Europe/Rome"]
    dati = [(_a_data(e["data"]), e) for e in eventi]
    if any(isinstance(d, datetime) and d.tzinfo is None for d, _ in dati):
        righe += VTIMEZONE_ROMA
    for d, e in dati:
        titolo = e.get("titolo") or "Scadenza"
        uid_src = f"{titolo}|{d.isoformat()}|{e.get('url') or ''}"
        uid = hashlib.sha1(uid_src.encode("utf-8")).hexdigest()[:24] + "@impactlab-milano"
        p_ini, v_ini = _fmt_dt(d)
        if isinstance(d, datetime):
            p_fin, v_fin = _fmt_dt(d + timedelta(minutes=durata_minuti))
        else:
            p_fin, v_fin = _fmt_dt(d + timedelta(days=1))  # DTEND esclusivo per eventi di giornata intera
        descr = e.get("descrizione") or ""
        if e.get("url"):
            descr = (descr + "\n\nFonte: " + e["url"]).strip()
        righe += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{stamp}", f"DTSTART{p_ini}:{v_ini}",
                  f"DTEND{p_fin}:{v_fin}", f"SUMMARY:{escape_testo(titolo)}"]
        if descr:
            righe.append(f"DESCRIPTION:{escape_testo(descr)}")
        if e.get("url"):
            righe.append(f"URL:{e['url']}")
        righe.append("TRANSP:TRANSPARENT")
        if allarme_minuti is not None:
            righe += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escape_testo('Promemoria: ' + titolo)}",
                      f"TRIGGER:-PT{int(allarme_minuti)}M", "END:VALARM"]
        righe.append("END:VEVENT")
    righe.append("END:VCALENDAR")
    return "\r\n".join(piega_riga(r) for r in righe) + "\r\n"


def salva_ics(path: str | Path, testo: str) -> Path:
    """Scrive il file .ics in UTF-8 senza convertire i CRLF."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(testo)
    return p


def ics_bytes(eventi: list[dict], **kw) -> bytes:
    """Comodo per FastAPI: Response(content=ics_bytes(...), media_type='text/calendar; charset=utf-8')."""
    return genera_ics(eventi, **kw).encode("utf-8")
