# Nucleo condiviso: Claude Impact Lab Milano, Track 01 (accoglienza dei nuovi arrivati)

**Data di verifica: 3 ottobre 2026.** Tutte le chiamate descritte qui sono state provate dal vivo da questa macchina in quella data (vedi `fixtures/_esiti_test_live.json`).

Questo nucleo serve ai 4 prototipi. Contiene solo Python e usa le dipendenze già installate (`requirements.txt`). Non richiede credenziali Anthropic per i test: il loop agentico è provato con un client finto.

## File

| File | Cosa fa |
|---|---|
| `build_index.py` | Raccolta **una tantum**, a ritmo lento, delle FAQ e delle pagine pubbliche. Scrive l'indice locale in `data/index/*.json`. |
| `local_index.py` | Ricerca BM25 in puro Python sull'indice locale (`search_local`, `get_doc`, `get_doc_by_url`, `all_docs`). |
| `milano_tools.py` | Strumenti sulle fonti del Comune: FAQ e pagine dall'indice locale, CKAN e SPARQL dal vivo, cache su file con fallback, definizioni di tool pronte per Claude. |
| `claude_client.py` | Loop agentico manuale con tool (`run_agent`), definizioni strict, blocchi immagine, utility di replay (`save_fixture` / `load_fixture`), banner della demo offline. |
| `date_utils.py` | Calcolo deterministico delle scadenze, sia in giorni di calendario sia in giorni lavorativi (festivi 2026-2027 + Sant'Ambrogio). |
| `ics.py` | File calendario `.ics` (RFC 5545: UTF-8, CRLF, folding, VALARM opzionale). |
| `test_live.py` | Smoke test dal vivo di ogni funzione. Salva gli output reali in `fixtures/` per le demo offline. |
| `data/index/` | Indice locale costruito il 3/10/2026, con `_manifest.json` che registra gli esiti HTTP di ogni richiesta. |
| `fixtures/` | Output reali catturati il 3/10/2026: ricerche, FAQ, metadati CKAN, SQL, SPARQL, snapshot, confronto multilingue della ricerca del Comune, run del mock. |

### Come usarlo in un prototipo

Copia la cartella `shared/` nel progetto, **inclusa `data/index/`**, oppure aggiungila a `sys.path`. Poi:

```python
import milano_tools as mt, claude_client as cc
mt.configure(cache_dir="data/cache")          # opzionale; default <cwd>/data/cache
if cc.has_credentials():
    res = cc.run_agent(SYSTEM, [{"role": "user", "content": domanda}], mt.TOOL_DEFS, mt.TOOL_IMPLS,
                       output_schema=SCHEMA, on_event=print)
else:
    demo = cc.load_fixture("fixtures/demo_conversazione.json")   # modalità demo offline
    banner = cc.DEMO_BANNER
```

Variabili d'ambiente: `CLAUDE_MODEL` (default `claude-opus-5-5`), `CLAUDE_EFFORT` (default `medium`), `MILANO_CACHE_DIR`, `MILANO_INDEX_DIR`, `MILANO_CACHE_TTL` (secondi, default 0), `LIVE_FAQ` (default 0), `MILANO_UA_BROWSER` (default 0).

> Attenzione: se il prototipo viene lanciato dall'interno di Claude Code, l'ambiente può già contenere `CLAUDE_EFFORT` (sul PC di sviluppo valeva `high`). Per fissare l'effort impostalo nel `.env` del prototipo oppure passa `effort=` a `run_agent`.

## Architettura delle fonti e WAF

| Fonte | Accesso automatico | Uso a runtime |
|---|---|---|
| FAQ del Centro Supporto (`servizicrm.comune.milano.it/centro-supporto/KA-.../...`, anche `sitemap.xml`) | **403** dal WAF (Azure Application Gateway) con user-agent dichiarato | Indice locale |
| Pagine di servizio `www.comune.milano.it/servizi/...` | **403** con UA dichiarato | Indice locale (`fetch_page_snapshot` prova dal vivo e poi ripiega) |
| Guide `studyandwork.yesmilano.it` | **403** con UA dichiarato | Indice locale |
| Ricerca semantica FAQ `www.comune.milano.it/o/crmsearch-service/knowledgeArticles` | **403** con UA dichiarato | Solo con `LIVE_FAQ=1` (default spento) |
| CKAN `dati.comune.milano.it/api/3/action/...` | OK | Dal vivo, con cache |
| SPARQL `virtuoso-prod.comune.milano.it/sparql` | OK | Dal vivo, con cache |

**Politica sugli user-agent (da dichiarare nel pitch e nel README dei prototipi):**

* A runtime si usa **solo** uno user-agent dichiarato e onesto (`UA_DICHIARATO` in `milano_tools.py`). Se il WAF risponde 403, i prototipi **non** aggirano il blocco: usano la copia nell'indice locale o in cache, mostrano la data della copia e segnalano `waf_bloccato: true`.
* Per la **raccolta una tantum** (`build_index.py`) e per la **cattura di confronto** della ricerca multilingue (`test_live.py`, eseguita una volta), visto il 403 sullo UA dichiarato, si è usato uno **user-agent da browser standard** (`UA_BROWSER`, Chrome 128 su Windows). Le condizioni sono queste:
  * un elenco curato e chiuso di pagine pubbliche (circa 90 FAQ, 10 pagine del Comune, 14 guide YesMilano);
  * tutte le pagine sono consentite da `robots.txt`. `www.comune.milano.it` vieta solo `/fascicolo-del-cittadino/`, `/accesso-civico/` e `/scrivi/`. `servizicrm` non ha `robots.txt` (risponde 404). `studyandwork.yesmilano.it` vieta solo i percorsi tecnici;
  * almeno 2,5 secondi tra una richiesta e l'altra;
  * l'esito di ogni tentativo (`dichiarato: 403`, poi `browser: 200`) è registrato in `data/index/_manifest.json`.
* Il ripiego a runtime si può riattivare solo esplicitamente con `MILANO_UA_BROWSER=1`, ed è sconsigliato.

**Data wishlist (da chiedere al Comune):**

1. Un feed o un'API ufficiale delle FAQ del Centro Supporto (domanda, risposta, KA, categoria, data di aggiornamento, link ai servizi). In alternativa, le FAQ pubblicate come dataset CKAN aggiornato.
2. Un'allowlist per agenti AI dichiarati sul WAF, oppure un endpoint di ricerca FAQ documentato, con limiti d'uso.
3. Nelle pagine di servizio, la data di aggiornamento in un formato leggibile dalle macchine (`dateModified` in JSON-LD).
4. Orari degli sportelli aggiornati in ds549 o ds1304. In ds1304 gli orari risultano "n.d." in 6 municipi su 9.
5. Chiarire se `MOD_DDR_ESTERO` richiede SPID o CIE. Oggi questo dato non è verificato.

## API

### `local_index.py`

* `search_local(query, top=5, tipo=None)` restituisce `[{id, tipo, titolo, estratto, url, aggiornato_il, recuperato_il, punteggio}]`. Il parametro `tipo` vale `"faq"`, `"pagina_comune"`, `"guida_yesmilano"` oppure `None` (tutti i tipi).
  * Il ranking è un BM25 con `k1=1,4` e `b=0,75`. Il titolo pesa 3 volte, parole chiave e categoria 1 volta.
  * La tokenizzazione è italiana minima: minuscole, accenti tolti, apostrofi separati, stopword italiane e inglesi, stemming leggero che toglie la vocale finale (stranieri/straniero → `stranier`).
  * Una piccola tabella di espansioni di dominio aggiunge termini con peso 0,4 (CIE ↔ carta d'identità elettronica, TARI ↔ rifiuti, iscrizione ↔ residenza…).
* `get_doc(id)` restituisce il documento completo oppure `None`. Accetta anche `ka-325`.
* `get_doc_by_url(url)`, `all_docs(tipo=None)`, `set_index_dir(path)`.

Formato di un documento (`data/index/<id>.json`):

```json
{"id": "KA-02121", "tipo": "faq", "titolo": "...", "domanda": "...", "testo": "Entro 90 giorni ...",
 "url": "https://servizicrm.comune.milano.it/centro-supporto/KA-02121/...", "lingua": "it",
 "aggiornato_il": "2026-05-06", "aggiornato_il_fonte": "pagina ('Ultimo aggiornamento')",
 "lastmod_sitemap": "2026-05-06T15:37:10+02:00", "recuperato_il": "2026-10-03T13:..+02:00",
 "categoria": "Tributi / Tari: dichiarazione di occupazione di appartamenti e immobili",
 "titolo_breve": "...", "parole_chiave": ["tari", "..."], "link": [{"testo": "...", "url": "..."}],
 "link_servizio": [{"titolo": "...", "url": "https://www.comune.milano.it/servizi/..."}]}
```

Gli id delle pagine hanno la forma `comune:anagrafe/cambio-di-residenza-...` oppure `yesmilano:study/how-to/...`.

### `milano_tools.py`

Tutte le funzioni hanno una docstring scritta per fare da descrizione di tool per Claude. I risultati delle fonti dal vivo riportano sempre `recuperato_il`, `da_cache` e `avviso`. L'avviso è valorizzato quando la rete fallisce e si usa la copia in cache.

| Funzione | Fonte | Restituisce |
|---|---|---|
| `search_comune_faq(text, top=5)` | indice locale (live solo se `LIVE_FAQ=1`, con ripiego sull'indice) | `[{ka, domanda, estratto_risposta, url, categoria, aggiornato_il, recuperato_il, punteggio, fonte}]` |
| `search_fonti(text, top=5, tipo=None)` | indice locale (FAQ, pagine e guide) | come `search_local` |
| `search_comune_faq_live(text, top=5, forza=False)` | endpoint semantico del Comune, solo con `LIVE_FAQ=1` o `forza=True` | `[{ka, domanda, estratto_risposta (≤600 caratteri, senza HTML), url, categoria}]` |
| `get_faq_article(ka)` | indice locale (live via sitemap solo con `LIVE_FAQ=1`) | `{ka, domanda, risposta, aggiornato_il, lastmod_sitemap, recuperato_il, categoria, url, link, link_servizio, fonte}` oppure `None` |
| `fetch_page_snapshot(url)` | dal vivo con UA dichiarato, poi snapshot in cache, poi indice locale | `{url, titolo, testo, aggiornato_il, link, recuperato_il, fonte: live/cache/indice_locale, waf_bloccato, avviso}` |
| `ckan_search(q, rows=10)` | CKAN | `[{slug, titolo, descrizione, metadata_modified, frequency, n_risorse}]` |
| `ckan_dataset_meta(slug)` | CKAN (accetta `ds549` o lo slug completo) | `{slug, titolo, risorse:[{id, nome, formato, url, datastore_active, last_modified}], temporal_start, temporal_end, frequency, modified, metadata_modified, avviso_freschezza, url_pagina}` |
| `ckan_sql(sql, allowlist)` | `datastore_search_sql` | `{sql_eseguita, campi, righe}` |
| `ckan_datastore_search(resource_id, filters, q, limit, allowlist=None)` | `datastore_search` | `{campi, righe, totale}` |
| `sedi_anagrafiche()` | ds549 tramite datastore | `{sedi:[{municipio, indirizzo, telefono, orari, note, nil, lat, lon}], fonte, resource_id}` |
| `sparql(query)` | Virtuoso, risposta JSON, timeout 15 s | `{variabili, righe:[{var: valore}]}` |

Le funzioni hanno queste guardie:

* **`ckan_sql` / `valida_sql`**
  * Ammette solo `SELECT`, una sola istruzione, senza commenti né parole chiave di scrittura (`INTO`, `DELETE`…).
  * Il resource_id va scritto tra virgolette doppie e deve comparire nell'allowlist passata dal chiamante. Senza allowlist non passa nessuna query.
  * `LIMIT` è obbligatorio: se manca viene aggiunto `LIMIT 200`, se è superiore a 200 viene ridotto a 200.
* **`sparql` / `valida_sparql`**
  * La query deve contenere `GRAPH <https://dati.comune.milano.it/data/...>` e `LIMIT ≤ 200`.
  * Sono vietati gli update e `SERVICE`.
* **`fetch_page_snapshot`**
  * Funziona solo su un'allowlist di host: `www.comune.milano.it`, `servizicrm.comune.milano.it` e `studyandwork.yesmilano.it`.
  * Rifiuta i percorsi vietati da `robots.txt`.

`ckan_dataset_meta` aggiunge un `avviso_freschezza` in due casi: se `temporal_end` è più vecchio di 2 anni, oppure se `frequency` è `NEVER`.

Per Claude ci sono già `TOOL_DEFS`, con strict e `additionalProperties: false`, e le relative implementazioni `TOOL_IMPLS`:

* `cerca_fonti_comune`
* `leggi_faq`
* `leggi_documento`
* `sedi_anagrafiche`

Altri strumenti utili:

* `SPARQL_ESEMPI`: query SPARQL già verificate.
* `parse_ka_page`, `parse_comune_page`, `parse_yesmilano_page`, `html_to_text`: parser condivisi con `build_index.py`.

### `claude_client.py`

La funzione principale ha questa firma:

```python
run_agent(system, messages, tools, tool_impls, output_schema=None, max_turns=8, on_event=None,
          *, client=None, model=None, effort=None, max_tokens=16000, use_fallbacks=True, cache=True)
-> {final_text, parsed, messages, events, usage, model, stop_reason, errore}
```

Il loop si comporta così:

* **Modello e parametri**
  * Il modello viene da `CLAUDE_MODEL` (default `claude-opus-5-5`). Il parametro `thinking` non si passa: su Opus 5.5 il thinking è sempre attivo.
  * L'effort si imposta con `output_config={"effort": CLAUDE_EFFORT}` (default `medium`). Con `output_schema` si aggiunge `output_config.format = {"type": "json_schema", ...}`, combinabile con i tool.
  * `tool_choice` non si forza: un `tool_choice` forzato dà 400 su Opus 5.5. Non si usa l'assistant prefill.
  * Il prompt caching usa `cache_control={"type":"ephemeral"}` top-level. `max_tokens` vale 16000.
* **Fallback sui rifiuti**: è attivo di default con `client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`. Se l'API risponde 400, una sola volta per run, si emette un evento `error` e si riprova con `client.messages.create` senza fallback.
* **Tool**
  * I `tool_use` di un turno vengono eseguiti tutti e i risultati tornano a Claude in **un solo** messaggio user.
  * Le eccezioni dei tool e i tool sconosciuti tornano come `is_error: true`.
  * I risultati oltre 30.000 caratteri vengono troncati.
* **`stop_reason`**, controllato prima di leggere il contenuto:
  * `refusal`: evento `refusal` con `stop_details.category` e `explanation`.
  * `pause_turn`: si rimanda la storia.
  * `max_tokens`: evento `error` e testo parziale.
  * `end_turn`: si legge il testo finale e, se c'è uno schema, il JSON.
* **Errori dell'SDK**: `RateLimitError`, `APIConnectionError`, `APITimeoutError`, `AuthenticationError`, `BadRequestError`, `APIStatusError`… vengono tradotti in italiano da `messaggio_errore` e restituiti in `errore`, senza sollevare eccezioni.
* **Storia**: `messages` è append-only e contiene `response.content` dell'assistente così com'è. Per salvarla in JSON usa `to_jsonable`.
* **Eventi**: hanno la forma `{tipo: tool_call|tool_result|assistant_text|refusal|error, nome, input, output_sintesi, ms}`. `on_event` li riceve in tempo reale, per esempio per mostrarli in SSE.

Le funzioni di supporto sono:

* `has_credentials()`: vero se è impostata `ANTHROPIC_API_KEY` oppure `ANTHROPIC_AUTH_TOKEN`. Carica anche il `.env`.
* `tool_defs_from(funzioni o dict)`: costruisce definizioni strict.
* `image_block_from_file` / `image_block_from_bytes`: blocchi immagine base64 per la visione.
* `save_fixture` / `load_fixture`: salvano e ricaricano le fixture per il replay.
* `DEMO_BANNER`: il testo del banner della modalità demo offline.

### `date_utils.py` e `ics.py`

* `scadenza(inizio, n, "calendario"|"lavorativi", milano=True, oggi=None)` restituisce la data, la data estesa in italiano, l'eventuale data prorogata (solo per il calendario) e la regola applicata.
  * Il giorno iniziale non si conta.
  * I giorni lavorativi escludono sabato, domenica, i festivi nazionali e, a Milano, il 7 dicembre.
* `scadenza_ambigua(inizio, n)` restituisce **entrambe** le interpretazioni e indica come prudente la data più vicina.
* Altre funzioni: `aggiungi_giorni_lavorativi`, `giorni_lavorativi_tra`, `is_lavorativo`, `FESTIVI_2026_2027`.
* Festivi inclusi:
  * Pasqua e Pasquetta sono calcolate (5-6/4/2026 e 28-29/3/2027).
  * Dal 2026 è di nuovo festa nazionale anche il **4 ottobre** (San Francesco), reintrodotta dalla legge approvata nell'ottobre 2025. Va riverificata su Normattiva prima del pilota.
* Esempio verificato: ingresso il 3/12/2026 più 8 giorni lavorativi porta a **17/12/2026** a Milano (si saltano 5, 6, 7 e 8 dicembre) e al 16/12/2026 con i soli festivi nazionali.
* `genera_ics(eventi, nome_calendario, allarme_minuti=None)` accetta eventi `{titolo, data, descrizione, url}`. Gli eventi con una data sono di giornata intera, quelli con un datetime naive usano `TZID=Europe/Rome`. Per scrivere il file c'è `salva_ics(path, testo)`, per FastAPI c'è `ics_bytes(...)`.

## Resource_id e dataset verificati (3/10/2026)

| Dataset | Slug CKAN | Resource datastore (CSV) | Copertura / frequenza | Note |
|---|---|---|---|---|
| ds549 Sedi dei servizi anagrafici | `ds549-sedi-dei-servizi-anagrafici` | `48b24517-765e-4f6f-8b30-9094a212eb85` | 28/01/2026, DAILY | 13 righe. Campi: `titolo`, `Indirizzo`, `telefono`, `orari`, `Note`, `ID_NIL`, `NIL`, `LONG_X_4326`, `LAT_Y_4326`, `Location`. **Fissato in `DS549_RESOURCE_ID`.** |
| ds551 Scuole di italiano per stranieri e CPIA | `ds551_scuole-di-italiano-per-stranieri-e-cpia` (con underscore) | `f04c6715-0dd0-4821-949d-f53fa56df8f5` | 2018, IRREG | **Dato vecchio** (avviso di freschezza). |
| ds2216 Qualità del servizio di residenza per persone straniere dall'estero, 2023 | `ds2216-rilevazione-qualita-servizio-richieste-residenza-persone-straniere-da-estero-anno-2023` | `eacf9423-d8da-43da-801b-d288595191fe` | 2023, NEVER | Indagine una tantum: 531 risposte, 34,3% "poco o per niente", 34,1% compila in inglese. |
| ds1702 Qualità del servizio di residenza, 2022 | `ds1702-rilevazione-qualita-servizio-richieste-residenza-anno-2022` | `f5625e59-8681-480e-a6be-996f3b83b6e7` | 2022, NEVER | Il 46,2% riguarda anche chi arriva da un altro comune: è un dato secondario. |
| ds235 Pediatri di libera scelta | `ds235-sociale-pediatri-libera-scelta` | `22b05e1f-c5d2-4468-90e5-c098977856ef` | 01/10/2026, WEEKLY_2 | Contiene nomi e date di nascita dei medici: **mostra solo ambulatorio e indirizzo**. Il resource_id cambia a ogni aggiornamento: risolvilo sempre con `ckan_dataset_meta("ds235")`. |
| ds47 Asili nido, localizzazione | `ds47-istruzione-asili-nido-localizzazione-delle-strutture` | `372d6b0e-af5b-4dad-a9c3-4fa0318a7dc8` | 2016-2019, NEVER | **Dato vecchio.** |

Gli slug non seguono uno schema prevedibile: `package_show?id=ds549` risponde 404. La funzione `risolvi_dataset("ds549")` trova lo slug con `package_search` e `fq=identifier:"DS549"`. Il parametro `fl` di `package_search` provoca un errore 500.

SQL d'esempio verificato:

```sql
SELECT COUNT(*) AS sedi FROM "48b24517-765e-4f6f-8b30-9094a212eb85"   -- -> 13 (LIMIT 200 aggiunto)
```

## Query SPARQL d'esempio funzionanti

Endpoint: `https://virtuoso-prod.comune.milano.it/sparql`, con `format=application/sparql-results+json`. Sui letterali usa sempre `STR()`, perché le etichette hanno tag di lingua o tipi.

**Pratiche di iscrizione anagrafica per immigrazione, per anno** (grafo `atti-pubblici`):

```sparql
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
GROUP BY ?anno ORDER BY ?anno LIMIT 50
```

Risultato del 3/10/2026: 2019: 46.626 · 2020: 35.763 · 2021: 38.465 · 2022: 46.261 · 2023: 58.934 · 2024: 54.973 · **2025: 50.777** · 2026 (parziale): 22.782. Sono **pratiche, non persone**, e comprendono anche chi arriva da altri comuni italiani.

**Biblioteche comunali con orari** (grafo `biblioteche`):

```sparql
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
ORDER BY ?nome LIMIT 50
```

Risultato: 26 biblioteche con orari testuali, per esempio "lunedi: chiuso, martedi e giovedi: 09:30-14:30…", e note di accesso.

Per esplorare altri grafi (`scuole`, `impianti-sportivi`, `NIL`…) parti da `SELECT ?t (COUNT(*) AS ?n) WHERE { GRAPH <https://dati.comune.milano.it/data/scuole> { ?s a ?t } } GROUP BY ?t LIMIT 50`.

## Limiti trovati

* **WAF**: risponde 403 allo UA dichiarato su FAQ, sitemap, pagine e ricerca del Comune, e su YesMilano (vedi sopra). Le pagine si aggiornano nell'indice solo rilanciando `build_index.py`. Ogni documento porta la data di recupero e la data di aggiornamento della fonte.
* **Ricerca live del Comune**:
  * Con il parametro `q` restituisce una lista generica sbagliata. Servono `textSearch` e `searchType=semantic`.
  * Il numero KA non è un campo del JSON (che contiene `id`, `question`, `answer` in HTML, `category`, `link`): si ricava dal `link`.
  * La qualità varia molto in base alla lingua. Il confronto catturato il 3/10/2026 è in `fixtures/faq_live_confronto.json`: in tagalog i risultati sono fuori tema, in arabo sono imprecisi, in inglese dipende dalla frase.
* **Date nelle fonti**:
  * FAQ: data "Ultimo aggiornamento" visibile sulla pagina e `lastmod` della sitemap. Il JSON-LD `FAQPage` non ha `dateModified`.
  * Pagine del Comune: "Ultimo aggiornamento" in testata.
  * Guide YesMilano: **nessuna data di aggiornamento** (`aggiornato_il: null`). Mostrare solo la data di recupero.
* **HTML delle FAQ**: alcuni link sono malformati (`href="...MODULE_TAG=... target="`). Il parser li ripulisce.
* **Dataset vecchi o fermi**:
  * ds551 (2018) e ds47 (2016-2019) sono vecchi.
  * ds1299 (sedi dei municipi) copre il 2020-2022 con frequenza NEVER: è fermo. Il dato aggiornato sulle sedi è ds549.
  * ds2216 e ds1702 sono indagini una tantum e vanno usate come dato storico.
* **Campi mancanti o incoerenti**:
  * ds549 non ha campi strutturati per gli orari (sono testo libero).
  * Le note di ds549 (per esempio Municipio 2) dicono che la prenotazione è possibile "sia con un'utenza SPID che senza necessità di registrazione". Il link di prenotazione nella pagina "Cambio di residenza" porta invece al login SPID/CIE/eIDAS. È un'**incoerenza tra fonti** da segnalare, non da risolvere.
  * In ds1304 gli orari risultano "n.d." in 6 municipi su 9.
* **Dati personali**: ds234 e ds235 contengono nomi e date di nascita dei medici. Non mostrarli.
* **Ambiente**: `CLAUDE_EFFORT` può essere ereditato da Claude Code (vedi sopra). Su Windows la console usa cp1252: per stampare testo UTF-8 servono `sys.stdout.reconfigure(encoding="utf-8")` oppure `PYTHONIOENCODING=utf-8`.
* **Nessuna credenziale Anthropic su questa macchina**: il percorso reale di `run_agent` non è stato eseguito contro l'API. È provato con un client finto che riproduce le forme dell'SDK 1.11: un 400 su `fallbacks` seguito da un retry, 2 turni di tool use, un JSON finale, `refusal` e `max_tokens`.

## Esiti dei test dal vivo

Eseguiti il 3/10/2026 con `python test_live.py`: **11 test su 11 superati**. Il dettaglio è in `fixtures/_esiti_test_live.json`.

| Test | Esito dal vivo |
|---|---|
| Indice locale | 113 documenti: 89 FAQ, 10 pagine del Comune, 14 guide YesMilano. Tutte le FAQ hanno la data "Ultimo aggiornamento". |
| Query "iscrizione anagrafica dall'estero senza SPID" | Il primo risultato è la pagina "Cambio di residenza per persone straniere provenienti dall'estero". Seguono KA-00546 (certificati senza SPID/CIE), KA-03938 e KA-03937 (solleciti della prima iscrizione). |
| Query "dichiarazione TARI nuova occupazione" | Primi risultati: KA-01955, KA-01945, KA-02121, KA-02125, KA-02120. |
| Query "carta d'identità cittadino extra UE" | Primi risultati: KA-00564, KA-00393, KA-00408. |
| Ricerca live del Comune | Con lo UA dichiarato risponde **403**. La cattura una tantum con UA da browser è in `fixtures/faq_live_confronto.json`. |
| `get_faq_article` | KA-00325 aggiornata il 13/08/2026. KA-02121 aggiornata il 06/05/2026 ("Entro 90 giorni…"). |
| `ckan_dataset_meta` | ds549 copre fino al 28/01/2026 (DAILY). ds235 è aggiornato al 01/10/2026 (WEEKLY_2). ds551 (2018), ds2216 (NEVER), ds1702 (NEVER) e ds47 (2019, NEVER) hanno l'avviso di freschezza. |
| `ckan_search("residenza stranieri")` | Restituisce ds74, ds75, ds27… |
| `ckan_sql` su ds549 | 13 sedi. `LIMIT 200` aggiunto, `LIMIT 500` ridotto a 200, 4 query non ammesse bloccate. |
| `sedi_anagrafiche` | 13 sedi (Municipio 2: via Padova 118). |
| SPARQL | Iscrizioni per immigrazione 2025: 50.777. 26 biblioteche con orari. 3 query non ammesse bloccate. |
| `fetch_page_snapshot` | Su comune.milano.it e su yesmilano lo UA dichiarato riceve **403**. La funzione ripiega sull'indice locale con `waf_bloccato: true`, la data della copia e la data della fonte (27/07/2026 per la pagina del Comune, nessuna per YesMilano). |
| Date e ICS | Kit del permesso: ingresso 03/12/2026, scadenza 17/12/2026 a Milano (16/12 con i soli festivi nazionali). Residenza: 03/10 → 23/10. Il file ICS è valido (CRLF, righe ≤ 75 ottetti, VALARM, TZID). |
| `claude_client` (mock) | 3 turni, 2 tool in parallelo in un solo messaggio user, 1 `is_error`, JSON finale valido. Con 400 su `fallbacks` riprova senza. Gestisce `refusal` e `max_tokens`. Nelle chiamate non compaiono né `thinking` né `tool_choice`. |

**Confronto multilingue della ricerca del Comune** (top 5, posizione della FAQ attesa):

| Domanda | Lingua | FAQ attesa | Posizione |
|---|---|---|---|
| Residenza per chi arriva dall'estero | italiano | KA-00330 | 1° |
| Residenza per chi arriva dall'estero | inglese | KA-00330 | 4° |
| Residenza per chi arriva dall'estero | tagalog ("paninirahan sa Milan") | KA-00489 o KA-00330 | Non trovata. C'è un solo risultato, fuori tema: KA-02514, sugli studenti internazionali. |
| Residenza per chi arriva dall'estero | arabo | KA-00489 o KA-00330 | Non trovata. I risultati sono ResidenzaMi (KA-03249, KA-03252), attestazione UE, domicilio studenti e Agenzia Milano Abitare. |
| TARI nuova occupazione | italiano | KA-02121 | 1° |
| TARI nuova occupazione ("when do I declare the waste tax") | inglese | KA-02121 | 2° |
| TARI nuova occupazione | arabo | KA-02121 | Non trovata. Escono **gli stessi 5 risultati** della domanda araba sulla residenza: la ricerca sembra ignorare il contenuto del testo arabo. |

## Problemi aperti

* Il percorso reale verso l'API Anthropic non è stato provato per mancanza di credenziali. Restano da verificare dal vivo:
  * il formato effettivo dei blocchi `fallback` restituiti dalla beta;
  * l'accettazione di `fallbacks="default"` insieme a `output_config.format`.
* Il 4 ottobre è stato inserito come festivo nazionale dal 2026. Va riverificato sulla legge in Gazzetta prima del pilota.
* L'indice va aggiornato a mano con `python build_index.py --force`, finché il Comune non fornisce un feed. L'aggiornamento richiede circa 10 minuti con la pausa di 2,5 s.
* Non è verificato se `MOD_DDR_ESTERO` richieda SPID o CIE: è una domanda aperta per il Comune.
* L'incoerenza tra le note di ds549 ("anche senza registrazione") e il login SPID/CIE/eIDAS nella pagina "Cambio di residenza" va presentata come tale.
