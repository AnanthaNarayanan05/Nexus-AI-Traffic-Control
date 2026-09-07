"""Uniform experience replay buffer for DQN (spec section 15, 17)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Transition:
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool
    # human-readable context kept for the replay inspector (spec section 17)
    info: dict


class ReplayBuffer:
    def __init__(self, capacity: int, state_dim: int, seed: int = 0) -> None:
        self.capacity = capacity
        self.state_dim = state_dim
        self._states = np.zeros((capacity, state_dim), dtype=np.float32)
        self._next = np.zeros((capacity, state_dim), dtype=np.float32)
        self._actions = np.zeros(capacity, dtype=np.int64)
        self._rewards = np.zeros(capacity, dtype=np.float32)
        self._dones = np.zeros(capacity, dtype=np.float32)
        self._info: list[dict] = [dict() for _ in range(capacity)]
        self._pos = 0
        self._full = False
        self._rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return self.capacity if self._full else self._pos

    def add(self, t: Transition) -> None:
        i = self._pos
        self._states[i] = t.state
        self._next[i] = t.next_state
        self._actions[i] = t.action
        self._rewards[i] = t.reward
        self._dones[i] = float(t.done)
        self._info[i] = t.info
        self._pos = (self._pos + 1) % self.capacity
        if self._pos == 0:
            self._full = True

    def sample(self, batch_size: int) -> tuple[np.ndarray, ...]:
        idx = self._rng.integers(0, len(self), size=batch_size)
        return (
            self._states[idx], self._actions[idx], self._rewards[idx],
            self._next[idx], self._dones[idx],
        )

    def sample_readable(self, n: int) -> list[Transition]:
        if len(self) == 0:
            return []
        idx = self._rng.integers(0, len(self), size=min(n, len(self)))
        return [
            Transition(
                state=self._states[i].copy(), action=int(self._actions[i]),
                reward=float(self._rewards[i]), next_state=self._next[i].copy(),
                done=bool(self._dones[i]), info=self._info[i],
            )
            for i in idx
        ]
