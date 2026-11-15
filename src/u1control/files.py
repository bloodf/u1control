"""File manager commands of the U1 Control tab (the `gcodes` and `camera` roots) and safe local downloads.
Mixed into service.Service, which provides _client() and _require_idle(). Free of the `orca` module."""

import base64
import os
import re

from moonraker import PrinterError

GCODE_ROOT = "gcodes"
FOLDER_NAME_RE = re.compile(r"^[\w .-]{1,64}$")
THUMB_RE = re.compile(r"^[\w .()+-]+(/[\w .()+-]+)*\.(png|jpg|jpeg)$", re.I)
FILE_ROOTS = ("gcodes", "camera")   # camera = U1 timelapse videos and snapshots
GCODE_EXTS = (".gcode", ".gco", ".g")
NAME_MAX = 200
UNSAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')   # separators, drive colons, Windows-reserved, control


class FilesMixin:

    def cmd_files(self, path=GCODE_ROOT):
        path = _safe_path(path)
        listing = self._client().directory(path)
        dirs = [{"name": d["dirname"], "modified": d.get("modified"), "size": d.get("size")}
                for d in _entries(listing, "dirs", "dirname")]
        files = []
        for f in _entries(listing, "files", "filename"):
            name = f["filename"]
            thumbs = [t for t in (f.get("thumbnails") or []) if isinstance(t, dict) and t.get("relative_path")]
            best = max(thumbs, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0), default=None)
            files.append({"name": name, "size": f.get("size"), "modified": f.get("modified"),
                          "time": f.get("estimated_time"), "weight": f.get("filament_weight_total"),
                          "thumb": best["relative_path"] if best else None})
        return {"path": path, "dirs": sorted(dirs, key=lambda d: d["name"].lower()),
                "files": sorted(files, key=lambda f: -(_number(f["modified"]) or 0)),
                "disk": listing.get("disk_usage")}

    def cmd_thumbnail(self, path, thumb=None):
        """thumb: the relative_path the file listing gave (saves a metadata request); else looked up."""
        path = _safe_path(path, (GCODE_ROOT,))
        rel = path[len(GCODE_ROOT) + 1:]
        folder = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
        if thumb is None:
            meta = self._client().metadata(rel)
            thumbs = sorted(meta.get("thumbnails") or [], key=lambda t: -(t.get("width", 0) * t.get("height", 0)))
            if not thumbs:
                return None
            thumb = thumbs[0]["relative_path"]
        thumb = str(thumb)
        if not THUMB_RE.match(thumb) or ".." in thumb.split("/"):
            raise ValueError("bad thumbnail path")
        data = self._client().thumbnail(folder + thumb)
        return "data:image/png;base64," + base64.b64encode(data).decode()

    def cmd_delete(self, path, is_dir=False):
        path = _safe_path(path)
        if "/" not in path:
            raise ValueError("refusing to delete a file root")
        if is_dir:
            return self._client().delete_directory(path, force=True)
        return self._client().delete_file(path)

    def cmd_mkdir(self, path):
        path = _safe_path(path)
        name = path.rsplit("/", 1)[-1]
        if "/" not in path or name.startswith(".") or not FOLDER_NAME_RE.match(name):
            raise ValueError("folder names use letters, digits, spaces, '-', '_' and '.'")
        return self._client().create_directory(path)

    def cmd_folders(self, root=GCODE_ROOT, limit=200):
        """Every folder under a root (breadth first, at most `limit`), for the Move dialog."""
        root = _safe_path(root)
        if "/" in root:
            raise ValueError("folders are listed from a file root")
        client, out, todo = self._client(), [root], [root]
        while todo and len(out) < limit:
            here = todo.pop(0)
            for d in _entries(client.directory(here, extended=False), "dirs", "dirname"):
                out.append(here + "/" + d["dirname"])
                todo.append(here + "/" + d["dirname"])
        return sorted(out[:limit], key=str.lower)

    def cmd_move(self, path, folder):
        """Move a file or folder into another folder of the same root (keeps its name)."""
        path, folder = _safe_path(path), _safe_path(folder)
        if "/" not in path:
            raise ValueError("refusing to move a file root")
        if path.split("/")[0] != folder.split("/")[0]:
            raise ValueError("files stay in their own root")
        if folder == path or folder.startswith(path + "/"):
            raise ValueError("can't move a folder into itself")
        dest = folder + "/" + path.rsplit("/", 1)[-1]
        if dest == path:
            return {"path": path}
        self._refuse_taken(folder, path.rsplit("/", 1)[-1])
        self._client().move(path, dest)
        return {"path": dest}

    def cmd_rename(self, path, name):
        """Rename a file or folder where it is. Refused: a name the folder already has (Moonraker's move would
        replace it), separators or characters Windows can't keep, a hidden name, and a print file losing its G-code
        extension (the printer only lists and prints those)."""
        path = _safe_path(path)
        if "/" not in path:
            raise ValueError("refusing to rename a file root")
        folder, old = path.rsplit("/", 1)
        name = str(name or "").strip()
        if not name or name.startswith(".") or len(name) > NAME_MAX or UNSAFE_NAME_RE.search(name):
            raise ValueError("a name can't be empty, start with '.', be longer than %d characters or hold "
                             "/ \\ : * ? \" < > | or control characters" % NAME_MAX)
        if name == old:
            return {"path": path}
        files, dirs = self._names(folder)
        if old not in files and old not in dirs:
            raise ValueError("%s is no longer in %s; nothing was renamed" % (old, folder))
        if name in files or name in dirs:
            raise ValueError("%s already has something named %s; nothing was renamed" % (folder, name))
        if old in files and folder.split("/")[0] == GCODE_ROOT and old.lower().endswith(GCODE_EXTS) \
                and not name.lower().endswith(GCODE_EXTS):
            raise ValueError("a print file keeps a G-code extension (.gcode, .gco or .g)")
        dest = folder + "/" + name
        self._client().move(path, dest)
        return {"path": dest}

    def _names(self, folder):
        """(file names, folder names) in a printer folder."""
        listing = self._client().directory(folder, extended=False)
        return ({e["filename"] for e in _entries(listing, "files", "filename")},
                {e["dirname"] for e in _entries(listing, "dirs", "dirname")})

    def _refuse_taken(self, folder, name):
        """Moonraker's move replaces what has that name: refuse instead, so nothing is lost."""
        files, dirs = self._names(folder)
        if name in files or name in dirs:
            raise ValueError("%s already has something named %s; nothing was moved" % (folder, name))

    def cmd_download(self, path):
        """Stream a printer file (e.g. a timelapse) to ~/Downloads/u1control/, never overwriting.
        The data goes to '<name>.part', then gets a final name that no other file has (see _publish); an
        interrupted download keeps its .part file. Runs on its own thread (see DEDICATED). Returns the saved path."""
        path = _safe_path(path)
        folder = os.path.join(os.path.expanduser("~"), "Downloads", "u1control")
        os.makedirs(folder, exist_ok=True)
        name = _local_name(path)
        part = []

        def open_out():
            target, out = _new_file(folder, name + ".part")
            part.append(target)
            return out

        try:
            self._client().download_to(path, open_out)
        except BaseException as e:
            if part:
                raise PrinterError("download interrupted, partial file kept at %s (%s)" % (part[0], e))
            raise
        try:
            return _publish(part[0], folder, name)
        except OSError as e:
            raise PrinterError("download kept at %s: couldn't give it its final name (%s)" % (part[0], e)) from e


