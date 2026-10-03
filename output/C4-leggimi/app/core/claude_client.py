# -*- coding: utf-8 -*-
"""
claude_client.py - Loop agentico manuale con tool, riusabile dai prototipi
==========================================================================

Basato sull'SDK Anthropic Python 1.11 (riferimento: skill claude-api,
python/README.md e tool-use.md). Regole applicate:

* modello da env CLAUDE_MODEL (default "claude-opus-5-5"); su Opus 5.5 il
  thinking e' sempre attivo: il parametro `thinking` NON si passa;
* profondita' con output_config={"effort": ...} (env CLAUDE_EFFORT, default "medium");
* tool_choice forzato (any/tool) da' 400 su Opus 5.5: si usa auto (default),
  un'istruzione nel prompt e tool con strict: true (additionalProperties: false);
* niente assistant prefill;
* output strutturato con output_config={"format": {"type": "json_schema", ...}},
  combinabile con i tool;
* tutti i tool_result di un turno in UN SOLO messaggio user; errori dei tool
  con is_error: true;
* si controlla stop_reason (refusal + stop_details, pause_turn, max_tokens)
  prima di leggere il contenuto;
* fallback sui rifiuti abilitato di default: client.beta.messages.create(...,
  betas=["server-side-fallback-2026-07-01"], fallbacks="default"); se l'API
  risponde 400 su fallbacks si ripete con client.messages.create senza;
* prompt caching con cache_control={"type": "ephemeral"} top-level;
* max_tokens 16000 (chiamate non streaming).

API principali:
    has_credentials() -> bool
    run_agent(system, messages, tools, tool_impls, output_schema=None, max_turns=8, on_event=None, ...)
    tool_defs_from(...)                 definizioni strict da funzioni o dict
    image_block_from_file(path) / image_block_from_bytes(data, media_type)
    save_fixture(path, payload) / load_fixture(path)   utility di replay
    to_jsonable(obj)                    serializza messaggi con blocchi SDK
"""
from __future__ import annotations

import base64
import inspect
import json
import mimetypes
import os
import time
import typing
from pathlib import Path
from typing import Any, Callable

#: Testo del banner da mostrare quando manca la chiave (modalita' demo offline).
DEMO_BANNER = ("Modalità demo offline: risposte di esempio preparate a mano, Claude non viene chiamato. "
               "Aggiungi ANTHROPIC_API_KEY nel .env per l'uso reale")

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOKENS_DEFAULT = 16000
MAX_TOOL_RESULT_CHARS = 30000

_dotenv_caricato = False


def _carica_dotenv() -> None:
    """Carica il .env della cartella corrente (o superiori) una sola volta,
    senza sovrascrivere variabili gia' impostate."""
    global _dotenv_caricato
    if _dotenv_caricato:
        return
    _dotenv_caricato = True
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True), override=False)
    except Exception:  # noqa: BLE001 - python-dotenv assente o .env illeggibile
        pass


def has_credentials() -> bool:
    """True se ANTHROPIC_API_KEY o ANTHROPIC_AUTH_TOKEN sono impostati (anche via .env)."""
    _carica_dotenv()
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip() or os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip())


def default_model() -> str:
    _carica_dotenv()
    return os.environ.get("CLAUDE_MODEL", "").strip() or "claude-opus-5-5"


def default_effort() -> str:
    _carica_dotenv()
    return os.environ.get("CLAUDE_EFFORT", "").strip() or "medium"


def make_client(**kwargs):
    """Crea anthropic.Anthropic() (credenziali dall'ambiente). Import ritardato:
    il modulo si importa anche senza SDK, per la modalita' demo."""
    import anthropic
    _carica_dotenv()
    kwargs.setdefault("timeout", 120.0)
    return anthropic.Anthropic(**kwargs)


# ---------------------------------------------------------------------------
# Messaggi d'errore in italiano
# ---------------------------------------------------------------------------

