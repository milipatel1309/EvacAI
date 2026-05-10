# EvacAI 🚨🌍

## Live Demo
🔗 **Cloud Deployment:** https://evac-ai.onrender.com/

---

# EvacAI

EvacAI is an AI-powered disaster preparedness and emergency response platform designed to help users receive real-time weather alerts, disaster intelligence, risk analysis, and AI-generated evacuation/action plans during emergency situations.

The project combines:

- 🌦 Real-time weather monitoring
- 🚨 Emergency alert systems
- 🧠 AI-powered disaster planning
- 📍 Geolocation services
- 📱 Native iOS mobile experience
- ☁️ Cloud-hosted backend infrastructure

The platform was developed as a full-stack AI emergency management solution integrating web technologies, cloud deployment, machine learning risk analysis, and a native iOS frontend.

---

# Project Architecture

```text
EvacAI
│
├── backend/                 → Python FastAPI cloud backend
│   ├── app/
│   │   ├── services/
│   │   ├── templates/
│   │   ├── static/
│   │   ├── demo_data/
│   │   ├── main.py
│   │   └── schemas.py
│   │
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── render.yaml
│   └── README.md
│
└── ios/                     → Native iOS application
    └── EvacAI/
        ├── APIService.swift
        ├── ContentView.swift
        ├── Models.swift
        └── EvacAIApp.swift
```

---

# What EvacAI Does

EvacAI helps users during emergency and disaster situations by combining live environmental intelligence with AI-generated action planning.

The system can:

- Detect weather and disaster alerts
- Analyze geographic risk
- Generate evacuation recommendations
- Provide emergency preparedness guidance
- Deliver real-time weather updates
- Display emergency resources nearby
- Predict disaster severity using ML models
- Generate AI-driven response plans

---

# Core Features

## 🌦 Real-Time Weather Monitoring

The system retrieves live weather information and environmental conditions using integrated APIs and cloud services.

Features include:

- Temperature
- Storm tracking
- Rainfall monitoring
- Wind conditions
- Severe weather analysis
- Regional weather intelligence

---

## 🚨 Emergency Alert Detection

EvacAI integrates emergency alert systems to identify active disaster threats.

Supported disaster types include:

- Floods
- Hurricanes
- Wildfires
- Tornadoes
- Severe storms
- Heat emergencies
- Snow emergencies

The backend processes and structures alerts for both web and mobile interfaces.

---

## 🧠 AI Action Planning

One of the core innovations of EvacAI is its AI-generated emergency response planning system.

Based on:

- User location
- Active alerts
- Weather severity
- Environmental risk
- Resource availability

the platform generates:

- Evacuation guidance
- Safety recommendations
- Emergency preparation plans
- Risk explanations
- Disaster-specific survival instructions

---

## 📍 Geolocation Intelligence

EvacAI supports intelligent geolocation workflows including:

- Address lookup
- Reverse geocoding
- Geographic risk estimation
- Location-based emergency planning
- Nearby resource detection

---

## ☁️ Cloud Deployment

The backend infrastructure is fully cloud deployable using:

- Docker
- Render deployment configuration
- API-based architecture

This allows the platform to scale for real-world deployment scenarios.

---

# Web Platform vs iOS Application

## 🌐 Web Platform

The web platform serves as the main cloud backend and browser-accessible system.

### Responsibilities

- API hosting
- Disaster intelligence processing
- AI action generation
- Weather integrations
- Risk model execution
- Emergency data aggregation

### Technologies Used

- Python
- FastAPI
- HTML/CSS
- JavaScript
- Docker
- Render
- IBM Watsonx integrations
- Mapbox APIs
- Google Maps APIs

---

## 📱 iOS Application

The iOS application provides a native Apple mobile experience for interacting with the EvacAI backend.

### Features

- Native SwiftUI interface
- Real-time alert display
- AI response visualization
- Emergency dashboards
- Mobile-friendly disaster planning
- API integration with cloud backend

### Technologies Used

- Swift
- SwiftUI
- Xcode
- REST API networking

---

# iOS Development with Codex

The EvacAI iOS application was developed using **Codex-assisted development workflows** inside Xcode.

This accelerated:

- SwiftUI interface generation
- API integration
- UI prototyping
- Emergency dashboard implementation
- Mobile architecture structuring

The project combines AI-assisted software engineering with traditional application development practices.

---

# Machine Learning & AI Components

EvacAI includes AI and ML-powered workflows for disaster intelligence.

Current capabilities include:

- Disaster risk estimation
- AI-generated emergency planning
- Alert interpretation
- Environmental severity analysis
- Intelligent preparedness recommendations

---

# Backend Services

The backend includes multiple modular services:

| Service | Purpose |
|---|---|
| weather.py | Weather intelligence |
| nws.py | National Weather Service alerts |
| ml_risk.py | Machine learning risk analysis |
| geocode.py | Address geolocation |
| reverse_geocode.py | Coordinate translation |
| resources.py | Emergency resource management |
| ibm_watsonx.py | AI generation workflows |
| mapbox.py | Mapping integrations |
| google_maps.py | Geospatial services |

---

# Technology Stack

## Backend

- Python
- FastAPI
- Docker
- REST APIs
- IBM Watsonx
- Mapbox
- Google Maps APIs
- Render Cloud Hosting

## Frontend

- HTML
- CSS
- JavaScript

## Mobile

- Swift
- SwiftUI
- Xcode

## AI / ML

- AI-generated disaster planning
- Risk prediction systems
- Intelligent emergency analysis

---

# Deployment

The backend is cloud deployable using Docker and Render.

## Deployment Files

- `Dockerfile`
- `render.yaml`
- `requirements.txt`

---

# Repository Structure

```text
backend/
│
├── app/
│   ├── services/
│   ├── static/
│   ├── templates/
│   ├── demo_data/
│   ├── main.py
│   └── schemas.py
│
├── Dockerfile
├── render.yaml
└── requirements.txt

ios/
│
└── EvacAI/
    ├── APIService.swift
    ├── ContentView.swift
    ├── Models.swift
    └── EvacAIApp.swift
```

---

# Running the Backend Locally

```bash
pip install -r requirements.txt

uvicorn app.main:app --reload
```

---

# Running the iOS App

1. Open `EvacAI.xcodeproj`
2. Launch Xcode
3. Select simulator or iPhone
4. Run the application

---

# Future Improvements

Planned future enhancements include:

- Push notification alerts
- Live GPS evacuation tracking
- AI voice assistant integration
- Offline disaster mode
- Expanded ML prediction models
- Multi-region emergency intelligence
- Apple Watch support

---

# Contributors

- Mili Patel
- OpenAI Codex-assisted development workflows

---

# License

This project is intended for educational, research, and innovation purposes.

---

# Screenshots

_Add application screenshots here_

---

# Acknowledgments

Special thanks to:

- OpenAI
- IBM Watsonx
- Render
- FastAPI
- SwiftUI
- Xcode
- Mapbox
- Google Maps APIs

---

# Contact

For collaborations, improvements, or deployment discussions, feel free to connect through GitHub.
