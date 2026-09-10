# 🚦 NEXUS AI Traffic Control

<p align="center">
  <img src="assets/nexus-banner.png" alt="NEXUS AI Traffic Control" width="100%">
</p>

<p align="center">
  <h1 align="center">NEXUS AI TRAFFIC CONTROL</h1>
</p>

<p align="center">
  <strong>Smarter Decisions. Safer Intersections. Better Traffic Flow.</strong>
</p>

<p align="center">
  A real-time intelligent traffic signal simulation platform powered by
  <strong>multiple Reinforcement Learning agents</strong>, coordinated decision-making,
  and an authoritative traffic-safety layer.
</p>

<p align="center">

![AI](https://img.shields.io/badge/AI-Reinforcement%20Learning-00D9FF?style=for-the-badge&logo=openai&logoColor=white)
![A2C](https://img.shields.io/badge/A2C-Emergency%20Response-0EA5E9?style=for-the-badge)
![DQN](https://img.shields.io/badge/DQN-Efficiency%20%26%20Safety-14B8A6?style=for-the-badge)
![PPO](https://img.shields.io/badge/PPO-Congestion%20Management-8B5CF6?style=for-the-badge)

</p>

<p align="center">

![React](https://img.shields.io/badge/Frontend-React%20%2B%20TypeScript-61DAFB?style=flat-square&logo=react&logoColor=white)
![PixiJS](https://img.shields.io/badge/Rendering-PixiJS-EF4444?style=flat-square)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![PyTorch](https://img.shields.io/badge/ML-PyTorch-EE4C2C?style=flat-square&logo=pytorch&logoColor=white)
![WebSockets](https://img.shields.io/badge/Communication-WebSocket-111827?style=flat-square)

</p>

<p align="center">

![Tests](https://img.shields.io/badge/Tests-238%20Backend%20%7C%2090%20Frontend-success?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active%20Development-00D9FF?style=flat-square)
![Simulation](https://img.shields.io/badge/Simulation-Real--Time%202D-111827?style=flat-square)

</p>

---

## 🌐 What is NEXUS?

**NEXUS AI Traffic Control** is a real-time intelligent traffic signal simulation platform designed to explore how multiple Reinforcement Learning algorithms can cooperate to control a dynamic urban intersection.

Instead of forcing one machine-learning algorithm to solve every traffic problem, NEXUS uses a **three-agent architecture** where each algorithm is assigned a specific objective:

| Agent | Objective | Focus |
|:---:|---|---|
| 🟦 **A2C** | Emergency Response | Emergency vehicle prioritization |
| 🟩 **DQN** | Traffic Efficiency | Stops, fuel, emissions and safety |
| 🟪 **PPO** | Congestion Management | Adaptive traffic flow and queue reduction |

These agents generate independent recommendations.

A coordination engine evaluates those recommendations.

An authoritative safety layer validates the resulting action.

Only then is the final signal decision applied to the traffic environment.

```text
Traffic Environment
        ↓
State Observation
        ↓
┌───────────────┬───────────────┬───────────────┐
│     A2C       │     DQN       │     PPO       │
│ Emergency     │ Efficiency    │ Congestion    │
│ Response      │ & Safety      │ Management     │
└───────┬───────┴───────┬───────┴───────┬───────┘
        │               │               │
        └───────────────┼───────────────┘
                        ↓
              Coordination Engine
                        ↓
               Safety Validation
                        ↓
                 Final Signal
                        ↓
              Traffic Environment
                        ↓
               Metrics & Learning
