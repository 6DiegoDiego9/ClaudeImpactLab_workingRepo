# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Team repo for **Milan | Claude Impact Lab** (3 Oct 2026, CityLab Milano): AI that makes Comune di Milano
public services more accessible (people with disabilities, older people, non-Italian speakers, low vision).
Deliverable: public repo + README + 2-minute video, **by 16:00**, then a live 2-minute pitch.

## Repository layout

- `input/`: event material. `ClaudeImpactLab_Milano.pdf` (slides; page 12 = data sources, page 20 = the
  5-step flow Personas → Brainstorm → User stories → Mockup → Build), `slides-speaker-notes.txt` (slide
  text + speaker notes, not in the PDF), `trascript_presentazione_progetto.txt` (opening talk, automatic
  transcription: "Cloud" = Claude, "IES/YASP Milano" = YesMilano).
- `docs/accessibility-checklist.md`: the 7-point WCAG check every UI must pass, plus easy-to-read rules and
  the Italian/EU legal context (Legge Stanca → WCAG 2.1 AA via EN 301 549).
- `output/<ID>-<name>/` (`C1-sblocca`, `C7-ponte`, `C2-benvenuto`, `C4-leggimi`): one self-contained
  prototype per idea, each meant to become the team's public submission repo. Python + FastAPI + static
  vanilla HTML/JS, its own README (event template), `requirements.txt`, `.env.example`, tests, and an
  offline demo mode. Run and test commands live in each prototype's README.
- `output/.env`: shared `ANTHROPIC_API_KEY` / `CLAUDE_MODEL` / `CLAUDE_EFFORT` (gitignored via `.env*`).
  `load_dotenv()` walks up from the prototype folder, so all prototypes pick it up unless a closer `.env`
  exists.
- `prompts/`, `transcripts/`: the team's prompts and the workshop transcript (.docx).

The event hub repo `github.com/Claude-Milano/impact-lab-oct-2026` holds the authoritative brief:
`CHALLENGE.md`, `DATA.md` (curated datasets + CKAN API), `RULES.md` (judging), `SUBMISSION.md`,
`templates/PROJECT_README.md`, and `starter/` (`runs_on_claude.py` tool-use example, `portal.py` CKAN helper).

## Brief

**Our team works on Track 01 only: Welcome journey for people arriving in Milan.**

- **For whom:** new residents, international students, people who don't speak Italian.
- **The job:** codice fiscale, residenza, housing, TARI, transport: what to do, in which order, with which
  City source.
- **Build on, don't duplicate:** the City's automatic welcome emails (new residents, address change) and the
  YesMilano path for international students. 16 of the 22 most-requested certificates are already online; a
  TARI pilot is at an advanced stage. Already running at the Comune: the Contact Center AI assistant
  (operator side), ConWEB (voice form filling), 020202 on WhatsApp (since 2020). Closest external
  competitor: **Sportellino**, a multilingual AI chatbot for migrants on WhatsApp/Telegram (since July 2025);
  every pitch must say how we differ.
- **Claude at work:** an agent that talks/chats in the newcomer's language, reasons over City rules and
  builds a personal checklist, citing the City source for each step.
- **Known weakness:** without identity data it risks becoming a smarter FAQ. Show which data the next
  version would need (and how it would get consent).
- **"Switch the AI off" test:** if only a static page of links and FAQs is left, it fails.

### Said on stage, not on the slides

- **The Comune under-communicates what it already runs.** Surfacing the right existing service is itself value.
- **Comune AI manifesto** (Oct 2025, Milano Digital Week): inclusion, transparency, participation, ethics,
  **human in the loop**. For chatbots it requires two visible safeguards: tell users they are talking to an
  automated system, and always offer a human operator (020202, Milano Welcome Center, via Sammartini 75).
- **YesMilano** is rich but static. The newcomer guides live on `studyandwork.yesmilano.it` (How To for
  students, Getting Started for professionals), English only.
- **Silvia Castellanza (Chief Data Officer, jury)** wants feedback on which data is missing: every README
  should include a "data wishlist".
- Organiser's example persona: child born in France to an Italian parent; birth certificate in French,
  anagrafe registration put off for years.

### Judging (each 0-5, max 35)

Day-one impact x2 · AI at work while running x2 · City data and sources x1 · Product and execution x1 ·
Pitch x1. Jury: Riccardo Colombo (Anthropic), Silvia Castellanza and Sara Belli (Comune di Milano).

### Submission: by 16:00, one per team

Public repo (MIT or Apache-2.0, donated to the Comune) + README from `templates/PROJECT_README.md` + demo
video link, via the "Submission" issue form in the hub repo. The README **must** have the section "Where
Claude works" (model, prompts, tools/MCP, what it decides, what a human confirms, what happens when it is
wrong). Without it "AI at work" scores 0. No commits before 10:00 on 3 Oct.

## Stack and Claude API

- Claude runs at runtime via the API (`anthropic` Python SDK). Default model `claude-opus-5-5`, configurable
  with `CLAUDE_MODEL`; effort via `output_config={"effort": ...}` (`CLAUDE_EFFORT`, default `medium`).
