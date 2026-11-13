"""Informations système : disques, mémoire, CPU."""
import os
import time

import psutil

from .util import HOME


def disks():
    """Partitions réelles (périphériques /dev) avec leur utilisation."""
    seen, out = set(), []
    for part in psutil.disk_partitions(all=False):
        if not part.device.startswith("/dev") or part.fstype in ("squashfs", "iso9660"):
            continue
        if part.device in seen:
            continue
        seen.add(part.device)
        try:
            u = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        out.append({"mount": part.mountpoint, "device": part.device, "fstype": part.fstype,
                    "total": u.total, "used": u.used, "free": u.free, "percent": u.percent})
    out.sort(key=lambda d: (d["mount"] != "/", d["mount"]))
    return out


def memory():
    m = psutil.virtual_memory()
    s = psutil.swap_memory()
    return {"total": m.total, "used": m.used, "available": m.available, "percent": m.percent,
            "cached": getattr(m, "cached", 0) + getattr(m, "buffers", 0),
            "swap_total": s.total, "swap_used": s.used, "swap_percent": s.percent}


def cpu():
    return {"percent": psutil.cpu_percent(interval=None), "count": psutil.cpu_count(),
            "load": os.getloadavg()}


def uptime() -> str:
    secs = int(time.time() - psutil.boot_time())
    d, r = divmod(secs, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d} j {h} h"
    return f"{h} h {m:02d} min"


def pretty_name() -> str:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


def top_processes(n=5):
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            procs.append((p.info["memory_info"].rss, p.info["name"]))
        except Exception:
            pass
    procs.sort(reverse=True)
    return procs[:n]


def home_path():
    return HOME
