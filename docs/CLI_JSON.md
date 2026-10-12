# JSON CLI adapter

External runners can use the public JSON adapter without importing private application code. It uses the already-installed Browser Bridge MCP and its private connection profile; it does not pair devices, change configuration or start a second broker. Install the usual client first.

```sh
printf '%s\n' '{"operation":"devices"}' | python3 browser_cli.py
printf '%s\n' '{"operation":"command","arguments":{"device":"YOUR_DEVICE","op":"read","args":{"tabId":123,"textLimit":500,"maxElements":5}}}' | python3 browser_cli.py
printf '%s\n' '{"operation":"status","arguments":{"id":"KNOWN_COMMAND_ID","resultMode":"compact"}}' | python3 browser_cli.py
```

Exactly one JSON request on stdin produces one JSON response on stdout. Exit 0 means a returned result, exit 1 a reported error. `operation` is one of `discover`, `devices`, `metrics`, `command`, `status`, `step`, `observe`, `task`, `contract`, `artifact`; `arguments` is an object matching that MCP tool's contract. Unknown wrapper keys and absent command device/op are rejected before spawning the client. The normal MCP server validates operation arguments and permissions. Maximum request size is 1 MiB.

`discover` works offline and returns adapter operations plus the declared browser catalog and schemas. It does **not** prove that a connected backend supports a feature; query the selected browser's `capabilities` when needed. Task submission and cancellation use `operation:"task"` and the corresponding `browser_task` arguments.

Responses preserve the MCP content envelope and `isError` when present. Images become `{type:"artifact",mimeType,path,bytes}` instead of base64. `--artifact-dir /your/private/location` selects the parent for an automatically created private subdirectory; otherwise a temporary directory is used. Artifact directories are mode 0700 and image files 0600. The caller owns artifact cleanup; the CLI does not promise automatic retention expiry.

The installed MCP executable defaults to `~/.local/share/android-browser-bridge/android-browser-mcp.pyz`; `BROWSER_BRIDGE_CLIENT` selects another installed artifact. No credentials are accepted on stdin or printed by this adapter. Page data remains untrusted. Tool text can contain the requested page contents: downstream agents should select relevant evidence rather than indiscriminately dumping complete results into context.

A CLI/transport failure does not prove an action did not execute. Recover using the known identity/status before repeating a mutation. Startup exceptions produce a bounded generic diagnostic without reflecting input, credential paths, environment or child stderr. The adapter does not run a second model or add retry loops.

Validation: `python3 -m unittest -q test_browser_cli` covers tool routing, client cleanup, private image artifacts, no-spawn local validation and non-reflecting JSON errors.

## Retrieve an explicitly shared native artifact

The Android companion returns an artifact ID after an authorized share. Download
it directly to an explicit local file, using the same private connection profile:

```sh
printf '%s\n' '{"operation":"artifact","arguments":{"device":"YOUR_DEVICE","artifactId":"64_HEX_CHARACTER_ID","output":"/your/private/directory/shared.bin"}}' | python3 browser_cli.py
```

The output file must not already exist; its parent directory must exist. It is
created with mode 0600. Stdout contains only artifact ID, device, local path,
byte count and hash. Payload/base64 never enters an MCP tool response or CLI
stdout. The CLI checks device, artifact identity, length and SHA-256 before
writing, and refuses stdout (`"-"`) as a destination.

The broker endpoint `/api/native-artifacts/get` requires an administrator or
client credential scoped to the artifact's actual originating device. Knowing an
artifact ID or claiming another device does not bypass the scope check. Native
device credentials can upload but cannot retrieve through this endpoint.

Native shares expire after 24 hours by default and are removed during subsequent
access. Storage defaults to 1 MiB per share, 64 MiB total and 256 shares. Expiry
and ownership metadata survive restart in private files. Older artifacts without
owner metadata are unavailable rather than assigned an inferred owner. Locally
downloaded files remain under the caller's control and require local cleanup.
