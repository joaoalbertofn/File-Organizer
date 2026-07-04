import os
import shutil
import logging
from typing import Dict, Any, Set, Tuple
from organizer.metadata import get_file_metadata
from organizer.geocoder import CachedGeocoder
from organizer.ai_tagger import AITagger

logger = logging.getLogger(__name__)

# Map variable names to their capitalized fallback label
VARIABLE_FALLBACK_LABELS = {
    "year": "Year",
    "month": "Month",
    "day": "Day",
    "country": "Country",
    "state": "State",
    "city": "City",
    "ai_tag": "AI_Tag",
    "ext": "Ext",
    "original_name": "Original_Name"
}

class FileOrganizer:
    """
    Main orchestrator for scanning, metadata parsing, geocoding, tagging,
    and reorganizing files.
    """
    CUSTOM_CATEGORIES = {"Anotacoes", "Comprovantes", "Instagram", "Screenshots"}

    def __init__(
        self,
        src: str,
        dest: str,
        folder_format: str = "{year}/{month}",
        file_format: str = "{original_name}",
        action: str = "copy",
        ai_rename: bool = False,
        dry_run: bool = False,
        limit: Optional[int] = None
    ):
        self.src = os.path.abspath(src)
        self.dest = os.path.abspath(dest)
        self.folder_format = folder_format
        self.file_format = file_format
        self.action = action.lower()
        self.ai_rename = ai_rename
        self.dry_run = dry_run
        self.limit = limit

        # Initialize helper modules
        self.geocoder = CachedGeocoder()
        self.ai_tagger = AITagger()

        # Track planned destination paths to resolve collisions during dry-run or sequential processing
        self.used_dest_paths: Set[str] = set()

        # Statistics
        self.stats = {
            "scanned": 0,
            "processed": 0,
            "skipped": 0,
            "errors": 0
        }

    def _get_variable_values(self, file_path: str) -> Dict[str, str]:
        """
        Extracts all metadata and geolocates/tags as required by the format templates.
        """
        # Get basic metadata
        meta = get_file_metadata(file_path)

        # Check if geocoding is needed (i.e. templates contain country, state, or city)
        needs_geocoding = any(
            var in self.folder_format or var in self.file_format 
            for var in ("country", "state", "city")
        )

        country = "Unknown"
        state = "Unknown"
        city = "Unknown"

        if needs_geocoding and meta["lat"] is not None and meta["lon"] is not None:
            try:
                geo_info = self.geocoder.reverse_geocode(meta["lat"], meta["lon"])
                country = geo_info.get("country", "Unknown")
                state = geo_info.get("state", "Unknown")
                city = geo_info.get("city", "Unknown")
            except Exception as e:
                logger.error(f"Geocoding failed for {file_path}: {e}")

        # Group files without GPS into custom categories (Screenshots, Comprovantes, WhatsApp, etc.)
        if country == "Unknown" and meta["ext"] not in {"txt", "pdf", "docx"}:
            custom_cat = self.ai_tagger.get_custom_category_for_no_gps(file_path)
            if custom_cat in self.CUSTOM_CATEGORIES:
                country = f"Z - Outros/{custom_cat}"
            else:
                country = "Z - Outros"

        # Check if AI tagging is needed
        ai_tag = "Unknown"
        image_exts = {"jpg", "jpeg", "png", "tiff", "heic", "heif", "gif", "webp"}
        video_exts = {"mp4", "mov", "avi", "mkv", "webm", "m4v"}
        
        if self.ai_rename and (meta["ext"] in image_exts or meta["ext"] in video_exts):
            try:
                ai_tag = self.ai_tagger.tag_file(file_path)
            except Exception as e:
                logger.error(f"AI Tagging failed for {file_path}: {e}")

        # Build replacement variables
        variables = {
            "year": meta["year"],
            "month": meta["month"],
            "day": meta["day"],
            "country": country,
            "state": state,
            "city": city,
            "ai_tag": ai_tag,
            "ext": meta["ext"],
            "original_name": meta["original_name"]
        }

        return variables

    def _format_target(self, variables: Dict[str, str]) -> Tuple[str, str]:
        """
        Formats folder structure and file name templates.
        Replaces missing/Unknown variables with f"Unknown_{VarName}".
        """
        folder_vars = {}
        file_vars = {}

        for var, val in variables.items():
            fallback_label = VARIABLE_FALLBACK_LABELS.get(var, var.capitalize())
            
            if val == "Unknown" or val is None or str(val).strip() == "":
                folder_vars[var] = f"Unknown_{fallback_label}"
                file_vars[var] = f"Unknown_{fallback_label}"
            else:
                folder_vars[var] = val
                file_vars[var] = val

        current_format = self.folder_format
        country_val = folder_vars.get("country", "")
        
        if "{country}" in self.folder_format:
            if country_val == "Z - Outros":
                # Strip year and ai_tag completely, placing files directly in the root of Z - Outros
                current_format = "Z - Outros"
            elif country_val.startswith("Z - Outros/"):
                # Strip ai_tag, keeping country/year (e.g. Z - Outros/Comprovantes/2014)
                if current_format.endswith("/{ai_tag}"):
                    current_format = current_format[:-9]
                elif "/{ai_tag}/" in current_format:
                    current_format = current_format.replace("/{ai_tag}/", "/")

        try:
            folder_path = current_format.format(**folder_vars)
        except KeyError as e:
            logger.error(f"Invalid variable in folder-format: {e}")
            folder_path = "Unknown_Format"

        try:
            # We don't append extension inside the format string unless user did.
            # But standard renaming keeps extension, so we handle it outside or using {ext}
            # Let's see if the file format has '{ext}'. If not, we will append it.
            file_name = self.file_format.format(**file_vars)
            if "{ext}" not in self.file_format:
                file_name = f"{file_name}.{file_vars['ext']}"
        except KeyError as e:
            logger.error(f"Invalid variable in file-format: {e}")
            file_name = f"{variables['original_name']}.{variables['ext']}"

        return folder_path, file_name

    def _resolve_collision(self, folder_path: str, file_name: str) -> str:
        """
        Appends a numeric suffix (e.g. _01, _02) to the filename if a collision
        is detected (either on disk or in the planned executions during dry-run).
        """
        base_dest_dir = os.path.join(self.dest, folder_path)
        name, ext = os.path.splitext(file_name)

        candidate_path = os.path.join(base_dest_dir, file_name)
        
        # If candidate path is not already in use (on disk or planned), return it
        if candidate_path not in self.used_dest_paths and not os.path.exists(candidate_path):
            self.used_dest_paths.add(candidate_path)
            return candidate_path

        # Resolve collision
        suffix_counter = 1
        while True:
            suffix = f"_{suffix_counter:02d}"
            new_file_name = f"{name}{suffix}{ext}"
            candidate_path = os.path.join(base_dest_dir, new_file_name)
            
            if candidate_path not in self.used_dest_paths and not os.path.exists(candidate_path):
                self.used_dest_paths.add(candidate_path)
                return candidate_path
            
            suffix_counter += 1

    def process_file(self, file_path: str):
        """Processes a single file: extracts tags, formats destination, copies/moves."""
        try:
            self.stats["scanned"] += 1
            logger.debug(f"Processing: {file_path}")

            # Get variables
            vars_dict = self._get_variable_values(file_path)

            # Format destination target names
            subfolder, new_filename = self._format_target(vars_dict)

            # Resolve collisions (intelligent suffixes)
            final_dest_path = self._resolve_collision(subfolder, new_filename)
            dest_dir = os.path.dirname(final_dest_path)

            # Log action details
            action_pt = "Copiando" if self.action == "copy" else "Movendo"
            mode_prefix = "[Simulação] " if self.dry_run else ""
            
            filename = os.path.basename(file_path)
            dest_group = vars_dict.get("country", "Unknown")
            year_val = vars_dict.get("year", "Unknown")
            tag_val = vars_dict.get("ai_tag", "Unknown")
            
            if dest_group in {"Comprovantes", "Screenshots", "WhatsApp", "Instagram", "Mapas", "Anotacoes"}:
                dest_desc = f"o grupo '{dest_group}'"
            else:
                dest_desc = f"'{dest_group}'"
                
            human_log = f"{mode_prefix}{action_pt} '{filename}' para {dest_desc} (Ano: {year_val}, Descrição: {tag_val})"
            
            # Print with ANSI escape code to clear the carriage-return progress bar line
            import sys
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            print(human_log)

            if self.dry_run:
                self.stats["processed"] += 1
                return

            # Real execution
            os.makedirs(dest_dir, exist_ok=True)

            if self.action == "move":
                shutil.move(file_path, final_dest_path)
            else:
                shutil.copy2(file_path, final_dest_path)

            self.stats["processed"] += 1

        except Exception as e:
            import sys
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()
            logger.error(f"Erro ao processar o arquivo '{file_path}': {e}", exc_info=True)
            self.stats["errors"] += 1

    def _print_progress_bar(self, current: int, total: int):
        """Prints a clean updating progress bar in the terminal."""
        if total == 0:
            return
        percent = float(current) / total
        bar_length = 30
        arrow = '█' * int(percent * bar_length)
        spaces = '░' * (bar_length - len(arrow))
        
        import sys
        sys.stdout.write(f"\rProgresso: [{arrow}{spaces}] {current}/{total} ({percent*100:.1f}%)")
        sys.stdout.flush()
        if current == total:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def run(self):
        """Walks the source directory and processes all files."""
        if not os.path.exists(self.src):
            logger.error(f"A pasta de origem não existe: {self.src}")
            return self.stats

        # Count and gather all eligible files first
        eligible_files = []
        for root, dirs, files in os.walk(self.src):
            abs_root = os.path.abspath(root)
            if abs_root == self.dest or abs_root.startswith(self.dest + os.sep):
                dirs.clear()
                continue
            for file in files:
                if not file.startswith("."):
                    eligible_files.append(os.path.join(root, file))

        total_files = len(eligible_files)
        if self.limit is not None:
            eligible_files = eligible_files[:self.limit]
            total_files = len(eligible_files)

        print(f"Iniciando a organização. Encontrados {total_files} arquivos para processar.")
        if self.dry_run:
            print("Executando em MODO SIMULAÇÃO (Dry-Run). Nenhum arquivo será alterado.")

        for idx, full_path in enumerate(eligible_files, 1):
            self.process_file(full_path)
            self._print_progress_bar(idx, total_files)

        # Print final report
        print("\n=== Organização Concluída ===")
        print(f"Arquivos analisados: {self.stats['scanned']}")
        print(f"Processados com sucesso: {self.stats['processed']}")
        print(f"Arquivos ignorados: {self.stats['skipped']}")
        print(f"Erros encontrados: {self.stats['errors']}")

        return self.stats
