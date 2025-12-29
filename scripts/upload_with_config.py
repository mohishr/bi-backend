#!/usr/bin/env python3
"""
Configuration-based bulk file uploader.
Reads upload configuration from JSON and uploads multiple folders.

Usage:
    python upload_with_config.py --config config.json
    python upload_with_config.py --config config.json --dry-run
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any

# Import the FileUploader from upload_files.py
sys.path.insert(0, os.path.dirname(__file__))
from upload_files import FileUploader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ConfigBasedUploader:
    """Upload files using a configuration file."""

    def __init__(self, config_file: str):
        """Initialize with config file."""
        self.config_file = Path(config_file)
        self.config = None
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from JSON file."""
        if not self.config_file.exists():
            logger.error(f"Configuration file not found: {self.config_file}")
            sys.exit(1)

        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
            logger.info(f"✓ Configuration loaded from: {self.config_file}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error reading config file: {e}")
            sys.exit(1)

    def validate_config(self) -> bool:
        """Validate configuration structure."""
        required_keys = ['api_url', 'folders']
        for key in required_keys:
            if key not in self.config:
                logger.error(f"Missing required config key: {key}")
                return False

        if not isinstance(self.config['folders'], list):
            logger.error("'folders' must be a list")
            return False

        if not self.config['folders']:
            logger.error("'folders' list is empty")
            return False

        return True

    def run(self, dry_run: bool = False) -> None:
        """Run the upload process."""
        if not self.validate_config():
            sys.exit(1)

        api_url = self.config.get('api_url', 'http://localhost:8000')
        upload_settings = self.config.get('upload_settings', {})
        output_settings = self.config.get('output', {})

        # Create uploader
        uploader = FileUploader(
            api_url=api_url,
            output_file=output_settings.get('results_file', 'upload_results.json'),
            timeout=upload_settings.get('timeout_seconds', 30),
            retry_attempts=upload_settings.get('retry_attempts', 3),
        )

        # Validate connection
        if not uploader.validate_api_connection():
            logger.error("Cannot connect to API. Please check the API URL.")
            sys.exit(1)

        # Process folders
        total_uploaded = 0

        for i, folder_config in enumerate(self.config['folders'], 1):
            folder_path = folder_config.get('path')
            description = folder_config.get('description', f"Folder {i}")

            if not folder_path:
                logger.warning(f"Folder {i}: Missing 'path' key, skipping")
                continue

            folder = Path(folder_path)
            if not folder.exists():
                logger.warning(f"Folder {i}: Path does not exist: {folder_path}")
                continue

            tags = folder_config.get('tags', [])
            pattern = folder_config.get('pattern', '*.*')
            recursive = folder_config.get('recursive', True)

            logger.info(
                f"\n{'='*60}"
            )
            logger.info(f"Processing: {description}")
            logger.info(f"Path: {folder_path}")
            logger.info(f"Tags: {', '.join(tags) if tags else 'None'}")
            logger.info(f"Pattern: {pattern}")
            logger.info(f"{'='*60}")

            if dry_run:
                # Count files without uploading
                if recursive:
                    files = list(folder.rglob(pattern))
                else:
                    files = list(folder.glob(pattern))
                files = [f for f in files if f.is_file()]

                logger.info(f"[DRY RUN] Would upload {len(files)} file(s)")
                for file in files:
                    logger.info(f"  - {file.name}")
                continue

            # Upload folder
            uploader.upload_folder(
                folder_path=str(folder),
                tags=tags if tags else None,
                pattern=pattern,
                recursive=recursive,
                monitor_parsing=upload_settings.get('monitor_parsing', True),
                max_wait_minutes=upload_settings.get('max_wait_minutes', 30),
            )

            total_uploaded += uploader.stats['successful_uploads']

        if not dry_run:
            logger.info(
                f"\n{'='*60}"
            )
            logger.info("All folders processed!")
            logger.info(f"Total uploaded: {total_uploaded}")
            logger.info(
                f"{'='*60}\n"
            )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Upload files using configuration file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload with default config
  python upload_with_config.py

  # Upload with custom config
  python upload_with_config.py --config my_config.json

  # Dry run to see what would be uploaded
  python upload_with_config.py --config config.json --dry-run

  # Create config from template
  cp config_template.json config.json
  python upload_with_config.py --config config.json
        """
    )

    parser.add_argument(
        '--config',
        default='config.json',
        help='Path to configuration JSON file (default: config.json)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be uploaded without actually uploading'
    )

    args = parser.parse_args()

    # Run uploader
    try:
        uploader = ConfigBasedUploader(args.config)
        uploader.run(dry_run=args.dry_run)
    except KeyboardInterrupt:
        logger.info("\nUpload interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
