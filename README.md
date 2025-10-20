# 🎵 GenreFlow
A production-grade music genre classifier that serves predictions via FastAPI

**GenreFlow** is a Kubernetes-native music genre classifier built with **FastAPI**, **Docker**, and **Helm**.  
It runs on a **k3s Raspberry Pi cluster** and in the cloud, serving predictions for uploaded files or Spotify tracks (via 30-second previews).  

> 🚧 *Work in progress – early setup phase (Milestone 0)*

---

## About the project

As a music lover learning how to DJ, I wanted to bring my passion and my work together in one project.
While I’m aware there are already many tools that can identify a song’s **genre** and **BPM**, I wanted to contribute my own take — a version that reflects both my curiosity and my technical background.

That idea became **GenreFlow**: a project that blends **AI and DevOps**, using **FastAPI**, **Docker**, and **Kubernetes** to deploy a music genre classification model capable of analyzing both **local audio files and Spotify tracks** (via preview URLs). The main objective of the project is to **identify the musical genre of a song, session, or playlist.** For sessions or playlists that contain mixed genres, the system will also determine the predominant one.

Beyond its purpose as a classifier, GenreFlow is also an experiment in building production-ready machine learning systems — complete with **CI/CD** **pipelines**, and **multi-architecture support** for environments like a **k3s Raspberry Pi cluster**.

---

## 💡 Vision

Bring MLOps and DevOps together by deploying an AI audio model as a real microservice.  
GenreFlow will classify music into genres and expose a simple API (`/predict/file` and `/predict/spotify`) with full observability and GitOps-ready deployment.

---

## 🧰 Tech Stack
| Area | Tools |
|------|-------|
| Backend | Python · FastAPI · Uvicorn |
| ML / Audio | PyTorch · torchaudio · librosa · ONNX / TFLite |
| Packaging | Docker (multi-arch) · Helm |
| Orchestration | Kubernetes (k3s / k8s) |
| CI/CD | GitHub Actions · Trivy · cosign |
| Observability | Prometheus · Grafana |
| Integrations | Spotify Web API (preview URLs + audio features) |

---

## 🚀 Roadmap
- [x] Project skeleton & docs  
- [ ] FastAPI `/healthz` + basic tests  
- [ ] `/predict/file` endpoint (local audio)  
- [ ] Docker image buildx (arm64/amd64)  
- [ ] Helm chart + k3s deployment  
- [ ] `/predict/spotify` (preview support)  
- [ ] Features→Genre fallback model  
- [ ] Prometheus metrics + Grafana dashboard  
- [ ] Public release v0.1.0  

---

## 🧩 Repository Layout (planned)
```
genreflow/
|
├─ model/ # training & export scripts
|
├─ server/ # FastAPI app & inference
|
├─ docker/ # Dockerfile(s)
|
├─ k8s/helm/ # Helm chart
|
├─ .github/workflows/ # CI/CD pipelines
|
├─ scripts/ # utility scripts
|
├─Makefile # Make targets
|
└─ README.md
```