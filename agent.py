import os
import base64
import requests
import json
import time
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", r"C:\Users\RITANKAR\Desktop\NoBroker\floorplan\output"))
INPUT_DIR = Path(os.getenv("INPUT_DIR", r"C:\Users\RITANKAR\Desktop\NoBroker\floorplan\input"))
TRACKER_FILE = Path("processed_files.json")

# Model configuration from n8n JSON
MODEL = "google/gemini-2.5-flash-image-preview" 
PROMPT = (
    "Convert this 2D floor plan into a clean 3D isometric architectural render. "
    "Requirements: Isometric view at 30-35 degree angle, show all walls with 9-10 ft height, "
    "maintain exact room layout and proportions, remove all text labels from the image, "
    "modern realistic furniture matching room types, soft lighting with ambient occlusion, "
    "light beige tiled flooring, neutral colours, clean white background, professional "
    "architectural visualization style, floating cutaway view with no ceiling, 4K quality render. "
    "DO NOT use top-down view, orthographic projection, wide-angle lens, or distort the original layout proportions."
)

class ProcessTracker:
    def __init__(self, tracker_file):
        self.tracker_file = tracker_file
        self.processed = self._load()

    def _load(self):
        if self.tracker_file.exists():
            with open(self.tracker_file, "r") as f:
                return json.load(f)
        return {}

    def is_processed(self, file_path):
        return str(file_path) in self.processed

    def mark_processed(self, file_path):
        self.processed[str(file_path)] = time.time()
        with open(self.tracker_file, "w") as f:
            json.dump(self.processed, f)

class OpenRouterClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def process_image(self, base64_image):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://github.com/yourusername/floorplan-generator",
            "X-Title": "Floor Plan Converter",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            }
                        },
                        {
                            "type": "text",
                            "text": PROMPT
                        }
                    ]
                }
            ],
            "temperature": 0.3,
            "top_p": 0.85,
            "max_tokens": 4096
        }

        response = requests.post(self.url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

class ImageProcessor:
    @staticmethod
    def encode_image(image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    @staticmethod
    def download_image(url, output_path):
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(output_path, 'wb') as out_file:
            for chunk in response.iter_content(chunk_size=8192):
                out_file.write(chunk)

class WorkflowManager:
    def __init__(self, client, tracker):
        self.client = client
        self.processor = ImageProcessor()
        self.tracker = tracker

    def process_local_file(self, file_path):
        if self.tracker.is_processed(file_path):
            logger.info(f"Skipping already processed file: {file_path}")
            return

        logger.info(f"Processing local file: {file_path}")
        try:
            base64_img = self.processor.encode_image(file_path)
            result = self.client.process_image(base64_img)
            
            choices = result.get('choices', [])
            if not choices:
                logger.error(f"No choices in API response: {result}")
                return

            message = choices[0].get('message', {})
            image_url = None
            if 'images' in message and message['images']:
                image_url = message['images'][0].get('image_url', {}).get('url')
            
            if not image_url and 'content' in message:
                content = message['content'].strip()
                if content.startswith('http'):
                    image_url = content

            if not image_url:
                logger.error(f"Could not extract image URL from response: {result}")
                return

            output_path = OUTPUT_DIR / (file_path.stem + "_3D.png")
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            if image_url.startswith('data:image'):
                header, encoded = image_url.split(",", 1)
                data = base64.b64decode(encoded)
                with open(output_path, "wb") as f:
                    f.write(data)
            else:
                self.processor.download_image(image_url, output_path)

            logger.info(f"Successfully saved 3D render to: {output_path}")
            self.tracker.mark_processed(file_path)

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")

    def process_url(self, url):
        logger.info(f"Processing URL: {url}")
        try:
            filename = url.split('/')[-1] or "temp_floorplan.jpg"
            temp_path = INPUT_DIR / filename
            INPUT_DIR.mkdir(parents=True, exist_ok=True)
            self.processor.download_image(url, temp_path)
            self.process_local_file(temp_path)
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")

class NewFileHandler(FileSystemEventHandler):
    def __init__(self, manager):
        self.manager = manager

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            time.sleep(2)  
            self.manager.process_local_file(Path(event.src_path))

def main():
    parser = argparse.ArgumentParser(description="Floor Plan Render Agent")
    parser.add_argument("--url", help="Process a floor plan from a URL")
    args = parser.parse_args()

    if not OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY not found in environment.")
        return

    tracker = ProcessTracker(TRACKER_FILE)
    client = OpenRouterClient(OPENROUTER_API_KEY)
    manager = WorkflowManager(client, tracker)

    if args.url:
        manager.process_url(args.url)
        return

    logger.info("Starting Floor Plan Render Agent...")
    logger.info(f"Monitoring Input: {INPUT_DIR}")
    logger.info(f"Output Directory: {OUTPUT_DIR}")

    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    event_handler = NewFileHandler(manager)
    observer = Observer()
    observer.schedule(event_handler, str(INPUT_DIR), recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
