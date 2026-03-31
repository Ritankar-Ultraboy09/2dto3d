import os
import base64
import requests
import json
import time
import logging
import argparse
import csv
from pathlib import Path
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("agent.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", r"C:\Users\KIIT\Desktop\Nobroker\2dto3d\output"))
INPUT_DIR = Path(os.getenv("INPUT_DIR", r"C:\Users\KIIT\Desktop\Nobroker\2dto3d\input"))
TRACKER_FILE = Path("processed_files.json")

MODEL = "google/gemini-2.5-flash-image" 
PROMPT = (
    "Convert this 2D floor plan into a photorealistic 3D isometric architectural visualization "
    "that matches professional real-estate rendering quality. "

    # Camera & Perspective
    "CAMERA: True isometric view at 40-45 degree elevated angle from top-right perspective. "
    "3/4 cutaway view with NO ceiling — all rooms fully visible from above. "
    "Walls rendered at exactly 9-10 ft height, clean flat tops with uniform thickness. "
    "FORBIDDEN: top-down orthographic view, fisheye lens, perspective distortion, ceiling. "

    # Layout Fidelity
    "LAYOUT: Replicate the 2D floor plan with exact room shapes, sizes, and spatial relationships. "
    "Preserve all wall positions, door openings, window placements, and room connectivity. "
    "Clean right-angle geometry only. Do not rotate, mirror, or reinterpret the layout. "
    "Remove all text, labels, dimensions, and annotations from the final render. "

    # Materials & Finishes
    "FLOORS: Uniform light beige/cream large-format ceramic tiles across all rooms. "
    "WALLS: Smooth matte off-white/warm white plaster finish, flat wall tops. "
    "Overall palette: warm neutral tones — ivory, cream, light greige, natural oak wood. "

    # Furniture & Fixtures (matching the reference style)
    "FURNITURE: Minimal Scandinavian-modern style. Low-profile furniture in light grey fabric and natural oak wood. "
    "Master bedroom: king bed with grey linen, wooden headboard, two oak nightstands, wall art, table lamp. "
    "Secondary bedrooms: queen beds with matching neutral bedding and oak side tables. "
    "Living room: L-shaped or 3-seater light grey sofa, rectangular wooden coffee table, neutral area rug, "
    "flat TV on a low wooden media unit. "
    "Dining area: small white dining table with 2-4 simple grey chairs, potted plant centerpiece. "
    "Kitchen: white modular cabinets with integrated appliances, sink visible, clean countertop. "
    "Bathrooms: white toilet, wall-mounted basin or vanity, glass shower enclosure where applicable. "
    "All furniture must be correctly scaled to room size. No oversized or undersized pieces. "

    # Lighting
    "LIGHTING: Soft uniform global illumination simulating bright overcast daylight. "
    "Gentle ambient occlusion at wall-floor junctions and furniture bases for subtle depth. "
    "No harsh shadows, no spotlights, no colored lighting — clean and evenly lit throughout. "

    # Render Quality & Output
    "RENDER: Ultra-sharp 4K photorealistic architectural visualization. "
    "Pure white background with slight drop shadow under the floor plate for lift. "
    "Professional real-estate marketing render — clean, minimal, no decorative overlays, "
    "no watermarks, no annotations, single image output only."
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

def main():
    parser = argparse.ArgumentParser(description="Floor Plan Render Agent")
    parser.add_argument("--url", help="Process a floor plan from a URL")
    parser.add_argument("--rows", type=int, help="Number of rows to process from CSV")
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
    logger.info(f"Output Directory: {OUTPUT_DIR}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open('floorplan.csv', 'r', newline='') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)
        row_count = 0
        for row in reader:
            if args.rows is not None and row_count >= args.rows:
                break
            urls = [cell for cell in row if cell.startswith('http')]
            for url in urls:
                manager.process_url(url)
            row_count += 1

if __name__ == "__main__":
    main()
