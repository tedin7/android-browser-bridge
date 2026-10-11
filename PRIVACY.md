# Privacy — Android Browser Bridge

Updated: 2026-10-11.

Browser Bridge connects your Firefox browser to a Linux broker you select.
The project operates no central service and includes no advertising, analytics,
or transmission of browser data to the maintainer.

## Data sent and recipients

Once you enable control, the paired broker can request tab titles and URLs,
visible page text, links, interactive element metadata and selectors, action
results, requested viewport screenshots, inspected non-password field values and operational errors. Visible page text and URLs may contain personal
information, messages, health or financial information, and other sensitive
data. Do not enable control on pages you do not wish to share.

Pairing codes and extension credentials are sent to the chosen broker for
authentication. The extension does not extract stored passwords, cookies, or
Firefox profile contents. The `read` operation does not include input field
values. `inspect` can return non-password input values; screenshots show rendered page content, including visible form fields. Password values are omitted from DOM metadata, but text visible on screen may appear in screenshots; visible text or URLs may still expose confidential information.

The recipient is your configured Linux broker. Your MCP client and model
provider may receive browser content returned by tool calls, process it, and
store it under their own settings and policies. Review those separately.
Your own reverse proxies and transport configuration may affect the data path.

## Storage

The extension stores broker addresses, its credential, device name, and control
enablement in local extension storage. The broker stores authentication
credentials in your Linux user profile and keeps command/results in memory for
up to ten minutes during normal operation. It does not log page contents or
tokens. Your LLM client may store conversation history and tool results.

## Choice, revocation and deletion

Control remains disabled until you enable it in the extension settings. Disable
control or uninstall the extension to stop polling. Use `browser_revoke` to
remove the device credential at the broker. An action already executing cannot
be undone by revocation. Delete conversation history or other copies at the
services that store them. Uninstalling the extension removes its local storage
according to Firefox behavior.

Use HTTPS for Internet connections. HTTP on a trusted private network is not
encrypted and exposes tokens and page results to parties able to observe that
traffic. No vendor tunnel or mandatory VPN is included.

Support: https://github.com/tedin7/android-browser-bridge/issues
Do not disclose tokens or private page contents in public issues.
