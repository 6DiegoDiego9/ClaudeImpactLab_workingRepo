# -*- coding: utf-8 -*-
"""JSON schemas for Claude's structured outputs (output_config.format) and a tiny validator.

All objects use additionalProperties: false and list every property as required, as the
structured-outputs API expects. Optional values are expressed as empty strings or lists.
"""
from __future__ import annotations

from typing import Any

ENTI = ["Anagrafe", "Municipio", "Prefettura", "Questura", "Scuola", "Milano Welcome Center", "Patronato", "Altro"]
CONFIDENZA = {"type": "string", "enum": ["alta", "media", "bassa"]}


def obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def arr(items: dict) -> dict:
    return {"type": "array", "items": items}


S = {"type": "string"}
B = {"type": "boolean"}

LINGUA = obj({
    "codice": {"type": "string", "description": "BCP 47, es. 'ar-EG', 'en', 'tl', 'it'"},
    "nome_it": S,
    "rtl": B,
})

FONTE = obj({
    "tipo": {"type": "string", "enum": ["faq", "pagina_comune", "dataset", "norma", "fonte_esterna", "nessuna"]},
    "id": {"type": "string", "description": "KA-xxxxx, id pagina, slug dataset o id fonte esterna; '' se nessuna"},
    "titolo": S,
    "url": S,
    "aggiornato_il": {"type": "string", "description": "Data di aggiornamento della fonte (YYYY-MM-DD) o periodo coperto del dataset; '' se non indicata"},
    "recuperato_il": {"type": "string", "description": "Data di recupero (YYYY-MM-DD)"},
})

# Phase 1: understand the story, decide which questions change the path.
SCHEMA_COMPRENSIONE = obj({
    "lingua": LINGUA,
    "riassunto_lingua_utente": {"type": "string", "description": "Cosa hai capito, nella lingua dell'utente, senza dati identificativi"},
    "riassunto_it": S,
    "procedure_ipotizzate": arr(obj({"nome_it": S, "ente": {"type": "string", "enum": ENTI}})),
    "domande": arr(obj({
        "id": {"type": "string", "description": "D1, D2, D3"},
        "testo_lingua": S,
        "testo_it": S,
        "perche_lingua": {"type": "string", "description": "Perche' la risposta cambia il percorso, nella lingua dell'utente"},
        "perche_it": S,
        "opzioni_lingua": arr(S),
    })),
    "fuori_perimetro": arr(obj({"domanda_it": S, "risposta_lingua": S, "risposta_it": S})),
    "dati_personali_omessi": B,
})

# Phase 2: the structured case card.
SCHEMA_SCHEDA = obj({
    "lingua": LINGUA,
    "sintesi_it": S,
    "sintesi_lingua_utente": S,
    "esito": obj({
        "tipo": {"type": "string", "enum": ["checklist", "instradare"]},
        "motivo_it": S,
        "motivo_lingua": S,
    }),
    "procedure": arr(obj({
        "id": {"type": "string", "description": "P1, P2, ..."},
        "nome_it": S,
        "nome_lingua": S,
        "ente": {"type": "string", "enum": ENTI},
        "cosa_fare_it": S,
        "cosa_fare_lingua": S,
        "canale_it": {"type": "string", "description": "online / sportello / portale ministero / scuola ..."},
        "fonte": FONTE,
        "confidenza": CONFIDENZA,
    })),
    "passi_fatti": arr(obj({"id": S, "testo_it": S, "testo_lingua": S, "confidenza": CONFIDENZA})),
    "passi_bloccati": arr(obj({
        "id": S, "testo_it": S, "testo_lingua": S, "motivo_it": S, "motivo_lingua": S,
        "alternativa_it": S, "alternativa_lingua": S, "fonte": FONTE, "confidenza": CONFIDENZA,
    })),
    "documenti_mancanti": arr(obj({
        "id": S,
        "documento_it": S,
        "documento_lingua": S,
        "per_procedura": {"type": "string", "description": "id della procedura (P1...)"},
        "obbligatorieta": {"type": "string", "enum": ["obbligatorio", "non_obbligatorio", "non_indicato"]},
        "fonte": FONTE,
        "confidenza": CONFIDENZA,
    })),
    "instradamento": obj({
        "id": {"type": "string", "description": "sempre 'R1'"},
        "dove": S,
        "ente": {"type": "string", "enum": ENTI},
        "perche_it": S,
        "perche_lingua": S,
        "indirizzo": S,
        "orari": S,
        "contatti": S,
        "fonte": FONTE,
        "confidenza": CONFIDENZA,
    }),
    "domande_per_operatore": arr(obj({"id": S, "testo_it": S, "perche_it": S})),
    "avvertenze": arr(obj({"id": S, "testo_it": S, "testo_lingua": S, "fonte": FONTE})),
    "faq_mancanti": arr(obj({"domanda_it": S, "tema": {"type": "string", "description": "Tema breve in italiano, es. 'Ricongiungimento', 'Scuola', 'Residenza'"}})),
    "dati_personali_omessi": B,
})

# Phase 3: an operator correction, translated back for the citizen.
SCHEMA_CORREZIONE = obj({
    "testo_corretto_it": {"type": "string", "description": "Il punto riscritto in italiano con la correzione dell'operatore"},
    "testo_corretto_lingua": {"type": "string", "description": "Lo stesso punto nella lingua del cittadino, linguaggio semplice"},
    "messaggio_cittadino_lingua": {"type": "string", "description": "Breve messaggio al cittadino: cosa e' cambiato e cosa fare ora"},
    "voce_checklist_lingua": {"type": "string", "description": "Una riga di checklist aggiornata, nella lingua del cittadino"},
    "avviso_it": {"type": "string", "description": "Se la correzione contraddice la fonte citata o dati personali sono stati omessi, spiegalo; altrimenti ''"},
})


def validate(value: Any, schema: dict, path: str = "$") -> list[str]:
    """Minimal structural validator for the subset of JSON Schema used above."""
    errors: list[str] = []
    t = schema.get("type")
    if t == "object":
        if not isinstance(value, dict):
            return [f"{path}: atteso oggetto"]
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errors.append(f"{path}.{k}: mancante")
        if schema.get("additionalProperties") is False:
            for k in value:
                if k not in props:
                    errors.append(f"{path}.{k}: proprieta' non prevista")
        for k, sub in props.items():
            if k in value:
                errors.extend(validate(value[k], sub, f"{path}.{k}"))
    elif t == "array":
        if not isinstance(value, list):
            return [f"{path}: attesa lista"]
        for i, v in enumerate(value):
            errors.extend(validate(v, schema.get("items", {}), f"{path}[{i}]"))
    elif t == "string":
        if not isinstance(value, str):
            errors.append(f"{path}: attesa stringa")
        elif "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: valore '{value}' non ammesso")
    elif t == "boolean":
        if not isinstance(value, bool):
            errors.append(f"{path}: atteso booleano")
    elif t == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{path}: atteso intero")
    return errors


def card_point_ids(card: dict) -> list[str]:
    """Ids of every point the operator can confirm or correct."""
    ids = [p["id"] for p in card.get("procedure", [])]
    ids += [p["id"] for p in card.get("passi_fatti", [])]
    ids += [p["id"] for p in card.get("passi_bloccati", [])]
    ids += [p["id"] for p in card.get("documenti_mancanti", [])]
    if card.get("instradamento"):
        ids.append(card["instradamento"]["id"] or "R1")
    ids += [p["id"] for p in card.get("avvertenze", [])]
    return ids
