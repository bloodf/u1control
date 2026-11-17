"""What u1control needs that it can't install by itself, and whether each one is there.

No I/O and no host calls here: the caller passes what it already knows (plugin.requirements_state), so the
check is cheap and never runs at import or while OrcaSlicer registers the plugin. Each answer is
{"id", "status": "ok" | "missing" | "unknown", "details": {...}}; the page says what each one is for and how
to get it (Settings > Requirements), and turns off what needs a missing one.
"""

PRINTER_AGENTS = "printer_agents"   # OrcaSlicer's "Use printer agents instead of print hosts" + u1control as agent
EXTENDED = "extended_firmware"      # paxx12's U1 Extended Firmware (Advanced Mode, [web] firmware_config: true)
SPOOLMAN = "spoolman"               # a Spoolman URL in Settings, or the printer's own Moonraker [spoolman]
SPOOLER = "spooler"                 # the Spooler plugin (Spoolman spools as OrcaSlicer filament profiles, the stock list)


def _item(rid, status, **details):
    return {"id": rid, "status": status, "details": {k: v for k, v in details.items() if v}}


def printer_agents(on):
    """OrcaSlicer has no API for the preference, so "not seen yet" is all we can say (unknown, never missing)."""
    return _item(PRINTER_AGENTS, "ok" if on else "unknown")


def extended_firmware(firmware):
    """From the connected printer's probe (service.firmware); unknown until a printer answered."""
    kind = (firmware or {}).get("kind")
    status = {"extended": "ok", "stock": "missing"}.get(kind, "unknown")
    return _item(EXTENDED, status, version=(firmware or {}).get("version") if status != "unknown" else "")


def spoolman(url, link):
    """url: Spoolman URL from Settings. link: what the last Spoolman connect found ("moonraker", "direct",
    "none" = no URL and no Spoolman on the printer, "" = not tried yet). No network probe of its own."""
    if url:
        return _item(SPOOLMAN, "ok", url=url, via="direct")
    if link == "moonraker":
        return _item(SPOOLMAN, "ok", via="printer")
    return _item(SPOOLMAN, "missing" if link == "none" else "unknown")


def spooler(state):
    """state: plugin.spooler_state() ({"installed", "url", ...}): its bundle, presets or settings file seen."""
    state = state or {}
    return _item(SPOOLER, "ok" if state.get("installed") else "missing", url=state.get("url"))


def check(agent_on, firmware, spoolman_url, spoolman_link, spooler_state=None):
    return [printer_agents(agent_on), extended_firmware(firmware), spoolman(spoolman_url, spoolman_link),
            spooler(spooler_state)]
