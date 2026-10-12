# Reproducible agent release gate

`release_gate.py` runs the same four fixed scenario descriptions through Codex and Claude against baseline and candidate builds: 16 episodes. It measures **actual emitted usage metadata**, never estimates tokens from text bytes. No live model is started unless `--run` is explicitly supplied.

The runner requires already installed clients in isolated working/configuration environments. Concrete owned fixture hooks are now provided by `benchmark_fixture.py`, `benchmark_hooks.py` and `benchmark_setup.py`. It does not install model clients, change their MCP settings or infer that a configured build label is the actual connected version. The prepare hook must inspect and confirm the requested build before returning ready. The hooks operate only on episode-owned disposable URLs. The new fixture implements all four scenarios; the existing interaction lab is not used for this gate.

## Frozen configuration

Configuration version 1 contains:

```json
{
  "version": 1,
  "clients": {
    "codex": {
      "model": "EXACT_MODEL_ID",
      "settingsLabel": "reasoning-and-tools-profile-v1",
      "baseline": {"command": ["/absolute/path/codex-baseline-runner"], "cwd": "/absolute/path/baseline", "buildId": "BASELINE_COMMIT"},
      "candidate": {"command": ["/absolute/path/codex-candidate-runner"], "cwd": "/absolute/path/candidate", "buildId": "CANDIDATE_COMMIT"}
    },
    "claude": {
      "model": "EXACT_MODEL_ID",
      "settingsLabel": "reasoning-and-tools-profile-v1",
      "baseline": {"command": ["/absolute/path/claude-baseline-runner"], "cwd": "/absolute/path/baseline", "buildId": "BASELINE_COMMIT"},
      "candidate": {"command": ["/absolute/path/claude-candidate-runner"], "cwd": "/absolute/path/candidate", "buildId": "CANDIDATE_COMMIT"}
    }
  },
  "fixture": {
    "prepare": ["/absolute/path/fixture-hook", "prepare"],
    "verify": ["/absolute/path/fixture-hook", "verify"],
    "cleanup": ["/absolute/path/fixture-hook", "cleanup"]
  },
  "limits": {"inputTokens": 300000, "outputTokens": 20000, "wallSeconds": 1200}
}
```

Commands are argument arrays executed without a shell. Model runners receive the fixed prompt on stdin and must emit JSON Lines on stdout. Pin model, reasoning settings, tool permissions and MCP endpoint/profile in these runners; `model` and `settingsLabel` document that frozen configuration but cannot enforce a third-party executable's behavior. Keep credentials outside this file. The report includes a SHA-256 of configuration plus scenario text, model/build labels, aggregate counters and outcomes, not raw model output or page contents.

Codex parsing accepts `turn.completed` events with `usage.input_tokens`, `output_tokens`, and optional `cached_input_tokens`. Codex input includes cached input, which is recorded separately without adding it twice. Claude parsing accepts one final `type:result` record with `usage.input_tokens`, `output_tokens`, `cache_read_input_tokens` and `cache_creation_input_tokens`; the latter two are added to obtain inclusive input. Missing, malformed, negative or duplicate cumulative Claude usage prevents promotion. A changed client metadata format requires an explicit parser update and fixture test, not guessed counters.

## Fixture hook protocol

Each hook receives one JSON object on stdin: `client`, `scenario`, `revision`, `buildId`, `episodeId`. Each must return one JSON object on stdout and exit zero. Hooks are bounded to 30 seconds (cleanup 10 seconds), inherit the caller environment and never receive model output as evidence.

