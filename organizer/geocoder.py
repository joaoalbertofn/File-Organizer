import logging
import os
import sqlite3
import time
from typing import Dict, Optional, Tuple
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

logger = logging.getLogger(__name__)

class CachedGeocoder:
    """
    Handles reverse geocoding of GPS coordinates (latitude and longitude)
    to administrative levels (country, state, city) using geopy and SQLite caching.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Store in home folder to share cache across runs
            home_dir = os.path.expanduser("~")
            app_dir = os.path.join(home_dir, ".file_organizer")
            os.makedirs(app_dir, exist_ok=True)
            self.db_path = os.path.join(app_dir, "geocoding_cache.db")
        else:
            self.db_path = db_path

        self._init_db()
        # Initialize geolocator with a custom user agent as requested by OSM terms of service
        self.geolocator = Nominatim(user_agent="file_organizer_mac_cli/1.0")

    def _init_db(self):
        """Initializes the SQLite database and table for caching."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS geocache (
                        lat REAL,
                        lon REAL,
                        country TEXT,
                        state TEXT,
                        city TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (lat, lon)
                    )
                """)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Error initializing SQLite geocache database at {self.db_path}: {e}")

    def _normalize_coords(self, lat: float, lon: float) -> Tuple[float, float]:
        """
        Normalize latitude and longitude by rounding to 4 decimal places.
        4 decimal places provides ~11m precision, which is more than enough for city/state/country resolution
        and significantly improves cache hit rates.
        """
        return round(float(lat), 4), round(float(lon), 4)

    def _get_from_cache(self, lat: float, lon: float) -> Optional[Dict[str, str]]:
        """Retrieves cached geocoding results if they exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT country, state, city FROM geocache WHERE lat = ? AND lon = ?", 
                    (lat, lon)
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "country": row[0],
                        "state": row[1],
                        "city": row[2]
                    }
        except sqlite3.Error as e:
            logger.debug(f"Database read error: {e}")
        return None

    def _save_to_cache(self, lat: float, lon: float, country: str, state: str, city: str):
        """Saves a geocoding result to the cache."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO geocache (lat, lon, country, state, city)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (lat, lon, country, state, city)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.warning(f"Failed to cache geocoding result: {e}")

    def reverse_geocode(self, lat: float, lon: float, retries: int = 3, delay: float = 1.0) -> Dict[str, str]:
        """
        Translates lat, lon into a dictionary containing country, state, city.
        Checks the local SQLite cache first. If not cached, performs an API call.
        Respects rate limits of OSM Nominatim by sleeping if requests are made.
        """
        lat_norm, lon_norm = self._normalize_coords(lat, lon)

        # Check Cache
        cached = self._get_from_cache(lat_norm, lon_norm)
        if cached:
            logger.debug(f"Geocache hit for coords ({lat_norm}, {lon_norm})")
            return cached

        # Cache miss, fetch from API
        logger.info(f"Geocache miss. Querying reverse geocoding API for ({lat_norm}, {lon_norm})...")
        
        # OSM Nominatim policy requires no more than 1 request per second
        # We enforce a small sleep to be respectful and avoid rate limiting
        time.sleep(delay)

        for attempt in range(retries):
            try:
                # query Nominatim
                location = self.geolocator.reverse((lat_norm, lon_norm), language='pt', timeout=10)
                if location and location.raw and 'address' in location.raw:
                    address = location.raw['address']
                    
                    # Extract variables, handle differing OSM labels
                    country = address.get('country', 'Unknown')
                    state = address.get('state', address.get('region', 'Unknown'))
                    city = address.get(
                        'city', 
                        address.get('town', address.get('village', address.get('municipality', 'Unknown')))
                    )

                    # Save to cache
                    self._save_to_cache(lat_norm, lon_norm, country, state, city)
                    return {
                        "country": country,
                        "state": state,
                        "city": city
                    }
                break
            except (GeocoderTimedOut, GeocoderServiceError) as e:
                logger.warning(f"Geocoding attempt {attempt + 1}/{retries} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(delay * 2)
            except Exception as e:
                logger.error(f"Unexpected error during geocoding: {e}")
                break

        # Fallback if API fails completely or no location found
        return {
            "country": "Unknown",
            "state": "Unknown",
            "city": "Unknown"
        }
