# Energie Backtest (Fluvius Upload)

## Overview
A Flask-based web application for analyzing energy consumption data from Fluvius exports. Users can upload CSV or XLSX files containing their energy consumption data and receive analysis including total costs, monthly trends, and peak vs off-peak usage breakdown.

## Project Structure
- `app.py` - Main Flask application serving the frontend and API endpoints
- `index.html` - Frontend UI for file upload and dashboard display
- `styles.css` - Styling for the web interface
- `upload_flow.py` - Handles parsing of Fluvius export files
- `energie_backtest/` - Core analysis module:
  - `models.py` - Data models (ConsumptionRecord)
  - `dynamic_tariffs.py` - Dynamic tariff calculations
  - `costs.py` - Cost calculation logic
  - `reporting.py` - Report generation
  - `tariffs.py` - Tariff definitions
  - `aggregates.py` - Aggregation utilities
- `docs/` - Example data files

## Technology Stack
- Python 3.11
- Flask 3.0.0 (web framework)
- openpyxl 3.1.2 (Excel file handling)

## Running the Application
The Flask app runs on port 5000:
```bash
python app.py
```

## API Endpoints
- `GET /` - Serves the main HTML page
- `GET /styles.css` - Serves the CSS file
- `POST /api/upload` - Handles file uploads and returns analysis results

## Recent Changes
- 2026-01-10: Initial setup for Replit environment, configured to run on port 5000
