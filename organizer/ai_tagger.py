import os
import logging
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)

# Try importing the google-genai library
try:
    from google import genai
    from google.genai.errors import APIError
except ImportError:
    genai = None
    APIError = Exception


# Mapping for macOS Vision tags to Portuguese description keywords
VISION_TAGS_MAP = {
    "sunset": "por_do_sol",
    "sunrise": "por_do_sol",
    "ocean": "praia_ou_mar",
    "sea": "praia_ou_mar",
    "beach": "praia_ou_mar",
    "water": "praia_ou_mar",
    "mountain": "natureza_ou_paisagem",
    "forest": "natureza_ou_paisagem",
    "tree": "natureza_ou_paisagem",
    "vegetation": "natureza_ou_paisagem",
    "scenery": "natureza_ou_paisagem",
    "nature": "natureza_ou_paisagem",
    "document": "documento",
    "printed_page": "documento",
    "handwriting": "anotacao",
    "screenshot": "screenshot",
    "food": "comida",
    "drink": "comida",
    "person": "retrato",
    "face": "retrato",
    "people": "grupo",
    "dog": "animal",
    "cat": "animal",
    "animal": "animal",
    "building": "monumento_ou_cidade",
    "tower": "monumento_ou_cidade",
    "skyscraper": "monumento_ou_cidade",
    "city": "monumento_ou_cidade",
    "map": "mapa"
}


# Load credentials from local file if it exists (ignored by Git for security)
DEFAULT_API_KEY = ""
DEFAULT_PROJECT_NAME = "Unknown"
DEFAULT_PROJECT_PATH = ""
DEFAULT_PROJECT_NUMBER = ""

cred_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "organizer_credentials.json")
if os.path.exists(cred_path):
    try:
        import json
        with open(cred_path, 'r') as f:
            creds = json.load(f)
            DEFAULT_API_KEY = creds.get("gemini_api_key", "")
            DEFAULT_PROJECT_NAME = creds.get("project_name", "Unknown")
            DEFAULT_PROJECT_PATH = creds.get("project_path", "")
            DEFAULT_PROJECT_NUMBER = creds.get("project_number", "")
    except Exception:
        pass


