# Personas e user stories: Track 01, idea 1+2

**Prodotto in una frase:** un agente che parla la lingua di chi arriva a Milano, gli costruisce la
checklist personale dei primi passi (codice fiscale, residenza, TARI, trasporti, medico) con la
fonte del Comune per ogni passo, e quando arriva una lettera del Comune la legge, la spiega e
aggiorna la checklist.

**Momento forte della demo:** Wei Ling fotografa la lettera, l'agente la spiega in inglese e la
checklist si aggiorna da sola. Test "spegni l'AI": senza Claude non resta niente.

Le personas sono **inventate** (regola: nessun dato personale). Le procedure citate nelle storie
non sono verificate: è l'agente a leggerle dalle fonti del Comune, mai il nostro codice a
cablarle.

## Personas

### P1. Wei Ling Tan, 23 anni, studentessa da Singapore (persona principale della demo)

- **Situazione:** arriva a settembre per un master al Politecnico. Cittadina non UE, parla inglese
  e mandarino, zero italiano. Ha un posto letto in affitto trovato online.
- **Dove si blocca:** non sa da dove partire né in che ordine. Trova pagine in italiano, PDF,
  informazioni sparse tra Comune, YesMilano, università. Riceve mail del Comune che non capisce.
- **Cosa vuole:** sapere cosa fare questa settimana, in inglese, con la certezza che la fonte sia
  ufficiale.
- **Perché la scegliamo:** il Comune ha citato dal palco proprio "chi arriva da Singapore"; YesMilano
  ha già un percorso per studenti internazionali da cui partire.

### P2. Marco Bianchi, 38 anni, italiano che rientra dalla Francia con la famiglia

- **Situazione:** torna a Milano da Lione con la moglie francese e il figlio di 2 anni nato in
  Francia. Parla italiano, ma i documenti del figlio sono francesi.
- **Dove si blocca:** non sa cosa vale dei documenti francesi (traduzione? apostille?), per il
  codice fiscale del figlio scambia mail e PDF scansionati, l'iscrizione all'anagrafe la rimanda
  perché non sa quando e dove andare.
- **Cosa vuole:** un ordine dei passi per tutta la famiglia, con i documenti giusti la prima volta.
- **Perché la scegliamo:** è il caso raccontato dall'organizzatore in apertura, la giuria lo
  riconosce.

### P3. Joana Ferreira, 64 anni, portoghese, raggiunge la figlia a Milano

- **Situazione:** cittadina UE, parla portoghese, capisce poco l'italiano scritto, vede male il
  testo piccolo. Usa lo smartphone soprattutto per WhatsApp e messaggi vocali.
- **Dove si blocca:** i moduli e le pagine lunghe; dipende dalla figlia per tutto.
- **Cosa vuole:** chiedere a voce, ricevere risposte brevi e grandi, nella sua lingua.
- **Perché la scegliamo:** copre il lato accessibilità (anziani, ipovisione) che è il tema della
  giornata. Nella demo basta mostrarla 15 secondi (testo grande, lingua, eventualmente voce).

## User stories

Priorità: **M** = per le 16:00, **S** = se c'è tempo, **C** = da mostrare come "versione successiva".

### Idea 1: la checklist personale

