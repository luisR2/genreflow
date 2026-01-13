## Architecture

This diagram shows the current MVP components and planned extensions.

```mermaid
flowchart TD
    User["👤 User"]

    %% Implemented (MVP)
    Frontend["Frontend<br/>(HTML / CSS / JS)<br/>Port: 3000"]
    Backend["Backend<br/>(FastAPI / Python)<br/>Port: 8080"]

    %% Planned components
    Spotify["Spotify API"]
    Classifier["Genre Classifier<br/>(ML Model)"]

    User --> Frontend
    Frontend -->|REST API| Backend
    Backend -.-> Spotify
    Backend -.-> Classifier

    %% Subgraphs
    subgraph MVP["Implemented (MVP)"]
        Frontend
        Backend
    end

    subgraph Planned["Planned / Not Yet Implemented"]
        Spotify
        Classifier
    end

    subgraph k3s["Deployed on k3s Raspberry Pi Cluster"]
        MVP
        Planned
    end

    %% Styling nodes
    style Frontend fill:#dbeafe,stroke:#2563eb,stroke-width:2px
    style Backend fill:#dbeafe,stroke:#2563eb,stroke-width:2px

    style Spotify fill:#f9fafb,stroke:#9ca3af,stroke-width:1.5px
    style Classifier fill:#f9fafb,stroke:#9ca3af,stroke-width:1.5px

    style User fill:#ffffff,stroke:#6b7280,stroke-dasharray: 5 5

    %% Styling subgraphs (important!)
    style MVP fill:#f0f9ff,stroke:#2563eb,stroke-width:2px
    style Planned fill:#fefce8,stroke:#ca8a04,stroke-width:2px
    style k3s fill:#fefce8,stroke:#a3a3a3,stroke-width:1.5px