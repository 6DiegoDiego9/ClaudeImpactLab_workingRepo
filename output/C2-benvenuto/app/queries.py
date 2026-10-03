"""Library of named, live-tested queries on the Comune di Milano open data.

Every query here was run live against dati.comune.milano.it (CKAN datastore SQL)
and virtuoso-prod.comune.milano.it (SPARQL) on 3 Oct 2026. Claude calls them
through the `run_named_query` tool; parameters are validated here (municipio is an
integer 1-9, the rest are enums), so no free text ever reaches the SQL/SPARQL.

Privacy: ds234/ds235 contain doctors' names and birth dates. The queries below
select ONLY the clinic address, NIL and a count, never the personal columns.
"""
from __future__ import annotations

from typing import Any

from app import config  # noqa: F401  (configures milano_tools paths)
import milano_tools as mt

# Datasets the prototype is allowed to query (CKAN identifiers).
DATASETS = {
    "ds235": "Pediatri di libera scelta (ambulatori)",
    "ds234": "Medici di medicina generale (ambulatori)",
    "ds551": "Scuole di italiano per stranieri e CPIA",
    "ds47": "Asili nido, localizzazione delle strutture",
    "ds1304": "Sportelli tributi",
    "ds561": "Consultori pubblici",
    "ds549": "Sedi dei servizi anagrafici",
}

# Static resource ids verified on 3 Oct 2026. ds234/ds235 change id at every weekly
# update, so they are always resolved through package_show (see resource_id()).
STATIC_RESOURCES = {
    "ds551": "f04c6715-0dd0-4821-949d-f53fa56df8f5",
    "ds47": "372d6b0e-af5b-4dad-a9c3-4fa0318a7dc8",
    "ds1304": "f1acb239-56c6-408d-a960-2859a6e0ce81",
    "ds561": "be81d419-a859-4fbc-b1a5-67a78167ab5d",
    "ds549": "48b24517-765e-4f6f-8b30-9094a212eb85",
}
DYNAMIC = ("ds235", "ds234")

# Columns that must never leave the tool layer (doctors' personal data).
PERSONAL_COLUMNS = {"nomemedico", "cognomemedico", "datanascita", "idmedico", "codice_regionale_medico"}

_rid_cache: dict[str, str] = {}
_meta_cache: dict[str, dict] = {}


def dataset_meta(code: str) -> dict:
    """CKAN metadata (coverage, frequency, freshness warning), cached per process."""
    code = code.lower()
    if code not in _meta_cache:
        _meta_cache[code] = mt.ckan_dataset_meta(code)
    return _meta_cache[code]


def resource_id(code: str) -> str:
    """Datastore resource id for a dataset code (resolved live for ds234/ds235)."""
    code = code.lower()
    if code in STATIC_RESOURCES:
        return STATIC_RESOURCES[code]
    if code not in _rid_cache:
        meta = dataset_meta(code)
        active = [r for r in meta["risorse"] if r["datastore_active"]]
        if not active:
            raise mt.FonteNonDisponibile(f"{code}: nessuna risorsa con datastore attivo")
        _rid_cache[code] = active[0]["id"]
    return _rid_cache[code]


def allowlist() -> set[str]:
    """Resource ids that free SQL may touch."""
    ids = set(STATIC_RESOURCES.values())
    for code in DYNAMIC:
        try:
            ids.add(resource_id(code))
        except Exception:  # noqa: BLE001 - CKAN down: the static ids still work
            pass
    return ids


def strip_personal(rows: list[dict]) -> list[dict]:
    return [{k: v for k, v in r.items() if k.lower() not in PERSONAL_COLUMNS} for r in rows]


