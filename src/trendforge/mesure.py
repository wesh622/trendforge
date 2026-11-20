"""Mesure du temps et du pic de mémoire d'une commande ou d'une fonction (V0)."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass

import psutil


@dataclass
class Mesure:
    secondes: float
    pic_mo: float
    code: int = 0
    erreur: str = ""


def _rss_arbre(p: psutil.Process) -> int:
    total = 0
    try:
        total += p.memory_info().rss
        for c in p.children(recursive=True):
            try:
                total += c.memory_info().rss
            except psutil.Error:
                pass
    except psutil.Error:
        pass
    return total


def mesurer_commande(cmd: list[str], intervalle: float = 0.05) -> Mesure:
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    ps = psutil.Process(proc.pid)
    pic = 0
    while proc.poll() is None:
        pic = max(pic, _rss_arbre(ps))
        time.sleep(intervalle)
    err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    return Mesure(time.perf_counter() - t0, pic / 2**20, proc.returncode, err[-2000:])


def mesurer_fonction(fn, *args, intervalle: float = 0.05, **kwargs):
    """Pic de RSS du processus Python courant (et de ses enfants) pendant l'appel."""
    moi = psutil.Process(os.getpid())
    base = _rss_arbre(moi)
    pic = [base]
    fini = threading.Event()

    def surveiller():
        while not fini.is_set():
            pic[0] = max(pic[0], _rss_arbre(moi))
            time.sleep(intervalle)

    th = threading.Thread(target=surveiller, daemon=True)
    th.start()
    t0 = time.perf_counter()
    try:
        res = fn(*args, **kwargs)
    finally:
        fini.set()
        th.join()
    return res, Mesure(time.perf_counter() - t0, pic[0] / 2**20)
