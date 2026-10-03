# CLAUDE.md

Team repo for **Milan | Claude Impact Lab** (3 Oct 2026, SmartCityLab Milano): AI that makes Comune
di Milano public services more accessible (people with disabilities, older people, non-Italian
speakers, low vision). Deliverable: public repo + README + 2-minute video, **by 16:00**.

## Brief

**Our team works on Track 01 only: Welcome journey for people arriving in Milan.**
Sources: `input/ClaudeImpactLab_Milano.pdf` (slides), `input/slides-speaker-notes.txt` (slide text + speaker
notes, not in the PDF), `input/trascript_presentazione_progetto.txt` (opening talk transcript).

- **For whom:** new residents, international students, people who don't speak Italian.
- **The job:** codice fiscale, residenza, housing, TARI, transport: what to do, in which order,
  with which City source.
- **Build on, don't duplicate:** the City's existing welcome emails (new residents, address change)
  and the YesMilano path for international students. 16 of the 22 most-requested certificates are
  already online; a TARI pilot is at an advanced stage.
- **Claude at work:** an agent that talks/chats in the newcomer's language, reasons over City rules
  and builds a personal checklist, citing the City source for each step.
- **Known weakness:** without identity data it risks becoming a smarter FAQ. Show which data the
  next version would need (and how it would get consent).
- **"Switch the AI off" test:** if only a static page of links and FAQs is left, it fails.

### Said on stage, not on the slides (opening talk transcript, 3 Oct)

- **The Comune under-communicates what it already runs.** Many services are live but hard to find:
  surfacing the right existing service for the newcomer is itself value. Check before building.
- **Comune AI manifesto** (published last year at Milano Digital Week): inclusion, transparency,
  participation, ethics, **human in the loop** (a person gives the final OK). Cite it in the README
  "Where does Claude work" section; the jury will recognise it.
- **YesMilano** (Milano & Partners) is the City's welcome portal: rich but static. Suggested: read it
  as a live source instead of duplicating its content. A copy is fine for the prototype, but design
  for linking to the source.
- **Silvia Castellanza (Chief Data Officer, jury)** wants informal feedback on which data is missing
  (e.g. real-time). Open data portal: ~2000 datasets, JSON/GeoJSON/API.
- Example persona from the organiser: child born in France to an Italian parent; codice fiscale via
  Agenzia Entrate by email + scanned PDF, birth certificate in French, anagrafe registration put off
  for years. Claude reading the Comune site told him the steps.
- Pitches happen live (2 min) besides the video. Prize: 1-month Claude Max for first place.

### Judging (each 0-5, max 35)

Day-one impact x2 · AI at work while running x2 · City data and sources x1 · Product and
execution x1 · Pitch (2 min) x1. Jury: Riccardo Colombo (Anthropic), Silvia Castellanza and
Sara Belli (Comune di Milano).

### Submission: by 16:00, one per team

Public repo (open source, donated to the Comune) + README + 2-minute demo video, via the
"Submission" issue form in `Claude-Milano/impact-lab-oct-2026`. The README must state the problem
and who has it, track and City sources, how to run it, video link, and the **required section
"Where does Claude work when someone uses this?"** (model, prompts, tools/MCP, what it decides,
what a human confirms). Without that section the "AI at work" criterion scores zero.
Public data only, no personal data.

## Stack

- **Claude runs at runtime via the API** (main rule of the day, judging criterion x2). Each
  participant gets $100 of API credits (console.anthropic.com, API only, not Claude.ai). Key in
  `.env` (gitignored), never committed. Spend credits on running the solution, not on building it.
- Front end: prefer something the jury can open from a link (static site + small API) over a
  local-only demo.

## Working rules

- Public data only, no personal data, not even in test fixtures: use invented personas.
- Every step the agent tells a newcomer cites the City source (URL). Never invent amounts,
  deadlines or requirements the source does not contain; when unsure, say so and link the source.
- A person confirms before anything is sent or filed (human in the loop, Comune AI manifesto).
- Every UI change passes the 7-point checklist in `docs/accessibility-checklist.md`.
- Small commits, pull before push, avoid two people editing the same file.
- UI copy in Italian (plus the newcomer's language); code, identifiers and comments in English.
