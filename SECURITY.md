# Security policy

## Reporting a vulnerability

Please report security problems privately, using GitHub's **Report a vulnerability** button on the repository's Security tab, and not in a public issue. This is a volunteer project, so replies may take a few days.

## Keep private data out of issues

Do not post any of these in issues, logs, captures or screenshots:

- MQTT usernames, passwords or the broker host
- your Prefix Topic (it identifies your system)
- device serial numbers (`hsn`), system ids (`sys`) or MAC addresses
- names, addresses or phone numbers from the system's `meta` data

Remove or replace them first. The capture tool in pylumencache obfuscates ids by default, but still check a file before sharing it.
