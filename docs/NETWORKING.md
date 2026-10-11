# Connessioni senza VPN o tunnel esterni

L'estensione Android effettua richieste verso il servizio sul Linux. Il Linux
non deve aprire connessioni entranti verso il telefono. Perciò il telefono può
essere su rete mobile con CGNAT: basta che possa raggiungere il servizio Linux.

| Situazione | Configurazione |
| --- | --- |
| Android e Linux nella stessa LAN fidata | IP privato Linux e porta TCP; HTTP ammesso, HTTPS preferibile |
| Android mobile, Linux con IP pubblico | HTTPS diretto al Linux; nessuna VPN o infrastruttura relay |
| Linux dietro NAT gestibile | Inoltro di una porta TCP al Linux e HTTPS |
| Linux con IPv6 pubblico | HTTPS IPv6, firewall entrante configurato e connettività IPv6 da Android |
| Linux dietro CGNAT senza accesso entrante | Collegamento diretto non disponibile; serve cambiare raggiungibilità o introdurre un altro trasporto |

## Stessa rete

```json
{
  "mcpServers": {
    "android-browser": {
      "command": "python3",
      "args": ["/path/android-browser-mcp.pyz", "--listen", "0.0.0.0",
               "--port", "8766", "--url", "http://192.168.1.10:8766"]
    }
  }
}
```

Sostituisci l'IP con quello del tuo Linux. Consenti la porta solo dalla rete
che intendi usare. HTTP trasporta token e contenuti senza cifratura: usarlo
solo su LAN fidata o su un trasporto già cifrato.

## Server pubblico, HTTPS senza proxy

Il servizio supporta TLS nativamente, senza nginx, Cloudflare o altri proxy:

```json
{
  "mcpServers": {
    "android-browser": {
      "command": "python3",
      "args": ["/path/android-browser-mcp.pyz", "--listen", "0.0.0.0",
               "--port", "8766", "--url", "https://linux.example.org:8766",
               "--cert", "/path/fullchain.pem", "--key", "/path/privkey.pem"]
    }
  }
}
```

Il certificato deve essere valido per il nome pubblicizzato e fidato da Firefox.
Gestione e rinnovo del certificato sono responsabilità del deployment; il
prototipo non richiede un provider specifico e non ottiene certificati da solo.
Il certificato può anche essere per un IP, se emesso per quell'indirizzo.
Un certificato autofirmato richiede una configurazione di fiducia sul dispositivo.
Non disabilitare la verifica TLS.

Per IPv6 usa `--listen ::` e un nome pubblico o URL con IP tra parentesi quadre.
Per un reverse proxy HTTPS già esistente, puoi mantenere il servizio in
loopback e pubblicizzare l'URL del proxy: non è obbligatorio installarne uno.

## Cambi rete e indirizzi alternativi

Con un endpoint pubblico stabile, passare dal Wi-Fi alla rete mobile non richiede
un nuovo abbinamento: l'estensione riprova dopo un errore di rete.

Puoi aggiungere fino a quattro `--fallback-url` al MCP. Ad esempio un indirizzo
LAN HTTPS e un indirizzo pubblico HTTPS che conducono **allo stesso broker**.
Il codice BB1 include gli indirizzi; l'estensione prova gli altri quando quello
corrente non risponde e ricorda l'ultimo funzionante. Non sono servizi diversi
e non devono usare credenziali diverse. Il broker ha un solo listener: per
percorsi TLS e HTTP simultanei serve un proxy proprio, oppure usare HTTPS
in entrambi i percorsi.

L'assegnazione di un IP pubblico non garantisce la raggiungibilità: controlla
firewall, routing, NAT, certificato e accesso effettivo dal dispositivo Android.
Se entrambe le estremità non sono raggiungibili, questo prototipo non include
WebRTC/STUN/TURN o una soluzione universale di attraversamento del NAT.
