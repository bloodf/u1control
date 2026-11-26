"""Spooler's stock in the U1 Control tab: the list Spooler publishes, and linking one of its spools
to a toolhead. Every printer command still goes through u1control's own queue (Service.submit), for
the printer the page shows; Spooler only supplies the list. Free of the `orca` module."""

import peers
import spoolman as sm
from i18n import tr
from moonraker import PrinterError

STOCK_CHANGED = "Spooler's stock list changed since this one was shown; nothing was written. Pick the spool again."
OWN_KEY = "spoolman:"   # the key of U1 Control's own Spoolman list (own_stock), followed by where it reads Spoolman


def _assign_args(head, spool_id, key):
    if not isinstance(spool_id, int) or isinstance(spool_id, bool) or spool_id <= 0:
        raise ValueError(tr("no spool chosen"))
    if not isinstance(key, str) or not key:
        raise ValueError(tr(STOCK_CHANGED))
    return head, spool_id, key


SPOOL_CACHE_VERSION = 1


class StockMixin:
    """For service.Service: needs lock, firmware, spoolman, bindings, _snapshot, _ctx, cmd_spools, cmd_bind_spool.
    `peers` is a peers.SpoolerLink, set by the plugin (None outside OrcaSlicer: no Spooler to find)."""

    peers = None

    def links_changed(self):
        if self.peers is not None:
            self.peers.links_changed()

    # The last Spoolman list (self.spools + bindings) is kept in memory for the printer's generation and saved to
    # spool_cache_path: a fresh tab or a restart shows it at once; the next read replaces it (self.spools_fresh).

    @staticmethod
    def _cache_key(target):
        return [target.ident, target.spoolman_url]

    def load_spool_cache(self, target):
        """Fill self.spools / self.bindings from the saved list when it is for this printer and Spoolman."""
        doc, _ = peers.read_json(self.spool_cache_path)
        if not doc or doc.get("version") != SPOOL_CACHE_VERSION or doc.get("key") != self._cache_key(target):
            return
        spools, bindings = doc.get("spools"), doc.get("bindings")
        if not isinstance(spools, list) or not isinstance(bindings, dict):
            return
        try:
            bindings = {int(k): int(v) for k, v in bindings.items()}
        except (TypeError, ValueError):
            return
        with self.lock:
            if self.target is target and not self.spools_fresh and not self.spools:
                self.spools, self.bindings = [x for x in spools if isinstance(x, dict) and "id" in x], bindings

    def save_spool_cache(self):
        if not self.spool_cache_path:
            return
        with self.lock:
            target, spools, bindings = self.target, list(self.spools), {str(k): v for k, v in self.bindings.items()}
        if target is None:
            return
        doc = {"version": SPOOL_CACHE_VERSION, "key": self._cache_key(target), "spools": spools, "bindings": bindings}
        if doc == self._cache_saved:
            return
        try:
            peers.write_json(self.spool_cache_path, doc)
            self._cache_saved = doc
        except OSError as e:
            self.log("u1control: can't save the spool list (%s)" % e)

    def cached_spools(self):
        """What the page shows before Spoolman answers (no I/O): {"spools", "bindings", "stale"}."""
        with self.lock:
            return {"spools": list(self.spools), "bindings": {str(k): v for k, v in self.bindings.items()},
                    "stale": not self.spools_fresh}

    def cached_spool(self, spool_id):
        with self.lock:
            return next((s for s in self.spools if s["id"] == spool_id), None)

    def want_stock(self, refresh=False):
        if self.peers is not None:
            self.peers.want_stock(refresh)

    def spooler_spoolman(self):
        """The Spoolman address the running Spooler uses ("" when Spooler doesn't run here or names none)."""
        if self.peers is None:
            return ""
        peer = self.peers.spooler()
        return peer["origin"] if peer["state"] == "active" else ""

    def _own_origin(self, target):
        """Where U1 Control reads Spoolman, as own_stock's key names it."""
        with self.lock:
            via_printer = self.spoolman is not None and self.spoolman.via_moonraker
        return "printer" if via_printer else peers.normalize_origin(target.spoolman_url or self.spooler_spoolman())

    def own_stock(self, target, refresh=False):
        """U1 Control's own Spoolman spools as a stock list, for when Spooler shares none (not installed, not running,
        or no list): code "own". With no Spoolman to read, code "no_spoolman" (the page says what to set); when the
        read fails, code "own_error" with the reason. None without a printer."""
        if target is None:
            return None
        base = {**peers.parse_stock(None, None), "source": "spoolman"}
        with self.lock:
            spools = list(self.spools)
        if refresh or not spools:
            # ponytail: an empty Spoolman is read again on every stock poll (5 s); a "read once" flag if that matters
            try:
                self.cmd_spools()
            except (PrinterError, sm.SpoolmanError) as e:
                if not target.spoolman_url and not self.spooler_spoolman() and self.spoolman_link != "moonraker":
                    return {**base, "state": "error", "code": "no_spoolman",
                            "text": "No Spoolman to list spools from: set its address in U1 Control's settings."}
                return {**base, "state": "error", "code": "own_error", "detail": str(e),
                        "text": "Couldn't read Spoolman: %s" % e}
            with self.lock:
                spools = list(self.spools)
        rows = [{"id": sp["id"], "filament_id": sp.get("filament_id"), "name": sp.get("name") or "",
                 "vendor": sp.get("vendor") or "Generic", "material": sp.get("material") or "",
                 "location": sp.get("location") or "", "colour": sp.get("colour"), "colours": sp.get("colours") or [],
                 "remaining": sp.get("remaining"), "initial": sp.get("initial"), "low": False, "use_first": False}
                for sp in spools if not sp.get("archived")]
        origin = self._own_origin(target)
        return {**base, "state": "ok", "code": "own", "text": "", "rows": rows, "key": OWN_KEY + origin, "origin": origin}

    def _usage_owner(self, target):
        """Who records this printer's filament use in Spoolman, for the stock view's note."""
        with self.lock:
            kind, smc = self.firmware["kind"], self.spoolman
        if target is None:
            return "unknown"
        if kind == "extended":
            return "printer"     # SpoolLink / Moonraker on the Extended Firmware
        if smc is not None and smc.via_moonraker:
            return "printer"     # the printer's own Moonraker Spoolman link
        if not target.spoolman_report_usage:
            return "off"
        return "u1control"

    def _origin_check(self, target, spooler_origin):
        """True: same Spoolman; False: different; None: can't tell (U1 Control reaches Spoolman through the
        printer, whose Spoolman address it doesn't know)."""
        mine = peers.normalize_origin(target.spoolman_url) if target else ""
        with self.lock:
            via_printer = self.spoolman is not None and self.spoolman.via_moonraker
        if not mine or via_printer or not spooler_origin:
            return None
        return mine == spooler_origin

    def cmd_stock(self, refresh=False):
        """Spooler's state and stock list, with what this printer needs to use it. When Spooler shares no list,
        the stock is U1 Control's own Spoolman read (own_stock), never an endless wait."""
        _, _, target = self._snapshot()
        if self.peers is None:
            spooler = {"state": "absent", "text": peers.STATE_TEXT["absent"], "detail": "", "version": "", "origin": ""}
            stock = {**peers.parse_stock(None, None), "state": "unavailable", "code": "unavailable", "text": spooler["text"]}
        else:
            self.want_stock(bool(refresh))
            spooler, stock = self.peers.stock()
            spooler = {k: v for k, v in spooler.items() if k != "session"}
        same = self._origin_check(target, spooler["origin"]) if spooler["state"] == "active" else None
        if stock["state"] not in ("ok", "stale"):
            own = self.own_stock(target, bool(refresh))
            if own is not None:
                stock, same = own, None
        with self.lock:
            bindings = {str(k): v for k, v in self.bindings.items()}
        return {"spooler": spooler, "stock": stock, "same_spoolman": same, "usage": self._usage_owner(target),
                "bindings": bindings}

    def _current_row(self, key, spool_id):
        if self.peers is None:
            raise ValueError(tr(peers.STATE_TEXT["absent"]))
        spooler, stock = self.peers.stock()
        if spooler["state"] != "active":
            raise ValueError(tr(spooler["text"]))
        if stock["key"] != key:
            raise ValueError(tr(STOCK_CHANGED))
        row = next((r for r in stock["rows"] if r["id"] == spool_id), None)
        if row is None:
            raise ValueError(tr("Spool #%d is no longer in Spooler's stock list; nothing was written.") % spool_id)
        return spooler, row

    def cmd_stock_assign(self, head, spool_id, key, force=False):
        """Link a spool picked from Spooler's list to a toolhead of the printer this request was made for.
        Checked first: Spooler still runs with the list the page showed, both plugins use the same Spoolman,
        and U1 Control's own Spoolman read finds that spool with the same filament. Then the normal bind."""
        head, spool_id, key = _assign_args(head, spool_id, key)
        _, _, target = self._ctx()
        if key.startswith(OWN_KEY):   # from own_stock: U1 Control's own Spoolman, nothing of Spooler's to check
            if target is None or key != OWN_KEY + self._own_origin(target):
                raise ValueError(tr(STOCK_CHANGED))
            return self.cmd_bind_spool(head, spool_id, bool(force))
        spooler, row = self._current_row(key, spool_id)
        if self._origin_check(target, spooler["origin"]) is False:
            raise ValueError(tr("U1 Control's Spoolman (%s) isn't the one Spooler uses (%s); nothing was written. "
                             "Set the same Spoolman address in both.") % (peers.normalize_origin(target.spoolman_url),
                                                                         spooler["origin"]))
        mine = self.cached_spool(spool_id)
        if mine is None or (row["filament_id"] is not None and mine.get("filament_id") != row["filament_id"]):
            self.cmd_spools()   # not in the list we hold, or another filament there: U1 Control's own fresh read
            mine = self.cached_spool(spool_id)
        if mine is None:
            raise ValueError(tr("Spool #%d isn't in the Spoolman U1 Control reaches; nothing was written. "
                             "Do both plugins use the same Spoolman?") % spool_id)
        if row["filament_id"] is not None and mine.get("filament_id") != row["filament_id"]:
            raise ValueError(tr("Spool #%d holds another filament in the Spoolman U1 Control reaches than in Spooler's "
                             "list; nothing was written. Do both plugins use the same Spoolman?") % spool_id)
        self._current_row(key, spool_id)   # Spooler didn't restart or change source during the read
        return self.cmd_bind_spool(head, spool_id, bool(force))