- On Opus 5.5: do not send `thinking: {type: "disabled"}` or `budget_tokens` (400); forced `tool_choice`
  (`any`/`tool`) returns 400, so use `auto` + prompt instruction + `strict: true` tools; no assistant prefill;
  structured output via `output_config.format`. Server-side refusal fallback is on by default
  (`client.beta.messages.create(..., betas=["server-side-fallback-2026-07-01"], fallbacks="default")`).
- Credits: $100 per participant, API only. Spend them on running the solution, not on building it.
- Quick key check: `cd output && python -c "from dotenv import load_dotenv; import anthropic, os; load_dotenv('.env'); print(anthropic.Anthropic().messages.create(model=os.getenv('CLAUDE_MODEL'), max_tokens=20, messages=[{'role':'user','content':'ok?'}]).content)"`

## City data access (verified 3 Oct 2026)

- **CKAN open data** `https://dati.comune.milano.it/api/3/action/`: 2,604 datasets, no key. `package_show`,
  `datastore_search`, and **`datastore_search_sql`** (CSV resources only) all work live. DCAT metadata exposes
  `temporal_coverage` and `frequency`: check them and warn on stale data. Stale examples: ds550/551/552/554
  (2018), ds47 nurseries (2016-2019), ds1299 municipi (2020-2022), ds1304 (2020-2021). ds549 (registry
  offices) is current (28/01/2026). ds234/ds235 contain doctors' names and birth dates: show only the clinic.
- **SPARQL** `https://virtuoso-prod.comune.milano.it/sparql` (behind portalelod.comune.milano.it, not in the
  hub brief): open, JSON output. Always restrict to a `GRAPH <https://dati.comune.milano.it/data/...>` and add
  `LIMIT` (the Area C graph has ~114M triples); use `STR()` when filtering typed literals.
- **MilanoStatistica** is a Qlik app: not queryable at runtime; use its stable XLS exports.
- **comune.milano.it, servizicrm.comune.milano.it (FAQ "Centro Supporto", KA-xxxxx) and YesMilano** sit behind
  an Azure WAF that returns 403 to non-browser clients, even with an honest declared user agent. Prototypes
  therefore use a **local index** of FAQ and pages collected once with source date + retrieval date; live
  calls only behind an opt-in flag. The FAQ semantic search endpoint `/o/crmsearch-service/knowledgeArticles`
  only works with `top`, `searchType=semantic`, `formatInput=true`, `category=`, `textSearch=` (not `q`); the KA
  number is not a JSON field, parse it from the link.

## Verified rules (do not repeat the earlier mistakes)

- Codice fiscale is listed in Allegato A (residence from abroad) **without** the mandatory asterisk: never say
  residence is blocked without it.
- Residence for people arriving from abroad is requested **only online** (MOD_DDR_ESTERO, KA-00330), within
  20 days (KA-00534), not at the counter. Whether that form requires SPID is unverified: say so.
- Residence-permit kit: within **8 working days** of entry (D.Lgs. 286/1998, art. 5 c. 2). Poste's "8 giorni"
  is a simplification, not a source conflict. CF at the consulate is a different branch, not a conflict.
- SPID does **not** depend on residence (it depends on the CF and a document accepted by the provider).
- Residence-application status is visible only in the Fascicolo with SPID/CIE (KA-00325, KA-03731); without
  SPID use the "Hai ancora bisogno di aiuto?" form (KA-03938).
- KA-00370: update "within 60 days of the permit's expiry", not "at least 60 days before".
- TARI new occupation: within 90 days (KA-02121), signed by the **head of the family record**; no-SPID channels:
  PEC `tassarifiuti@pec.comune.milano.it` or the Protocollo in via Larga (KA-01955).
- Foreign minors can enrol at school at any time of the year (DPR 394/1999, art. 45).
- Pitch numbers: lead with **ds2216** (2023, foreigners from abroad, online residence service: 34.3% "helped
  little or not at all", 34.1% answered in English). The 46.2% from ds1702 (2022) includes arrivals from other
  Italian municipalities: cite it with that caveat. The survey datasets have no free-text comments.

## Working rules

- Public data only, no personal data, not even in test fixtures: use invented personas and mark them as such.
- Every step the agent tells a newcomer cites the City source (URL or KA + date). Never invent amounts,
  deadlines or requirements the source does not contain; when unsure, say so and link the source.
- Deadlines are computed by code (calendar vs working days), not by the model.
- A person confirms before anything is sent or filed. Prototypes never write to City systems: they draft
  emails/PEC that the person sends.
- No Comune logos or official styling; label UIs "prototipo non ufficiale".
- Browser speech recognition (Web Speech API) sends audio to a third party: demo only, with invented cases.
- Every UI change passes the 7-point checklist in `docs/accessibility-checklist.md`.
- Small commits, pull before push, avoid two people editing the same file.
- UI copy in Italian (plus the newcomer's language); code, identifiers and comments in English.