| # | Pri | Storia | Criteri di accettazione |
|---|---|---|---|
| US1 | M | Come **Wei Ling**, voglio scrivere nella mia lingua e ricevere risposte nella stessa lingua, così non devo tradurre niente. | L'agente risponde nella lingua del primo messaggio; i nomi ufficiali (es. "codice fiscale", "anagrafe") restano in italiano con la spiegazione accanto, perché sono quelli che troverà allo sportello. |
| US2 | M | Come **Wei Ling**, voglio rispondere a poche domande sulla mia situazione, così la lista vale per me e non per tutti. | Massimo 5 domande, una alla volta (cittadinanza UE/non UE, motivo: studio/lavoro/famiglia, ha già casa, ha figli, quando è arrivata). Si può saltare una domanda. |
| US3 | M | Come **Wei Ling**, voglio una checklist ordinata dei passi, così so cosa fare prima e cosa dopo. | Ogni passo ha: cosa fare, perché viene prima del successivo, dove (online o sportello), cosa portare. Due situazioni diverse (P1 e P2) producono liste diverse. |
| US4 | M | Come **Wei Ling**, voglio vedere la fonte ufficiale di ogni passo, così mi fido. | Ogni passo ha il link a una pagina di comune.milano.it, yesmilano.it o di un altro ente pubblico. Se l'agente non trova la fonte lo dice ("non ho trovato una fonte ufficiale, verifica qui") invece di inventare importi, scadenze o requisiti. |
| US5 | M | Come **Wei Ling**, voglio segnare un passo come fatto, così vedo a che punto sono. | Spunta per passo, stato visibile; i passi che dipendono da uno non fatto restano marcati "dopo". |
| US6 | S | Come **Marco**, voglio sapere quali documenti stranieri servono e se vanno tradotti, così non perdo l'appuntamento. | Per ogni passo allo sportello l'agente elenca i documenti e segnala quelli emessi all'estero con cosa la fonte chiede (traduzione, apostille), citando la pagina. |
| US7 | S | Come **Wei Ling**, voglio scaricare le scadenze nel mio calendario, così il Comune mi "ricorda" le cose prima che diventino un problema. | Export `.ics` con i passi che hanno una scadenza presa dalla fonte. Nessuna scadenza inventata: se la fonte non la dà, il passo non va in calendario. |
| US8 | S | Come **Joana**, voglio leggere tutto in grande e con frasi brevi, così non dipendo da mia figlia. | Testo ridimensionabile al 200% senza rompere il layout, contrasto 4,5:1, una cosa per schermata (checklist `docs/accessibility-checklist.md`). |
| US9 | C | Come **Joana**, voglio fare le domande a voce. | Solo mockup o accenno nel pitch. |

### Idea 2: "Spiegami questa lettera"

| # | Pri | Storia | Criteri di accettazione |
|---|---|---|---|
| US10 | M | Come **Wei Ling**, voglio fotografare o incollare una lettera o mail del Comune, così capisco cosa mi chiede. | Accetta foto (JPG/PNG) o testo incollato. L'agente restituisce nella mia lingua: di cosa si tratta, cosa devo fare, entro quando (solo se scritto nella lettera), link alla pagina del Comune collegata. |
| US11 | M | Come **Wei Ling**, voglio che la lettera aggiorni la mia checklist, così non devo capire io dove va. | Se la lettera riguarda un passo della lista, il passo si aggiorna (es. "convocazione ricevuta, appuntamento il ..."); se è una cosa nuova, propone un passo nuovo. **L'utente conferma** prima che la lista cambi (human in the loop). |
| US12 | M | Come **Wei Ling**, voglio vedere il testo originale accanto alla spiegazione, così posso controllare. | Originale e spiegazione affiancati; le frasi della spiegazione che riportano date o importi rimandano al punto della lettera da cui vengono. |
| US13 | S | Come **Marco**, voglio che l'agente mi dica quando non è sicuro di aver letto bene, così non sbaglio una data. | Se la foto è illeggibile o una cifra è incerta, l'agente lo dice e chiede di confermare o rifotografare. |
| US14 | C | Come **Comune**, voglio che la lettera contenga già un link/QR all'agente, così il cittadino non deve cercarlo. | Solo nel pitch, come "versione successiva" insieme ai dati che servirebbero (vedi sotto). |

**Lettere per la demo:** 2-3 lettere **inventate** sul modello di quelle reali (mail di benvenuto
nuovi residenti, avviso TARI, convocazione anagrafe), con nomi e codici finti.

## Dove lavora Claude (bozza per la sezione obbligatoria del README)

| Momento | Cosa fa Claude | Cosa conferma una persona |
|---|---|---|
| Intervista (US1-2) | Rileva la lingua, fa le domande, ne deduce il profilo | La persona risponde e può correggere il profilo |
| Checklist (US3-4, US6) | Legge le pagine del Comune/YesMilano (tool di fetch), ordina i passi, estrae documenti e requisiti con citazione | Nessuna azione verso terzi: la lista è solo informativa |
| Lettera (US10-13) | Legge la foto (vision), spiega, collega la lettera a un passo | La persona conferma prima che la checklist cambi |

Riferimento da citare: Manifesto per l'uso dell'AI del Comune di Milano (inclusione, trasparenza,
human in the loop).

## Versione successiva: quali dati servirebbero (risposta al "rischia di essere una FAQ")

- Un segnale di arrivo (cambio di residenza o iscrizione all'anagrafe) per far partire l'agente
  insieme alla mail di benvenuto che il Comune già manda, con consenso esplicito.
- Lo stato delle pratiche (ricevuta, in lavorazione, chiusa) dal sistema del Comune, per spuntare i
  passi in automatico.
- Gli appuntamenti disponibili agli sportelli, per proporre la data invece di mandare il link.
