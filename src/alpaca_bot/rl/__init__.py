"""Reinforcement Learning fuers Handeln - mit den Sicherungen, die es braucht.

## Ehrliche Einordnung, bevor du hier Zeit investierst

Ein DQN, das aus Fehlern und Erfolgen lernt, ist ein gutes Ziel. Es hat
im Trading aber vier bekannte Schwachstellen, die man kennen muss, sonst
baut man ein System, das im Training grossartig aussieht und live verliert:

1. **Datenhunger.** DQN braucht Millionen Uebergaenge. Zehn Jahre
   Tagesdaten sind 2.500 Schritte je Aktie. Selbst mit 500 Aktien sind
   das stark korrelierte, nicht unabhaengige Erfahrungen.

2. **Nicht-Stationaritaet.** RL setzt voraus, dass die Umgebung stabil
   ist. Der Markt von 2021 ist nicht der von 2023. Eine gelernte Politik
   veraltet, waehrend sie gelernt wird.

3. **Auswendiglernen des Kurspfads.** Bei Belohnung = Gewinn merkt sich
   das Netz die konkrete Historie. Das ist die haeufigste Ursache fuer
   traumhafte Trainingskurven ohne jeden Wert.

4. **Zuordnungsproblem.** War ein Gewinn die Folge der Entscheidung oder
   Zufall? Bei 95 % Rauschen ist das kaum trennbar.

## Was daraus folgt - und wie dieses Paket es umsetzt

RL ist im Trading **stark bei der Positionsgroesse und schwach bei der
Richtung**. Deshalb ist die Aktionsmenge hier nicht "kaufen/verkaufen",
sondern eine Ziel-Positionsgroesse. Das Modell lernt, WIE VIEL es bei
gegebener Lage riskiert - genau die Frage, bei der RL nachweislich hilft
und die laut Strategie-Analyse ohnehin mehr Rendite bringt als bessere
Einstiegssignale.

Und - das ist der eigentliche Punkt - jede Auswertung laeuft gegen drei
Vergleichspolitiken:

    Buy & Hold  |  Zufallspolitik  |  immer flach

**Schlaegt der Agent die Zufallspolitik out-of-sample nicht, hat er
nichts gelernt.** Dieser Test ist in `train.evaluate()` fest verdrahtet
und laesst sich nicht abschalten. Die meisten DQN-Trading-Projekte im
Netz fuehren ihn nicht durch - deshalb sehen sie alle so gut aus.
"""

from .env import Action, RewardConfig, TradingEnv
from .dqn import DQNAgent, DQNConfig
from .train import evaluate, train_walk_forward

__all__ = [
    "TradingEnv",
    "RewardConfig",
    "Action",
    "DQNAgent",
    "DQNConfig",
    "train_walk_forward",
    "evaluate",
]
