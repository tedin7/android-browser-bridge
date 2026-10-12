/* Local-only opt-in configuration; never populated by broker messages. */
(() => {
  const form = document.getElementById('webmcp-config');
  if (!form) return;
  const field = id => document.getElementById(id);
  const it = navigator.language?.toLowerCase().startsWith('it');
  const labels = it ? {
    'webmcp-heading':'Strumenti del sito (WebMCP sperimentale)',
    'webmcp-help':'Disattivato per impostazione iniziale. Richiede supporto nativo del browser. I siti e strumenti qui autorizzati saranno disponibili ai server collegati; le loro dichiarazioni non concedono altri permessi. Firefox senza supporto continua a usare i controlli DOM.',
    'webmcp-enabled-label':'Abilita solo i siti e strumenti elencati',
    'webmcp-origins-label':'Origini HTTPS autorizzate, una per riga',
    'webmcp-names-label':'Nomi esatti degli strumenti, uno per riga',
    'webmcp-save':'Salva autorizzazioni WebMCP'
  } : {
    'webmcp-heading':'Site tools (experimental WebMCP)',
    'webmcp-help':'Disabled by default. Requires native browser support. Listed sites and tools become available to connected servers; tool declarations grant no additional authority. Firefox without support continues using DOM controls.',
    'webmcp-enabled-label':'Enable only the listed sites and tools',
    'webmcp-origins-label':'Allowed HTTPS origins, one per line',
    'webmcp-names-label':'Exact tool names, one per line',
    'webmcp-save':'Save WebMCP permissions'
  };
  for (const [id, text] of Object.entries(labels)) field(id).textContent = text;
  const split = value => value.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  browser.storage.local.get(['webmcp']).then(saved => {
    const settings = normalizeWebMCPSettings(saved.webmcp);
    field('webmcp-enabled').checked = settings.enabled;
    field('webmcp-origins').value = settings.allowedOrigins.join('\n');
    field('webmcp-names').value = settings.allowedToolNames.join('\n');
  }).catch(() => { field('webmcp-status').textContent = it ? 'Impossibile leggere le autorizzazioni.' : 'Could not read permissions.'; });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    try {
      const webmcp = normalizeWebMCPSettings({enabled: field('webmcp-enabled').checked,
        allowedOrigins: split(field('webmcp-origins').value), allowedToolNames: split(field('webmcp-names').value)});
      await browser.storage.local.set({webmcp});
      field('webmcp-status').textContent = it ? 'Autorizzazioni salvate.' : 'Permissions saved.';
    } catch (failure) { field('webmcp-status').textContent = failure.message; }
  });
})();
