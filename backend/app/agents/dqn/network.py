"""DQN Q-network (docs/dqn.md section 4)."""

from __future__ import annotations

import torch
import torch.nn as nn

from app.agents.common.networks import mlp_trunk, orthogonal_init


class QNetwork(nn.Module):
    def __init__(self, state_dim: int, n_actions: int, hidden: int = 128) -> None:
        super().__init__()
        self.trunk = mlp_trunk(state_dim, hidden, layers=2)
        self.head = nn.Linear(hidden, n_actions)
        orthogonal_init(self.trunk, gain=2.0 ** 0.5)
        orthogonal_init(self.head, gain=1.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.trunk(x))
