"""PPO - Adaptive Traffic Congestion Reduction (docs/ppo.md).

One of the three active RL agents (R10). Objective: cut queues and waiting time
while lifting throughput - reward R = -alpha*Q - beta*W + gamma*T. Wired into the
live loop, training, evaluation, coordination and the full UI alongside A2C and DQN.
"""

from app.agents.ppo.agent import PPOAction, PPOAgent

__all__ = ["PPOAgent", "PPOAction"]
