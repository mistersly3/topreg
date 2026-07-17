# TOPREG.it — Portale poker automatizzato

Sito statico in inglese, target internazionale, aggiornato automaticamente ogni 6 ore con news dal mondo poker. Zero manutenzione, zero costi di hosting.

## Struttura

- `build.py` — generatore: scarica i feed RSS e produce il sito in `site/`
- `config.json` — feed, banner affiliati, email sponsor (l'unico file da modificare)
- `site/` — sito generato (index.html, robots.txt, CNAME)
- `.github/workflows/build.yml` — rigenera e pubblica ogni 6 ore
- `sample/` — feed di esempio per test offline: `python3 build.py --offline sample/pokernews.xml`

## Messa online (una volta sola, ~20 minuti)

1. Crea un account/repository su GitHub chiamato `topreg` e carica tutti questi file.
2. Nel repository: Settings → Pages → Source: **GitHub Actions**.
3. Tab Actions → esegui "Build and deploy TOPREG" manualmente la prima volta.
4. Dal pannello del tuo registrar di topreg.it, punta il DNS:
   - record `CNAME` per `www` → `TUOUSERNAME.github.io`
   - record `A` per il dominio nudo → `185.199.108.153` (e .109/.110/.111)
5. Settings → Pages → Custom domain: `www.topreg.it` → attiva "Enforce HTTPS".

Da quel momento il sito si aggiorna da solo ogni 6 ore, per sempre.

## Monetizzazione — passi da fare tu

1. **Iscriviti ai programmi affiliati** (serve un sito online, quindi prima pubblica):
   - GGPartners (GGPoker) — revshare ~30%
   - Stars Affiliate Club (PokerStars) — revshare 25-50%, CPA $100-250
   - 888 Affiliates, WPT Global, e network come Gambling Affiliation
2. Quando ricevi i link di tracking, sostituisci i valori `#REPLACE_...` in `config.json`. Al build successivo i banner puntano ai tuoi link.
3. **Sponsorizzazioni dirette**: il sito ha già la sezione "Advertise on TOPREG" con mailto. Crea l'indirizzo `partners@topreg.it` presso il tuo registrar.

## Avvertenze legali (importante)

- Il Decreto Dignità vieta in Italia ogni pubblicità al gioco con vincite in denaro, inclusi link affiliati (sanzioni AGCOM 5.000–500.000 €). Per questo il sito è **in inglese e non diretto al pubblico italiano** (disclaimer già nel footer). **Non aggiungere contenuti in italiano con link a operatori di gioco.**
- I programmi affiliati chiedono in quali mercati operi: dichiara mercati esteri, non l'Italia.
- Per la struttura societaria (es. LLC Wyoming/Delaware, ~$150-500/anno tramite agenti registrati) e la fiscalità da residente italiano, consulta un commercialista/avvocato: una società estera non ti esonera dalle leggi italiane se risiedi in Italia.
- Le news sono aggregate come titolo + estratto + link alla fonte originale (uso lecito da aggregatore); il sito non copia articoli interi.

## Aspettative realistiche

Nessun programma serio paga "a click": si guadagna con revenue share o CPA sui giocatori che si registrano e giocano. I primi mesi il traffico sarà basso; crescerà con l'indicizzazione. Per accelerare: aggiungi col tempo contenuti originali (classifiche, guide), che sono ciò che Google premia e ciò che convince gli sponsor a pagare.