def source_info(code: str) -> dict:
    """Citation block for a dataset: slug, URL, coverage, frequency, freshness warning."""
    try:
        m = dataset_meta(code)
    except Exception as e:  # noqa: BLE001
        return {"dataset": code, "errore_metadati": str(e)}
    return {"dataset": code, "slug": m["slug"], "titolo": m["titolo"], "url": m["url_pagina"],
            "periodo_coperto": f"{m['temporal_start']} - {m['temporal_end']}",
            "frequenza": m["frequency"], "modificato_il": m["modified"],
            "avviso_freschezza": m["avviso_freschezza"], "recuperato_il": m["recuperato_il"]}


# ---------------------------------------------------------------------------
# Query builders. Each returns (kind, query_text, dataset_code).
# ---------------------------------------------------------------------------

def _q_ambulatori(code: str, m: int) -> str:
    rid = resource_id(code)
    return (f'SELECT "via", "civico", "CAP", "ID_NIL", "NIL", COUNT(*) AS medici_attivi '
            f'FROM "{rid}" WHERE "MUNICIPIO" = {m} AND "attivo" = 1 '
            f'GROUP BY "via", "civico", "CAP", "ID_NIL", "NIL" ORDER BY medici_attivi DESC, "NIL" LIMIT 15')


def _q_scuole_italiano(m: int, filtro: str) -> str:
    rid = STATIC_RESOURCES["ds551"]
    # "Zona" is inconsistent in the source ('Zona 2' and '2'): keep only the digits.
    where = [f"regexp_replace(\"Zona\", '[^0-9]', '', 'g') = '{m}'"]
    if filtro in ("gratis_babysitting_a1", "gratis_a1"):
        where.append('"gratis" = 1')
        where.append('("Livello-a1-elementare" = 1 OR "Livello-principianti" = 1)')
    if filtro == "gratis_babysitting_a1":
        where.append('"baby-sitting" = 1')
    return ('SELECT "Nome-associazione", "indirizzo", "NIL", "Zona", "tipo", "gratis", "baby-sitting", '
            '"Livello-principianti", "Livello-a1-elementare", "In regola con il permesso di soggiorno", '
            '"tipologia utenti 1", "tipologia utenti 2", "permalink" '
            f'FROM "{rid}" WHERE ' + " AND ".join(where) + ' ORDER BY "NIL" LIMIT 30')


def _q_consultori(m: int) -> str:
    rid = STATIC_RESOURCES["ds561"]
    return ('SELECT "DENOM_STRUTTURA", "INDIRIZZO_UBICAZIONE", "CAP", "NIL", "DENOM_GESTORE" '
            f'FROM "{rid}" WHERE "MUNICIPIO" = {m} LIMIT 20')


def _q_nidi(m: int) -> str:
    rid = STATIC_RESOURCES["ds47"]
    return ('SELECT "NOMINATIVO", "TIPO_VIA", "INDIRIZZO", "NUMEROCIVICO", "NIL", "TIPO_STRUTTURA", '
            '"CODANNOSCOLASTICO" '
            f'FROM "{rid}" WHERE "MUNICIPIO" = {m} AND "GRADO" = \'Nido d\'\'infanzia\' '
            f'AND "TIPO_STRUTTURA" = \'Comunale\' '
            f'AND "CODANNOSCOLASTICO" = (SELECT MAX("CODANNOSCOLASTICO") FROM "{rid}") '
            'ORDER BY "NIL" LIMIT 30')


def _q_sportello_tributi(m: int) -> str:
    rid = STATIC_RESOURCES["ds1304"]
    return ('SELECT "Sportello tributi", "Indirizzo", "civico", "orari", "telefono", "appuntamento", '
            f'"sito web per prendere appuntamento", "NIL" FROM "{rid}" '
            f'WHERE "Sportello tributi" = \'Sportello tributi Municipio {m}\' LIMIT 5')


def _q_sedi_anagrafiche(m: int) -> str:
    rid = STATIC_RESOURCES["ds549"]
    return (f'SELECT "titolo", "Indirizzo", "telefono", "orari", "Note", "NIL" FROM "{rid}" '
            f'WHERE "titolo" ILIKE \'%Municipio {m}%\' OR "titolo" ILIKE \'%centrale%\' LIMIT 10')