- `prepare`: create isolated fixture state, confirm actual selected browser/runtime build, and return `{"ready":true,"buildId":"REQUESTED_ACTUAL_BUILD","context":{"device":"authorized-id","fixtureUrl":"reachable-owned-fixture","tabId":123}}`. Context is embedded as data in the fixed model prompt. Include scenario-specific values and known action identity when required.
- `verify`: independently query final fixture state and return `{"verified":true,"checks":{"savedValue":true,"expectedCount":true}}`. Checks must be nonempty and all exactly `true`. Never obtain `verified` by asking the model whether it succeeded.
- For `uncertain_result`, verifier must additionally attest `"faultInjected":true,"effectCount":1`. The supplied fixture actually commits an identified application effect, closes its HTTP connection without a response, and exposes a separate reconcile-by-identity control. A normal successful click is not a lost-response test. This is an application-response fault, not an MCP broker transport fault; deterministic broker tests separately cover transport uncertainty.
- `cleanup`: remove only the episode's fixture state/tabs and return `{"cleaned":true}`. Runs even after model failure or budget exhaustion. A failed cleanup blocks promotion.

The scenarios are form submission, asynchronous filtering, independent values in two tabs and recovery after a lost response. The supplied hooks independently inspect server state and the browser status element, so a model declaration of success is insufficient. Real-device/model runs remain an integration requirement; fixture unit tests do not establish them. `concurrent_tabs` exercises a single agent operating two pages; multi-agent collision testing belongs to the separate deterministic regression suite.

## Running and interpreting results

```sh
python3 release_gate.py /private/frozen-gate.json
python3 release_gate.py /private/frozen-gate.json --run --output state/release-gate.json
python3 -m unittest -q test_release_gate
```

Without `--run`, only configuration structure is validated and `executed:false` is recorded. Reports are atomically written with mode 0600. A run stops after a failed/unverified episode, missing usage, any budget cap or cleanup failure. Incomplete matrices cannot pass. No automatic retry starts further paid work.

Token limits are checked as clients emit usage; clients commonly emit totals only after a turn, so one turn can overshoot before accounting arrives. Wall-time enforcement terminates the process group independently. Cleanup can add up to ten seconds after the model budget expires. Processes are capped to 16 MiB output, and output text is discarded after parsing metadata. The report's `promotable` field means **this success/usage gate passed**, not that all roadmap gates passed.

`observedToolCalls` counts recognized metadata tool records (Codex MCP calls, Claude tool-use records); those client categories are not directly interchangeable and neither is an inference count. The harness explicitly marks the 30% **model-call reduction** target as unmeasured. It cannot certify that optimization, transport timing, Android power consumption, signing, publication or external marketplace review. Other release gates must establish those separately.

## Concrete fixture setup (no agents started)

Start the owned HTTP fixture in a separate terminal:

```sh
python3 benchmark_fixture.py --state-file /private/gate-server.json
```

The server binds loopback only and writes its origin/admin token to that mode-0600 file. It opens no browser, exposes no page logs and starts no model. Keep it running for the gate; stop it after cleanup. Choose `--port` when a stable loopback port is needed. The browser must reach this origin, or an explicitly configured forwarding address: the scripts do not create public exposure, VPNs or tunnels.

Create private settings for the config generator:

```json
{
  "serverState": "/private/gate-server.json",
  "browserOrigin": "http://127.0.0.1:YOUR_FIXTURE_PORT",
  "revisions": {
    "baseline": {"repo": "/owned/baseline-checkout", "connectionFile": "/private/baseline-connection.json", "device": "baseline-fixture"},
    "candidate": {"repo": "/owned/candidate-checkout", "connectionFile": "/private/candidate-connection.json", "device": "candidate-fixture"}
  },
  "clients": {
    "codex": {"model": "PINNED_CODEX_MODEL", "settingsLabel": "frozen-reasoning-and-tools", "command": ["/owned/codex-runner", "--model", "{model}", "--repo", "{repo}", "--connection", "{connectionFile}"]},
    "claude": {"model": "PINNED_CLAUDE_MODEL", "settingsLabel": "frozen-reasoning-and-tools", "command": ["/owned/claude-runner", "--model", "{model}", "--repo", "{repo}", "--connection", "{connectionFile}"]}
  }
}
```