def messaggio_errore(e: Exception) -> str:
    """Traduce le eccezioni dell'SDK in un messaggio in italiano per l'utente."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return f"Errore: {e}"
    if isinstance(e, anthropic.AuthenticationError):
        return "Chiave API non valida o mancante: controlla ANTHROPIC_API_KEY nel file .env."
    if isinstance(e, anthropic.PermissionDeniedError):
        return "La chiave API non ha i permessi per questa richiesta (o per questo modello)."
    if isinstance(e, anthropic.NotFoundError):
        return "Modello o endpoint non trovato: controlla CLAUDE_MODEL."
    if isinstance(e, anthropic.RateLimitError):
        ra = None
        try:
            ra = e.response.headers.get("retry-after")
        except Exception:  # noqa: BLE001
            pass
        return "Troppe richieste a Claude in poco tempo: riprova" + (f" tra {ra} secondi." if ra else " tra poco.")
    if isinstance(e, anthropic.BadRequestError):
        return f"Richiesta non valida per l'API di Claude: {getattr(e, 'message', e)}"
    if isinstance(e, anthropic.APITimeoutError):
        return "Claude non ha risposto in tempo (timeout): riprova."
    if isinstance(e, anthropic.APIConnectionError):
        return "Impossibile raggiungere l'API di Claude: controlla la connessione di rete."
    if isinstance(e, anthropic.APIStatusError):
        if getattr(e, "status_code", 0) >= 500:
            return f"Il servizio di Claude e' temporaneamente non disponibile (errore {e.status_code}): riprova piu' tardi."
        return f"Errore dell'API di Claude ({getattr(e, 'status_code', '?')}): {getattr(e, 'message', e)}"
    return f"Errore imprevisto: {type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Serializzazione e utility di replay
# ---------------------------------------------------------------------------

def to_jsonable(obj: Any) -> Any:
    """Converte (ricorsivamente) oggetti SDK (pydantic) in strutture JSON."""
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json", exclude_none=True)
        except TypeError:
            return obj.model_dump()
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return {k: to_jsonable(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


def save_fixture(path: str | os.PathLike, payload: Any) -> Path:
    """Salva una fixture JSON (UTF-8, indentata) convertendo gli oggetti SDK."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_fixture(path: str | os.PathLike) -> Any:
    """Carica una fixture JSON salvata con save_fixture."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Immagini (visione)
# ---------------------------------------------------------------------------

def image_block_from_bytes(data: bytes, media_type: str) -> dict:
    """Blocco immagine base64 da mettere nel content di un messaggio user.
    media_type: image/jpeg, image/png, image/gif o image/webp."""
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                        "data": base64.standard_b64encode(data).decode("ascii")}}


def image_block_from_file(path: str | os.PathLike) -> dict:
    """Blocco immagine base64 da un file locale (tipo dedotto dall'estensione)."""
    p = Path(path)
    mt = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    if mt == "image/jpg":
        mt = "image/jpeg"
    return image_block_from_bytes(p.read_bytes(), mt)


# ---------------------------------------------------------------------------
# Definizioni di tool strict
# ---------------------------------------------------------------------------

_PY2JSON = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _schema_tipo(ann: Any) -> dict:
    if ann in _PY2JSON:
        return {"type": _PY2JSON[ann]}
    origin = typing.get_origin(ann)
    if origin in (list, typing.List):
        args = typing.get_args(ann)
        return {"type": "array", "items": _schema_tipo(args[0]) if args else {"type": "string"}}
    if origin is typing.Literal:
        vals = list(typing.get_args(ann))
        return {"type": _PY2JSON.get(type(vals[0]), "string"), "enum": vals}
    return {"type": "string"}


def tool_defs_from(*items: Any) -> list[dict]:
    """Costruisce definizioni di tool strict (strict: true,
    additionalProperties: false, tutti i parametri required).

    Accetta:
    * funzioni Python annotate: nome = nome della funzione, descrizione = prima
      parte della docstring, parametri dagli annotation (str/int/float/bool/
      list[...]/Literal[...]);
    * dict {name, description, input_schema} (lo schema viene reso strict);
    * dict {name, description, properties} (scorciatoia).
    """
    out = []
    for it in items:
        if isinstance(it, (list, tuple)):
            out.extend(tool_defs_from(*it))
            continue
        if callable(it) and not isinstance(it, dict):
            sig = inspect.signature(it)
            hints = typing.get_type_hints(it)
            props = {}
            for n, par in sig.parameters.items():
                if par.kind in (par.VAR_POSITIONAL, par.VAR_KEYWORD):
                    continue
                props[n] = _schema_tipo(hints.get(n, str))
            doc = inspect.getdoc(it) or it.__name__
            out.append({"name": it.__name__, "description": doc.split("\n\n")[0].strip()[:1024], "strict": True,
                        "input_schema": {"type": "object", "properties": props, "required": list(props),
                                         "additionalProperties": False}})
            continue
        d = dict(it)
        schema = dict(d.get("input_schema") or {"type": "object", "properties": d.pop("properties", {})})
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        schema.setdefault("required", list(schema["properties"]))
        schema["additionalProperties"] = False
        out.append({"name": d["name"], "description": d.get("description", ""), "strict": True,
                    "input_schema": schema})
    return out


# ---------------------------------------------------------------------------
# Loop agentico
# ---------------------------------------------------------------------------

def _blocchi(content: Any) -> list:
    return list(content or [])


def _attr(b: Any, nome: str, default: Any = None) -> Any:
    if isinstance(b, dict):
        return b.get(nome, default)
    return getattr(b, nome, default)


def _sintesi(x: Any, n: int = 300) -> str:
    try:
        s = x if isinstance(x, str) else json.dumps(to_jsonable(x), ensure_ascii=False)
    except (TypeError, ValueError):
        s = str(x)
    return s if len(s) <= n else s[: n - 1] + "…"


def _contenuto_tool(risultato: Any) -> str | list:
    """Il risultato del tool diventa testo (JSON se non e' gia' stringa); se e'
    gia' una lista di blocchi (es. immagini) viene passato cosi' com'e'."""
    if isinstance(risultato, list) and risultato and isinstance(risultato[0], dict) and "type" in risultato[0]:
        return risultato
    s = risultato if isinstance(risultato, str) else json.dumps(to_jsonable(risultato), ensure_ascii=False)
    if len(s) > MAX_TOOL_RESULT_CHARS:
        s = s[:MAX_TOOL_RESULT_CHARS] + f"\n[... risultato troncato a {MAX_TOOL_RESULT_CHARS} caratteri]"
    return s


def _somma_usage(tot: dict, usage: Any) -> None:
    if usage is None:
        return
    for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
        v = _attr(usage, k)
        if isinstance(v, int):
            tot[k] = tot.get(k, 0) + v


def _chiama(client: Any, kwargs: dict, stato: dict, emit: Callable[[dict], None]) -> Any:
    """Prima prova con il fallback sui rifiuti (beta); su 400 riprova senza."""
    if stato.get("usa_fallbacks"):
        try:
            return client.beta.messages.create(**kwargs, betas=[FALLBACK_BETA], fallbacks="default")
        except Exception as e:  # noqa: BLE001
            if _e_bad_request(e):
                stato["usa_fallbacks"] = False
                emit({"tipo": "error", "nome": "fallbacks",
                      "output_sintesi": "Fallback sui rifiuti non accettato (400): riprovo senza. " + _sintesi(str(e), 200)})
            else:
                raise
    return client.messages.create(**kwargs)


def _e_bad_request(e: Exception) -> bool:
    try:
        import anthropic
        if isinstance(e, anthropic.BadRequestError):
            return True
    except ImportError:  # pragma: no cover
        pass
    return getattr(e, "status_code", None) == 400


def run_agent(system: str | list | None, messages: list, tools: list | None, tool_impls: dict[str, Callable] | None,
              output_schema: dict | None = None, max_turns: int = 8, on_event: Callable[[dict], None] | None = None,
              *, client: Any = None, model: str | None = None, effort: str | None = None,
              max_tokens: int = MAX_TOKENS_DEFAULT, use_fallbacks: bool = True, cache: bool = True) -> dict:
    """Esegue un loop agentico con tool fino alla risposta finale.

    Parametri:
        system: prompt di sistema (stringa o lista di blocchi).
        messages: storia iniziale (lista di messaggi). Non viene modificata: la
            storia completa append-only e' restituita in 'messages' (con
            response.content dell'assistente cosi' com'e').
        tools: definizioni dei tool (meglio strict, vedi tool_defs_from).
        tool_impls: {nome_tool: funzione(input_dict) -> risultato}.
        output_schema: JSON Schema della risposta finale (output_config.format).
        max_turns: numero massimo di chiamate a Claude.
        on_event: callback chiamata a ogni evento (per lo streaming in UI).

    Restituisce {final_text, parsed, messages, events, usage, model, stop_reason, errore}.
    Gli eventi sono {tipo: tool_call|tool_result|assistant_text|refusal|error,
    nome, input, output_sintesi, ms}.
    """
    client = client or make_client()
    model = model or default_model()
    effort = effort or default_effort()
    tool_impls = tool_impls or {}
    storia = list(messages)
    eventi: list[dict] = []
    usage: dict = {}
    stato = {"usa_fallbacks": use_fallbacks}
    risultato = {"final_text": "", "parsed": None, "messages": storia, "events": eventi, "usage": usage,
                 "model": model, "stop_reason": None, "errore": None}

    def emit(ev: dict) -> None:
        ev = {"tipo": ev.get("tipo"), "nome": ev.get("nome"), "input": ev.get("input"),
              "output_sintesi": ev.get("output_sintesi"), "ms": ev.get("ms")}
        eventi.append(ev)
        if on_event:
            try:
                on_event(ev)
            except Exception:  # noqa: BLE001 - la UI non deve rompere il loop
                pass

    output_config: dict = {"effort": effort}
    if output_schema:
        output_config["format"] = {"type": "json_schema", "schema": output_schema}

    for turno in range(max_turns):
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": storia, "output_config": output_config}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        if cache:
            kwargs["cache_control"] = {"type": "ephemeral"}
        t0 = time.perf_counter()
        try:
            resp = _chiama(client, kwargs, stato, emit)
        except Exception as e:  # noqa: BLE001
            msg = messaggio_errore(e)
            emit({"tipo": "error", "nome": type(e).__name__, "output_sintesi": msg,
                  "ms": int((time.perf_counter() - t0) * 1000)})
            risultato["errore"] = msg
            return risultato
        ms_api = int((time.perf_counter() - t0) * 1000)
        _somma_usage(usage, _attr(resp, "usage"))
        risultato["model"] = _attr(resp, "model", model)
        stop = _attr(resp, "stop_reason")
        risultato["stop_reason"] = stop
        content = _blocchi(_attr(resp, "content"))
        # Storia append-only: il contenuto dell'assistente cosi' com'e'
        storia.append({"role": "assistant", "content": content})

        testi = [_attr(b, "text", "") for b in content if _attr(b, "type") == "text"]
        for t in testi:
            if t.strip():
                emit({"tipo": "assistant_text", "nome": None, "output_sintesi": _sintesi(t, 500), "ms": ms_api})

        if stop == "refusal":
            det = _attr(resp, "stop_details")
            cat = _attr(det, "category") if det else None
            spieg = _attr(det, "explanation") if det else None
            msg = "Claude ha rifiutato di rispondere a questa richiesta" + (f" (categoria: {cat})" if cat else "") + "."
            emit({"tipo": "refusal", "nome": cat, "output_sintesi": spieg or msg, "ms": ms_api})
            risultato["final_text"] = "\n".join(testi).strip() or msg
            risultato["errore"] = msg
            return risultato

        if stop == "pause_turn":
            # Turno sospeso lato server: si rimanda la storia cosi' com'e' per riprendere.
            continue

        tool_uses = [b for b in content if _attr(b, "type") == "tool_use"]

        if stop == "max_tokens":
            emit({"tipo": "error", "nome": "max_tokens",
                  "output_sintesi": "Risposta troncata: raggiunto il limite di max_tokens.", "ms": ms_api})
            risultato["final_text"] = "\n".join(testi).strip()
            risultato["errore"] = "Risposta troncata (max_tokens)."
            return risultato

        if stop == "tool_use" and tool_uses:
            blocchi_risultato = []
            for tu in tool_uses:
                nome, inp, tid = _attr(tu, "name"), _attr(tu, "input") or {}, _attr(tu, "id")
                emit({"tipo": "tool_call", "nome": nome, "input": to_jsonable(inp)})
                t1 = time.perf_counter()
                is_error = False
                impl = tool_impls.get(nome)
                if impl is None:
                    out, is_error = f"Errore: tool sconosciuto '{nome}'.", True
                else:
                    try:
                        out = impl(inp)
                    except Exception as e:  # noqa: BLE001 - l'errore torna a Claude come is_error
                        out, is_error = f"Errore nel tool {nome}: {type(e).__name__}: {e}", True
                ms = int((time.perf_counter() - t1) * 1000)
                blocco = {"type": "tool_result", "tool_use_id": tid, "content": _contenuto_tool(out)}
                if is_error:
                    blocco["is_error"] = True
                blocchi_risultato.append(blocco)
                emit({"tipo": "tool_result", "nome": nome, "input": to_jsonable(inp),
                      "output_sintesi": ("[ERRORE] " if is_error else "") + _sintesi(out), "ms": ms})
            # Tutti i risultati del turno in UN SOLO messaggio user
            storia.append({"role": "user", "content": blocchi_risultato})
            continue

        # end_turn / stop_sequence: risposta finale
        testo = "\n".join(testi).strip()
        risultato["final_text"] = testo
        if output_schema:
            try:
                risultato["parsed"] = json.loads(testi[0] if testi else "")
            except (ValueError, IndexError) as e:
                emit({"tipo": "error", "nome": "json", "output_sintesi": f"JSON finale non valido: {e}"})
                risultato["errore"] = "La risposta finale non e' un JSON valido."
        return risultato

    emit({"tipo": "error", "nome": "max_turns",
          "output_sintesi": f"Raggiunto il numero massimo di turni ({max_turns}) senza una risposta finale."})
    risultato["errore"] = f"Numero massimo di turni ({max_turns}) raggiunto."
    return risultato


__all__ = ["DEMO_BANNER", "has_credentials", "default_model", "default_effort", "make_client", "run_agent",
           "tool_defs_from", "image_block_from_file", "image_block_from_bytes", "save_fixture", "load_fixture",
           "to_jsonable", "messaggio_errore"]
