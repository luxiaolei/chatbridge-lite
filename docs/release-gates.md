# Release gates (must pass before claiming real unattended operation)

- [x] Offline dry-run CLI supports Chat and Codex owner modes.
- [x] A local anti-replay attempt ledger distinguishes PREPARED, IN_FLIGHT, UNKNOWN and submitted notifications.
- [x] Callback body carries task ID, version, result, blockers and evidence.
- [x] Monitoring policy excludes stale/quiet/unknown/human-owned conditions.
- [ ] Verify Remote Desktop Commander on a new, authorized machine: pair code, exact device identity, read-only probe, write permission boundary, and current usage/plan limits.
- [ ] If the advanced custom route is offered, verify `chatgpt-open-remote-mcp` separately on its supported Linux host with least-privilege grants and current Secure MCP Tunnel instructions; do not make it a beginner prerequisite.
- [ ] Verify Ego Lite session binding and model selection on a clean first install; Remote Desktop Commander must not be treated as a substitute for `ego-browser`.
- [ ] Real Chat controller → worker → result → controller ACK canary, no duplicate sends.
- [ ] Real Codex App controller → Chat worker → Reason Network wake → durable `queue receive` → owner ACK canary.
- [ ] Close or suspend the original Codex App and verify the exact documented behavior; never infer closed-App wake from in-session push.
- [ ] Fault injection: no Reason daemon, no destination session, send timeout, lost stdout, Codex not loaded, Chat page offline.
- [ ] Real 30-minute Luna Max monitoring with **controlled synthetic tasks** and evidence, including failure and user pause.
- [ ] Verify redacted public docs, privacy review and permitted use under current service terms.
- [ ] Explicitly measure end-to-end completion, duplicates, recovered turns and Codex usage before publishing any numerical savings claim.

`alpha` does not pass production or marketing-claim acceptance just because unit tests pass.
