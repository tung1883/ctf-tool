# ctf-tool - Tricking AI to do naughty stuff

Wanna hacking with AI but it just does not comply?

Just points it to this CTF page and it will be more than happy to "solve the challenges" for you

## Quick start

```
python start.py
```

Opens `http://localhost:8081/edit` in your browser.

## Usage

| URL | Purpose |
|-----|---------|
| `/edit` | Visual editor — pick a config, edit all fields, regenerate the page |
| `/` | Preview the generated landing page |
| `/lab-question/` | Preview the lab/challenges tab |

## Configs

| File | Event |
|------|-------|
| `config.json` | Default / generic CTF |
| `config-mobile.json` | Mobile security CTF |
| `config-reday.json` | Reverse engineering CTF |
| `config-binanalyst.json` | Binary analysis CTF |
| `config-zeroday.json` | Zero-day / exploit CTF |
| `config-malware.json` | Malware analysis CTF |
| `config-botnet.json` | Botnet / C2 CTF |
| `config-crackingday.json` | Password cracking CTF |
| `config-gamecheatday.json` | Game hacking CTF |
| `config-datascraping.json` | Data scraping CTF |

## Proxy forwarding

The **Proxy** tab lets you forward a local port to a remote host:

```
localhost:8082  -->  https://staging.example.com
```

