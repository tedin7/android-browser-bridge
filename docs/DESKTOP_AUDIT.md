# Audit desktop con Browser Bridge, senza Playwright

La stessa estensione funziona su Firefox desktop. Un dispositivo desktop abbinato
può ricevere le operazioni MCP e controllare il viewport; il tablet Android
mantiene invece le dimensioni dello schermo. Un audit responsive desktop non
prova il rendering reale di Android.

Per una prova autonoma, dalla checkout:

```sh
python3 desktop_audit.py https://example.org \
  --viewport 1280x720 --viewport 390x844 \
  --selector body --output state/desktop-audit.json
```

Richiede Firefox desktop e npm; web-ext 10 viene eseguito tramite npm exec.
Il comando autorizza solo un Firefox temporaneo, con profilo, broker e credenziali
propri. Non collega né modifica il profilo Firefox personale o il tablet.
Non usa Playwright e non esegue JavaScript arbitrario nelle pagine.

La risposta contiene viewport richiesto/misurato, corrispondenza e dati di layout
per al massimo tre elementi per selettore. Puoi ripetere --selector. Il report
privato non include valori dei moduli o testo completo della pagina.
Gli screenshot sono disabilitati per default; --screenshot-dir PATH li salva
come file PNG separati, quando desideri una verifica visiva.

L’estensione 0.3.1 introduce due funzioni fisse:

- viewport con width/height su Firefox desktop: ridimensiona la finestra,
  misura il viewport e riporta se corrisponde; massimo due tentativi.
- inspect con layout:true: position, top/left/right/bottom, zIndex, display,
  overflow e dimensioni, intersezione col viewport e hit-test del punto centrale.

Il punto centrale non prova che ogni pixel sia scoperto. Quando un elemento è
fuori schermo, invisibile o non verificabile, occluded è null, non un successo.
I dati CSS e geometrici possono verificare un pulsante sticky o un overflow;
non dimostrano da soli la correttezza dei colori o dell’intera composizione.
Un audit visivo può ancora richiedere uno screenshot.

Per layout:true serve il nuovo motore 0.3.1; con un’estensione precedente l’MCP
segnala la funzione mancante. viewport non può ridimensionare lo schermo Android.
Su un browser desktop condiviso il resize riguarda tutta la finestra, non una
singola scheda: per gli audit usa il profilo isolato del comando sopra.

Firefox può imporre una larghezza minima alla finestra desktop. Nella prova
su un host SSH remoto 1280×720 e 500×844 corrispondevano alle dimensioni misurate;
una richiesta 390×844 misurava 500×844 con matched:false. Non presentare
quel risultato come un test a 390 pixel o come una prova di Android.
