# TraceWise PCB Validator

TraceWise is a PCB design validation platform for early-stage review of KiCad board files. It combines exact rule-based checking, reference-board comparison, optional AI-assisted guidance, and a React frontend that now owns the full product workflow.

## What It Does

- Validates real `.kicad_pcb` and `.dxf` files
- Checks board size, drill count, hole diameter, trace width, spacing, and routing health
- Compares a candidate board against an approved reference PCB
- Generates severity-based validation results and a compact PDF report
- Supports optional AI guidance for plain-English explanation and fix suggestions

## Core Features

- React frontend for the full validation flow
- FastAPI backend for upload, validation, reporting, and AI orchestration
- Rule-based PCB validation
- Reference comparison against an approved board
- PDF validation report generation

## Demo Boards Included

- `demo_boards/triac_reference.kicad_pcb` - approved reference board
- `demo_boards/triac_changed_example.kicad_pcb` - changed candidate board for demo validation

## Tech Stack

- React
- Plain CSS
- FastAPI
- Python
- KiCad `.kicad_pcb` parsing
- Custom rule engine
- Gemini / OpenAI API integration
- ReportLab for PDF reports

## Run Locally

Install backend dependencies:

```powershell
pip install -r requirements.txt
```

Install frontend dependencies:

```powershell
cd frontend
npm install
```

Start the backend API:

```powershell
python apps.py
```

Start the React frontend in a second terminal:

```powershell
cd frontend
npm run dev
```

Open the frontend at `http://127.0.0.1:5173`.

## AI Setup

Set either one of these environment variables:

- `GEMINI_API_KEY`
- `OPENAI_API_KEY`

The core rule-based validator still works without an AI key.

## Repository Structure

```text
tracewise-pcb-validator/
|-- api_server.py
|-- apps.py
|-- validation_service.py
|-- cad_rules.py
|-- kicad_parser.py
|-- cad_parser.py
|-- pcb_report_generator.py
|-- llm_assistant.py
|-- demo_boards/
|-- assets/
`-- frontend/
```

## Status

This is now an API-backed React product prototype for AI-assisted PCB design validation and review.
