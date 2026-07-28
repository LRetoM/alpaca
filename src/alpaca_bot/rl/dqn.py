"""Double DQN mit Replay-Puffer und Zielnetz.

Bewusst die vollstaendige, korrekte Variante - die Abkuerzungen, die man
in Tutorials findet, sind genau die Stellen, an denen ein DQN im Trading
scheitert:

* **Zielnetz** (Mnih et al. 2015). Ohne getrenntes Zielnetz jagt das
  Netz seinem eigenen, staendig wandernden Ziel hinterher und divergiert.
* **Double DQN** (van Hasselt et al. 2016). Standard-DQN ueberschaetzt
  Q-Werte systematisch, weil dasselbe Netz die Aktion auswaehlt und
  bewertet. Bei verrauschten Belohnungen - also im Trading - ist dieser
  Effekt gravierend: Der Agent haelt jede zufaellig gute Aktion fuer gut.
* **Huber-Verlust** statt quadratischem Fehler. Ein einzelner
  30-%-Kurstag wuerde bei MSE den Gradienten dominieren.
* **Replay-Puffer.** Aufeinanderfolgende Marktzustaende sind hochgradig
  korreliert. Ohne Durchmischung lernt das Netz die Reihenfolge statt
  die Struktur.
* **Gradienten-Clipping** gegen die gelegentliche Ausreisser-Belohnung.

Was hier bewusst NICHT drin ist: Prioritized Replay und Dueling-Architektur.
Beide bringen in Spielen etwas, erhoehen hier aber nur die Zahl der
Stellschrauben - und jede zusaetzliche Stellschraube ist eine weitere
Gelegenheit, die Historie zu ueberoptimieren.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class DQNConfig:
    hidden: tuple[int, ...] = (128, 64)
    lr: float = 3e-4
    gamma: float = 0.99
    """Diskontfaktor. 0.99 bei Tagesdaten heisst: ein Effekt in 100 Tagen
    zaehlt noch zu ~37 %. Fuer kurzfristige Strategien niedriger setzen."""
    batch_size: int = 64
    buffer_size: int = 100_000
    target_sync: int = 500
    """Alle n Lernschritte wird das Zielnetz nachgezogen."""
    learn_every: int = 4
    warmup: int = 1_000
    """So viele Uebergaenge sammeln, bevor gelernt wird - sonst lernt das
    Netz auf 30 Beispielen und ueberschreibt sich selbst."""
    eps_start: float = 1.0
    eps_end: float = 0.05
    eps_decay_steps: int = 20_000
    grad_clip: float = 10.0
    seed: int = 42
    device: str = "auto"


class QNetwork(nn.Module):
    def __init__(self, state_dim: int, n_actions: int, hidden: tuple[int, ...]):
        super().__init__()
        layers: list[nn.Module] = []
        prev = state_dim
        for h in hidden:
            layers += [nn.Linear(prev, h), nn.ReLU()]
            prev = h
        layers.append(nn.Linear(prev, n_actions))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class ReplayBuffer:
    """Erfahrungsspeicher. Genau hier lernt das System aus Fehlern UND Erfolgen:
    beide bleiben gespeichert und werden immer wieder neu durchgespielt."""

    def __init__(self, capacity: int, seed: int = 0):
        self.buf: deque = deque(maxlen=capacity)
        self.rng = random.Random(seed)

    def push(self, s, a, r, s2, done) -> None:
        self.buf.append((s, a, r, s2, float(done)))

    def sample(self, n: int):
        batch = self.rng.sample(self.buf, n)
        s, a, r, s2, d = zip(*batch)
        return (
            np.asarray(s, dtype=np.float32),
            np.asarray(a, dtype=np.int64),
            np.asarray(r, dtype=np.float32),
            np.asarray(s2, dtype=np.float32),
            np.asarray(d, dtype=np.float32),
        )

    def __len__(self) -> int:
        return len(self.buf)


class DQNAgent:
    """Double-DQN-Agent."""

    def __init__(self, state_dim: int, n_actions: int, config: DQNConfig | None = None):
        self.cfg = config or DQNConfig()
        self.state_dim, self.n_actions = state_dim, n_actions

        torch.manual_seed(self.cfg.seed)
        np.random.seed(self.cfg.seed)
        random.seed(self.cfg.seed)

        self.device = torch.device(
            ("mps" if torch.backends.mps.is_available()
             else "cuda" if torch.cuda.is_available() else "cpu")
            if self.cfg.device == "auto"
            else self.cfg.device
        )

        self.q = QNetwork(state_dim, n_actions, self.cfg.hidden).to(self.device)
        self.target = QNetwork(state_dim, n_actions, self.cfg.hidden).to(self.device)
        self.target.load_state_dict(self.q.state_dict())
        self.target.eval()

        self.opt = torch.optim.Adam(self.q.parameters(), lr=self.cfg.lr)
        self.buffer = ReplayBuffer(self.cfg.buffer_size, self.cfg.seed)
        self.rng = np.random.default_rng(self.cfg.seed)

        self.steps = 0
        self.learn_steps = 0
        self.losses: list[float] = []

    # --- Verhalten ---------------------------------------------------------
    @property
    def epsilon(self) -> float:
        """Explorationsrate, linear fallend."""
        c = self.cfg
        frac = min(1.0, self.steps / max(1, c.eps_decay_steps))
        return c.eps_start + frac * (c.eps_end - c.eps_start)

    def act(self, state: np.ndarray, greedy: bool = False) -> int:
        """Waehlt eine Aktion. `greedy=True` fuer die Auswertung (keine Zufallszuege)."""
        if not greedy and self.rng.random() < self.epsilon:
            return int(self.rng.integers(0, self.n_actions))
        with torch.no_grad():
            s = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
            return int(self.q(s).argmax(dim=1).item())

    def q_values(self, state: np.ndarray) -> np.ndarray:
        """Q-Werte - fuer die Nachvollziehbarkeit im Protokoll."""
        with torch.no_grad():
            s = torch.as_tensor(state, dtype=torch.float32, device=self.device).unsqueeze(0)
            return self.q(s).cpu().numpy()[0]

    # --- Lernen ------------------------------------------------------------
    def remember(self, s, a, r, s2, done) -> None:
        self.buffer.push(s, a, r, s2, done)
        self.steps += 1

    def learn(self) -> float | None:
        c = self.cfg
        if len(self.buffer) < max(c.warmup, c.batch_size):
            return None
        if self.steps % c.learn_every != 0:
            return None

        s, a, r, s2, d = self.buffer.sample(c.batch_size)
        s = torch.as_tensor(s, device=self.device)
        a = torch.as_tensor(a, device=self.device)
        r = torch.as_tensor(r, device=self.device)
        s2 = torch.as_tensor(s2, device=self.device)
        d = torch.as_tensor(d, device=self.device)

        q_sa = self.q(s).gather(1, a.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            # Double DQN: Online-Netz WAEHLT, Zielnetz BEWERTET.
            best = self.q(s2).argmax(dim=1, keepdim=True)
            q_next = self.target(s2).gather(1, best).squeeze(1)
            target = r + c.gamma * q_next * (1 - d)

        loss = F.smooth_l1_loss(q_sa, target)

        self.opt.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(self.q.parameters(), c.grad_clip)
        self.opt.step()

        self.learn_steps += 1
        if self.learn_steps % c.target_sync == 0:
            self.target.load_state_dict(self.q.state_dict())

        value = float(loss.item())
        self.losses.append(value)
        return value

    # --- Persistenz --------------------------------------------------------
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(
            {
                "q": self.q.state_dict(),
                "target": self.target.state_dict(),
                "config": self.cfg.__dict__,
                "state_dim": self.state_dim,
                "n_actions": self.n_actions,
                "steps": self.steps,
            },
            path,
        )
        return path

    @classmethod
    def load(cls, path: str | Path) -> DQNAgent:
        blob = torch.load(path, map_location="cpu", weights_only=False)
        cfg = DQNConfig(**blob["config"])
        agent = cls(blob["state_dim"], blob["n_actions"], cfg)
        agent.q.load_state_dict(blob["q"])
        agent.target.load_state_dict(blob["target"])
        agent.steps = blob.get("steps", 0)
        return agent
