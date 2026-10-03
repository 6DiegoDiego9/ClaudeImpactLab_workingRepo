"""JSON schemas for Claude's structured outputs (output_config.format) and their validation.

Both schemas are strict-compatible: every object lists all properties as required
and sets additionalProperties: false. Empty strings / 0 / [] mean "not applicable".
"""
from __future__ import annotations

from typing import Any

CAMPI_DOMANDA = ["municipio", "figli", "data_inizio_casa", "tari", "spid", "nessuna"]


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_S = {"type": "string"}
_B = {"type": "boolean"}
_I = {"type": "integer"}

FONTE = _obj({
    "etichetta": {"type": "string", "description": "es. 'FAQ KA-02121' o 'Open data ds551'"},
    "url": _S,
    "data": {"type": "string", "description": "es. 'aggiornata il 06/05/2026', 'periodo coperto 2018', 'recuperata il 03/10/2026'"},
})

PROFILO = _obj({
    "municipio": {"type": "integer", "description": "1-9, 0 se non noto"},
    "nil": _S,
    "fasce_figli": {"type": "array", "items": {"type": "string", "enum": ["0-2", "3-5", "6-10", "11-13", "14-17"]}},
    "nessun_figlio": _B,
    "bambino_in_arrivo": {"type": "string", "enum": ["si", "no", "non_detto"]},
    "data_inizio_casa": {"type": "string", "description": "YYYY-MM-DD o vuoto"},
    "data_iscrizione": {"type": "string", "description": "YYYY-MM-DD o vuoto"},
    "tari": {"type": "string", "enum": ["gia_dichiarata", "no_io_intestatario", "no_altro_intestatario", "non_so", "non_detto"]},
    "spid_o_cie": {"type": "string", "enum": ["si", "no", "non_so", "non_detto"]},
})

INTERVISTA_SCHEMA = _obj({
    "lingua": {"type": "string", "description": "codice BCP 47 della lingua della persona, es. 'ar'"},
    "direzione_testo": {"type": "string", "enum": ["rtl", "ltr"]},
    "avviso_ia": {"type": "string", "description": "'Stai parlando con un sistema automatico...' nella lingua della persona"},
    "messaggio": {"type": "string", "description": "1-2 frasi brevi nella lingua della persona"},
    "domanda": _obj({
        "campo": {"type": "string", "enum": CAMPI_DOMANDA},
        "testo": _S,
        "spiegazione": _S,
        "tipo_input": {"type": "string", "enum": ["scelta_singola", "scelta_multipla", "data", "nessuno"]},
        "opzioni": {"type": "array", "items": _obj({"valore": _S, "etichetta": _S})},
        "facoltativa": _B,
    }),
    "profilo": PROFILO,
    "pronto_per_il_piano": _B,
    "riepilogo_risposte": {"type": "string", "description": "riepilogo delle risposte nella lingua della persona, da confermare"},
})

SCADENZA = _obj({
    "tipo": {"type": "string", "enum": ["nessuna", "giorni_da_inizio_casa", "data_fissa"]},
    "giorni": {"type": "integer", "description": "per giorni_da_inizio_casa, es. 90; altrimenti 0"},
    "data_fissa": {"type": "string", "description": "YYYY-MM-DD per data_fissa, altrimenti vuoto"},
    "nota": _S,
})

PIANO_SCHEMA = _obj({
    "lingua": _S,
    "direzione_testo": {"type": "string", "enum": ["rtl", "ltr"]},
    "titolo": _S,
    "sintesi": _S,
    "azioni": {"type": "array", "items": _obj({
        "id": _S,
        "titolo": _S,
        "perche": _S,
        "come": _S,
        "canale_senza_spid": _S,
        "scadenza": SCADENZA,
        "fonti": {"type": "array", "items": FONTE},
        "avviso_freschezza": _S,
    })},
    "servizi_vicini": {"type": "array", "items": _obj({
        "categoria": {"type": "string", "enum": ["consultorio", "pediatra", "medico", "corso_italiano", "nido",
                                                 "scuola", "sportello_tributi", "anagrafe", "biblioteca", "altro"]},
        "nome": _S,
        "indirizzo": _S,
        "nil": _S,
        "motivazione": _S,
        "requisiti": _S,
        "fonte": FONTE,
        "avviso_freschezza": _S,
    })},
    "servizi_poco_conosciuti": {"type": "array", "items": _obj({"titolo": _S, "descrizione": _S, "fonte": FONTE})},
    "non_ti_riguarda": {"type": "array", "items": _obj({"titolo": _S, "perche": _S, "fonte": FONTE})},
    "piu_avanti": {"type": "array", "items": _obj({"titolo": _S, "quando": _S, "fonte": FONTE})},
    "bozza_tari": _obj({
        "stato": {"type": "string", "enum": ["da_inviare", "la_firma_un_altro", "in_ritardo", "non_serve", "da_verificare"]},
        "spiegazione": _S,
        "chi_firma": _S,
        "destinatario_pec": _S,
        "destinatario_email": _S,
        "oggetto": _S,
        "nome_allegato": _S,
        "corpo_it": _S,
        "corpo_traduzione": _S,
        "checklist_it": {"type": "array", "items": _S},
        "checklist_traduzione": {"type": "array", "items": _S},
        "alternative": _S,
        "fonti": {"type": "array", "items": FONTE},
    }),
    "riepilogo_operatore_it": _S,
    "anomalie_fonti": {"type": "array", "items": _S},
})


# ---------------------------------------------------------------------------
# Minimal validator (no external dependency): checks types, enums, required keys
# and additionalProperties: false. Returns a list of error strings.
# ---------------------------------------------------------------------------

_TYPES = {"string": str, "integer": int, "boolean": bool, "array": list, "object": dict, "number": (int, float)}


def validate(value: Any, schema: dict, path: str = "$") -> list[str]:
    errs: list[str] = []
    t = schema.get("type")
    py = _TYPES.get(t)
    if py is not None:
        if t == "integer" and isinstance(value, bool):
            return [f"{path}: atteso integer, trovato boolean"]
        if not isinstance(value, py):
            return [f"{path}: atteso {t}, trovato {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: valore {value!r} non in {schema['enum']}")
    if t == "object":
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}: manca '{k}'")
        if schema.get("additionalProperties") is False:
            for k in value:
                if k not in props:
                    errs.append(f"{path}: proprieta' non ammessa '{k}'")
        for k, sub in props.items():
            if k in value:
                errs.extend(validate(value[k], sub, f"{path}.{k}"))
    if t == "array" and "items" in schema:
        for i, it in enumerate(value):
            errs.extend(validate(it, schema["items"], f"{path}[{i}]"))
    return errs
