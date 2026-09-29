"""Befundregister: das Gedaechtnis des Labors - jeder Lauf hinterlaesst eine Zeile.

Das Problem, das hier geloest wird: Ein Labor produziert hunderte Zahlen,
und nach zwei Wochen weiss niemand mehr, welche Variante auf welchen Daten
mit welchen Kosten was ergeben hat - und vor allem nicht, WIE VIELE
Varianten insgesamt probiert wurden. Ohne diese Zahl ist jeder "Fund"
unbewertbar (Zufallsschwelle sqrt(2 ln N) + 0,5).

Deshalb schreibt jedes Labor-Skript am Ende `eintragen(...)`:

    befunde.eintragen(skript="22", panel="qlib", variante="kombi2",
                      zeitraum="2006-2020", parameter={...},
                      kennzahlen={"cagr": 0.059, "sharpe": 0.48, ...},
                      urteil="bestanden|verworfen|zu_duenn", lehre="...")

Zwei Ablagen, bewusst getrennt:
  * `results/labor/befunde.jsonl` - vollstaendig, maschinenlesbar, lokal
    (results/ ist gitignored: Rohdaten bleiben auf dem Rechner)
  * `docs/befunde-2027.md` - der gerenderte Auszug, der ins Repo geht:
    das dauerhafte Gedaechtnis, auch wenn Rechner und Cache weg sind

Das Register ist additiv. Nichts wird geloescht, auch kein Fehlschlag -
Fehlschlaege sind die wertvolleren Zeilen: Sie sagen, was NICHT noch
einmal probiert werden muss, und sie halten den Versuchszaehler ehrlich.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import pandas as pd

from .config import PROJECT_ROOT

REGISTER = PROJECT_ROOT / "results" / "labor" / "befunde.jsonl"
BERICHT = PROJECT_ROOT / "docs" / "befunde-2027.md"

URTEILE = ("bestanden", "verworfen", "zu_duenn", "kandidat", "widerlegt")


def eintragen(*, skript: str, panel: str, variante: str, zeitraum: str,
              parameter: dict, kennzahlen: dict, urteil: str, lehre: str = "",
              hypothese: str | None = None, quelle_lauf: str | None = None) -> dict:
    """Haengt einen Befund an das Register. Gibt die geschriebene Zeile zurueck."""
    if urteil not in URTEILE:
        raise ValueError(f"urteil muss eines von {URTEILE} sein")
    zeile = {
        "ts": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "skript": str(skript), "panel": panel, "variante": variante, "zeitraum": zeitraum,
        "parameter": _sauber(parameter), "kennzahlen": _sauber(kennzahlen),
        "urteil": urteil, "lehre": lehre, "hypothese": hypothese, "quelle_lauf": quelle_lauf,
    }
    REGISTER.parent.mkdir(parents=True, exist_ok=True)
    with REGISTER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(zeile, ensure_ascii=False) + "\n")
    return zeile


def _sauber(d: dict) -> dict:
    out = {}
    for k, v in (d or {}).items():
        if isinstance(v, float):
            out[k] = None if not math.isfinite(v) else round(v, 5)
        elif isinstance(v, (int, str, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


def laden() -> pd.DataFrame:
    if not REGISTER.exists():
        return pd.DataFrame()
    rows = [json.loads(l) for l in REGISTER.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    kz = pd.json_normalize(df["kennzahlen"]).add_prefix("k_")
    pa = pd.json_normalize(df["parameter"]).add_prefix("p_")
    return pd.concat([df.drop(columns=["kennzahlen", "parameter"]), kz, pa], axis=1)


def versuchszaehler() -> dict:
    """Wie viele Varianten wurden insgesamt probiert - und was heisst das fuer die Schwelle?"""
    df = laden()
    n = int(len(df)) if not df.empty else 0
    n_var = int(df[["panel", "variante", "p_regime", "p_haltedauer"]].astype(str).drop_duplicates().shape[0]) \
        if not df.empty and "p_regime" in df.columns else n
    schwelle = math.sqrt(2 * math.log(max(n_var, 2))) + 0.5
    return {"befunde": n, "varianten": n_var, "schwelle_sigma": round(schwelle, 2)}


def bericht(schreiben: bool = True) -> str:
    """Rendert das Register als Markdown-Tabellen - das dauerhafte Gedaechtnis im Repo."""
    df = laden()
    vz = versuchszaehler()
    L = ["# Befundregister 2027 — jeder Lauf, jedes Urteil", "",
         f"> Automatisch erzeugt aus `results/labor/befunde.jsonl` am "
         f"{dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC. "
         f"**{vz['befunde']} Befunde, {vz['varianten']} unterschiedliche Varianten → "
         f"Zufallsschwelle {vz['schwelle_sigma']} Sigma.** Ein t-Wert darunter ist kein Fund.",
         "", "Nichts hier wird gelöscht. Verworfene Zeilen sind die wertvollsten: Sie sagen,",
         "was nicht noch einmal probiert werden muss.", ""]
    if df.empty:
        L.append("_Noch keine Befunde._")
        text = "\n".join(L)
    else:
        for urteil in ("bestanden", "kandidat", "zu_duenn", "verworfen", "widerlegt"):
            teil = df[df["urteil"] == urteil]
            if teil.empty:
                continue
            L += [f"## {urteil.upper()} ({len(teil)})", "",
                  "| Skript | Panel | Variante | Zeitraum | Regime | H | Kosten | CAGR | SPY | Univ.EW | Sharpe | MaxDD | Lehre |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for _, r in teil.iterrows():
                def g(k, fmt="{:.1%}"):
                    v = r.get(k)
                    try:
                        return fmt.format(float(v)) if v is not None and pd.notna(v) else ""
                    except (TypeError, ValueError):
                        return str(v)
                L.append(f"| {r['skript']} | {r['panel']} | {r['variante']} | {r['zeitraum']} | "
                         f"{r.get('p_regime', '') or ''} | {r.get('p_haltedauer', '') or ''} | "
                         f"{g('p_kosten_bps', '{:.0f}')} | {g('k_cagr')} | {g('k_bench_cagr')} | "
                         f"{g('k_univ_cagr')} | {g('k_sharpe', '{:.2f}')} | {g('k_max_drawdown')} | "
                         f"{str(r.get('lehre') or '').replace('|', '/')} |")
            L.append("")
        text = "\n".join(L)
    if schreiben:
        BERICHT.parent.mkdir(parents=True, exist_ok=True)
        BERICHT.write_text(text, encoding="utf-8")
    return text


def urteil_portfolio(k: dict, *, spy_toleranz: float = 0.02) -> tuple[str, str]:
    """Mechanisches Urteil fuer ein Rangportfolio - dieselbe Regel fuer jede Variante.

    bestanden: CAGR >= SPY - Toleranz UND MaxDD <= 0,8 x SPY-MaxDD UND CAGR >= Univ.EW - Toleranz
    kandidat : eines der drei knapp verfehlt
    verworfen: sonst
    """
    cagr, spy, univ = k.get("cagr"), k.get("bench_cagr"), k.get("univ_cagr")
    dd, spy_dd = k.get("max_drawdown"), k.get("bench_maxdd")
    if cagr is None or spy is None:
        return "zu_duenn", "keine Kennzahlen"
    a = cagr >= spy - spy_toleranz
    b = dd is not None and spy_dd is not None and dd >= 0.8 * spy_dd   # dd negativ: -0.24 >= 0.8*-0.55
    c = univ is None or cagr >= univ - spy_toleranz
    treffer = sum([a, b, c])
    if treffer == 3:
        return "bestanden", "CAGR >= SPY, Drawdown <= 0,8 x SPY, Auswahl >= Universum"
    if treffer == 2:
        fehlt = [n for n, ok in (("CAGR<SPY", a), ("DD>0,8xSPY", b), ("Auswahl<Universum", c)) if not ok]
        return "kandidat", "knapp: " + ", ".join(fehlt)
    fehlt = [n for n, ok in (("CAGR<SPY", a), ("DD>0,8xSPY", b), ("Auswahl<Universum", c)) if not ok]
    return "verworfen", ", ".join(fehlt)
