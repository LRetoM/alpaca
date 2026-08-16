"""Bot-Flotte: mehrere Varianten gleichzeitig messen - ohne sich zu betruegen.

Mehrere Bots parallel laufen zu lassen ist der schnellste Erkenntnisweg, den
dieses Projekt hat. Weil alle Bots dieselben Tage, Symbole und Kurse sehen,
kuerzt sich beim Vergleich der Marktfaktor heraus (siehe `vergleich_gepaart`
in shadow_eval.py): Die noetige Laufzeit sinkt von ~9 Monaten auf 6-10 Wochen.

**Es ist zugleich der gefaehrlichste Teil des ganzen Systems.**

Laufen 20 Bots und ist in Wahrheit KEINER besser als die anderen, zeigt der
beste nach drei Monaten trotzdem eine deutliche Ueberrendite - rein zufaellig.
Der Erwartungswert des Maximums von N unabhaengigen Standardnormalgroessen
liegt bei etwa sqrt(2*ln N):

        N=3  -> 1.48      N=20 -> 2.45      N=100 -> 3.03
        N=10 -> 2.15      N=50 -> 2.80

Ein t-Wert von 2.4 beim besten von 20 Bots ist also kein Befund, sondern der
Normalfall. Dieses Modul erzwingt deshalb drei Dinge:

  1. **Voranmeldung.** Jeder Bot braucht VOR seinem ersten Lauf eine
     Hypothese - warum sollte er besser sein, und woher stammt die Vermutung?
     Ohne das findet man im Nachhinein immer eine Begruendung, und aus
     Rauschen wird eine Geschichte.

  2. **Der Versuchszaehler vergisst nicht.** Stillgelegte Bots werden nicht
     geloescht; sie zaehlen dauerhaft mit. Einen Verlierer zu entfernen und
     zu vergessen ist der haeufigste Weg der Selbsttaeuschung.

  3. **Eine Achse je Bot.** Unterscheiden sich zwei Bots in fuenf Parametern
     und einer gewinnt, hat man nichts gelernt. `anmelden()` verlangt deshalb
     `achse` und `wert` und prueft gegen den Basis-Bot.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass

import pandas as pd

from .engine import EngineConfig
from .shadow import ShadowStore

# Die Startaufstellung aus docs/schattenbetrieb.md §5.3. Bewusst klein:
# Jeder weitere Bot hebt die Zufallsschwelle (siehe Modul-Docstring).
STARTAUFSTELLUNG = [
    dict(bot_id="B00_basis", name="Basis", familie="referenz",
         achse=None, wert=None, aenderung={},
         hypothese="Referenz fuer die faktoriellen Vergleiche B01-B08 "
                   "(je EIN geaenderter Parameter gegen diese Basis). "
                   "WICHTIG, gefunden am 16.08.2026: Diese Konfiguration "
                   "entspricht NICHT mehr dem Live-Bot. Am 30.07.2026 "
                   "(Commits 3e3d30e, f253724) wurden deploy_to_target und "
                   "allow_topup zum Live-STANDARD, B00 blieb bei False/False "
                   "stehen. Die Vergleiche B01-B07 gegen B00 bleiben "
                   "INTERN gueltig (beide Seiten teilen dieselbe False/False-"
                   "Basis, der jeweils eine Achse ist sauber isoliert) - nur "
                   "die Behauptung 'entspricht dem Live-Bot' war falsch. Die "
                   "tatsaechliche Live-Konfiguration liefert B09_nachkauf "
                   "(zufaellig exakt deckungsgleich seit 30.07.2026, siehe "
                   "dort). Fuer Vergleiche gegen den ECHTEN Live-Bot ist "
                   "B09_nachkauf die richtige Basis, nicht B00."),
    dict(bot_id="B01_stop_eng", name="Enger Stop", familie="stop_abstand",
         achse="stop_atr", wert="1.5", aenderung={"stop_atr": 1.5},
         hypothese="Ein schnellerer Ausstieg spart Verluste. Gegenhypothese "
                   "zu B02 - beide koennen nicht gleichzeitig stimmen."),
    dict(bot_id="B02_stop_weit", name="Weiter Stop", familie="stop_abstand",
         achse="stop_atr", wert="3.0", aenderung={"stop_atr": 3.0},
         hypothese="MAE-Befund: Gewinner gehen zwischenzeitlich tief ins "
                   "Minus. Ein enger Stop schneidet genau die Trades ab, "
                   "die am Ende funktioniert haetten."),
    dict(bot_id="B03_ziel_weit", name="Weites Ziel", familie="gewinnziel",
         achse="target_atr", wert="3.0", aenderung={"target_atr": 3.0},
         hypothese="MFE-Befund: Zwischen hoechstem erreichtem Kurs und "
                   "tatsaechlichem Ausstieg liegt Luft - das Ziel wird zu "
                   "frueh genommen."),
    dict(bot_id="B04_halten_lang", name="Lange Haltedauer", familie="haltedauer",
         achse="max_hold_days", wert="10", aenderung={"max_hold_days": 10},
         hypothese="Der Umkehr-Effekt koennte laenger tragen als die 3-5 "
                   "Tage, auf denen er gemessen wurde."),
    dict(bot_id="B05_schwelle_hoch", name="Hohe Schwelle", familie="auswahl",
         achse="min_score", wert="0.50", aenderung={"min_score": 0.50},
         hypothese="Weniger, aber ueberzeugendere Trades senken die Kosten. "
                   "ACHTUNG: §0.2 hat historisch KEINEN Effekt gefunden - "
                   "dieser Bot prueft, ob das vorwaerts genauso aussieht."),
    dict(bot_id="B06_ohne_regime", name="Ohne Regimefilter", familie="regime",
         achse="market_regime_filter", wert="aus", aenderung={},
         hypothese="Prueft, ob der SPY-Regimefilter ueberhaupt etwas "
                   "beitraegt - er sperrt Kaeufe im Baerenmarkt, aber "
                   "gemessen wurde sein Beitrag nie."),
    # --- Die beiden Wege zu hoeherem Investitionsgrad, GETRENNT getestet ---
    # Gemessen am 2026-07-30: Bei vollen 15 von 15 Positionen standen nur
    # 53,9 % des Kapitals im Markt. Ursache ist die Volatilitaets-Skalierung,
    # die als absoluter Multiplikator wirkt und Umkehr-Kandidaten (per
    # Definition stark gefallen, also volatil) systematisch verkleinert.
    # Es gibt zwei Auswege - welcher traegt, entscheidet die Messung.
    dict(bot_id="B07_mehr_positionen", name="Mehr Positionen",
         familie="investitionsgrad", achse="max_positions", wert="25",
         aenderung={"max_positions": 25},
         hypothese="Weg A zu hoeherem Investitionsgrad: mehr Plaetze statt "
                   "groesserer Positionen. Mehr Breite senkt das Einzelrisiko, "
                   "erhoeht aber den Umschlag - und Kosten fressen laut "
                   "Messung 0.2 bereits 72-109 % des Bruttogewinns."),
    dict(bot_id="B08_voll_investiert", name="Voll investiert",
         familie="investitionsgrad", achse="deploy_to_target", wert="True",
         aenderung={"deploy_to_target": True},
         hypothese="Weg B: gleiche Positionszahl, aber das freie Kapital wird "
                   "bis target_invested verteilt (Volatilitaet bestimmt nur "
                   "noch die relative Gewichtung). Kein zusaetzlicher "
                   "Umschlag, dafuer groessere Einzelpositionen. ACHTUNG: "
                   "Hoeherer Investitionsgrad verstaerkt Gewinne UND Verluste "
                   "- ohne nachgewiesenen Vorsprung ist das nicht per se gut."),
    dict(bot_id="B09_nachkauf", name="Nachkauf in Gewinner",
         familie="investitionsgrad", achse="allow_topup", wert="True",
         aenderung={"allow_topup": True, "deploy_to_target": True},
         # Gemessen wird gegen B08, nicht gegen B00: Beide sind voll
         # investiert, der EINZIGE Unterschied ist der Nachkauf.
         basis_bot="B08_voll_investiert",
         hypothese="Weg C: Bestehende Positionen aufstocken, statt auf freie "
                   "Plaetze zu warten. Nur in Gewinner und nur solange der "
                   "Score ueber der Kaufschwelle liegt - in Verlierer "
                   "nachzukaufen waere Average-Down. Offene Frage: Verstaerkt "
                   "das die Gewinner oder konzentriert es Kapital in Werten, "
                   "die ohnehin gleich ihr Ziel erreichen und verkauft "
                   "werden?\n\n"
                   "NACHTRAG 16.08.2026: Diese Konfiguration "
                   "(deploy_to_target=True, allow_topup=True, sonst "
                   "for_reversal()-Standard) ist seit dem 30.07.2026 "
                   "zufaellig EXAKT identisch mit dem, was scripts/"
                   "12_daemon.py tatsaechlich live faehrt (Skript-Defaults "
                   "seit Commits 3e3d30e/f253724). B09 ist damit die "
                   "korrekte Referenz fuer 'vergleiche gegen den echten "
                   "Live-Bot' - nicht B00_basis (siehe dessen Eintrag)."),
]


@dataclass
class Bot:
    bot_id: str
    name: str
    familie: str
    basis_bot: str | None
    achse: str | None
    wert: str | None
    hypothese: str
    status: str
    startkapital: float
    config: EngineConfig

    def signal_schluessel(self) -> str:
        """Bots mit gleichem Schluessel teilen sich die Signalberechnung.

        Die meisten Varianten aendern nur AUSSTIEGSparameter (stop_atr,
        target_atr, max_hold_days, min_score) - die beeinflussen die
        Signalberechnung nicht, nur die Auswertung der fertigen Signale.
        Sieben Bots brauchen dadurch zwei Signaldurchlaeufe statt sieben.
        """
        w = self.config.reversal_weights
        return json.dumps({
            "strategy": self.config.strategy,
            "rueckgang": w.rueckgang, "rsi2": w.rsi2,
            "ausverkauf": w.ausverkauf, "band_unten": w.band_unten,
            "regime": w.market_regime_filter,
        }, sort_keys=True)


def _store(store: ShadowStore | None) -> ShadowStore:
    return store or ShadowStore()


def anmelden(
    bot_id: str, *, name: str, familie: str, hypothese: str,
    achse: str | None = None, wert: str | None = None,
    aenderung: dict | None = None, basis_bot: str | None = "B00_basis",
    quelle: str | None = None, startkapital: float = 100_000.0,
    store: ShadowStore | None = None,
) -> str:
    """Meldet einen Bot an - VOR seinem ersten Lauf.

    `hypothese` ist Pflicht und beantwortet: Warum sollte das besser sein?
    Ohne diese Disziplin passiert unweigerlich Folgendes: Ein Bot gewinnt,
    man findet im Nachhinein eine Begruendung, und aus Rauschen wird eine
    Geschichte. Die Voranmeldung macht den Unterschied zwischen einem
    bestaetigten und einem erfundenen Befund nachpruefbar.
    """
    s = _store(store)
    if not hypothese or len(hypothese.strip()) < 20:
        raise ValueError(
            "Die Hypothese ist Pflicht und muss erklaeren, WARUM dieser Bot "
            "besser sein sollte. Ohne sie laesst sich ein spaeterer Sieg "
            "nicht von einer nachtraeglichen Erzaehlung unterscheiden."
        )
    if bot_id != "B00_basis" and not achse:
        raise ValueError(
            "Jeder Bot darf sich vom Basis-Bot in GENAU EINER Achse "
            "unterscheiden (§5.3). Ohne `achse` ist spaeter nicht "
            "zuzuordnen, woran ein Unterschied lag."
        )

    basis = EngineConfig.for_reversal()
    cfg_dict = basis.as_dict()
    cfg_dict.update(aenderung or {})

    with s._conn() as c:
        vorhanden = c.execute("SELECT status FROM bots WHERE bot_id=?",
                              (bot_id,)).fetchone()
        if vorhanden:
            return f"{bot_id} ist bereits angemeldet (Status: {vorhanden['status']})."

        c.execute(
            "INSERT INTO bots (bot_id, name, familie, basis_bot, achse, wert,"
            " config_json, hypothese, quelle, angemeldet_am, aktiv_ab, status,"
            " startkapital) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (bot_id, name, familie, basis_bot if bot_id != "B00_basis" else None,
             achse, wert, json.dumps(cfg_dict, ensure_ascii=False), hypothese,
             quelle, dt.datetime.now(dt.UTC).isoformat(),
             dt.datetime.now(dt.UTC).isoformat(), "laeuft", startkapital),
        )
        # Versuchszaehler hochsetzen - dauerhaft, auch wenn der Bot spaeter
        # stillgelegt wird.
        c.execute(
            "INSERT INTO versuchszaehler (id, n_bots_gesamt, aktualisiert)"
            " VALUES (1, 1, ?)"
            " ON CONFLICT(id) DO UPDATE SET"
            "   n_bots_gesamt = versuchszaehler.n_bots_gesamt + 1,"
            "   aktualisiert = excluded.aktualisiert",
            (dt.datetime.now(dt.UTC).isoformat(),),
        )
    return f"{bot_id} angemeldet."


def stilllegen(bot_id: str, grund: str = "", store: ShadowStore | None = None) -> str:
    """Legt einen Bot still. Er wird NICHT geloescht.

    Der Versuchszaehler behaelt ihn - sonst sinkt die Signifikanzschwelle
    genau dann, wenn man Verlierer entfernt, und jeder verbleibende Bot
    sieht besser aus, als er ist.
    """
    s = _store(store)
    with s._conn() as c:
        c.execute(
            "UPDATE bots SET status='stillgelegt', aktiv_bis=?,"
            " hypothese = hypothese || ' | stillgelegt: ' || ?"
            " WHERE bot_id=?",
            (dt.datetime.now(dt.UTC).isoformat(), grund or "ohne Angabe", bot_id),
        )
    return f"{bot_id} stillgelegt (zaehlt weiter im Versuchszaehler)."


def _bot_aus_zeile(row) -> Bot:
    d = json.loads(row["config_json"])
    basis = EngineConfig.for_reversal()
    erlaubt = set(basis.as_dict())
    cfg = EngineConfig(**{k: v for k, v in d.items()
                          if k in erlaubt and k != "strategy"},
                       strategy=d.get("strategy", "reversal"))
    cfg.reversal_weights = basis.reversal_weights
    if row["bot_id"] == "B06_ohne_regime":
        # Regimefilter sitzt in den Gewichten, nicht in EngineConfig.
        import copy
        cfg.reversal_weights = copy.replace(basis.reversal_weights,
                                            market_regime_filter=False)
    return Bot(
        bot_id=row["bot_id"], name=row["name"], familie=row["familie"],
        basis_bot=row["basis_bot"], achse=row["achse"], wert=row["wert"],
        hypothese=row["hypothese"], status=row["status"],
        startkapital=float(row["startkapital"] or 100_000), config=cfg,
    )


def aktive_bots(store: ShadowStore | None = None) -> list[Bot]:
    s = _store(store)
    with s._conn() as c:
        rows = c.execute(
            "SELECT * FROM bots WHERE status='laeuft' ORDER BY bot_id"
        ).fetchall()
    return [_bot_aus_zeile(r) for r in rows]


def alle_bots(store: ShadowStore | None = None) -> pd.DataFrame:
    return _store(store).table("bots")


def n_versuche(store: ShadowStore | None = None) -> int:
    """Anzahl ALLER je gestarteten Versuche - Grundlage der Schwelle."""
    s = _store(store)
    with s._conn() as c:
        row = c.execute("SELECT * FROM versuchszaehler WHERE id=1").fetchone()
    if not row:
        return 1
    return max(1, int(row["n_bots_gesamt"]) + int(row["n_hypothesen"] or 0))


def schwelle_sigma(store: ShadowStore | None = None) -> float:
    """Ab welchem t-Wert bedeutet ein Sieg ueberhaupt etwas?

        schwelle = sqrt(2 * ln(n_versuche)) + 0.5

    Der Zuschlag von 0.5 ist ein bewusster Sicherheitsaufschlag. Jede
    Auswertung zeigt diese Schwelle mit an; Befunde darunter gelten als
    nicht belastbar.
    """
    n = n_versuche(store)
    return round(math.sqrt(2 * math.log(max(n, 2))) + 0.5, 2)


def startaufstellung_anmelden(store: ShadowStore | None = None,
                              verbose: bool = True) -> int:
    """Meldet die Bots aus §5.3 an. Mehrfach aufrufbar."""
    s = _store(store)
    n = 0
    for b in STARTAUFSTELLUNG:
        msg = anmelden(
            b["bot_id"], name=b["name"], familie=b["familie"],
            hypothese=b["hypothese"], achse=b["achse"], wert=b["wert"],
            aenderung=b["aenderung"], quelle="docs/schattenbetrieb.md §5.3",
            # Manche Bots werden sinnvoll gegen einen ANDEREN Bot als die
            # Basis gemessen: B09 unterscheidet sich von B08 in genau einer
            # Achse (allow_topup), von B00 dagegen in zweien. Gegen B00
            # verglichen liesse sich ein Unterschied nicht zuordnen.
            basis_bot=b.get("basis_bot", "B00_basis"),
            store=s,
        )
        if verbose:
            print(f"  {msg}")
        n += int("angemeldet." in msg)
    return n


def uebersicht(store: ShadowStore | None = None) -> str:
    s = _store(store)
    df = alle_bots(s)
    lines = ["=" * 78, "  BOT-FLOTTE", "=" * 78]
    if df.empty:
        lines.append("  Keine Bots angemeldet.")
        lines.append("  -> python scripts/18_fleet.py --startaufstellung")
        return "\n".join(lines)

    for _, r in df.iterrows():
        marke = "*" if r["status"] == "laeuft" else " "
        achse = f"{r['achse']}={r['wert']}" if r["achse"] else "(Referenz)"
        lines.append(f" {marke} {r['bot_id']:<18} {achse:<28} {r['status']}")
        lines.append(f"     {r['hypothese'][:110]}")
    n = n_versuche(s)
    lines += [
        "",
        f"  Versuche gesamt (inkl. stillgelegter): {n}",
        f"  Zufallsschwelle: t > {schwelle_sigma(s)}",
        "",
        "  Ein t-Wert unterhalb dieser Schwelle ist bei dieser Zahl von",
        "  Versuchen der NORMALFALL, kein Befund.",
    ]
    return "\n".join(lines)
