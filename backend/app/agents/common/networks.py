"""Shared network building blocks (custom PyTorch - docs/assumptions.md A7)."""

from __future__ import annotations

import torch
import torch.nn as nn


def mlp_trunk(in_dim: int, hidden: int, layers: int = 2) -> nn.Sequential:
    mods: list[nn.Module] = []
    d = in_dim
    for _ in range(layers):
        mods += [nn.Linear(d, hidden), nn.Tanh()]
        d = hidden
    return nn.Sequential(*mods)


def orthogonal_init(module: nn.Module, gain: float = 1.0) -> nn.Module:
    for m in module.modules():
        if isinstance(m, nn.Linear):
            nn.init.orthogonal_(m.weight, gain)
            nn.init.zeros_(m.bias)
    return module


@torch.no_grad()
def soft_update(target: nn.Module, source: nn.Module, tau: float = 1.0) -> None:
    for tp, sp in zip(target.parameters(), source.parameters(), strict=True):
        tp.data.mul_(1.0 - tau).add_(tau * sp.data)
