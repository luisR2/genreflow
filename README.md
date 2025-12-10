# GenreFlow
A music genre classifier that serves predictions via FastAPI

> 🚧 *Work in progress – early setup phase - API and features may change*

**GenreFlow** is a Kubernetes-native music genre classifier built with **FastAPI**, **Docker**, and **k8s**.  
It runs on a **k3s Raspberry Pi cluster**, serving predictions for uploaded files or Spotify tracks (via 30-second previews).  

---

## About the project

As a music lover learning how to DJ, I wanted to bring my passion and my work together in one project.
While I’m aware there are already many tools that can identify a song’s **genre** and **BPM**, I wanted to contribute my own take, a version that reflects both my curiosity and my technical background.

That idea became **GenreFlow**: a project that blends **Music and DevOps**, using **FastAPI**, **Docker**, and **Kubernetes** to deploy a music genre classification model capable of analyzing **audio files**. The main objective of the project is to **identify the musical genre of a song, session, or playlist.** For sessions or playlists that contain mixed genres, the system will also determine the predominant one.

Beyond its purpose as a classifier, GenreFlow is also an experiment in building production-ready systems, complete with **CI/CD** **pipelines**, and **multi-architecture support** for environments like a **k3s Raspberry Pi cluster**.

---

## Vision

Bring Music and DevOps together by deploying an audio model as a real microservice.  
GenreFlow will classify music into genres and expose a simple API with full observability and GitOps-ready deployment.

The idea is to be able to load complete playlists and have detailed analysis of some of the necessary data for a DJ to prepare a session, like BPM, genre, key etc...

---


## Architecture


## Tech Stack

| Area | Tools |
|------|-------|
| Backend | Python · FastAPI · Uvicorn |
| Frontend | HTML · CSS · Javascript | 
| Packaging | Docker (multi-arch) |
| Orchestration | Kubernetes (k3s / k8s) |
| CI/CD | ArgoCD · GitHub Actions · Trivy |
| Observability | Prometheus · Grafana |
| Integrations | Spotify Web API (preview URLs + audio features) |

---

## Repository Layout
```
genreflow/
├─ backend/              # Backend service (FastAPI + inference)
│  ├─ app/               # Application code
│  ├─ tests/             # Backend tests
│  ├─ pyproject.toml     # Poetry config (backend-only)
│  └─ Dockerfile         # Backend image
├─ frontend/             # Frontend FastAPI static UI + Dockerfile
├─ k8s/                  # Kubernetes manifests (argocd/, backend/, frontend/)
├─ scripts/              # Utility scripts
├─ logging_config.json   # Shared logging config (backend & frontend)
├─ Makefile              # Common tasks
└─ README.md

## Roadmap

---

```


## License