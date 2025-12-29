#!/usr/bin/env python3
"""
Bulk File Upload Script with Progress Monitoring
Uploads files from a folder to the BI backend API and monitors parsing progress.

Usage:
    python upload_files.py --folder /path/to/files --api-url http://localhost:8000 --tags tag1,tag2
    python upload_files.py --folder ./documents --output-file uploads.log
"""

import os
import sys
import argparse
import json
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('upload_progress.log')
    ]
)
logger = logging.getLogger(__name__)


class FileUploader:
    """Upload files to the BI backend API with progress tracking."""

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        output_file: Optional[str] = None,
        timeout: int = 30,
        retry_attempts: int = 3,
    ):
        """
        Initialize the file uploader.

        Args:
            api_url: Base URL of the BI backend API
            output_file: Path to save upload results JSON
            timeout: Request timeout in seconds
            retry_attempts: Number of retries for failed uploads
        """
        self.api_url = api_url.rstrip('/')
        self.output_file = output_file
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.upload_results = []
        self.stats = {
            'total_files': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'total_size_bytes': 0,
            'start_time': None,
            'end_time': None,
        }

    def validate_api_connection(self) -> bool:
        """Check if API is accessible."""
        try:
            response = requests.get(
                f"{self.api_url}/docs",
                timeout=5
            )
            if response.status_code == 200:
                logger.info(f"✓ API is accessible at {self.api_url}")
                return True
            else:
                logger.error(f"✗ API returned status code {response.status_code}")
                return False
        except ConnectionError:
            logger.error(f"✗ Could not connect to API at {self.api_url}")
            return False
        except Timeout:
            logger.error(f"✗ API connection timed out at {self.api_url}")
            return False
        except Exception as e:
            logger.error(f"✗ Error connecting to API: {e}")
            return False

    def upload_file(
        self,
        file_path: Path,
        tags: Optional[List[str]] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Upload a single file to the API.

        Args:
            file_path: Path to the file
            tags: Optional list of tags
            retry_count: Current retry attempt number

        Returns:
            Dictionary with upload result
        """
        file_size = file_path.stat().st_size
        file_name = file_path.name

        try:
            logger.info(f"Uploading: {file_name} ({self._format_size(file_size)})")

            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f)}
                data = {}

                if tags:
                    data['tags'] = ','.join(tags)

                response = requests.post(
                    f"{self.api_url}/files/upload",
                    files=files,
                    data=data,
                    timeout=self.timeout
                )

            if response.status_code == 200:
                result = response.json()
                file_id = result.get('file_id')
                logger.info(
                    f"  ✓ Uploaded successfully (ID: {file_id})"
                )
                self.stats['successful_uploads'] += 1
                self.stats['total_size_bytes'] += file_size

                return {
                    'file_name': file_name,
                    'file_path': str(file_path),
                    'file_size': file_size,
                    'file_id': file_id,
                    'status': 'uploaded',
                    'tags': tags or [],
                    'upload_time': datetime.now().isoformat(),
                    'error': None,
                }

            elif response.status_code == 429:
                logger.warning(
                    f"  ⚠ Queue full (429). Retrying in 5 seconds..."
                )
                if retry_count < self.retry_attempts:
                    time.sleep(5)
                    return self.upload_file(file_path, tags, retry_count + 1)
                else:
                    logger.error(
                        f"  ✗ Failed after {self.retry_attempts} retries (queue full)"
                    )
                    self.stats['failed_uploads'] += 1
                    return {
                        'file_name': file_name,
                        'file_path': str(file_path),
                        'file_size': file_size,
                        'status': 'failed',
                        'error': f"Queue full (429) after {self.retry_attempts} retries",
                    }

            else:
                error_msg = response.text or f"HTTP {response.status_code}"
                logger.error(f"  ✗ Upload failed: {error_msg}")
                self.stats['failed_uploads'] += 1
                return {
                    'file_name': file_name,
                    'file_path': str(file_path),
                    'file_size': file_size,
                    'status': 'failed',
                    'error': error_msg,
                }

        except Exception as e:
            logger.error(f"  ✗ Exception during upload: {e}")
            self.stats['failed_uploads'] += 1
            return {
                'file_name': file_name,
                'file_path': str(file_path),
                'file_size': file_size,
                'status': 'failed',
                'error': str(e),
            }

    def check_parsing_status(self, file_id: int) -> Dict[str, Any]:
        """
        Check the parsing status of an uploaded file.

        Args:
            file_id: ID of the uploaded file

        Returns:
            Dictionary with status information
        """
        try:
            response = requests.get(
                f"{self.api_url}/files/{file_id}/parsing-status",
                timeout=self.timeout
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {
                    'file_id': file_id,
                    'parsing_state': 'unknown',
                    'error': f"HTTP {response.status_code}",
                }

        except Exception as e:
            return {
                'file_id': file_id,
                'parsing_state': 'unknown',
                'error': str(e),
            }

    def monitor_parsing(
        self,
        file_ids: List[int],
        max_wait_minutes: int = 30,
        check_interval_seconds: int = 10,
    ) -> Dict[int, str]:
        """
        Monitor parsing progress for uploaded files.

        Args:
            file_ids: List of file IDs to monitor
            max_wait_minutes: Maximum time to wait for all files to complete
            check_interval_seconds: Seconds between status checks

        Returns:
            Dictionary mapping file_id to final parsing_state
        """
        final_states = {}
        max_checks = (max_wait_minutes * 60) // check_interval_seconds
        check_count = 0
        incomplete_ids = set(file_ids)

        logger.info(
            f"\n{'='*60}"
        )
        logger.info(
            f"Monitoring parsing progress for {len(file_ids)} files..."
        )
        logger.info(
            f"Max wait time: {max_wait_minutes} minutes, "
            f"Check interval: {check_interval_seconds} seconds"
        )
        logger.info(
            f"{'='*60}\n"
        )

        start_time = time.time()

        while incomplete_ids and check_count < max_checks:
            check_count += 1
            logger.info(
                f"[Check {check_count}] Status at "
                f"{datetime.now().strftime('%H:%M:%S')}"
            )

            for file_id in list(incomplete_ids):
                status = self.check_parsing_status(file_id)
                state = status.get('parsing_state', 'unknown')

                if state in ['done', 'failed']:
                    final_states[file_id] = state
                    incomplete_ids.remove(file_id)

                    emoji = '✓' if state == 'done' else '✗'
                    logger.info(
                        f"  {emoji} File ID {file_id}: {state.upper()}"
                    )

            if incomplete_ids:
                remaining = len(incomplete_ids)
                elapsed_minutes = (time.time() - start_time) / 60
                logger.info(
                    f"  Waiting... ({remaining} files still processing, "
                    f"elapsed: {elapsed_minutes:.1f}min)\n"
                )
                time.sleep(check_interval_seconds)
            else:
                break

        # Handle timeout
        for file_id in incomplete_ids:
            final_states[file_id] = 'timeout'
            logger.warning(f"  ⚠ File ID {file_id}: Timeout waiting for completion")

        elapsed_time = time.time() - start_time
        logger.info(
            f"\n{'='*60}"
        )
        logger.info(f"Monitoring completed in {elapsed_time/60:.1f} minutes")
        logger.info(
            f"{'='*60}\n"
        )

        return final_states

    def upload_folder(
        self,
        folder_path: str,
        tags: Optional[List[str]] = None,
        pattern: str = "*.*",
        recursive: bool = True,
        monitor_parsing: bool = True,
        max_wait_minutes: int = 30,
    ) -> None:
        """
        Upload all files from a folder.

        Args:
            folder_path: Path to the folder containing files
            tags: Optional list of tags for all files
            pattern: File pattern to match (default: all files)
            recursive: Search subdirectories
            monitor_parsing: Monitor parsing progress after upload
            max_wait_minutes: Max time to wait for parsing completion
        """
        folder = Path(folder_path)

        if not folder.exists():
            logger.error(f"✗ Folder does not exist: {folder_path}")
            return

        if not folder.is_dir():
            logger.error(f"✗ Path is not a directory: {folder_path}")
            return

        # Find files
        if recursive:
            files = list(folder.rglob(pattern))
        else:
            files = list(folder.glob(pattern))

        # Filter out directories
        files = [f for f in files if f.is_file()]

        if not files:
            logger.error(f"✗ No files found matching pattern '{pattern}'")
            return

        self.stats['total_files'] = len(files)
        self.stats['start_time'] = datetime.now().isoformat()

        logger.info(
            f"\n{'='*60}"
        )
        logger.info(f"Starting file uploads")
        logger.info(
            f"Folder: {folder_path}"
        )
        logger.info(
            f"Files found: {len(files)}"
        )
        logger.info(
            f"Tags: {', '.join(tags) if tags else 'None'}"
        )
        logger.info(
            f"{'='*60}\n"
        )

        # Upload files
        uploaded_file_ids = []
        for i, file_path in enumerate(files, 1):
            logger.info(f"[{i}/{len(files)}] Uploading: {file_path.name}")
            result = self.upload_file(file_path, tags)
            self.upload_results.append(result)

            if result['status'] == 'uploaded':
                uploaded_file_ids.append(result['file_id'])

        # Summary
        logger.info(
            f"\n{'='*60}"
        )
        logger.info(f"Upload Summary:")
        logger.info(f"  Total files: {self.stats['total_files']}")
        logger.info(f"  Successful: {self.stats['successful_uploads']}")
        logger.info(f"  Failed: {self.stats['failed_uploads']}")
        logger.info(
            f"  Total size: {self._format_size(self.stats['total_size_bytes'])}"
        )
        logger.info(
            f"{'='*60}\n"
        )

        # Monitor parsing if enabled
        if monitor_parsing and uploaded_file_ids:
            parsing_states = self.monitor_parsing(
                uploaded_file_ids,
                max_wait_minutes=max_wait_minutes
            )

            # Update results with parsing status
            for result in self.upload_results:
                if result.get('file_id') in parsing_states:
                    result['parsing_state'] = parsing_states[result['file_id']]

        # Save results
        if self.output_file:
            self._save_results()

        self.stats['end_time'] = datetime.now().isoformat()
        self._print_final_report()

    def _save_results(self) -> None:
        """Save upload results to JSON file."""
        try:
            output = {
                'stats': self.stats,
                'results': self.upload_results,
            }

            with open(self.output_file, 'w') as f:
                json.dump(output, f, indent=2)

            logger.info(f"✓ Results saved to: {self.output_file}")

        except Exception as e:
            logger.error(f"✗ Failed to save results: {e}")

    def _print_final_report(self) -> None:
        """Print final report."""
        logger.info(
            f"\n{'='*60}"
        )
        logger.info("FINAL REPORT")
        logger.info(
            f"{'='*60}"
        )

        # Upload stats
        logger.info(f"\nUpload Statistics:")
        logger.info(f"  Total files: {self.stats['total_files']}")
        logger.info(f"  Successful: {self.stats['successful_uploads']}")
        logger.info(f"  Failed: {self.stats['failed_uploads']}")
        logger.info(
            f"  Success rate: {self._calculate_success_rate()}%"
        )
        logger.info(
            f"  Total size: {self._format_size(self.stats['total_size_bytes'])}"
        )

        # Parsing stats
        parsing_states = [r.get('parsing_state') for r in self.upload_results if 'parsing_state' in r]
        if parsing_states:
            done_count = parsing_states.count('done')
            failed_count = parsing_states.count('failed')
            timeout_count = parsing_states.count('timeout')

            logger.info(f"\nParsing Statistics:")
            logger.info(f"  Completed: {done_count}")
            logger.info(f"  Failed: {failed_count}")
            logger.info(f"  Timeout: {timeout_count}")

        # Time stats
        if self.stats['start_time'] and self.stats['end_time']:
            start = datetime.fromisoformat(self.stats['start_time'])
            end = datetime.fromisoformat(self.stats['end_time'])
            duration = (end - start).total_seconds()
            logger.info(f"\nExecution Time:")
            logger.info(f"  Start: {start.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"  End: {end.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"  Duration: {duration/60:.1f} minutes")

        logger.info(
            f"{'='*60}\n"
        )

    def _calculate_success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.stats['total_files'] == 0:
            return 0.0
        return (self.stats['successful_uploads'] / self.stats['total_files']) * 100

    @staticmethod
    def _format_size(bytes_size: int) -> str:
        """Format bytes to human-readable size."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Bulk file upload with progress monitoring',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload all files from a folder
  python upload_files.py --folder ./documents

  # Upload with tags
  python upload_files.py --folder ./documents --tags tag1,tag2

  # Upload to custom API URL
  python upload_files.py --folder ./documents --api-url http://api.example.com:8000

  # Monitor parsing without waiting
  python upload_files.py --folder ./documents --no-monitor-parsing

  # Save results to file
  python upload_files.py --folder ./documents --output-file results.json
        """
    )

    parser.add_argument(
        '--folder',
        required=True,
        help='Path to folder containing files to upload'
    )
    parser.add_argument(
        '--api-url',
        default='http://localhost:8000',
        help='Base URL of the API (default: http://localhost:8000)'
    )
    parser.add_argument(
        '--tags',
        default='',
        help='Comma-separated tags (e.g., tag1,tag2)'
    )
    parser.add_argument(
        '--pattern',
        default='*.*',
        help='File pattern to match (default: *.*)'
    )
    parser.add_argument(
        '--recursive',
        action='store_true',
        default=True,
        help='Search subdirectories (default: True)'
    )
    parser.add_argument(
        '--no-recursive',
        action='store_false',
        dest='recursive',
        help='Do not search subdirectories'
    )
    parser.add_argument(
        '--monitor-parsing',
        action='store_true',
        default=True,
        help='Monitor parsing progress (default: True)'
    )
    parser.add_argument(
        '--no-monitor-parsing',
        action='store_false',
        dest='monitor_parsing',
        help='Do not monitor parsing'
    )
    parser.add_argument(
        '--max-wait-minutes',
        type=int,
        default=30,
        help='Max time to wait for parsing (default: 30 minutes)'
    )
    parser.add_argument(
        '--output-file',
        default='upload_results.json',
        help='Path to save results JSON (default: upload_results.json)'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Request timeout in seconds (default: 30)'
    )

    args = parser.parse_args()

    # Parse tags
    tags = [t.strip() for t in args.tags.split(',') if t.strip()] if args.tags else None

    # Create uploader
    uploader = FileUploader(
        api_url=args.api_url,
        output_file=args.output_file,
        timeout=args.timeout,
    )

    # Check connection
    if not uploader.validate_api_connection():
        logger.error("Cannot proceed without API connection")
        sys.exit(1)

    # Upload files
    try:
        uploader.upload_folder(
            folder_path=args.folder,
            tags=tags,
            pattern=args.pattern,
            recursive=args.recursive,
            monitor_parsing=args.monitor_parsing,
            max_wait_minutes=args.max_wait_minutes,
        )
    except KeyboardInterrupt:
        logger.info("\n Upload interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f" Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