_SPARQL_BIBLIOTECHE = """
PREFIX bo: <https://dati.comune.milano.it/biblioteche/onto/>
PREFIX om: <https://dati.comune.milano.it/ontomi/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?nome ?indirizzo ?orari ?note
WHERE {
  GRAPH <https://dati.comune.milano.it/data/biblioteche> {
    ?a a bo:BibliotecaAnagrafica ; om:nome ?nome ; bo:orarioBiblioteca ?orari ; om:haIndirizzo ?i .
    ?i om:indirizzoCompleto ?indirizzo ; om:haMunicipio <https://dati.comune.milano.it/data/Municipio/%d> .
    OPTIONAL { ?a rdfs:comment ?note }
  }
}
ORDER BY ?nome LIMIT 20""".strip()

GRADI_SCUOLA = {
    "infanzia": "Scuola dell'Infanzia",
    "primaria": "Scuola Primaria",
    "secondaria_primo_grado": "Scuola Secondaria di Primo Grado",
}

_SPARQL_SCUOLE = """
PREFIX so: <https://dati.comune.milano.it/scuole/onto/>
PREFIX om: <https://dati.comune.milano.it/ontomi/>
SELECT ?nome ?indirizzo ?nil ?gestione ?paritaria ?anno
WHERE {
  GRAPH <https://dati.comune.milano.it/data/scuole> {
    ?c a so:ScuolaCaratteristiche ; so:annoScolastico ?anno ; so:gradoScuola ?g ;
       so:riferiteAScuola ?s ; om:haIndirizzo ?i ; so:tipoStruttura ?gestione .
    OPTIONAL { ?c so:paritaria ?paritaria }
    ?s om:nome ?nome .
    ?i om:indirizzoCompleto ?indirizzo ; om:haMunicipio <https://dati.comune.milano.it/data/Municipio/%d> ; om:haNIL ?n .
    ?n om:nil ?nil .
    FILTER(STR(?anno) = "2025/2026" && STR(?g) = "%s")
  }
}
ORDER BY ?nil ?nome LIMIT 40""".strip()

_SPARQL_ISCRIZIONI = mt.SPARQL_ESEMPI["iscrizioni_immigrazione_per_anno"]

NAMED = {
    "pediatri_municipio": "Ambulatori dei pediatri di libera scelta attivi nel municipio (ds235): solo indirizzo, NIL e numero di pediatri, mai nomi.",
    "medici_municipio": "Ambulatori dei medici di medicina generale attivi nel municipio (ds234): solo indirizzo, NIL e numero di medici, mai nomi.",
    "scuole_italiano": "Scuole di italiano per stranieri nel municipio (ds551, dato del 2018), con filtro su gratuita', baby-sitting e livello A1/principianti.",
    "consultori_municipio": "Consultori familiari pubblici nel municipio (ds561, aggiornamento mensile).",
    "nidi_municipio": "Nidi d'infanzia comunali nel municipio (ds47, ultimo anno disponibile: dato vecchio 2016-2019).",
    "sportello_tributi_municipio": "Sportello tributi del municipio (ds1304, dato 2020-2021, orari spesso 'n.d.').",
    "sedi_anagrafiche_municipio": "Sedi anagrafiche del municipio e sede centrale (ds549, aggiornato al 28/01/2026): utile per la prima CIE.",
    "biblioteche_municipio": "Biblioteche comunali del municipio con orari (SPARQL, grafo LOD biblioteche).",
    "scuole_municipio": "Scuole dell'infanzia, primarie o secondarie di primo grado del municipio, anno 2025/2026 (SPARQL, grafo LOD scuole).",
    "iscrizioni_immigrazione_per_anno": "Pratiche di iscrizione anagrafica per immigrazione per anno (SPARQL, grafo atti-pubblici): contesto, sono pratiche e non persone.",
}


