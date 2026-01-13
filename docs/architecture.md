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

    %% Styling
    style Frontend fill:#dbeafe,stroke:#2563eb,stroke-width:2px
    style Backend fill:#dbeafe,stroke:#2563eb,stroke-width:2px

    style Spotify fill:#f3f4f6,stroke:#9ca3af,stroke-width:1.5px
    style Classifier fill:#f3f4f6,stroke:#9ca3af,stroke-width:1.5px

    style User fill:#ffffff,stroke:#6b7280,stroke-dasharray: 5 5