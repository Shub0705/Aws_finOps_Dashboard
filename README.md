☁️ AWS FinOps Dashboard
Cloud Cost Management | Resource Monitoring | Infrastructure Visibility

A centralized AWS FinOps platform for monitoring cloud infrastructure, tracking resources, and improving cloud cost visibility.

📌 Overview

AWS FinOps Dashboard is a cloud financial management application designed to bring cloud resource monitoring and cost management into one centralized platform.

Key Features
☁️ Cloud Cost Management – Manage and monitor cloud cost information.
📊 Resource Tracking – Track infrastructure resources and usage.
🔍 AWS Resource Collection – Collect AWS infrastructure information.
👥 Human Resource Collection – Dedicated human resource collection service.
🐳 Containerized Architecture – Independent services managed through Docker Compose.
🔐 Security Scanning – Vulnerability and configuration scanning using Trivy.
🏗️ System Architecture

The following diagram represents the high-level application architecture.

mermaid
flowchart TB
    U(["👤 User"])

    subgraph UI["Frontend"]
        FE["React + Vite Dashboard"]
    end

    subgraph APP["Backend Application"]
        API["FastAPI Backend"]
        RT["Resource Tracking"]
        CM["Cost Management"]
    end

    subgraph SERVICES["Background Services"]
        RC["Resource Collector"]
        HRC["Human Resource Collector"]
        MSC["Multiservice Collector"]
    end

    DB[("PostgreSQL 16")]
    AWS["☁️ AWS Cloud"]

    U --> FE
    FE --> API
    API --> RT
    API --> CM
    RT --> DB
    CM --> DB

    RC --> AWS
    HRC --> AWS
    MSC --> AWS

    style FE fill:#2563eb,color:#fff,stroke:#1d4ed8
    style API fill:#15803d,color:#fff,stroke:#166534
    style DB fill:#d97706,color:#fff,stroke:#b45309
    style AWS fill:#ea580c,color:#fff,stroke:#c2410c
    style RC fill:#7c3aed,color:#fff
    style HRC fill:#7c3aed,color:#fff
    style MSC fill:#7c3aed,color:#fff

🔄 Application Workflow
Layer	Component	Description
01	React Frontend	User interface and dashboard
02	FastAPI Backend	API and business logic
03	Resource Tracking	Infrastructure resource tracking
04	Cost Management	Cloud cost management
05	Collectors	Background resource collection
06	PostgreSQL	Persistent data storage
🛠️ Technology Stack
Technology	Purpose
React	Frontend framework
Vite	Frontend build tool
Python	Backend programming
FastAPI	REST API framework
Uvicorn	Application server
PostgreSQL 16	Database
Docker	Containerization
Docker Compose	Service orchestration
AWS	Cloud infrastructure
Trivy	Security scanning
Git & GitHub	Version control
📂 Project Structure
text
aws-finops-dashboard/
│
├── backend/
│   ├── app/
│   │   ├── cost_management/
│   │   ├── routes/
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
Start Backend
bash
docker compose up -d --build

Start Resource Collector
bash
docker compose -f docker-compose.resource-collector.yml up -d --build

Start Human Resource Collector
bash
docker compose -f docker-compose.human-resource.yml up -d --build

Check Running Containers
bash
docker ps

View Application Logs
bash
docker compose logs -f

🔐 Security & Vulnerability Scanning

This project uses Trivy for security analysis.

Scan Project Filesystem
bash
trivy fs --scanners vuln,misconfig,secret .

Scan Backend
bash
trivy fs --scanners vuln,misconfig,secret backend/

Scan Docker Image
bash
trivy image aws-finops-dashboard-backend

Generate Security Report
bash
trivy fs --scanners vuln,misconfig,secret \
  --format json \
  --output trivy-report.json .

🚀 Deployment Information
Service	Container Port	Host Port
Backend API	8000	8002
Resource Test API	8000	8003 (localhost)
PostgreSQL	5432	5433
Resource Collector	8000	Internal
Human Resource Collector	8000	Internal
🔮 Future Enhancements
Advanced cloud cost analytics.
Automated cost optimization recommendations.
Infrastructure monitoring and alerting.
Cloud resource inventory reporting.
Security and compliance dashboards.
CI/CD pipeline integration.
📌 Project Status

Development in Progress

<p align="center">
AWS FinOps Dashboard
</p>

<p align="center">
Cloud Visibility • Cost Optimization • Infrastructure Management
</p>
