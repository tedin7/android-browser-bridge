# Keeping the bridge always on

This guide keeps an Android broker reachable from agents on another machine,
across closed sessions, crashes and reboots. Names in angle brackets are
placeholders: keep your real hosts, addresses and device names in a private
note, never in this repository.

```
Android (Termux)              <relay-host>                  <agent-host>
broker 127.0.0.1:8766  <-ssh -R-  127.0.0.1:<relay-port>  <-ssh -R-  127.0.0.1:<agent-port>
```

Agents on `<agent-host>` use `http://127.0.0.1:<agent-port>`. Every hop listens
on loopback only; the broker keeps its own authentication.

## Why processes die on Android

Linux distributions inside Termux usually run under `proot` with
`--kill-on-exit`. When that proot instance exits, every process it started dies
with it, including ones started with `nohup`, `setsid` or `disown`. A broker or
tunnel launched from an agent session inside proot therefore stops as soon as
that session ends, while the other side of the tunnel keeps an open port that
answers with a reset.

Start long-lived processes from Termux itself (a Termux shell, Termux:Boot or a
tmux server started from Termux), never from inside a proot session. Check with:

```sh
grep TracerPid /proc/<pid>/status   # 0 means no proot tracer
```

## 1. Supervisor on Android (Termux)

A small loop restarts the broker and the first tunnel when they disappear and
keeps Android from suspending Termux:

```sh
#!/data/data/com.termux/files/usr/bin/bash
set -u
termux-wake-lock
while true; do
  if ! curl -s -m 5 -o /dev/null http://127.0.0.1:8766/health; then
    nohup proot-distro login <distro> -- python3 <path>/android-browser-mcp.pyz \
      --broker-only --local --port 8766 --state-dir <state-dir> >>broker.log 2>&1 &
    sleep 10
  fi
  if ! pgrep -f -- "-R 127.0.0.1:<relay-port>:127.0.0.1:8766" >/dev/null; then
    ssh -f -T -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=15 -o ServerAliveCountMax=2 \
      -R 127.0.0.1:<relay-port>:127.0.0.1:8766 <relay-host>
  fi
  sleep 30
done
```

- Guard against a second copy (a pid file is enough).
- Start it at boot with a Termux:Boot script in `~/.termux/boot/`.
- To start it now without a visible window, ask an existing Termux tmux server
  to create a dedicated one, so it is not a child of any proot session:
  `tmux run-shell -b "tmux -S ~/.bridge.sock new-session -d <supervisor>"`.

## 2. Service on the relay host (systemd)

```ini
[Unit]
Description=Browser Bridge tunnel to <agent-host>
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/ssh -T -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -R 127.0.0.1:<agent-port>:127.0.0.1:<relay-port> <agent-host>
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

`ExitOnForwardFailure` makes ssh exit if the remote port is still held by a
stale connection; systemd then retries every 10 seconds until it is free.

## 3. Check every hop

```sh
curl -s http://127.0.0.1:8766/health              # on Android
curl -s http://127.0.0.1:<relay-port>/health      # on <relay-host>
curl -s http://127.0.0.1:<agent-port>/health      # on <agent-host>
```

All three return `{"ok":true,...}`. If only the last hop fails, restart the
service on the relay host; if the first two fail, the supervisor on Android is
not running.

## Keeping this repository public-safe

`test_public_hygiene.py` rejects public IP addresses, personal email
addresses, private keys and bridge credentials in tracked files. Put your own
host, device and person names in an untracked `.private-names` file (one per
line) to reject them too, and enable the hook once per clone:

```sh
git config core.hooksPath .githooks
```
