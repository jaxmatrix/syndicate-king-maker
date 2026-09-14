# Syndicate: The King Maker — Architecture & Execution Blueprint

**Syndicate: The King Maker** is an autonomous, global B2B commercial site selection and physical market expansion engine. It converts high-level business criteria into high-probability physical presence hotspots across any city or commercial coordinate globally.

---

## 1. Core Architecture Stack

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              SYNDICATE COMMAND CENTER (UI)                             │
├──────────────────────────┬───────────────────────────────┬─────────────────────────────┤
│   LEFT PANEL (380px)     │       CENTER MAP CANVAS       │    RIGHT SIDEBAR (420px)    │
│  Business Profile & ICP  │  Global Tactical Dark Engine  │   Live Agent Execution Log  │
│                          │                               │              &              │
│  • Company & Offering    │  • Global Pin Drop Tool       │ Interactive Agent Chat Room │
│  • Preset Archetypes     │  • Dynamic Radius Controller  │                             │
│  • B2B Deal Constraints  │    (500m to 15,000m range)    │  • Real-time SSE / Log Feed │
│  • Firebase Auth Status  │  • Tactical Building Pins     │  • Multi-turn User Chat     │
│  • Run Scan Trigger      │  • Offline Touchpoint Pins    │  • Mastra Agent Insights    │
│                          │  • Voronoi Hotspot Catchment  │  • Actionable Strategic ROI │
└──────────────────────────┴───────────────────────────────┴─────────────────────────────┘
                                           │
                                           │ REST / SSE
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   MASTRA AGENT & INTELLIGENCE RUNTIME LAYER                            │
│                                                                                        │
│  Mastra King Maker Agent: `syndicate-king-maker`                                       │
│  • System Prompt: Specialized Commercial Site Selection, Urban Footfall & GTM Physics  │
│  • Tools Bound:                                                                        │
│    1. `anakinWireTool`: Sector pain & community complaint extraction (Reddit/Trustpilot)│
│    2. `googlePlacesScanner`: Corporate tower, business park & headcount discovery       │
│    3. `offlineTouchpointSimulator`: 350m–600m radius executive lunch/cafe simulation   │
│    4. `hotspotOptimizer`: Spatial density scoring, daily flow & monthly ICP reach       │
│  • Multi-Turn Conversational Reasoning: Explains why hotspots were selected & refines  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Surfaces & Components to Build

### Surface 1: Global Map & Dynamic Spatial Pin Drop
- **Location Agnostic**: Any latitude/longitude on Earth can be analyzed (San Francisco, London, Tokyo, Singapore, Bangalore, Mumbai, New York, etc.).
- **Interactive Drop-Pin Mode**: Clicking "Drop Pin" activates a crosshair on the map. Placing or dragging the marker dynamically updates the center coordinates.
- **Dynamic Radius Controller**: An interactive slider (500m to 15,000m) with a live glowing catchment boundary on the map.

### Surface 2: Live Right Sidebar (Agent Telemetry + Chat Console)
- **Tab A: Live Agent Telemetry**:
  - Step 1: Ingesting business parameters and deal profile.
  - Step 2: Querying Anakin Wire for sector pain points and common vendor failures.
  - Step 3: Scanning Google Places within the target radius for corporate towers and office parks.
  - Step 4: Simulating offline touchpoints (executive coffee, business dining, transit hubs).
  - Step 5: Clustering hotspots and generating strategic outlet recommendations.
- **Tab B: Interactive Agent Chat Room**:
  - Powered by the Mastra King Maker Agent.
  - The user can ask questions: *"Why pick SOMA over FiDi?"*, *"What if we focus on deals over $50k?"*, *"Suggest 3 street corners for a flagship pop-up"*.
  - The agent responds with cited data from the simulation and dynamically updates map filters.

### Surface 3: Mastra Agent Framework
- Configured with typed tool schemas and a tailored system persona:
  - Role: Senior Commercial Real Estate Strategist, B2B Growth Architect, and Spatial GTM Lead.
  - Incorporates Anakin's network-layer Wire data and Google Places coordinates.

---

## 3. Milestones & Implementation Checklist

- [ ] **Milestone 1**: Set up project workspace with Mastra agent files and blueprint reference.
- [ ] **Milestone 2**: Implement Mastra King Maker Agent (`agent.ts`, tools, and chat loop).
- [ ] **Milestone 3**: Implement 3-column UI with Global Pin Drop, Dynamic Radius Slider, and Right Sidebar (Live Log + Chat).
- [ ] **Milestone 4**: Wire the backend API with the Mastra agent and live simulation streaming.
- [ ] **Milestone 5**: Package, test, and deploy to Helix (`https://syndicate-app.jai.allr.work`).
