import os
import shutil
import tempfile
import unittest
import sqlite3
from datetime import datetime
from PIL import Image

# Import package modules
from organizer.geocoder import CachedGeocoder
from organizer.metadata import get_file_metadata, extract_image_metadata
from organizer.ai_tagger import AITagger
from organizer.processor import FileOrganizer


class TestGeocoder(unittest.TestCase):
    def setUp(self):
        # Create a temp directory for database cache
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_cache.db")
        self.geocoder = CachedGeocoder(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_cache_initialization(self):
        self.assertTrue(os.path.exists(self.db_path))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='geocache'")
            self.assertIsNotNone(cursor.fetchone())

    def test_coordinate_normalization(self):
        lat1, lon1 = self.geocoder._normalize_coords(45.123456, -122.987654)
        lat2, lon2 = self.geocoder._normalize_coords(45.123412, -122.987699)
        self.assertEqual((lat1, lon1), (45.1235, -122.9877))
        self.assertEqual((lat2, lon2), (45.1234, -122.9877))

    def test_cache_save_and_retrieve(self):
        # Save to cache
        self.geocoder._save_to_cache(45.1234, -122.9876, "Brasil", "São Paulo", "Campinas")
        
        # Get from cache
        data = self.geocoder._get_from_cache(45.1234, -122.9876)
        self.assertIsNotNone(data)
        self.assertEqual(data["country"], "Brasil")
        self.assertEqual(data["state"], "São Paulo")
        self.assertEqual(data["city"], "Campinas")


class TestAITaggerHeuristics(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tagger = AITagger(api_key="MOCK_NO_KEY")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_filename_heuristics(self):
        # Test screenshot detection
        screenshot_path = os.path.join(self.test_dir, "screenshot_2026.png")
        with open(screenshot_path, "w") as f:
            f.write("mock content")
        
        # Tag image should capture "screenshot" from filename if it can't open the image
        tag = self.tagger.tag_image(screenshot_path)
        self.assertEqual(tag, "screenshot")

    def test_image_dimension_heuristics(self):
        # Create a panorama image (width > 2 * height)
        pano_path = os.path.join(self.test_dir, "pano.jpg")
        img = Image.new("RGB", (300, 100), color="blue")
        img.save(pano_path)

        tag = self.tagger.tag_image(pano_path)
        self.assertEqual(tag, "panorama")

        # Create a vertical image
        vert_path = os.path.join(self.test_dir, "vert.jpg")
        img_vert = Image.new("RGB", (100, 300), color="red")
        img_vert.save(vert_path)

        tag_vert = self.tagger.tag_image(vert_path)
        self.assertEqual(tag_vert, "vertical")


class TestFileMetadata(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_image_metadata_extraction(self):
        img_path = os.path.join(self.test_dir, "photo.jpg")
        img = Image.new("RGB", (100, 100), color="green")
        
        # Inject standard EXIF datetime
        exif = img.getexif()
        # 36867 is DateTimeOriginal
        exif[36867] = "2024:12:25 15:30:45"
        img.save(img_path, exif=exif)

        meta = get_file_metadata(img_path)
        self.assertEqual(meta["year"], "2024")
        self.assertEqual(meta["month"], "12")
        self.assertEqual(meta["day"], "25")
        self.assertEqual(meta["original_name"], "photo")
        self.assertEqual(meta["ext"], "jpg")

    def test_fallback_to_file_stats(self):
        txt_path = os.path.join(self.test_dir, "notes.txt")
        with open(txt_path, "w") as f:
            f.write("Important notes")

        meta = get_file_metadata(txt_path)
        now = datetime.now()
        self.assertEqual(meta["year"], f"{now.year:04d}")
        self.assertEqual(meta["month"], f"{now.month:02d}")
        self.assertEqual(meta["original_name"], "notes")
        self.assertEqual(meta["ext"], "txt")


class TestFileOrganizer(unittest.TestCase):
    def setUp(self):
        self.src_dir = tempfile.mkdtemp()
        self.dest_dir = tempfile.mkdtemp()

        # Create some mock source files
        self.photo1 = os.path.join(self.src_dir, "photo1.jpg")
        img1 = Image.new("RGB", (100, 100), color="blue")
        exif1 = img1.getexif()
        exif1[36867] = "2023:05:15 12:00:00"
        img1.save(self.photo1, exif=exif1)

        self.photo2 = os.path.join(self.src_dir, "photo2.jpg")
        img2 = Image.new("RGB", (100, 100), color="red")
        exif2 = img2.getexif()
        exif2[36867] = "2023:05:15 13:00:00"
        img2.save(self.photo2, exif=exif2)

        # A document file (no country metadata)
        self.doc = os.path.join(self.src_dir, "report.pdf")
        with open(self.doc, "w") as f:
            f.write("PDF mock content")

    def tearDown(self):
        shutil.rmtree(self.src_dir)
        shutil.rmtree(self.dest_dir)

    def test_dry_run(self):
        organizer = FileOrganizer(
            src=self.src_dir,
            dest=self.dest_dir,
            folder_format="{year}/{month}",
            file_format="{original_name}",
            action="copy",
            dry_run=True
        )
        stats = organizer.run()
        
        # Stats should verify files scanned and processed
        self.assertEqual(stats["scanned"], 3)
        self.assertEqual(stats["processed"], 3)
        self.assertEqual(stats["errors"], 0)

        # Dest dir should be empty because it is a dry run
        dest_files = os.listdir(self.dest_dir)
        self.assertEqual(len(dest_files), 0)

    def test_copy_organization_with_fallback(self):
        # We use a folder format requiring country.
        # Since these files don't have country metadata, they should go to fallback folder (Unknown_Country)
        organizer = FileOrganizer(
            src=self.src_dir,
            dest=self.dest_dir,
            folder_format="{country}/{year}",
            file_format="{original_name}",
            action="copy",
            dry_run=False
        )
        stats = organizer.run()
        
        self.assertEqual(stats["processed"], 3)

        # Check destination files
        # Expect structure: Dest / Z - Outros / photo1.jpg
        # Expect structure: Dest / Z - Outros / photo2.jpg
        expected_photo1 = os.path.join(self.dest_dir, "Z - Outros", "photo1.jpg")
        expected_photo2 = os.path.join(self.dest_dir, "Z - Outros", "photo2.jpg")
        
        self.assertTrue(os.path.exists(expected_photo1))
        self.assertTrue(os.path.exists(expected_photo2))

    def test_collision_handling(self):
        # Create two files that will resolve to the exact same directory and name
        # Ex: folder "{year}" and file name "photo.jpg"
        col_dir = tempfile.mkdtemp()
        dest_dir = tempfile.mkdtemp()
        
        photo_a = os.path.join(col_dir, "photo_a.jpg")
        img_a = Image.new("RGB", (100, 100))
        exif_a = img_a.getexif()
        exif_a[36867] = "2025:01:01 12:00:00"
        img_a.save(photo_a, exif=exif_a)

        photo_b = os.path.join(col_dir, "photo_b.jpg")
        img_b = Image.new("RGB", (100, 100))
        exif_b = img_b.getexif()
        exif_b[36867] = "2025:01:01 12:00:00"
        img_b.save(photo_b, exif=exif_b)

        try:
            organizer = FileOrganizer(
                src=col_dir,
                dest=dest_dir,
                folder_format="{year}",
                file_format="holiday_snap",  # Hardcoded destination name to force collision!
                action="copy",
                dry_run=False
            )
            organizer.run()

            # We should have holiday_snap.jpg and holiday_snap_01.jpg in dest_dir / 2025
            path1 = os.path.join(dest_dir, "2025", "holiday_snap.jpg")
            path2 = os.path.join(dest_dir, "2025", "holiday_snap_01.jpg")

            self.assertTrue(os.path.exists(path1))
            self.assertTrue(os.path.exists(path2))

        finally:
            shutil.rmtree(col_dir)
            shutil.rmtree(dest_dir)


if __name__ == "__main__":
    unittest.main()
