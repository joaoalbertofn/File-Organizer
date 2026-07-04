import os
import sys
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

# Third-party libraries (optional imports are wrapped for safety)
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None

try:
    import mutagen
except ImportError:
    mutagen = None

try:
    from pymediainfo import MediaInfo
except ImportError:
    MediaInfo = None

logger = logging.getLogger(__name__)


def _convert_to_degrees(value) -> float:
    """Helper function to convert the GPS coordinates stored in EXIF to float degrees."""
    # EXIF coordinates might be (degrees, minutes, seconds) as rational numbers
    # Pillow 10+ handles this differently than older versions.
    try:
        # If it's a tuple/list of numbers or IFDRational objects
        d = float(value[0])
        m = float(value[1])
        s = float(value[2])
        return d + (m / 60.0) + (s / 3600.0)
    except (TypeError, ZeroDivisionError, IndexError, ValueError):
        try:
            return float(value)
        except Exception:
            return 0.0


def extract_gps_coords(exif_data: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """Extracts latitude and longitude as decimal degrees from EXIF data."""
    if not exif_data:
        return None, None

    gps_info = {}
    # Find the GPS info tag
    for tag, value in exif_data.items():
        decoded = TAGS.get(tag, tag)
        if decoded == "GPSInfo":
            gps_info = value
            break

    if not gps_info:
        return None, None

    # Decode GPS tags
    gps_data = {}
    for t in gps_info:
        sub_tag = GPSTAGS.get(t, t)
        gps_data[sub_tag] = gps_info[t]

    lat = None
    lon = None

    gps_latitude = gps_data.get("GPSLatitude")
    gps_latitude_ref = gps_data.get("GPSLatitudeRef")
    gps_longitude = gps_data.get("GPSLongitude")
    gps_longitude_ref = gps_data.get("GPSLongitudeRef")

    if gps_latitude and gps_latitude_ref:
        lat = _convert_to_degrees(gps_latitude)
        if gps_latitude_ref not in ("N", "n"):
            lat = -lat

    if gps_longitude and gps_longitude_ref:
        lon = _convert_to_degrees(gps_longitude)
        if gps_longitude_ref not in ("E", "e"):
            lon = -lon

    return lat, lon


def get_file_time_fallback(file_path: str) -> datetime:
    """
    Gets the best available OS date/time for a file.
    On macOS, st_birthtime returns the actual creation date.
    """
    stat = os.stat(file_path)
    try:
        # macOS specific creation time attribute
        timestamp = stat.st_birthtime
    except AttributeError:
        # Fallback to modification time on other systems
        timestamp = stat.st_mtime
    
    return datetime.fromtimestamp(timestamp)


def extract_image_metadata(file_path: str) -> Dict[str, Any]:
    """Extracts date/time and GPS coords from an image file."""
    metadata = {
        "date": None,
        "lat": None,
        "lon": None
    }
    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            if exif:
                # Pillow Image.getexif() extracts the main EXIF table
                # For GPS, we need to extract the detailed GPSInfo tag which is often in exif.get_ifd(0x8825)
                # But let's build a lookup from both
                exif_dict = dict(exif)
                for key in [0x8825]: # GPSInfo tag id
                    try:
                        exif_dict[key] = exif.get_ifd(key)
                    except (ValueError, KeyError):
                        pass

                # Extract date
                # EXIF tags: 36697 (DateTimeOriginal), 36868 (DateTimeDigitized), 306 (DateTime)
                date_str = None
                for tag_id in [36867, 36868, 306]: # DateTimeOriginal, DateTimeDigitized, DateTime
                    if tag_id in exif:
                        date_str = exif[tag_id]
                        break

                if date_str:
                    try:
                        # EXIF format is typically "YYYY:MM:DD HH:MM:SS"
                        metadata["date"] = datetime.strptime(str(date_str).strip(), "%Y:%m:%d %H:%M:%S")
                    except ValueError:
                        pass

                # Extract GPS
                lat, lon = extract_gps_coords(exif_dict)
                metadata["lat"] = lat
                metadata["lon"] = lon
    except Exception as e:
        logger.debug(f"Pillow failed to parse EXIF for {file_path}: {e}")

    return metadata


def extract_video_metadata(file_path: str) -> Dict[str, Any]:
    """Extracts metadata from a video file using pymediainfo."""
    metadata = {
        "date": None,
        "lat": None,
        "lon": None
    }
    if MediaInfo is None:
        return metadata

    try:
        media_info = MediaInfo.parse(file_path)
        for track in media_info.tracks:
            if track.track_type == "General":
                # Look for creation dates
                date_keys = ["tagged_date", "encoded_date", "file_last_modification_date"]
                for key in date_keys:
                    val = getattr(track, key, None)
                    if val:
                        # Format is typically "UTC YYYY-MM-DD HH:MM:SS" or similar
                        val_str = str(val).replace("UTC", "").strip()
                        # pymediainfo formats vary, let's try standard parses
                        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Z %Y-%m-%d %H:%M:%S"):
                            try:
                                metadata["date"] = datetime.strptime(val_str, fmt)
                                break
                            except ValueError:
                                continue
                        if metadata["date"]:
                            break
                
                # Check for GPS coordinates embedded in videos (e.g. QuickTime files from iPhones)
                # Quicktime videos store location in format like "+37.7749-122.4194/" or as keys
                location = getattr(track, "xyz", None) or getattr(track, "location", None)
                if location:
                    # e.g., "+37.7749-122.4194/" or "+37.7749-122.4194"
                    import re
                    match = re.match(r"([+-]\d+\.\d+)([+-]\d+\.\d+)", str(location))
                    if match:
                        try:
                            metadata["lat"] = float(match.group(1))
                            metadata["lon"] = float(match.group(2))
                        except ValueError:
                            pass
                break
    except Exception as e:
        logger.debug(f"pymediainfo failed to parse {file_path}: {e}")

    return metadata


def extract_audio_metadata(file_path: str) -> Dict[str, Any]:
    """Extracts date/time metadata from an audio file using mutagen."""
    metadata = {
        "date": None,
        "lat": None,
        "lon": None
    }
    if mutagen is None:
        return metadata

    try:
        audio = mutagen.File(file_path)
        if audio:
            # Look for common tags representing year/date
            # ID3 tags (MP3): TDRC, TDAT, TYER
            # MP4/M4A tags: \xa9day
            # Vorbis/FLAC: date, year
            date_str = None
            if hasattr(audio, "tags") and audio.tags:
                tags = audio.tags
                # Try specific ID3 tags
                for key in ["TDRC", "TYER", "TDAT", "\xa9day", "date", "year"]:
                    if key in tags:
                        val = tags[key]
                        if isinstance(val, list) and len(val) > 0:
                            date_str = str(val[0])
                        else:
                            date_str = str(val)
                        break

            if date_str:
                # Clean up year or full ISO timestamp
                date_str = date_str.strip()
                for fmt in ("%Y-%m-%d", "%Y", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        metadata["date"] = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
    except Exception as e:
        logger.debug(f"mutagen failed to parse {file_path}: {e}")

    return metadata


def get_file_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extracts all metadata (Year, Month, Day, Lat, Lon, Original Name, Ext) from any file.
    Uses specific handlers based on file extension and falls back gracefully.
    """
    filename = os.path.basename(file_path)
    original_name, raw_ext = os.path.splitext(filename)
    ext = raw_ext.lstrip(".").lower()

    # Default metadata structure
    result = {
        "year": "Unknown",
        "month": "Unknown",
        "day": "Unknown",
        "lat": None,
        "lon": None,
        "original_name": original_name,
        "ext": ext
    }

    # Group file extensions
    image_exts = {"jpg", "jpeg", "png", "tiff", "heic", "heif", "gif", "webp"}
    video_exts = {"mp4", "mov", "avi", "mkv", "webm", "m4v"}
    audio_exts = {"mp3", "m4a", "wav", "flac", "ogg", "wma"}

    extracted = {"date": None, "lat": None, "lon": None}

    if ext in image_exts:
        extracted = extract_image_metadata(file_path)
    elif ext in video_exts:
        extracted = extract_video_metadata(file_path)
    elif ext in audio_exts:
        extracted = extract_audio_metadata(file_path)

    # Use OS file stats as ultimate fallback for date
    date_val = extracted.get("date")
    if not date_val:
        date_val = get_file_time_fallback(file_path)

    if date_val:
        result["year"] = f"{date_val.year:04d}"
        result["month"] = f"{date_val.month:02d}"
        result["day"] = f"{date_val.day:02d}"

    result["lat"] = extracted.get("lat")
    result["lon"] = extracted.get("lon")

    return result
