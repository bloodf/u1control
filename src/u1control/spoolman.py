"""Spoolman integration, one spool per U1 toolhead.

Transport: Moonraker's /server/spoolman/proxy when the printer has [spoolman] configured
(extended firmware's SpoolLink does this), otherwise Spoolman's REST API directly.

Binding toolhead -> spool:
  * extended firmware: print_task_config.filament_spool_id[] + SET_SPOOL_ID CHANNEL=n SPOOL_ID=id
    (SpoolLink then writes the filament info and switches the active spool on tool change).
  * stock firmware: the spool's `location` is set to "<printer> T<n>" so the binding lives in
    Spoolman and every client sees it; the plugin writes filament info with SET_PRINT_FILAMENT_CONFIG.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request

import u1
from moonraker import PrinterError, _NO_PROXY

LOCATION_FMT = "%s T%d"


class SpoolmanError(RuntimeError):
    pass


class Spoolman:
    def __init__(self, url="", moonraker=None, timeout=5.0, opener=None):
        self.url = (url or "").rstrip("/")
        if self.url and "://" not in self.url:
            self.url = "http://" + self.url
        self.mr = moonraker
        self.timeout = timeout
        self._open = (opener or _NO_PROXY).open
        self.via_moonraker = False

    def connect(self):
        """Prefer the printer's own Spoolman link; fall back to the configured URL."""
        if self.mr is not None:
            try:
                status = self.mr.request("GET", "/server/spoolman/status", timeout=3) or {}
                if status.get("spoolman_connected"):
                    self.via_moonraker = True
                    return {"via": "moonraker", "active_spool": status.get("spool_id")}
            except PrinterError:
                pass
        if not self.url:
            raise SpoolmanError("Spoolman not configured: set its URL in u1control settings")
        self.via_moonraker = False
        self.call("GET", "/v1/health")
        return {"via": "direct", "active_spool": None}

    def call(self, method, path, query=None, body=None):
        if self.via_moonraker:
            result = self.mr.request("POST", "/server/spoolman/proxy", json_body={
                "use_v2_response": True, "request_method": method, "path": path,
                "query": urllib.parse.urlencode(query or {}), "body": body})
            if isinstance(result, dict) and result.get("error"):
                raise SpoolmanError("Spoolman: %s" % result["error"].get("message", result["error"]))
            return result.get("response") if isinstance(result, dict) else result
        url = self.url + "/api" + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self._open(req, timeout=self.timeout) as resp:
                raw = resp.read(32 * 1024 * 1024)
        except urllib.error.HTTPError as e:
            raise SpoolmanError("Spoolman said HTTP %d" % e.code)
        except (OSError, ValueError) as e:
            raise SpoolmanError("can't reach Spoolman at %s (%s)" % (self.url, getattr(e, "reason", e)))
        return json.loads(raw.decode("utf-8")) if raw else None

    # ------------------------------------------------------------------ api

    def spools(self):
        return self.call("GET", "/v1/spool", {"allow_archived": "false", "sort": "last_used:desc"}) or []

    def set_location(self, spool_id, location):
        return self.call("PATCH", "/v1/spool/%d" % int(spool_id), body={"location": location[:64]})

    def use_weight(self, spool_id, grams):
        return self.call("PUT", "/v1/spool/%d/use" % int(spool_id), body={"use_weight": round(float(grams), 2)})


# ---------------------------------------------------------------------- matching

def spool_view(spool):
    """Flatten a Spoolman spool for the UI and for matching."""
    f = spool.get("filament") or {}
    colours = f.get("multi_color_hexes")
    colours = [u1.norm_colour(c) for c in colours.split(",")] if isinstance(colours, str) else []
    return {
        "id": spool.get("id"),
        "filament_id": f.get("id"),
        "name": f.get("name") or "",
        "vendor": (f.get("vendor") or {}).get("name") or "Generic",
        "material": f.get("material") or "",
        "colour": u1.norm_colour(f.get("color_hex")) or (colours[0] if colours else None),
        "colours": [c for c in colours if c],
        "remaining": spool.get("remaining_weight"),
        "location": spool.get("location") or "",
        "last_used": spool.get("last_used") or "",
        "archived": bool(spool.get("archived")),
        "extruder_temp": f.get("settings_extruder_temp"),
        "bed_temp": f.get("settings_bed_temp"),
    }


def match_score(head, spool):
    """Lower is better; None = incompatible material."""
    if not head.get("type") or not spool.get("material"):
        return None
    if u1.material_family(head["type"]) != u1.material_family(spool["material"]):
        return None
    score = u1.colour_distance(head.get("colour"), spool.get("colour"))
    if head["type"].upper() != spool["material"].upper():
        score += 50
    if head.get("vendor") and head["vendor"].lower() != spool["vendor"].lower():
        score += 25
    return score


def best_spool(head, spools, exclude=(), max_score=120.0):
    """Closest compatible spool for a toolhead, or None when nothing is close enough."""
    ranked = sorted((s for s in ((match_score(head, sp), sp) for sp in spools if sp["id"] not in exclude)
                     if s[0] is not None), key=lambda x: x[0])
    return ranked[0][1] if ranked and ranked[0][0] <= max_score else None


def _location_key(text):
    return " ".join(str(text or "").split()).lower()


def location_score(location, printer_name, head):
    """How surely a Spoolman location binds toolhead index `head` (0-based) of this printer, the same
    rule Spooler uses: 2 for "<printer name> T<n>", 1 for any name ending in the word "U1" (the old
    "U1 T<n>" included), 0 for none."""
    key, suffix = _location_key(location), " t%d" % (head + 1)
    if not key.endswith(suffix):
        return 0
    name = key[:-len(suffix)].strip()
    if name == _location_key(printer_name):
        return 2
    return 1 if re.fullmatch(r"(?:.*\s)?u1", name) else 0


def bindings_from_locations(spools, printer_name):
    """{toolhead: spool_id} from spool locations like "Snapmaker U1 T2" (1-based in the UI). Matches
    Spooler (github.com/bloodf/spooler) so both plugins see the same spool on each head: archived
    spools never bind; this printer's exact name beats a name that only ends in "U1"; between equals
    the spool used last wins."""
    out = {}
    for t in range(u1.TOOLHEADS):
        scored = [(location_score(sp.get("location"), printer_name, t), sp) for sp in spools
                  if not sp.get("archived")]
        best = max((score for score, _ in scored), default=0)
        found = [sp for score, sp in scored if score and score == best]
        if found:
            found.sort(key=lambda sp: str(sp.get("last_used") or ""), reverse=True)
            out[t] = found[0]["id"]
    return out


def head_changed(old, new):
    keys = ("type", "colour", "vendor", "loaded")
    return any((old or {}).get(k) != (new or {}).get(k) for k in keys)


def filament_command_for(head_index, spool, extended, force=False):
    """Printer command that applies a spool to a toolhead. force=True (FORCE=1) overrides an official /
    RFID-tagged head: only for a manual bind the user confirmed, never for automatic follow."""
    if extended:
        return "SET_SPOOL_ID CHANNEL=%d SPOOL_ID=%d" % (int(head_index), int(spool["id"]))
    return u1.filament_config_command(head_index, spool["vendor"], spool["material"],
                                      spool["name"] or "Basic", spool["colour"] or "#FFFFFF", force=force)