def build(nome: str, municipio: int, grado_scuola: str = "primaria", filtro_corsi: str = "gratis_babysitting_a1") -> tuple[str, str, str | None]:
    """Return (kind, query, dataset_code) for a named query. Raises ValueError on bad params."""
    if nome not in NAMED:
        raise ValueError(f"Query sconosciuta: {nome}. Disponibili: {', '.join(NAMED)}")
    m = int(municipio)
    if nome != "iscrizioni_immigrazione_per_anno" and not 1 <= m <= 9:
        raise ValueError("municipio deve essere un intero da 1 a 9")
    if nome == "pediatri_municipio":
        return "sql", _q_ambulatori("ds235", m), "ds235"
    if nome == "medici_municipio":
        return "sql", _q_ambulatori("ds234", m), "ds234"
    if nome == "scuole_italiano":
        if filtro_corsi not in ("gratis_babysitting_a1", "gratis_a1", "tutti"):
            raise ValueError("filtro_corsi non valido")
        return "sql", _q_scuole_italiano(m, filtro_corsi), "ds551"
    if nome == "consultori_municipio":
        return "sql", _q_consultori(m), "ds561"
    if nome == "nidi_municipio":
        return "sql", _q_nidi(m), "ds47"
    if nome == "sportello_tributi_municipio":
        return "sql", _q_sportello_tributi(m), "ds1304"
    if nome == "sedi_anagrafiche_municipio":
        return "sql", _q_sedi_anagrafiche(m), "ds549"
    if nome == "biblioteche_municipio":
        return "sparql", _SPARQL_BIBLIOTECHE % m, None
    if nome == "scuole_municipio":
        if grado_scuola not in GRADI_SCUOLA:
            raise ValueError("grado_scuola deve essere infanzia, primaria o secondaria_primo_grado")
        return "sparql", _SPARQL_SCUOLE % (m, GRADI_SCUOLA[grado_scuola]), None
    return "sparql", _SPARQL_ISCRIZIONI, None


SPARQL_SOURCES = {
    "biblioteche_municipio": {"grafo": "https://dati.comune.milano.it/data/biblioteche",
                              "endpoint": mt.SPARQL_ENDPOINT, "nota": "Linked Open Data del Comune, grafo biblioteche"},
    "scuole_municipio": {"grafo": "https://dati.comune.milano.it/data/scuole", "endpoint": mt.SPARQL_ENDPOINT,
                         "nota": "Linked Open Data del Comune, grafo scuole, anno scolastico 2025/2026"},
    "iscrizioni_immigrazione_per_anno": {"grafo": "https://dati.comune.milano.it/data/atti-pubblici",
                                         "endpoint": mt.SPARQL_ENDPOINT,
                                         "nota": "Pratiche, non persone; comprendono chi arriva da altri comuni"},
}


def run(nome: str, municipio: int, grado_scuola: str = "primaria",
        filtro_corsi: str = "gratis_babysitting_a1") -> dict[str, Any]:
    """Execute a named query live (with file cache fallback) and attach source/freshness info."""
    kind, q, code = build(nome, municipio, grado_scuola, filtro_corsi)
    if kind == "sql":
        res = mt.ckan_sql(q, allowlist())
        rows = strip_personal(res["righe"])
        for r in rows:
            r.pop("_full_text", None)
        return {"query": nome, "tipo": "sql", "sql_eseguita": res["sql_eseguita"], "n_righe": len(rows),
                "righe": rows, "fonte": source_info(code), "recuperato_il": res["recuperato_il"],
                "da_cache": res["da_cache"], "avviso_rete": res["avviso"]}
    res = mt.sparql(q)
    return {"query": nome, "tipo": "sparql", "sparql_eseguita": q, "n_righe": len(res["righe"]),
            "righe": res["righe"], "fonte": SPARQL_SOURCES.get(nome), "recuperato_il": res["recuperato_il"],
            "da_cache": res["da_cache"], "avviso_rete": res["avviso"]}
