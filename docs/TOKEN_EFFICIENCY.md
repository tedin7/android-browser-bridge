# Risposte compatte e uso efficiente del modello

Dalla versione MCP 0.3.1, browser_command usa resultMode compact per default.
Questa parte funziona anche con le estensioni precedenti: non serve reinstallare
Android solo per ridurre il testo restituito al modello.

| Modalità | Comportamento |
| --- | --- |
| compact (default) | read: 2.000 caratteri e 20 controlli; locate: 20 candidati; niente CSS selector o rect ripetuti salvo richiesta |
| full | Dettagli e limiti precedenti: read 12.000 caratteri/120 controlli, locate 100 candidati |
| fields | Sottoinsieme di campi al livello superiore, più metadati protetti di navigazione/sicurezza/paginazione |

I limiti specificati esplicitamente in args prevalgono. I riferimenti restano
utilizzabili per le azioni. Gli stati false di visibilità/abilitazione rimangono;
i duplicati delle etichette vengono rimossi mantenendo accessibleName.
I valori di href/name troppo lunghi vengono abbreviati con flag espliciti.
Non navigare un href marcato troncato: recupera il dettaglio completo prima.
I conteggi totali e il troncamento impediscono di confondere una pagina di
risultati con l’inventario completo. Gli URL dei frame possono omettere query e
fragment con urlQueryOmitted; frameId rimane il riferimento operativo.

Per un’ispezione precisa, usa browser_command con op inspect, args tabId/ref e
resultMode fields, resultFields per esempio ["rect", "visible", "enabled"].
La normale inspect conserva i dettagli completi di un elemento; liste options
molto lunghe richiedono fields quando non servono. Un risultato compatto non è
una garanzia assoluta di numero massimo di byte.

Per leggere solo testo: args selector mirato, maxElements:0 e textLimit adeguato.
Per cercare un pulsante: locate con role/name/label e pochi candidati, poi ref.
Conosci già il dispositivo e i tabId? Riutilizzali nella sessione; ripeti discovery
solo dopo errori di connessione o cambi di target. Usa batch per azioni correlate,
ma ricorda che i suoi passi sono sequenziali e un errore ferma i successivi.

## Screenshot e involucro MCP

Screenshot è utile per aspetto, canvas o sovrapposizioni non risolte dal DOM.
Non richiederlo dopo ogni clic. Nei batch viene restituito come contenuto image,
con imageIndex nel risultato testuale: il base64 non viene duplicato nel JSON.
Questo non elimina il costo visivo dell’immagine per il modello.

Se usi un orchestratore exec, inoltra i blocchi separatamente:

```js
function emitMcp(result) {
  for (const content of result.content) {
    if (content.type === "text") text(content.text);
    else if (content.type === "image") image(content);
  }
}
```

Evita di stampare l’intero oggetto MCP e il testo decodificato una seconda volta.
Log, HTML, JavaScript minificato e tabelle grezze vanno conservati in file:
manda al modello righe rilevanti, conteggi, errori e percorsi di prova.

## Misurazione

python3 benchmark_response.py confronta le dimensioni full/defaultcompact su
fixture locali in un Firefox isolato. Riporta byte UTF-8 e caratteri, non token.
Le immagini non si misurano come token contando i byte del file. I contatori
cumulativi Codex includono contesto ripetuto e input cached; non rappresentano
il numero di caratteri unici caricati né una percentuale del piano.
