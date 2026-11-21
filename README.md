☁️ AWS FinOps Dashboard

<p align="center">
<strong>Cloud Cost Management • Resource Monitoring • Infrastructure Visibility</strong>
</p>

<p align="center">
A centralized AWS FinOps platform designed to monitor cloud resources, track infrastructure usage, and improve cloud cost visibility.
</p>

📌 Overview

The AWS FinOps Dashboard is a cloud financial management application that brings infrastructure monitoring and cost visibility into one centralized platform.

The application combines a React frontend, FastAPI backend, PostgreSQL database, and independent Dockerized collectors to support cloud resource tracking and cost management.

Key Capabilities
Cloud Cost Management – Organize and manage cloud cost information.
Resource Tracking – Monitor infrastructure resources and their usage.
Resource Collection – Collect AWS resource information through dedicated services.
Human Resource Collection – Run a separate collector for human-resource-related data.
Centralized Dashboard – Access application functionality through a React interface.
Containerized Deployment – Run backend services using Docker Compose.
🏗️ System Architecture

The following diagram illustrates the application's high-level architecture.

mermaid
flowchart TB
    USER(["👤 User"])

    subgraph FRONTEND["Frontend Layer"]
        REACT["React + Vite Dashboard"]
    end

    subgraph BACKEND["Application Layer"]
        API["FastAPI Backend"]
        RESOURCE["Resource Tracking Router"]
        COST["Cost Management Module"]
    end

    subgraph COLLECTORS["Collection Services"]
        RC["AWS Resource Collector"]
        HRC["Human Resource Collector"]
        MRC["Multiservice Collector"]
    end

    subgraph DATABASE["Data Layer"]
        DB[("PostgreSQL 16")]
    end

    AWS["☁️ AWS Cloud Services"]

    USER --> REACT
    REACT --> API

    API --> RESOURCE
    API --> COST

    RESOURCE --> DB
    COST --> DB

    RC --> AWS
    HRC --> AWS
    MRC --> AWS

    RC -.-> DB
    HRC -.-> DB
    MRC -.-> DB

    classDef frontend fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef backend fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef database fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef collector fill:#f3e8ff,stroke:#9333ea,color:#581c87

    class REACT frontend
    class API,RESOURCE,COST backend
    class DB database
    class RC,HRC,MRC collector


Note: This is a conceptual architecture. Actual collector-to-database connections and data flows should be confirmed against the implementation.

🔄 Application Workflow
Step	Component	Responsibility
01	React Frontend	User interaction and dashboard interface
02	FastAPI Backend	API requests and application logic
03	Resource Tracking	Resource tracking operations
04	Cost Management	Cloud cost-related operations
05	Resource Collectors	AWS resource data collection
06	PostgreSQL	Persistent application data storage
🛠️ Technology Stack
Layer	Technology
Frontend	React, Vite, JavaScript
Backend	Python, FastAPI
API Server	Uvicorn
Database	PostgreSQL 16
Containerization	Docker
Orchestration	Docker Compose
Cloud Platform	Amazon Web Services
Security Scanner	Trivy
Version Control	Git & GitHub
📂 Project Structure
text
aws-finops-dashboard/
│
├── backend/
│   ├── app/
│   │   ├── cost_management/
│   │   │   ├── database.py
│   │   │   ├── models.py
│   │   │   ├── pricing_importer.py
│   │   │   └── router.py
│   │   │
│   │   ├── routes/
│   │   │   └── resource_tracking.py
│   │   │
│   │   ├── main.py
│   │   ├── resource_collector.py
│   │   ├── human_resource_collector.py
│   │   └── multiservice_collector.py
│   │
│   ├── migrations/
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── services/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
│
├── docker-compose.yml
├── docker-compose.cost-management.yml
├── docker-compose.resource-collector.yml
├── docker-compose.human-resource.yml
├── docker-compose.multiservice.yml
├── docker-compose.resource-test.yml
│
└── README.md

🐳 Docker Deployment

The application uses multiple Docker Compose configurations to manage individual services.

Start the main backend
bash
docker compose up -d --build

Start individual services
bash
docker compose -f docker-compose.resource-collector.yml up -d --build

docker compose -f docker-compose.human-resource.yml up -d --build

docker compose -f docker-compose.multiservice.yml up -d --build

docker compose -f docker-compose.cost-management.yml up -d

Monitor running containers
bash
docker ps

Check service status
bash
docker compose ps

View application logs
bash
docker compose logs -f

🔐 Security & Vulnerability Scanning

The project uses Trivy to identify vulnerabilities and security configuration issues.

Filesystem Security Scan
bash
trivy fs --scanners vuln,misconfig,secret .

Backend Security Scan
bash
trivy fs --scanners vuln,misconfig,secret backend/

Docker Image Scan
bash
trivy image aws-finops-dashboard-backend

Generate JSON Security Report
bash
trivy fs --scanners vuln,misconfig,secret \
  --format json \
  --output trivy-report.json .

🚀 Current Deployment

The following services have been observed running in the Docker environment:

Container	Service	Port
finops-backend	Backend API	8002
finops-backend-resource-test	Resource Test API	8003 (localhost only)
cloudpilot-cost-db	PostgreSQL	5433
cloudpilot-resource-collector	Resource Collector	Internal 8000
cloudpilot-human-resource-collector	Human Resource Collector	Internal 8000

Container status and port mappings should be refreshed after deployment changes.

📈 Project Goals
Improve AWS cloud cost visibility.
Centralize infrastructure resource information.
Support modular cloud data collection.
Simplify cloud resource monitoring.
Improve application security and deployment practices.
🔮 Future Enhancements
Advanced cloud cost analytics.
Automated cost optimization recommendations.
Cloud resource inventory reporting.
Security and compliance dashboards.
Infrastructure monitoring and alerting.
CI/CD integration with automated security scanning.
👨‍💻 Development

This project is actively being developed.

Repository: AWS FinOps Dashboard

Status: Development in Progress

<p align="center">
<strong>Built to improve cloud visibility, cost awareness, and infrastructure management.</strong>
</p>
