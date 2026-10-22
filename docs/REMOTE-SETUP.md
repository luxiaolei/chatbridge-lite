# Remote Desktop Commander: recommended local-computer connection

This is the **recommended first setup** for a ChatGPT Web worker that needs to read or edit files or run approved commands on your own computer. It is a separate product from ChatBridge Lite.

- Official project: https://github.com/desktop-commander/remote-desktop-commander
- Official setup walkthrough: https://github.com/desktop-commander/remote-desktop-commander/blob/main/docs/SETUP.md
- Device dashboard: https://mcp.desktopcommander.app/
- ChatGPT app listing: https://chatgpt.com/plugins/plugin_asdk_app_6a057d268ebc81919918d37eec718425

## 1. Pair your computer

On the computer ChatGPT should access, open a terminal and run:

```bash
npx @wonderwhy-er/desktop-commander@latest remote
```

Requirements: Node.js 18+ and a Remote Desktop Commander account. On first run, a browser opens a device-verification page.

1. Sign in to the account you intend to use.
2. Compare the one-time verification code in the browser with the code printed in the terminal.
3. Approve only if the codes match.
4. Wait for the terminal to report that the device is ready.
5. Keep the remote-device process running while you need access. Stopping it disconnects the computer.

If you already installed the official ChatGPT app integration, proceed to Step 2. Do not create a second connector unnecessarily.

## 2. Connect ChatGPT

1. In ChatGPT, open Apps / Connectors and search for **Remote Desktop Commander**.
2. Install/connect the official app if it is available for your account/workspace, then finish its OAuth sign-in with the same account used to pair the device.
3. Select the paired computer when prompted.
4. If the app listing is unavailable and your workspace/account supports custom remote MCP connectors, follow the official setup guide. Its documented endpoint is:

   ```text
   https://mcp.desktopcommander.app/mcp
   ```

   The manual ChatGPT connector flow may require Developer Mode or workspace permission. Do not assume every account can add a custom connector.

## 3. Verify the exact machine with a read-only task

Ask ChatGPT:

```text
Using Remote Desktop Commander, tell me the paired device name and operating system.
List only the top-level entries in the project directory I specify.
Do not create, edit, delete, install, or execute anything yet.
```

Confirm the reported device is the intended computer. Then try one harmless read-only project inspection before authorizing writes or terminal commands.

## 4. Security and limits

Remote Desktop Commander tools execute under the connected user's local OS permissions. A connection can therefore expose broad filesystem and terminal capabilities; use it like a credential-bearing development tool.

- Pair only a device you own/control and verify the one-time code.
- Never paste passwords, cookies, OAuth secrets or tokens into prompts or repository files.
- Give the worker only the access needed for its assigned task; inspect the exact host and command before allowing changes.
- Stop the local agent with Ctrl+C when it is not needed, or revoke the device from the dashboard.
- Usage limits, free allowances and paid tiers can change. Check the current dashboard and terms before planning frequent or unattended calls. This repository does not promise a particular free quota or price.
- Do not use this integration to bypass ChatGPT/Codex quotas or platform restrictions.

## 5. Important ChatBridge Lite boundary

Remote Desktop Commander is the **local-machine access connector**. It can let a ChatGPT worker reach approved files and commands, including the locally installed Reason Network CLI when permitted.

The current ChatBridge Lite alpha still uses the existing ChatBridge + Ego Lite `ego-browser` runtime to dispatch and inspect ChatGPT Web conversations. Remote Desktop Commander does **not** replace that browser-dispatch component in this release. The two solve different problems:

| Component | Responsibility |
| --- | --- |
| Remote Desktop Commander | Authorized local filesystem / terminal access from ChatGPT |
| Ego Lite / `ego-browser` | Current ChatGPT Web conversation/browser dispatch |
| Reason Network | Active callback notification into the named Codex App session |
| ChatBridge queue | Durable task/result/owner-ACK record |

The public [chatgpt-open-remote-mcp](https://github.com/luxiaolei/chatgpt-open-remote-mcp) repository is an advanced, Linux-focused alternative with explicit grants and OpenAI Secure MCP Tunnel setup. It is not the default beginner path and does not replace Ego Lite without a separately implemented and tested adapter.

## Troubleshooting

- **Device offline:** ensure the `npx ... remote` process is still running.
- **ChatGPT sees no device:** confirm both the local device and ChatGPT app use the same Remote Desktop Commander account, then refresh the app connection.
- **Custom connector unavailable:** ask the workspace admin or use the official app listing if available. Do not work around a disabled policy.
- **Unexpected access:** stop the local agent and revoke the device from the dashboard before investigating.
