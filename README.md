# 2D to 3D Floor Plan Render Agent
# Only input and ouput of .png image files.
A functional agentic codebase that automates the conversion of 2D floor plan images into 3D isometric architectural renders using the OpenRouter API.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   - Rename `.env.example` to `.env`.
   - Add your `OPENROUTER_API_KEY`.
   - (Optional) Customize `INPUT_DIR` and `OUTPUT_DIR`.

## Usage

### 1. Directory Watcher (Agent Mode)
The agent will monitor the `INPUT_DIR` for any new images (`.png`, `.jpg`, `.jpeg`) and automatically process them, saving the 3D renders to `OUTPUT_DIR`.

```bash
python agent.py
```

### 2. Direct URL Processing
You can process a single floor plan image from a URL:

```bash
python agent.py --url "https://assets.nobroker.in/media/building/8a9fac83954b73c601954b9f19ea0cc1/floorPlan/0meLpDCXmU1740732442311/0meLpDCXmU1740732442311_floorPlan_GiWJSNakI31740735357167.jpg"
```

## How it Works
- **Model**: Uses `google/gemini-2.0-flash-001` via OpenRouter for high-quality vision-to-image generation.
- **Prompting**: Implements a specific architectural prompt designed for isometric, ceiling-less cutaway views.
- **Automation**: Uses `watchdog` for real-time file system monitoring.
