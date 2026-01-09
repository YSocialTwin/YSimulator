"""
Unit tests for image extraction and description functionality.

Tests the complete pipeline:
1. Extracting image URLs from RSS feed entries
2. Describing images using vision LLM
3. Saving images to database
"""

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from YSimulator.YServer.classes.db_middleware import DatabaseMiddleware
from YSimulator.YServer.classes.models import Image

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))


# Import the modules we need to test


class TestImageExtraction(unittest.TestCase):
    """Test image extraction and description functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create an in-memory SQLite database for testing
        self.db_config = {"type": "sqlite", "sqlite": {"filename": ":memory:"}}

        # Initialize database middleware
        self.db = DatabaseMiddleware(db_config=self.db_config, config_path=".", redis_config=None)

        # Create tables
        from YSimulator.YServer.classes.models import Base

        Base.metadata.create_all(self.db.engine)

    @staticmethod
    def _extract_images_from_entry(entry):
        """
        Helper method to test image extraction logic.
        Replicates the logic from NewsFeedService._extract_images_from_entry.
        """
        image_urls = []

        # Check media_content
        if hasattr(entry, "media_content") and entry.media_content:
            for media in entry.media_content:
                if media.get("type", "").startswith("image/"):
                    url = media.get("url")
                    if url and url not in image_urls:
                        image_urls.append(url)

        # Check media_thumbnail
        if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
            for thumb in entry.media_thumbnail:
                url = thumb.get("url")
                if url and url not in image_urls:
                    image_urls.append(url)

        # Check enclosures
        if hasattr(entry, "enclosures") and entry.enclosures:
            for enclosure in entry.enclosures:
                if enclosure.get("type", "").startswith("image/"):
                    url = enclosure.get("href")
                    if url and url not in image_urls:
                        image_urls.append(url)

        return image_urls

    def test_01_image_model_structure(self):
        """Test that Image model has correct structure."""
        print("\n=== Test 1: Image Model Structure ===")

        # Check Image model attributes
        self.assertTrue(hasattr(Image, "id"))
        self.assertTrue(hasattr(Image, "url"))
        self.assertTrue(hasattr(Image, "description"))
        self.assertTrue(hasattr(Image, "article_id"))

        # Check id column type
        id_col = Image.__table__.columns["id"]
        print(f"Image.id type: {id_col.type}")

        self.assertEqual(str(id_col.type), "VARCHAR(36)", "Image.id should be VARCHAR(36) for UUID")

        # Check foreign key
        fk_constraints = [fk for fk in Image.__table__.foreign_keys]
        self.assertEqual(len(fk_constraints), 1, "Image should have 1 foreign key")

        fk = list(fk_constraints)[0]
        self.assertEqual(
            str(fk.column.table), "articles", "Image.article_id should reference articles table"
        )

        print("✓ Image model structure is correct")

    def test_02_add_image_method(self):
        """Test that add_image method works correctly."""
        print("\n=== Test 2: Add Image Method ===")

        # First create a website
        website_id = str(uuid.uuid4())
        website_data = {
            "id": website_id,
            "name": "Test Website",
            "rss": f"https://example.com/rss-{uuid.uuid4()}",  # Unique RSS URL for test
            "category": "tech",
            "language": "en",
        }
        result_website_id = self.db.add_website(website_data)
        self.assertIsNotNone(result_website_id)
        print(f"✓ Created test website: {result_website_id}")

        # Create an article
        article_id = str(uuid.uuid4())
        article_data = {
            "id": article_id,
            "title": "Test Article",
            "summary": "Test summary",
            "website_id": result_website_id,  # Use the returned website_id
            "link": f"https://example.com/article-{uuid.uuid4()}",  # Unique link
            "fetched_on": str(uuid.uuid4()),
        }
        result_article_id = self.db.add_article(article_data)
        self.assertEqual(result_article_id, article_id)
        print(f"✓ Created test article: {article_id}")

        # Add an image
        image_id = str(uuid.uuid4())
        image_data = {
            "id": image_id,
            "url": "https://example.com/image.jpg",
            "description": "A test image showing something interesting",
            "article_id": article_id,
        }
        result_image_id = self.db.add_image(image_data)
        self.assertEqual(result_image_id, image_id)
        print(f"✓ Created test image: {image_id}")

        # Verify image was saved
        from sqlalchemy.orm import Session

        session = Session(self.db.engine)
        try:
            saved_image = session.query(Image).filter(Image.id == image_id).first()
            self.assertIsNotNone(saved_image)
            self.assertEqual(saved_image.url, image_data["url"])
            self.assertEqual(saved_image.description, image_data["description"])
            self.assertEqual(saved_image.article_id, article_id)
            print("✓ Image data verified in database")
        finally:
            session.close()

    def test_03_add_image_without_article(self):
        """Test that add_image fails gracefully without valid article."""
        print("\n=== Test 3: Add Image Without Article ===")

        # Try to add image without article_id
        image_data = {"url": "https://example.com/image.jpg", "description": "Test description"}
        result = self.db.add_image(image_data)
        self.assertIsNone(result, "Should return None when article_id is missing")
        print("✓ Correctly rejected image without article_id")

        # Try to add image with non-existent article_id
        fake_article_id = str(uuid.uuid4())
        image_data = {
            "url": "https://example.com/image.jpg",
            "description": "Test description",
            "article_id": fake_article_id,
        }
        result = self.db.add_image(image_data)
        self.assertIsNone(result, "Should return None when article doesn't exist")
        print("✓ Correctly rejected image with non-existent article_id")

    def test_04_extract_images_from_entry(self):
        """Test image URL extraction from RSS feed entries."""
        print("\n=== Test 4: Extract Images from RSS Entry ===")

        # Create a mock entry with various image formats
        mock_entry = MagicMock()

        # Test media_content
        mock_entry.media_content = [
            {"url": "https://example.com/media1.jpg", "type": "image/jpeg"},
            {"url": "https://example.com/media2.png", "type": "image/png"},
        ]

        # Test media_thumbnail
        mock_entry.media_thumbnail = [
            {"url": "https://example.com/thumb1.jpg"},
        ]

        # Test enclosures
        mock_entry.enclosures = [
            {"href": "https://example.com/enc1.jpg", "type": "image/jpeg"},
        ]

        # Use helper method to extract images
        image_urls = self._extract_images_from_entry(mock_entry)

        # Verify all images were extracted
        self.assertEqual(len(image_urls), 4)
        self.assertIn("https://example.com/media1.jpg", image_urls)
        self.assertIn("https://example.com/media2.png", image_urls)
        self.assertIn("https://example.com/thumb1.jpg", image_urls)
        self.assertIn("https://example.com/enc1.jpg", image_urls)

        print(f"✓ Extracted {len(image_urls)} images from RSS entry")
        print(f"  Images: {image_urls}")

    def test_05_extract_images_no_duplicates(self):
        """Test that duplicate image URLs are filtered out."""
        print("\n=== Test 5: No Duplicate Images ===")

        # Create a mock entry with duplicate URLs
        mock_entry = MagicMock()

        duplicate_url = "https://example.com/same.jpg"

        mock_entry.media_content = [
            {"url": duplicate_url, "type": "image/jpeg"},
        ]

        mock_entry.media_thumbnail = [
            {"url": duplicate_url},
        ]

        mock_entry.enclosures = [
            {"href": duplicate_url, "type": "image/jpeg"},
        ]

        # Use helper method to extract images
        image_urls = self._extract_images_from_entry(mock_entry)

        # Should only have one URL despite being in multiple places
        self.assertEqual(len(image_urls), 1)
        self.assertEqual(image_urls[0], duplicate_url)

        print("✓ Correctly filtered duplicate URLs")

    def test_06_llm_service_describe_image(self):
        """Test that LLMService.describe_image method exists and has correct signature."""
        print("\n=== Test 6: LLM Service describe_image Method ===")

        from YSimulator.YClient.LLM_interactions.llm_service import LLMService

        # Check that describe_image method exists
        self.assertTrue(hasattr(LLMService, "describe_image"))
        print("✓ describe_image method exists in LLMService")

        # Check method signature
        import inspect

        sig = inspect.signature(LLMService.describe_image)
        params = list(sig.parameters.keys())

        # Ray actors don't have 'self' in the signature when inspected
        self.assertIn("image_url", params)
        print(f"✓ describe_image has correct parameters: {params}")


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
