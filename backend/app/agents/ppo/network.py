"""PPO policy + value network (docs/ppo.md section 4)."""

from __future__ import annotations

import torch
import torch.nn as nn

from app.agents.common.networks import mlp_trunk, orthogonal_init


class PolicyValueNet(nn.Module):
    def __init__(self, state_dim: int, n_actions: int, hidden: int = 128) -> None:
        super().__init__()
        self.trunk = mlp_trunk(state_dim, hidden, layers=2)
        self.policy_head = nn.Linear(hidden, n_actions)
        self.value_head = nn.Linear(hidden, 1)
        orthogonal_init(self.trunk, gain=2.0 ** 0.5)
        orthogonal_init(self.policy_head, gain=0.01)
        orthogonal_init(self.value_head, gain=1.0)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.trunk(x)
        return self.policy_head(h), self.value_head(h).squeeze(-1)
