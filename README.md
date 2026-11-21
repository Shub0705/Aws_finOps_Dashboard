AWS FinOps Dashboard

An AWS FinOps application for monitoring cloud resource usage, tracking infrastructure resources, and managing cloud costs.

Architecture
mermaid
flowchart TD
    U[User / Browser] --> FE[React Frontend]
    FE --> API[FastAPI Backend]
    API --> RT[Resource Tracking]
    API --> CM[Cost Management]
    RT --> DB[(PostgreSQL)]
    CM --> DB

    RC[Resource Collector] --> AWS[AWS Services]
    HRC[Human Resource Collector] --> AWS

Technology Stack
Frontend: React, Vite, JavaScript
Backend: Python, FastAPI, Uvicorn
Database: PostgreSQL 16
Infrastructure: Docker and Docker Compose
Cloud: AWS
Security scanning: Trivy
Project Structure
text
aws-finops-dashboard/
├── backend/
│   ├── app/
│   │   ├── cost_management/
│   │   ├── routes/
│   │   ├── main.py
│   │   ├── resource_collector.py
│   │   └── human_resource_collector.py
│   ├── migrations/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
├── docker-compose.yml
├── docker-compose.cost-management.yml
├── docker-compose.resource-collector.yml
├── docker-compose.human-resource.yml
└── README.md

Running the Application

Start the main backend:

bash
docker compose up -d --build


Check running containers:

bash
docker compose ps


View backend logs:

bash
docker compose logs -f backend

Security Scanning

Scan the backend filesystem:

bash
trivy fs --scanners vuln,misconfig,secret backend/


Scan the backend Docker image:

bash
trivy image aws-finops-dashboard-backend

Project Status

Development in progress.
