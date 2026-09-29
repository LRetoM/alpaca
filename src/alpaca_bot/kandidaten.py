"""Neue Faktorkandidaten - Ideen, die noch nie gemessen wurden.

**Abgrenzung zu `research.candidate_factors`:** Dort stehen die
Kandidaten des ersten Messlaufs, aus dem die heutige Umkehr-Strategie
hervorging. Hier stehen NEUE Ideen, die noch durch dieselbe Pruefkette
muessen.

**Die Messlatte ist hoch, und das aus Erfahrung:**

  * Kein Einzelfaktor dieses Projekts kam je ueber IC 0,05. Bester
    bestaetigter Wert: `reversal_3d` mit 0,018.
  * Die fuenf bestehenden Umkehr-Bausteine sind stark korreliert - sie
    messen im Kern dasselbe. Ein sechster Baustein derselben Art bringt
    fast nichts.
  * PEAD sah auf 60 Symbolen exzellent aus (IC 0,032, t=6,7) und brach
    auf 800 Symbolen vollstaendig zusammen (BEFUNDE §B4).

**Was ein Kandidat leisten muss, um ueberhaupt interessant zu sein:**
Nicht nur einen IC ueber der Schwelle, sondern EIGENSTAENDIGE Information
gegenueber den bestehenden Faktoren (`earnings.eigenstaendigkeit`). Ein
Faktor mit IC 0,03, der zu 0,9 mit `reversal_3d` korreliert, ist derselbe
Faktor unter anderem Namen und bringt keinen einzigen Basispunkt.

**Bewusst ausgewaehlt nach dem Kriterium "misst etwas ANDERES":** Alle
Kandidaten hier zielen auf Information, die in den bestehenden Faktoren
NICHT steckt - Handelsverhalten, Kursstruktur ueber laengere Fenster,
Wechselwirkung mit dem Gesamtmarkt.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind


def neue_kandidaten(df: pd.DataFrame, markt: pd.Series | None = None) -> pd.DataFrame:
    """Berechnet alle neuen Kandidaten fuer EIN Symbol. Strikt kausal.

    Jede Spalte verwendet ausschliesslich Daten bis zum jeweiligen Tag -
    geprueft ueber `pit.audit_feature_function`. Ein Faktor, der in die
    Zukunft sieht, zeigt traumhafte Werte und ist wertlos.
    """
    c = df["close"].astype(float)
    out = pd.DataFrame(index=df.index)

    hoch = df["high"].astype(float) if "high" in df else c
    tief = df["low"].astype(float) if "low" in df else c
    vol = df["volume"].astype(float) if "volume" in df else None

    # ---------------------------------------------------------------- Struktur
    # Wie viele der letzten n Tage schlossen im Plus? Misst die
    # BESTAENDIGKEIT einer Bewegung, nicht ihre Groesse - zwei Werte mit
    # identischer 5-Tages-Rendite koennen voellig verschieden dorthin
    # gelangt sein (einmal ruckartig, einmal stetig).
    ret = c.pct_change()
    for n in (5, 10, 21):
        out[f"aufwaertstage_{n}"] = (ret > 0).rolling(n).mean()

    # Beschleunigung: Wird die Bewegung schneller oder langsamer? Die
    # bestehenden Faktoren messen nur die Bewegung selbst.
    out["beschleunigung_5_10"] = c.pct_change(5) - c.pct_change(10) / 2
    out["beschleunigung_10_21"] = c.pct_change(10) - c.pct_change(21) / 2

    # --------------------------------------------------------------- Spanne
    # Wo im Tagesbereich schloss der Kurs, gemittelt? Ein Wert, der
    # wiederholt nahe dem Tageshoch schliesst, wird gekauft; nahe dem
    # Tief, verkauft. `schluss_lage` in research.py misst nur EINEN Tag.
    spanne = (hoch - tief).replace(0, np.nan)
    lage = (c - tief) / spanne
    for n in (3, 10):
        out[f"schluss_lage_{n}"] = lage.rolling(n).mean()

    # Verengt sich die Tagesspanne? Kompression geht Ausbruechen oft
    # voraus - eine andere Information als die Volatilitaet selbst.
    tr = ind.atr(df, 5) if {"high", "low"}.issubset(df.columns) else None
    if tr is not None:
        tr20 = ind.atr(df, 20)
        out["spanne_kompression"] = tr / tr20.replace(0, np.nan)

    # ------------------------------------------------------------- Luecken
    # Eroeffnungsluecken: Uebernacht-Information, die im Schlusskurs
    # NICHT steckt. Alle bestehenden Faktoren rechnen Schluss zu Schluss.
    if "open" in df:
        o = df["open"].astype(float)
        luecke = o / c.shift(1) - 1
        out["luecke_letzte"] = luecke
        out["luecke_summe_5"] = luecke.rolling(5).sum()
        # Wird die Luecke im Tagesverlauf geschlossen? Misst, ob der
        # Markt die Uebernacht-Bewegung bestaetigt oder verwirft.
        out["luecke_gefuellt"] = ((c - o) / o.replace(0, np.nan)).rolling(5).mean()

    # ------------------------------------------------------------- Volumen
    if vol is not None:
        dv = vol * c
        # Handelt der Wert an Aufwaertstagen mehr als an Abwaertstagen?
        # Klassische Akkumulations-Idee, misst Handelsverhalten statt Kurs.
        auf = (dv * (ret > 0)).rolling(21).sum()
        ab = (dv * (ret < 0)).rolling(21).sum()
        out["akkumulation_21"] = (auf - ab) / (auf + ab).replace(0, np.nan)

        # Volumen-Trend unabhaengig vom Kurs
        out["volumen_trend"] = (dv.rolling(5).mean()
                                / dv.rolling(60).mean().replace(0, np.nan))

        # Kursbewegung je Volumeneinheit, invers zu Amihud gedacht:
        # Bewegt sich der Kurs OHNE Volumen, ist die Bewegung duenn.
        out["bewegung_je_volumen"] = (ret.abs().rolling(10).mean()
                                      / (dv.rolling(10).mean() / 1e6).replace(0, np.nan))

    # -------------------------------------------------------------- Markt
    if markt is not None:
        m = markt.reindex(df.index).ffill()
        mret = m.pct_change()
        # Relative Staerke gegen den Markt - misst etwas anderes als die
        # absolute Bewegung, die alle bestehenden Faktoren erfassen.
        for n in (5, 21):
            out[f"rel_staerke_{n}"] = c.pct_change(n) - m.pct_change(n)

        # Beta ueber 60 Tage: Wie stark haengt der Wert am Markt?
        kov = ret.rolling(60).cov(mret)
        var = mret.rolling(60).var()
        out["beta_60"] = kov / var.replace(0, np.nan)

        # Eigenbewegung: Was bleibt nach Abzug der Marktbewegung? Das ist
        # der Teil, der wirklich zum Unternehmen gehoert.
        out["eigenbewegung_5"] = (ret - out["beta_60"] * mret).rolling(5).sum()

    return out.replace([np.inf, -np.inf], np.nan)


def beschreibung() -> dict[str, str]:
    """Was jeder Kandidat misst - fuer den Bericht und die Voranmeldung."""
    return {
        "aufwaertstage_5": "Anteil positiver Tage der letzten 5 - Bestaendigkeit statt Groesse",
        "aufwaertstage_10": "dito ueber 10 Tage",
        "aufwaertstage_21": "dito ueber 21 Tage",
        "beschleunigung_5_10": "Wird die Bewegung schneller? (5T gegen halbe 10T)",
        "beschleunigung_10_21": "dito auf laengerem Fenster",
        "schluss_lage_3": "Schluss im Tagesbereich, 3-Tage-Mittel - Kauf- oder Verkaufsdruck",
        "schluss_lage_10": "dito ueber 10 Tage",
        "spanne_kompression": "ATR(5)/ATR(20) - Verengung geht Ausbruechen oft voraus",
        "luecke_letzte": "Letzte Eroeffnungsluecke - Uebernacht-Information",
        "luecke_summe_5": "Summe der Luecken ueber 5 Tage",
        "luecke_gefuellt": "Wird die Luecke im Tagesverlauf bestaetigt oder verworfen?",
        "akkumulation_21": "Volumen an Auf- gegen Abwaertstagen - Handelsverhalten",
        "volumen_trend": "Volumen 5T gegen 60T, kursunabhaengig",
        "bewegung_je_volumen": "Bewegt sich der Kurs ohne Volumen? (duenne Bewegung)",
        "rel_staerke_5": "Rendite minus Marktrendite, 5 Tage",
        "rel_staerke_21": "dito, 21 Tage",
        "beta_60": "Marktabhaengigkeit ueber 60 Tage",
        "eigenbewegung_5": "Rendite nach Abzug der Marktbewegung - der firmeneigene Teil",
    }
