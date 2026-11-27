# RINK-OS // NHL Hockey Operations & Analytics Command Center

[![Live Demo](https://img.shields.io/badge/Live_Demo-RINK--OS_Platform-003E7E?style=for-the-badge&logo=githubpages&logoColor=white)](https://GK1724.github.io/rink-os/)
[![Python](https://img.shields.io/badge/ETL_Pipeline-Python_3.11+-1E293B?style=for-the-badge&logo=python&logoColor=white)](./etl/rink_os_etl.py)
[![Data Source](https://img.shields.io/badge/Telemetry-Official_NHL_API-0F172A?style=for-the-badge)](https://api-web.nhle.com/v1/)

**RINK-OS** is an end-to-end NHL Hockey Operations decision-support platform designed around the **"3-Click Rule"**—translating 60Hz optical tracking, play-by-play shot coordinates, shift intervals, and salary cap constraints into actionable decisions for General Managers, Coaching Staff, Scouts, and High-Performance teams.

Built using the **2026–27 Toronto Maple Leafs** regular season (`9-14-3`, `21 PTS` through 26 games) as a live diagnostic case study.

---

## Core Operational Suites (9 Interactive Modules)

### 1. Coaching & Tactical Suite
* **5v5 Tactical & Line Chemistry:** Isolates forward trios and defense pairings across configurable game windows with a **WOWY (With Or Without You)** matrix (`CF%`, `xGF%`, `HDCF%`, `xGF/60`), an interactive **SVG Offensive Zone Shot Heatmap**, optical zone entry/exit tracking, and **8-second shift video cutups**.
* **Live Bench Tablet:** High-contrast in-game view for TV timeouts and intermissions featuring trapped D-zone shift fatigue alerts (`65s+`), head-to-head line-matching matrices with center faceoff win rates, and an empty-net goalie pull optimizer curve.
* **Defensive Zone Forensics:** Root-cause breakdown of high-danger chances against (*Lost Man-to-Man Switch*, *Weak-Side Backdoor Seam*, *Failed D-to-D Rim Exit*, *Lost Net-Front Box-Out*), pairing-specific breakout exit rates, and an `oZS% vs. xGA/60` deployment scatter plot.
* **Special Teams Lab & Pre-Scout Engine:** Interactive 1-3-1 Power Play passing network (`25.35% PP`), Penalty Kill breakdown audit (`82.28% PK`), and automated pre-game opponent dossiers.

### 2. Front Office & Scouting Suite
* **Roster & Cap Simulator:** Live `$104.0M` salary cap compliance tracker modeling active commitments (`$112.19M`), LTIR relief pools (`Max Domi`, `Elvis Merzlikins`), deadline cap accrual, and a **WAR vs. Cap Hit** surplus-value scatter plot.
* **Pro Scouting Trade Target "Fit Finder":** Roster gap percentile radar overlay, cosine-similarity player matching engine with 50% salary retention toggles, and one-click integration into the Cap Simulator.
* **Playoff Odds & Season Trajectory Simulator:** 10,000-iteration Monte Carlo simulator projecting 82-game points distributions (`25th / 50th / 75th` percentiles) with interactive sliders for `5v5 xGF%` improvement and team `SV%` regression.
* **2026 Draft & Marlies Prospect Hub:** Rookie telemetry for #1 overall pick **Gavin McKenna**, sortable **NHLe (NHL Equivalency)** draft board (`pStar %`, `pNHL %`, scout grades), and Toronto Marlies AHL call-up readiness tracker.

### 3. Performance & Sports Science Suite
* **Goaltending Biomechanics & Workload Lab:** Isolates team defensive breakdowns from individual goaltending performance via **Goals Saved Above Expected (GSAx)** split by shot danger and pre-shot movement (`Anthony Stolarz` vs. `Sergei Bobrovsky`), paired with a **Catapult GPS ACWR (Acute-to-Chronic Workload Ratio)** fatigue traffic-light monitor.

---

## Architecture & Data Pipeline

```text
┌──────────────────────────┐     ┌─────────────────────────────┐     ┌───────────────────────────┐
│   Official NHL APIs      │     │   Python ETL & Modeling     │     │   RINK-OS Front-End       │
│  • [api-web.nhle.com/v1/](https://api-web.nhle.com/v1/)  │ ──▶ │  • etl/rink_os_etl.py       │ ──▶ │  • index.html (9 Modules) │
│  • [api.nhle.com/stats/](https://api.nhle.com/stats/)   │     │  • etl/build_metrics.py     │     │  • SVG Rink Heatmaps      │
│  • Shift Charts & PBP    │     │  • Coordinate Normalization │     │  • Monte Carlo & Cap Sim  │
└──────────────────────────┘     └─────────────────────────────┘     └───────────────────────────┘