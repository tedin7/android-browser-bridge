# Estensione Firefox Android

## Stato attuale

Il repository contiene il sorgente e un pacchetto **non firmato**, per test.
Non c'è ancora una pubblicazione su Mozilla Add-ons. Non è stato verificato
su un vero Firefox Android: la prova finale richiede un dispositivo.

**Download diretto dell'estensione di sviluppo:**
https://github.com/tedin7/android-browser-bridge/releases/download/v0.1.2-dev/android-browser-bridge.xpi

**Release con pacchetto MCP e sorgenti:**
https://github.com/tedin7/android-browser-bridge/releases/tag/v0.1.2-dev

Versioni minime: Firefox desktop 140, Firefox Android 142. Il manifest ora
dichiara i tipi di dati trasferiti e la pagina di configurazione spiega il
consenso al controllo. La privacy policy è [PRIVACY.md](../PRIVACY.md).

## Installazione facile dallo store Mozilla Add-ons

**Scheda di questa estensione nello store: non ancora pubblicata.** Non c'è
quindi un URL AMO installabile da fornire per Browser Bridge in questa release.
Il download GitHub qui sopra è una build di sviluppo, non la scheda dello store.

Quando sarà pubblicata e dichiarata compatibile con Android, l'utente dovrà
aprire il suo link AMO in Firefox Android, premere Aggiungi a Firefox e accettare
i permessi. Poi aprirà Browser Bridge e incollerà il codice BB1 generato dal suo
MCP. Non dovrà usare Nightly o modificare le verifiche delle firme.

Il maintainer deve pubblicare l'URL effettivo della scheda AMO qui e nel README
solo dopo averlo verificato; non costruire un URL presunto a partire dal nome.

Per utenti finali, la strada semplice sarà installazione da Mozilla Add-ons
o XPI firmato. La firma richiede l'account Mozilla del publisher; non è inclusa
nel processo di build.

## Prova con Firefox Nightly

1. Installa Firefox Nightly per Android da una fonte Mozilla ufficiale.
2. Scarica `android-browser-bridge.xpi` dalla release GitHub del progetto.
3. Per testare questo XPI non firmato, apri `about:config` in Nightly e imposta
   `xpinstall.signatures.required` a `false`, se necessario per la tua versione.
4. Apri Impostazioni → Informazioni su Firefox; tocca il logo cinque volte.
5. Torna alle impostazioni → Installa estensione da file e seleziona l'XPI.
6. Conferma i permessi solo se desideri consentire al tuo Linux il controllo
   delle pagine. Le impostazioni dell'estensione si aprono dopo l'installazione.
7. Dal tuo assistente Linux chiama `browser_pair`, ad esempio con
   `{"device":"my-phone"}`. Incolla la stringa `BB1.…` nell'estensione.
8. Abilita il controllo remoto e premi Salva. Il codice vale cinque minuti.

Non servono ADB, root, Termux o un'app VPN sul dispositivo Android.
Non usare le impostazioni per estensioni non firmate come istruzione di
installazione per utenti finali: la release stabile va firmata.

## Disabilitare o revocare

Disabilita il controllo nelle impostazioni dell'estensione, oppure rimuovila.
Dal Linux puoi chiamare `browser_revoke` con il nome del dispositivo:
la credenziale non sarà più accettata. Un'azione già in esecuzione non può
essere annullata dalla revoca.

## Limiti del controllo

Funziona sulle pagine HTTP(S), nei limiti dei permessi Firefox. Non controlla
le altre app Android, l'interfaccia del browser o le pagine interne protette.
Gli iframe di altre origini e gli shadow root chiusi non sono gestiti. Alcuni
siti richiedono gesti reali dell'utente e possono rifiutare clic sintetici.

Android può sospendere Firefox in background o a schermo bloccato: riaprilo
per riprendere. Non è garantita l'operatività continua 24/7.

## Firma e pubblicazione per il maintainer

Prima della firma: eseguire test reali su Android, definire la privacy policy
e la dichiarazione dei dati trasferiti, verificare i requisiti AMO correnti.
Creare un pacchetto con `python3 build.py`, poi sottoporlo a Mozilla AMO come
listed o unlisted. Distribuire l'XPI firmato risultante, non rinominare l'XPI
non firmato come se fosse stato approvato. Non pubblicare token o credenziali.

Per la pubblicazione dallo store: accedi a
https://addons.mozilla.org/developers/addon/submit/distribution,
scegli la distribuzione su addons.mozilla.org, carica il pacchetto e completa
scheda, compatibilità Android, dichiarazioni dei dati e privacy policy. Attendi
firma/review secondo il flusso Mozilla; solo allora aggiungi il link pubblico
della scheda alle istruzioni. Il progetto non ha eseguito questa pubblicazione.

Riferimenti Mozilla:
- https://extensionworkshop.com/documentation/publish/install-self-distributed/
- https://extensionworkshop.com/documentation/develop/choosing-a-firefox-version-for-extension-development/
- https://extensionworkshop.com/documentation/publish/submitting-an-add-on/
