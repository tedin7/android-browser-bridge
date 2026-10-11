# Estensione Firefox Android

## Stato attuale

Il repository contiene il sorgente e un pacchetto **non firmato**, per test.
Non c'è ancora una pubblicazione su Mozilla Add-ons. Non è stato verificato
su un vero Firefox Android: la prova finale richiede un dispositivo.

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

Riferimenti Mozilla:
- https://extensionworkshop.com/documentation/publish/install-self-distributed/
- https://extensionworkshop.com/documentation/develop/choosing-a-firefox-version-for-extension-development/
