"""Spooler's stock in the U1 Control tab: the list Spooler publishes, and linking one of its spools
to a toolhead. Every printer command still goes through u1control's own queue (Service.submit), for
the printer the page shows; Spooler only supplies the list. Free of the `orca` module."""

import peers

STOCK_CHANGED = "Spooler's stock list changed since this one was shown; nothing was written. Pick the spool again."


def _assign_args(head, spool_id, key):
    if not isinstance(spool_id, int) or isinstance(spool_id, bool) or spool_id <= 0:
        raise ValueError("no spool chosen")
    if not isinstance(key, str) or not key:
        raise ValueError(STOCK_CHANGED)
    return head, spool_id, key


class StockMixin:
    """For service.Service: needs lock, firmware, spoolman, bindings, _snapshot, _ctx, cmd_spools, cmd_bind_spool.
    `peers` is a peers.SpoolerLink, set by the plugin (None outside OrcaSlicer: no Spooler to find)."""

    peers = None

    def want_stock(self, refresh=False):
        if self.peers is not None:
            self.peers.want_stock(refresh)

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
        """Spooler's state and stock list, with what this printer needs to use it."""
        if self.peers is None:
            spooler = {"state": "absent", "text": peers.STATE_TEXT["absent"], "detail": "", "version": "",
                       "session": "", "origin": ""}
            return {"spooler": spooler, "stock": {**peers.parse_stock(None, None), "state": "unavailable",
                                                  "text": spooler["text"]},
                    "same_spoolman": None, "usage": "unknown", "bindings": {}}
        self.want_stock(bool(refresh))
        _, _, target = self._snapshot()
        spooler, stock = self.peers.stock()
        with self.lock:
            bindings = {str(k): v for k, v in self.bindings.items()}
        return {"spooler": {k: v for k, v in spooler.items() if k != "session"}, "stock": stock,
                "same_spoolman": self._origin_check(target, spooler["origin"]) if spooler["state"] == "active" else None,
                "usage": self._usage_owner(target), "bindings": bindings}

    def _current_row(self, key, spool_id):
        if self.peers is None:
            raise ValueError(peers.STATE_TEXT["absent"])
        spooler, stock = self.peers.stock()
        if spooler["state"] != "active":
            raise ValueError(spooler["text"])
        if stock["key"] != key:
            raise ValueError(STOCK_CHANGED)
        row = next((r for r in stock["rows"] if r["id"] == spool_id), None)
        if row is None:
            raise ValueError("Spool #%d is no longer in Spooler's stock list; nothing was written." % spool_id)
        return spooler, row

    def cmd_stock_assign(self, head, spool_id, key, force=False):
        """Link a spool picked from Spooler's list to a toolhead of the printer this request was made for.
        Checked first: Spooler still runs with the list the page showed, both plugins use the same Spoolman,
        and U1 Control's own Spoolman read finds that spool with the same filament. Then the normal bind."""
        head, spool_id, key = _assign_args(head, spool_id, key)
        _, _, target = self._ctx()
        spooler, row = self._current_row(key, spool_id)
        if self._origin_check(target, spooler["origin"]) is False:
            raise ValueError("U1 Control's Spoolman (%s) isn't the one Spooler uses (%s); nothing was written. "
                             "Set the same Spoolman address in both." % (peers.normalize_origin(target.spoolman_url),
                                                                         spooler["origin"]))
        self.cmd_spools()   # U1 Control's own, fresh read of the spool it will write
        with self.lock:
            mine = next((s for s in self.spools if s["id"] == spool_id), None)
        if mine is None:
            raise ValueError("Spool #%d isn't in the Spoolman U1 Control reaches; nothing was written. "
                             "Do both plugins use the same Spoolman?" % spool_id)
        if row["filament_id"] is not None and mine.get("filament_id") != row["filament_id"]:
            raise ValueError("Spool #%d holds another filament in the Spoolman U1 Control reaches than in Spooler's "
                             "list; nothing was written. Do both plugins use the same Spoolman?" % spool_id)
        self._current_row(key, spool_id)   # Spooler didn't restart or change source during the read
        return self.cmd_bind_spool(head, spool_id, bool(force))