def _entries(listing, kind, key):
    """The listing's entries of one kind with a usable, visible name (a malformed entry is skipped)."""
    raw = listing.get(kind) if isinstance(listing, dict) else None
    return [e for e in raw if isinstance(e, dict) and isinstance(e.get(key), str) and e[key]
            and not e[key].startswith(".")] if isinstance(raw, list) else []


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _local_name(path):
    """The printer file's name as saved here. The printer names its files (Linux allows '\\' and ':'); on
    Windows those would point into another folder or drive, so they become '_'."""
    name = UNSAFE_NAME_RE.sub("_", path.rsplit("/", 1)[-1]).strip()
    return name if name.strip(".") else "download"


def _candidates(name):
    stem, ext_ = os.path.splitext(name or "download")
    for n in range(10000):
        yield name if n == 0 else "%s (%d)%s" % (stem, n, ext_)


def _publish(src, folder, name):
    """Give a finished download a final name that no file has, never replacing one, even one another
    program creates at the same moment: a hard link fails when the name exists; where the filesystem has
    no hard links, the name is first reserved with an exclusive create."""
    for candidate in _candidates(name):
        target = os.path.join(folder, candidate)
        try:
            _link_new(src, target)
        except FileExistsError:
            continue
        return target
    raise PrinterError("too many files named %s in %s" % (name, folder))


def _link_new(src, dst):
    try:
        os.link(src, dst)
    except FileExistsError:
        raise
    except OSError:   # no hard links here: reserve the name, then move the data over our own empty file
        with open(dst, "xb"):
            pass
        os.replace(src, dst)
        return
    os.unlink(src)


def _new_file(folder, name):
    """Open folder/name for writing without overwriting: 'name (1).ext', 'name (2).ext', ..."""
    for candidate in _candidates(name):
        target = os.path.join(folder, candidate)
        try:
            return target, open(target, "xb")
        except FileExistsError:
            continue
    raise PrinterError("too many files named %s in %s" % (name, folder))


def _safe_path(path, roots=FILE_ROOTS):
    """Normalize a Moonraker path under one of roots; reject traversal."""
    path = str(path or "").strip().strip("/")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or parts[0] not in roots or ".." in parts:
        raise ValueError("bad path %r" % path)
    return "/".join(parts)
