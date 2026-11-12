"""Filament use of the prints u1control sent, waiting to be booked in Spoolman (stock firmware).

A job is identified by printer (normalized address) and file path, plus an id of its own. It is booked
once its printer reports that same file printing and then complete. Every decision is taken under one
lock, so only one thread books a job. Spoolman's "use" call adds weight: a call that fails may or may not
have been applied, so it is never repeated by itself; it is listed as unconfirmed instead.

Jobs are kept in a file in the plugin's storage folder (LedgerStore), rewritten whole after every change,
so closing OrcaSlicer no longer forgets them. A toolhead's use is saved as "sending" before its Spoolman
call: one still "sending" when the file is read again (OrcaSlicer closed or crashed during the call) may
have been applied, so it becomes unconfirmed, never sent again. A job that had been seen printing is only
booked after the restart if u1control sees it printing again; seen finished, or another file, it is
unconfirmed (it can't tell that print from a later one). No API key is written to the file.
Free of the `orca` module.
"""

import json
import os
import threading
import time
import traceback
import uuid

import extended as ext
import settings
import spoolman as sm
import u1
from moonraker import PrinterError, normalize_host
JOB_POLL = 5.0                  # tracker: seconds between print_stats checks of a printer with a pending job
JOB_TTL = 3 * 24 * 3600.0       # a job that never finishes is dropped after this long
RETRY_AFTER = 60.0              # heads not yet attempted (Spoolman unreachable before any write) retry after this
MAX_UNCONFIRMED = 20
MAX_ACKNOWLEDGED = 50           # entries the user marked as checked in Spoolman, kept for audit
MAX_JOBS = 200
LEDGER_VERSION = 1
ACTIVE = ("printing", "paused")
FAILED = ("cancelled", "error")


def job_key(filename):
    """Normalized printer path of a job: 'gcodes/Dir/Part.GCode' and 'dir/part.gcode' match; folders count."""
    path = str(filename or "").replace("\\", "/").strip().strip("/").lower()
    return path[len("gcodes/"):] if path.startswith("gcodes/") else path


def printer_ident(host):
    """One spelling per printer address: '192.168.1.5' and 'http://192.168.1.5/' are the same printer."""
    try:
        return normalize_host(host)
    except PrinterError:
        return str(host or "").strip()


class Job:
    def __init__(self, host, api_key, path, per_head, bindings=None, printer_name="", spoolman_url="", report=True,
                 now=None, job_id=None):
        self.id = job_id or uuid.uuid4().hex
        self.host, self.api_key, self.path = host, api_key, job_key(path)
        self.per_head = dict(per_head)             # toolhead -> grams still to book
        self.bindings = dict(bindings) if bindings else None   # toolhead -> spool id when sent, if known
        self.printer_name, self.spoolman_url, self.report = printer_name, spoolman_url, report
        self.created = time.time() if now is None else now
        self.armed = False        # seen printing this file after it was registered
        self.saw_other = False    # seen any other state or file after it was registered
        self.retry_at = None      # set when part of the job waits for a new attempt
        self.restored = False     # read back from disk and not observed since
        self.sending = {}         # toolhead -> grams whose Spoolman call may be in flight
        self.booking = False      # taken out to be booked (still saved until that ends)

    @property
    def key(self):
        return (self.host, self.path)

    def to_dict(self):
        return {"id": self.id, "host": self.host, "path": self.path,
                "per_head": {str(h): g for h, g in self.per_head.items()},
                "bindings": None if self.bindings is None else {str(h): s for h, s in self.bindings.items()},
                "printer_name": self.printer_name, "spoolman_url": self.spoolman_url, "report": self.report,
                "created": self.created, "armed": self.armed, "saw_other": self.saw_other, "retry_at": self.retry_at,
                "sending": {str(h): g for h, g in self.sending.items()}, "booking": self.booking}

    @classmethod
    def from_dict(cls, d):
        """A job read back from disk; raises ValueError/TypeError/KeyError on a malformed entry."""
        heads = lambda m: {int(h): float(g) for h, g in (m or {}).items() if 0 <= int(h) < u1.TOOLHEADS}  # noqa: E731
        bindings = d.get("bindings")
        job = cls(str(d["host"]), "", str(d["path"]), heads(d["per_head"]),
                  {int(h): int(s) for h, s in bindings.items()} if isinstance(bindings, dict) else None,
                  str(d.get("printer_name") or ""), str(d.get("spoolman_url") or ""), bool(d.get("report", True)),
                  float(d["created"]), str(d["id"]))
        job.armed, job.saw_other = bool(d.get("armed")), bool(d.get("saw_other"))
        job.retry_at = float(d["retry_at"]) if d.get("retry_at") is not None else None
        job.sending = heads(d.get("sending"))
        job.booking = bool(d.get("booking"))
        job.restored = True
        return job