Custom runner paths above are optional. Omit `command` to use the included `benchmark_agent.py` launcher; optionally set `executable` to your installed Codex or Claude path. The built-in runner pins the selected revision/profile as the MCP, requests structured JSON output and the exact model. Codex ignores user config while retaining its existing authentication; Claude uses strict MCP configuration and permits only the bridge MCP tools. Installed clients must support these flags; incompatible versions fail rather than silently falling back. Custom commands remain available when a deployment needs a different frozen configuration. Each runner must use the selected revision's MCP/profile, accept its prompt on stdin, and emit that client's structured JSON Lines. Tokens stay in the referenced private profile and are loaded only into the MCP subprocess environment. Command templates support `{repo}`, `{connectionFile}`, `{device}`, `{model}` and `{cwd}` substitution without a shell.

```sh
python3 benchmark_setup.py /private/gate-settings.json --output-dir state/frozen-gate
python3 release_gate.py state/frozen-gate/release-gate.json
# Only when the prepared environments and paid run are intended:
python3 release_gate.py state/frozen-gate/release-gate.json --run
```

Setup generates complete private hook/gate configs and separate client working directories without starting models or operating the tablet. It fingerprints source files and pins expected MCP/extension versions. Preparation refuses drift or a mismatched extension. Use separately prepared authorized baseline/candidate browser devices; the tool will not silently downgrade a user's extension or label a candidate extension as baseline. Source changes require regeneration. Client MCP routing is the frozen runner's responsibility; the hook cannot attest that an unrelated third-party executable honors its command configuration.

Preparation opens only its own fixture tabs and records them privately; verification checks server effects and visible browser status. Cleanup closes only URLs under the exact episode prefix, including tabs opened before a lost prepare response, and removes episode state. It preserves unrelated tabs. A disconnected browser can prevent cleanup; the gate then fails rather than claiming success. The uncertainty scenario counts every commit attempt, deliberately detecting a duplicated effect even if the same application action ID was reused.

Local validation: `python3 -m unittest -q test_benchmark_fixture test_release_gate`. These exercise actual loopback HTTP response loss, independent state checks for all four scenarios, source drift, cleanup ownership and full configuration generation; browser operations are replaced by an owned fake in this suite. No paid Codex/Claude episode or real tablet action was performed to produce this validation.

The bundled Codex launch shape was checked against installed `codex exec --help` and the [official CLI reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli); Claude flags were checked against the installed CLI help. Paid client behavior has not been exercised by these tests. Authentication and model access must already work in the chosen environment.

## Two revisions on one Android Firefox installation

A baseline can coexist with the candidate as a separately installed test add-on.
Create a detached worktree at the historical baseline commit. Change only
`manifest.json`'s display name and `browser_specific_settings.gecko.id` to a
unique benchmark identity, then package its unchanged extension sources. Enroll
a separate browser device ID for it. Do not copy the candidate's pairing secrets
into it or overwrite the candidate add-on.

The setup fingerprints this modified baseline checkout, including its manifest,
and still requires the actual historical extension version. Record the original
commit and the two manifest-only changes in the benchmark report. This is a
baseline with an isolated add-on identity, not an unmodified signed release.
Both add-ons share Firefox's tabs and page sessions; episode-owned tabs and
sequential execution remain required. A distinct add-on identity is not a
separate Android browser profile. Installation and opt-in pairing are real
Firefox steps; preparing the XPI alone is not readiness for a paid run.

The original baseline commit used for the current candidate is
`6a3544387743049411c06de29391b67f5f9cdaef` (extension and MCP 0.3.1). The prepared
local baseline uses add-on ID
`android-browser-bridge-benchmark-baseline@local.invalid` and display name
`Browser Bridge benchmark baseline`. These changes preserve the old browser
engine and prevent replacement of the user's 1.0.0 installation. No completed
baseline/candidate matrix is claimed by this preparation.