class AITagger:
    """
    Tags images using computer vision.
    Attempts to use the Google Gemini API first if GEMINI_API_KEY is defined
    or falls back to the embedded credentials.
    If the API is unavailable, falls back to a rule-based
    heuristic image analyzer (aspect ratio, dominant colors, filename context).
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY") or DEFAULT_API_KEY
        self.project_name = DEFAULT_PROJECT_NAME
        self.project_path = DEFAULT_PROJECT_PATH
        self.project_number = DEFAULT_PROJECT_NUMBER
        self.client = None
        self.gemini_disabled = False

        # Cache path and existence of the native macOS Vision binary
        self.mac_tagger_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mac_tagger")
        self.mac_tagger_exists = os.path.exists(self.mac_tagger_path)

        if self.api_key and genai is not None:
            try:
                # Initialize Google GenAI client
                # Note: passing api_key explicitly or it defaults to GEMINI_API_KEY env var
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"AI Tagger initialized successfully with Gemini API (Project: {self.project_name}).")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini API client: {e}. Falling back to heuristics.")
        else:
            if not self.api_key:
                logger.debug("GEMINI_API_KEY environment variable and default key are not set.")
            if genai is None:
                logger.debug("google-genai package is not installed.")
            logger.info("AI Tagger initialized using local heuristic rules (Gemini API disabled).")

    def analyze_mac_vision(self, file_path: str) -> Dict[str, list]:
        """
        Runs the native compiled macOS mac_tagger binary to get tags and OCR text.
        """
        import subprocess
        import json
        
        if not self.mac_tagger_exists:
            return {"tags": [], "text": []}
            
        try:
            result = subprocess.run(
                [self.mac_tagger_path, file_path],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception as e:
            logger.debug(f"Failed to run mac_tagger on {file_path}: {e}")
            
        return {"tags": [], "text": []}

    def get_custom_category_for_no_gps(self, file_path: str) -> Optional[str]:
        """
        Categorizes files without GPS based on filename and Vision classification/OCR text.
        """
        filename_lower = os.path.basename(file_path).lower()
        
        # 1. Quick filename checks (very fast, no vision API needed)
        if "whatsapp" in filename_lower or "-wa" in filename_lower or "wa-" in filename_lower or "wa00" in filename_lower:
            return "WhatsApp"
        if "instagram" in filename_lower or "insta" in filename_lower or "picsart" in filename_lower:
            return "Instagram"
        if "screenshot" in filename_lower or "print" in filename_lower or "captura" in filename_lower:
            return "Screenshots"
        if "comprovante" in filename_lower or "recibo" in filename_lower or "compro" in filename_lower:
            return "Comprovantes"
        if "mapa" in filename_lower or "map" in filename_lower:
            return "Mapas"
        if "anotacao" in filename_lower or "documento" in filename_lower or "doc" in filename_lower:
            return "Anotacoes"

        # 2. Vision & OCR analysis
        analysis = self.analyze_mac_vision(file_path)
        tags = [t.lower() for t in analysis.get("tags", [])]
        ocr_text = [t.lower() for t in analysis.get("text", [])]
        
        # Check Comprovantes (OCR is highly accurate here)
        comprovante_keywords = {"comprovante", "pagamento", "recibo", "transferência", "pix", "boleto", "valor", "cnpj", "nota fiscal", "extrato"}
        for line in ocr_text:
            if any(kw in line for kw in comprovante_keywords):
                return "Comprovantes"
                
        # Check Screenshots
        if "screenshot" in tags:
            return "Screenshots"
            
        # Check Instagram
        for line in ocr_text:
            if "instagram" in line:
                return "Instagram"
                
        # Check Mapas
        if any(t in tags for t in ("map", "map_or_chart")):
            return "Mapas"
            
        # Check Anotacoes
        if any(t in tags for t in ("document", "printed_page", "handwriting")):
            return "Anotacoes"
            
        return None

    def _get_heuristic_tag(self, image_path: str) -> str:
        """
        Fallback rule-based heuristic tagger when API is unavailable.
        Analyzes image/video dimensions, aspect ratio, dominant colors, and filename.
        """
        filename_lower = os.path.basename(image_path).lower()
        _, raw_ext = os.path.splitext(filename_lower)
        ext = raw_ext.lstrip(".").lower()
        video_exts = {"mp4", "mov", "avi", "mkv", "webm", "m4v"}
        
        # 1. Filename heuristics
        if "screenshot" in filename_lower or "print" in filename_lower or "captura" in filename_lower:
            return "screenshot"
        if "whatsapp" in filename_lower or "wa" in filename_lower:
            return "social"
        if "selfie" in filename_lower:
            return "selfie"
        if "scan" in filename_lower or "doc" in filename_lower or "pdf" in filename_lower:
            return "documento"

        # If it's a video, don't try to open with PIL
        if ext in video_exts:
            if "trip" in filename_lower or "viagem" in filename_lower or "vacation" in filename_lower:
                return "viagem"
            return "video"

        # 2. Check dimensions/aspect ratio first (e.g. panorama, vertical)
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                aspect_ratio = width / height
                if aspect_ratio >= 2.0:
                    return "panorama"
                if aspect_ratio <= 0.5:
                    return "vertical"
        except Exception as e:
            logger.debug(f"Failed to open image for aspect ratio check {image_path}: {e}")

        # 3. Try macOS native Vision classification (highly accurate local tagging)
        analysis = self.analyze_mac_vision(image_path)
        vision_tags = [t.lower() for t in analysis.get("tags", [])]
        for tag in vision_tags:
            if tag in VISION_TAGS_MAP:
                return VISION_TAGS_MAP[tag]

        # 4. Fallback to basic color heuristics
        try:
            with Image.open(image_path) as img:

                # Check dominant color (resize to 1x1 to get average color)
                # This is a very fast estimation of dominant color
                small_img = img.resize((1, 1), Image.Resampling.NEAREST)
                pixel = small_img.getpixel((0, 0))
                
                # Handle different mode pixels (RGB, RGBA, L, etc.)
                if isinstance(pixel, tuple):
                    r = pixel[0]
                    g = pixel[1]
                    b = pixel[2]
                else:
                    # Greyscale
                    r = g = b = pixel

                # Heuristic rules based on average RGB:
                # High brightness and low color variance -> likely a document/text
                if r > 220 and g > 220 and b > 220:
                    return "documento"
                # Dark image -> night / low light
                if r < 40 and g < 40 and b < 40:
                    return "noturno"
                # Dominant blue -> sky / ocean
                if b > r * 1.2 and b > g * 1.2:
                    return "mar_ou_ceu"
                # Dominant green -> vegetation / landscape
                if g > r * 1.1 and g > b * 1.1:
                    return "natureza"
                # Dominant red/orange -> warm / indoor / sunset
                if r > g * 1.3 and r > b * 1.3:
                    return "quente"

                # Generic categories based on aspect ratio
                if aspect_ratio > 1.2:
                    return "paisagem"
                else:
                    return "retrato"

        except Exception as e:
            logger.debug(f"Heuristic image analysis failed for {image_path}: {e}")
            
        return "imagem"

    def tag_file(self, file_path: str) -> str:
        """
        Analyzes the image or video and returns 1 or 2 lowercase keywords, sanitized.
        """
        # Verify file exists
        if not os.path.exists(file_path):
            return "desconhecido"

        filename = os.path.basename(file_path)
        _, raw_ext = os.path.splitext(filename)
        ext = raw_ext.lstrip(".").lower()

        image_exts = {"jpg", "jpeg", "png", "tiff", "heic", "heif", "gif", "webp"}
        video_exts = {"mp4", "mov", "avi", "mkv", "webm", "m4v"}

        # Use Gemini API if configured
        if self.client and not self.gemini_disabled:
            try:
                logger.debug(f"Querying Gemini API to tag file: {file_path}")
                prompt = (
                    "Retorne apenas uma ou duas palavras-chave descritivas e gerais em português para este arquivo de mídia "
                    "(ex: 'praia', 'selfie', 'show', 'paisagem', 'documento', 'comida', 'retrato', 'festa', 'viagem'). "
                    "Não use pontuação, artigos ou explicações, apenas as palavras-chave minúsculas separadas por vírgula ou espaço. "
                    "Seja breve."
                )
                
                if ext in image_exts:
                    with Image.open(file_path) as img:
                        response = self.client.models.generate_content(
                            model="gemini-2.5-flash",
                            contents=[img, prompt]
                        )
                elif ext in video_exts:
                    # Limit to 40MB to avoid long upload times
                    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    if file_size_mb <= 40.0:
                        logger.info(f"Uploading video file to Gemini API for tagging: {filename} ({file_size_mb:.2f} MB)")
                        uploaded_file = self.client.files.upload(file=file_path)
                        try:
                            response = self.client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=[uploaded_file, prompt]
                            )
                        finally:
                            # Cleanup uploaded file from Gemini storage
                            try:
                                self.client.files.delete(name=uploaded_file.name)
                            except Exception as cleanup_err:
                                logger.warning(f"Failed to delete remote file {uploaded_file.name} from Gemini API storage: {cleanup_err}")
                    else:
                        logger.warning(f"Video file too large ({file_size_mb:.2f} MB) for API tagging. Using filename heuristics.")
                        return self._get_heuristic_tag(file_path)
                else:
                    return "documento"

                # Sanitize the output (lowercase, strip, replace spaces/slashes)
                raw_tags = response.text.strip().lower()
                
                # Clean tags (keep only alphanumeric and simple separator)
                clean_tags = "".join(
                    c if c.isalnum() or c in (",", " ", "-", "_") else ""
                    for c in raw_tags
                )
                
                # Take the first 1-2 words/tags
                tags_list = [t.strip() for t in clean_tags.replace(",", " ").split() if t.strip()]
                if tags_list:
                    # Join with underscore, limiting to max 2 words
                    selected_tag = "_".join(tags_list[:2])
                    logger.info(f"Gemini tagged {filename} as: '{selected_tag}'")
                    return selected_tag
                    
            except APIError as e:
                err_msg = str(e).upper()
                # Check for rate-limiting (429/RESOURCE_EXHAUSTED) or auth issues (403/PERMISSION_DENIED)
                if any(kw in err_msg for kw in ("RESOURCE_EXHAUSTED", "PERMISSION_DENIED", "429", "403", "SERVICE_DISABLED", "API_KEY_INVALID")):
                    logger.warning(f"Gemini API quota or permission error ({e}). Disabling Gemini requests for the remainder of this run.")
                    self.gemini_disabled = True
                logger.warning(f"Gemini API error for {filename}: {e}. Falling back to local tagger.")
            except Exception as e:
                logger.warning(f"Error calling Gemini API for {filename}: {e}. Falling back to local tagger.")

        # Fallback to local heuristic rules
        heuristic_tag = self._get_heuristic_tag(file_path)
        logger.debug(f"Heuristic tagged {filename} as: '{heuristic_tag}'")
        return heuristic_tag

    def tag_image(self, image_path: str) -> str:
        """Deprecated: Use tag_file instead."""
        return self.tag_file(image_path)