class LedgerStore:
    """The ledger file: {"version": 1, "jobs": [...], "unconfirmed": [...], "acknowledged": [...]}, replaced whole
    on every save. "acknowledged" (optional, older files have none) keeps unconfirmed entries the user marked as
    checked in Spoolman, with the time they did so: a local note only, nothing is sent to Spoolman for it."""

    def __init__(self, path, log=print):
        self.path, self.log = path, log

    def load(self):
        """(jobs, unconfirmed, notice, acknowledged). A file that can't be read is set aside, never overwritten."""
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return [], [], "", []
        except (OSError, ValueError) as e:
            return [], [], self._set_aside("unreadable (%s)" % e), []
        if not isinstance(data, dict) or data.get("version") != LEDGER_VERSION:
            return [], [], self._set_aside("of an unknown format"), []
        jobs, bad = [], 0
        for entry in data.get("jobs") if isinstance(data.get("jobs"), list) else []:
            try:
                jobs.append(Job.from_dict(entry))
            except (KeyError, TypeError, ValueError, AttributeError):
                bad += 1
        raw = data.get("unconfirmed") if isinstance(data.get("unconfirmed"), list) else []
        unconfirmed = [u for u in raw if isinstance(u, dict)]
        bad_entries = len(raw) - len(unconfirmed)
        acked = data.get("acknowledged") if isinstance(data.get("acknowledged"), list) else []
        acknowledged = [u for u in acked if isinstance(u, dict)][-MAX_ACKNOWLEDGED:]
        notes = []
        if bad:
            notes.append("%d unreadable job(s) in %s were skipped" % (bad, self.path))
        if bad_entries:
            notes.append("%d unreadable unconfirmed entr%s in %s were skipped; check Spoolman for prints that "
                         "finished meanwhile" % (bad_entries, "y" if bad_entries == 1 else "ies", self.path))
        return jobs, unconfirmed[-MAX_UNCONFIRMED:], "; ".join(notes), acknowledged

    def _set_aside(self, why):
        aside = "%s.bad-%d" % (self.path, int(time.time()))
        try:
            os.replace(self.path, aside)
        except OSError as e:
            return "the print ledger %s is %s and could not be moved aside (%s); it was not used" % (self.path, why, e)
        return "the print ledger was %s; it was kept as %s and not used. Check Spoolman for prints that " \
               "finished meanwhile." % (why, aside)

    def save(self, jobs, unconfirmed, acknowledged=()):
        """Raises OSError when the file can't be written."""
        folder = os.path.dirname(self.path) or "."
        os.makedirs(folder, exist_ok=True)
        tmp = os.path.join(folder, ".%s.%d.tmp" % (os.path.basename(self.path), threading.get_ident()))
        doc = {"version": LEDGER_VERSION, "jobs": [j.to_dict() for j in jobs], "unconfirmed": unconfirmed,
               "acknowledged": list(acknowledged)}
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(doc, f, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise


class Ledger:
    def __init__(self, store=None):
        self.lock = threading.Lock()
        self.store = store
        self.jobs = {}
        self.unconfirmed = []     # [{"id", "at", "spool", "grams", "head", "file", "error", "job", "printer", "spoolman"}]
        self.acknowledged = []    # the same entries plus "acknowledged_at", once the user checked them in Spoolman
        self.seen = {}            # host -> time.monotonic() of the last observation
        self.save_error = ""
        self.restore_notice = ""
        if store is not None:
            jobs, self.unconfirmed, self.restore_notice, self.acknowledged = store.load()
            for job in jobs:
                for head, grams in sorted(job.sending.items()):   # closed or crashed during this call
                    self.unconfirmed.append(_unconfirmed(job, head, job.per_head.pop(head, grams),
                                                         "OrcaSlicer closed while this was being recorded"))
                job.sending = {}
                key = ("retry", job.id) if job.retry_at is not None else ("restored", job.id) if job.booking else job.key
                job.booking = False   # read back mid-booking: waits again, and restored + armed decides it
                if job.per_head:
                    self.jobs[key] = job
            self.unconfirmed = [_with_id(u) for u in self.unconfirmed[-MAX_UNCONFIRMED:]]
            self._save()

    def _save(self):   # caller holds self.lock (or is __init__)
        """Write the ledger; False when it couldn't be (the change stays in memory, and is reported)."""
        if self.store is None:
            return True
        try:
            self.store.save(list(self.jobs.values()), self.unconfirmed, self.acknowledged)
        except OSError as e:
            self.save_error = "can't save the print ledger (%s); pending prints won't survive a restart" % e
            return False
        self.save_error = ""
        return True

    def add(self, job):
        with self.lock:
            replaced = self.jobs.pop(job.key, None)
            self.jobs[job.key] = job
            if len(self.jobs) > MAX_JOBS:   # oldest first
                oldest = min(self.jobs, key=lambda k: self.jobs[k].created)
                self.jobs.pop(oldest)
            self._save()
        return replaced

    def fill_api_key(self, host, api_key):
        """Jobs read back from disk carry no key: give them the one of the printer at that address."""
        with self.lock:
            for job in self.jobs.values():
                if job.host == host and not job.api_key:
                    job.api_key = api_key

    def hosts(self):
        with self.lock:
            return sorted({(j.host, j.api_key) for j in self.jobs.values() if j.retry_at is None and not j.booking})

    def pending(self):
        with self.lock:
            return list(self.jobs.values())

    def observe(self, host, state, filename, now=None):
        """Feed one print_stats sample of `host`. Returns [(job, outcome)] taken out of the ledger:
        "book" (printed and finished), "ambiguous" (finished but never seen printing, or seen printing before
        a restart and not since), "failed" (cancelled or error), "expired"."""
        now = time.time() if now is None else now
        path, out = job_key(filename), []
        with self.lock:
            self.seen[host] = time.monotonic()
            changed = False
            for key, job in list(self.jobs.items()):
                if job.host != host or job.retry_at is not None or job.booking:
                    continue
                before = (job.armed, job.saw_other, job.restored)
                outcome = _step(job, state, path, now)
                changed = changed or outcome is not None or before != (job.armed, job.saw_other, job.restored)
                if outcome:
                    del self.jobs[key]
                    if outcome == "book":   # stays saved until booked: a restart now leaves it unconfirmed
                        job.booking = True
                        self.jobs[("booking", job.id)] = job
                    out.append((job, outcome))
            if changed:   # a status sample every few seconds rewrites the file only when something changed
                self._save()
        return out

    def due(self, now=None):
        """Jobs whose remaining heads may be tried again (nothing was written for them)."""
        now = time.time() if now is None else now
        with self.lock:
            ready = [(k, j) for k, j in self.jobs.items() if j.retry_at is not None and j.retry_at <= now]
            for key, job in ready:
                del self.jobs[key]
                job.retry_at = None
                job.booking = True
                self.jobs[("booking", job.id)] = job
            self._save()
        return [j for _, j in ready]

    def retry_later(self, job, now=None):
        job.retry_at = (time.time() if now is None else now) + RETRY_AFTER
        with self.lock:
            self.jobs.pop(("booking", job.id), None)
            job.booking = False
            self.jobs[("retry", job.id)] = job   # never replaces a newer send of the same file
            self._save()

    def begin_use(self, job, head, grams):
        """Save that `grams` of `head` are about to be sent. False (send nothing) when that can't be saved."""
        with self.lock:
            job.sending[head] = grams
            if self._save():
                return True
            job.sending.pop(head, None)
            return False

    def end_use(self, job, head, applied, error=""):
        """After the Spoolman call: applied, or listed as unconfirmed (it may have been)."""
        with self.lock:
            grams = job.sending.pop(head, 0)
            if not applied:
                self.unconfirmed = (self.unconfirmed + [_unconfirmed(job, head, grams, error)])[-MAX_UNCONFIRMED:]
            self._save()

    def end_booking(self, job):
        """Booking finished or stopped: forget it, unless it waits for a retry (retry_later keeps it)."""
        with self.lock:
            if self.jobs.get(("booking", job.id)) is job:
                del self.jobs[("booking", job.id)]
            job.booking = False
            self._save()

    def unconfirmed_use(self, entry):
        with self.lock:
            self.unconfirmed = (self.unconfirmed + [entry])[-MAX_UNCONFIRMED:]
            self._save()


    def acknowledge(self, entry_id, now=None):
        """The user checked this unconfirmed use in Spoolman themselves: move it to the acknowledged list with the
        time. Only a local note; nothing is sent to Spoolman. Raises ValueError for an unknown id."""
        with self.lock:
            entry = next((u for u in self.unconfirmed if u.get("id") == entry_id), None)
            if entry is None:
                raise ValueError("That unconfirmed entry is no longer listed; nothing was changed.")
            done = {**entry, "acknowledged_at": time.time() if now is None else now}
            self.unconfirmed = [u for u in self.unconfirmed if u is not entry]
            self.acknowledged = (self.acknowledged + [done])[-MAX_ACKNOWLEDGED:]
            if not self._save():
                self.unconfirmed = self.unconfirmed + [entry]
                self.acknowledged = [u for u in self.acknowledged if u is not done]
                raise ValueError(self.save_error)
            return done


def _with_id(entry):
    """Entries from older files have no id: give them a stable one (job + toolhead), and no time (unknown)."""
    if entry.get("id"):
        return entry
    return {**entry, "id": "%s:%s" % (entry.get("job") or "legacy", entry.get("head")), "at": entry.get("at")}


def _unconfirmed(job, head, grams, error):
    return {"id": uuid.uuid4().hex, "at": time.time(), "spool": (job.bindings or {}).get(head), "grams": grams,
            "head": head, "file": job.path, "error": error, "job": job.id, "printer": job.host,
            "printer_name": job.printer_name, "spoolman": job.spoolman_url}


def _step(job, state, path, now):
    if now - job.created > JOB_TTL:
        return "expired"
    if job.restored:
        job.restored = False
        if job.armed and path == job.path and state in FAILED:
            return "failed"
        if job.armed and not (path == job.path and state in ACTIVE):
            return "restart"   # printing before the restart; how it ended wasn't seen
    if path != job.path:
        job.saw_other = True
        return None
    if state in ACTIVE:
        job.armed = True
        return None
    if state == "complete":
        if job.armed:
            return "book"
        return "ambiguous" if job.saw_other else None   # else: the previous print of this file, still shown
    if state in FAILED and job.armed:
        return "failed"
    job.saw_other = True
    return None


class UsageMixin:
    """Job tracking for service.Service: needs ledger, lock, target, firmware, bindings, client_factory, log,
    _closing and _notice."""

    def remember_job(self, filename, mapping, filaments, host=None, api_key="", options=None):
        """Called by the print setup step before Orca uploads the job: per-toolhead grams to book once this
        printer reports the file printed. host: the printer it goes to (default: the selected one).
        options: {"printer_name", "spoolman_url", "spoolman_report_usage"} (default: the selected target's)."""
        per_head = {}
        for f in filaments:
            t = mapping.get(f["index"])
            if t is not None and f.get("weight"):
                per_head[t] = per_head.get(t, 0) + f["weight"]
        with self.lock:
            target, kind, bindings = self.target, self.firmware["kind"], dict(self.bindings)
        ident = printer_ident(host) if host else (target.ident if target else "")
        if not ident or not per_head:
            return None
        same = target is not None and target.ident == ident
        opts = options or {}
        name = opts.get("printer_name") or (target.name if target else settings.CONNECTION["printer_name"])
        url = opts["spoolman_url"] if "spoolman_url" in opts else (target.spoolman_url if target else "")
        report = opts.get("spoolman_report_usage", target.spoolman_report_usage if target else True)
        if not report or (same and kind == "extended"):
            return None   # nothing to book: usage is off, or SpoolLink books it
        job = Job(ident, api_key or (target.api_key if same else ""), filename, per_head,
                        bindings if same and kind == "stock" and bindings else None, name, url, report)
        if self.ledger.add(job):
            self.log("u1control: %s was sent again before the earlier copy finished; only the new one is tracked" % job.path)
        if self.ledger.save_error:
            self.log("u1control: " + self.ledger.save_error)
            self._notice("U1 Control " + self.ledger.save_error + ".")
        return job

    def _track(self):
        """Follow every printer with a pending job, whether the page is open or not."""
        while not self._closing.wait(JOB_POLL):
            for job in self.ledger.due():
                self._settle(job, "book")
            for host, key in self.ledger.hosts():
                if time.monotonic() - self.ledger.seen.get(host, 0.0) < JOB_POLL:
                    continue   # the page's own status already looked at it
                try:
                    stats = (self.client_factory(host, key).query({"print_stats": ["state", "filename"]})
                             .get("print_stats") or {})
                except Exception as e:
                    self.log("u1control: job check on %s failed: %s" % (host, e))
                    continue
                for job, outcome in self.ledger.observe(host, stats.get("state"), stats.get("filename")):
                    self._settle(job, outcome)

    def _settle(self, job, outcome):
        if outcome == "book":
            try:
                self._book(job)
            except Exception as e:  # keep the tracker alive; the job was taken out, so say so
                self.log("u1control: booking %s failed: %s\n%s" % (job.path, e, traceback.format_exc()))
                self._notice("Spoolman usage for %s not recorded: %s" % (job.path, e))
            finally:
                self.ledger.end_booking(job)
        elif outcome in ("ambiguous", "restart"):
            why = ("printing before OrcaSlicer closed; how it ended wasn't seen" if outcome == "restart"
                   else "finished without being seen printing")
            for head, grams in sorted(job.per_head.items()):
                self.ledger.unconfirmed_use(_unconfirmed(job, head, grams, why))
            if outcome == "restart":
                self._notice("%s was printing before OrcaSlicer closed and u1control didn't see how it ended, so its "
                             "filament use was not recorded. Check Spoolman." % job.path)
            else:
                self._notice("%s finished, but u1control never saw it printing, so its filament use was not recorded. "
                             "Check Spoolman." % job.path)
        elif outcome == "failed":
            self._notice("%s was cancelled or failed; its filament use was not recorded." % job.path)
        elif outcome == "expired":
            self._notice("u1control stopped waiting for %s to finish; its filament use was not recorded." % job.path)

    def _book(self, job):
        """Book one finished job, one Spoolman call per toolhead, each saved as "sending" first. A failed call
        may have been applied, so it is listed as unconfirmed and never repeated; heads not tried yet wait for
        another attempt."""
        client = self.client_factory(job.host, job.api_key)
        try:
            if self._job_on_extended(job, client):
                return   # SpoolLink / Moonraker book it
            smc = sm.Spoolman(job.spoolman_url, client)
            smc.connect()
            if smc.via_moonraker:
                return   # Moonraker's spoolman books the active spool
            bindings = job.bindings
            if bindings is None:
                bindings = sm.bindings_from_locations([sm.spool_view(s) for s in smc.spools()], job.printer_name)
        except (PrinterError, sm.SpoolmanError, OSError, ValueError) as e:
            self.ledger.retry_later(job)
            self._notice("Spoolman usage for %s waits for a retry: %s" % (job.path, e))
            return
        job.bindings = bindings
        booked, unlinked = [], []
        for head in sorted(job.per_head):
            grams, sid = job.per_head[head], bindings.get(head)
            if not sid:
                job.per_head.pop(head)
                unlinked.append("T%d" % (head + 1))
                continue
            if not self.ledger.begin_use(job, head, grams):
                self.ledger.retry_later(job)   # nothing sent for this head; try again once the file can be saved
                self._notice("Spoolman usage for %s waits: %s." % (job.path, self.ledger.save_error))
                return
            job.per_head.pop(head)
            try:
                smc.use_weight(sid, grams)
            except (PrinterError, sm.SpoolmanError, OSError, ValueError) as e:
                self.ledger.end_use(job, head, False, str(e))
                self._notice("Spoolman may not have recorded %s g on spool #%d (T%d): %s. Check spool #%d before adding it "
                             "by hand; u1control won't repeat it." % (round(grams, 2), sid, head + 1, e, sid))
                if job.per_head:
                    self.ledger.retry_later(job)
                return
            self.ledger.end_use(job, head, True)
            booked.append(head)
        if booked:
            self._notice("Spoolman updated with this print's filament use")
        if unlinked:
            self._notice("No Spoolman spool was linked to %s; that filament use was not recorded." % ", ".join(unlinked))

    def _job_on_extended(self, job, client):
        with self.lock:
            if self.target is not None and self.target.ident == job.host and self.firmware["kind"] != "unknown":
                return self.firmware["kind"] == "extended"
        return u1.detect_firmware(client.info(), ext.Extended(client).status())["kind"] == "extended"

    def cmd_usage(self):
        """What the page shows about filament use: unconfirmed entries (with identity), the last acknowledged
        ones, and notices about the ledger file (set aside, unreadable entries, can't be saved)."""
        return {"pending": [{"file": j.path, "printer": j.host, "grams": j.per_head} for j in self.ledger.pending()],
                "unconfirmed": list(self.ledger.unconfirmed), "acknowledged": list(self.ledger.acknowledged[-5:]),
                "acknowledged_total": len(self.ledger.acknowledged),
                "save_error": self.ledger.save_error, "restore_notice": self.ledger.restore_notice}

    def cmd_usage_ack(self, id):
        """Mark one unconfirmed use as checked by the user. Local and audited; never a Spoolman call."""
        self.ledger.acknowledge(str(id))
        return self.cmd_usage()
