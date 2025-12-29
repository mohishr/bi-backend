# Bulk File Upload Scripts

Standalone Python scripts for uploading files to the BI backend API with progress monitoring and logging.

## Overview

Two upload scripts are provided:

1. **`upload_files.py`** - Command-line based uploader with flexible options
2. **`upload_with_config.py`** - Configuration file-based uploader for batch operations

Both scripts:
- ✅ Upload files from a folder
- ✅ Add tags to files
- ✅ Monitor parsing progress
- ✅ Log all activities
- ✅ Save results to JSON
- ✅ Handle API errors gracefully
- ✅ Retry failed uploads

## Requirements

```bash
pip install requests
```

No other project dependencies needed. These are standalone scripts!

## Usage

### Method 1: Direct Command-Line Upload

**Basic upload:**
```bash
python upload_files.py --folder ./documents
```

**With tags:**
```bash
python upload_files.py --folder ./documents --tags tag1,tag2
```

**Custom API URL:**
```bash
python upload_files.py --folder ./documents --api-url http://api.example.com:8000
```

**Specific file pattern:**
```bash
python upload_files.py --folder ./documents --pattern "*.txt"
```

**Skip parsing monitoring:**
```bash
python upload_files.py --folder ./documents --no-monitor-parsing
```

**Custom output file:**
```bash
python upload_files.py --folder ./documents --output-file results.json
```

**All options:**
```bash
python upload_files.py \
  --folder ./documents \
  --api-url http://localhost:8000 \
  --tags important,urgent \
  --pattern "*.pdf" \
  --recursive \
  --monitor-parsing \
  --max-wait-minutes 60 \
  --output-file upload_results.json \
  --timeout 30
```

### Method 2: Configuration File Upload

**Step 1: Create config file**
```bash
cp config_template.json config.json
```

**Step 2: Edit config.json** with your settings:
```json
{
  "api_url": "http://localhost:8000",
  "folders": [
    {
      "path": "./documents",
      "tags": ["document"],
      "pattern": "*.txt",
      "recursive": true
    }
  ],
  "upload_settings": {
    "timeout_seconds": 30,
    "monitor_parsing": true,
    "max_wait_minutes": 30
  }
}
```

**Step 3: Run upload**
```bash
python upload_with_config.py --config config.json
```

**Dry run (see what would be uploaded):**
```bash
python upload_with_config.py --config config.json --dry-run
```

## Output

### Console Logging

Real-time progress displayed in console:
```
2025-12-15 10:30:45,123 - INFO - ✓ API is accessible at http://localhost:8000
2025-12-15 10:30:46,456 - INFO - ============================================================
2025-12-15 10:30:46,457 - INFO - Starting file uploads
2025-12-15 10:30:46,458 - INFO - Folder: ./documents
2025-12-15 10:30:46,459 - INFO - Files found: 5
2025-12-15 10:30:46,460 - INFO - Tags: document, important
2025-12-15 10:30:46,461 - INFO - ============================================================
2025-12-15 10:30:47,500 - INFO - [1/5] Uploading: document1.txt (1.24 MB)
2025-12-15 10:30:48,123 - INFO -   ✓ Uploaded successfully (ID: 123)
```

### Log File

All output saved to `upload_progress.log`:
- Timestamps for all operations
- Upload success/failure details
- Parsing progress updates
- Final statistics

### Results JSON

Results saved to `upload_results.json`:
```json
{
  "stats": {
    "total_files": 5,
    "successful_uploads": 5,
    "failed_uploads": 0,
    "total_size_bytes": 6291456,
    "start_time": "2025-12-15T10:30:46.123456",
    "end_time": "2025-12-15T10:45:30.654321"
  },
  "results": [
    {
      "file_name": "document1.txt",
      "file_path": "/path/to/document1.txt",
      "file_size": 1048576,
      "file_id": 123,
      "status": "uploaded",
      "parsing_state": "done",
      "tags": ["document", "important"],
      "upload_time": "2025-12-15T10:30:47.500000",
      "error": null
    }
  ]
}
```

## Command-Line Options

### upload_files.py

```
--folder FOLDER               Path to folder (REQUIRED)
--api-url URL                 API URL (default: http://localhost:8000)
--tags TAGS                   Comma-separated tags (default: none)
--pattern PATTERN             File pattern (default: *.*)
--recursive                   Search subdirectories (default: True)
--no-recursive                Don't search subdirectories
--monitor-parsing             Monitor parsing progress (default: True)
--no-monitor-parsing          Don't monitor parsing
--max-wait-minutes MINUTES    Max wait time (default: 30)
--output-file FILE            Results JSON file (default: upload_results.json)
--timeout SECONDS             Request timeout (default: 30)
--help                        Show help message
```

### upload_with_config.py

```
--config FILE                 Config JSON file (default: config.json)
--dry-run                     Show what would be uploaded
--help                        Show help message
```

## Configuration File Format

```json
{
  "api_url": "http://localhost:8000",
  "folders": [
    {
      "path": "./documents",
      "tags": ["document", "important"],
      "pattern": "*.txt",
      "recursive": true,
      "description": "Text documents"
    },
    {
      "path": "./data",
      "tags": ["data"],
      "pattern": "*.csv",
      "recursive": false,
      "description": "CSV files"
    }
  ],
  "upload_settings": {
    "timeout_seconds": 30,
    "retry_attempts": 3,
    "monitor_parsing": true,
    "max_wait_minutes": 30,
    "check_interval_seconds": 10
  },
  "output": {
    "results_file": "upload_results.json",
    "log_file": "upload_progress.log"
  }
}
```

## Error Handling

### Queue Full (HTTP 429)

If API queue is full, the script automatically retries:
```
⚠ Queue full (429). Retrying in 5 seconds...
```

Up to 3 retries by default (configurable via `--retry-attempts`).

### Connection Errors

Script validates API connection before starting:
```
✗ Could not connect to API at http://localhost:8000
✗ API connection timed out
```

### File Not Found

```
✗ Folder does not exist: /path/to/folder
✗ No files found matching pattern '*.txt'
```

## Monitoring Parsing Progress

After upload completes, script monitors the parsing state:

```
============================================================
Monitoring parsing progress for 5 files...
Max wait time: 30 minutes, Check interval: 10 seconds
============================================================

[Check 1] Status at 10:30:50
  File ID 123: pending
  Waiting... (1 files still processing, elapsed: 0.2min)

[Check 2] Status at 10:31:00
  ✓ File ID 123: DONE
```

### Parsing States

- **pending** - File uploaded, waiting to be processed
- **queued** - File in processing queue
- **parsing** - Currently being parsed
- **done** - Successfully parsed
- **failed** - Parsing failed
- **timeout** - Timeout waiting for completion

## Examples

### Example 1: Upload all PDFs with tags

```bash
python upload_files.py \
  --folder ./important_docs \
  --tags urgent,legal \
  --pattern "*.pdf"
```

### Example 2: Upload from multiple folders with config

**config.json:**
```json
{
  "api_url": "http://localhost:8000",
  "folders": [
    {
      "path": "./contracts",
      "tags": ["legal"],
      "pattern": "*.pdf"
    },
    {
      "path": "./reports",
      "tags": ["report"],
      "pattern": "*.xlsx"
    }
  ],
  "upload_settings": {
    "monitor_parsing": true,
    "max_wait_minutes": 60
  }
}
```

**Run:**
```bash
python upload_with_config.py --config config.json
```

### Example 3: Quick test without monitoring

```bash
python upload_files.py \
  --folder ./test \
  --no-monitor-parsing \
  --pattern "test_*.txt"
```

### Example 4: Batch upload with detailed logging

```bash
python upload_files.py \
  --folder ./batch_data \
  --output-file batch_$(date +%Y%m%d).json \
  --max-wait-minutes 120
```

## Troubleshooting

### API Connection Issues

1. Verify API is running:
   ```bash
   curl http://localhost:8000/docs
   ```

2. Check custom API URL:
   ```bash
   python upload_files.py \
     --folder ./docs \
     --api-url http://your-api-url:port
   ```

### Queue Full Errors

If getting many 429 errors:
- Reduce upload concurrency (upload fewer files at once)
- Increase `--max-wait-minutes`
- Check parsing backlog on server

### Files Not Found

1. Verify folder path:
   ```bash
   ls -la ./documents
   ```

2. Check pattern:
   ```bash
   python upload_files.py --folder ./documents --pattern "*.txt"
   ```

3. Try recursive search:
   ```bash
   python upload_files.py --folder ./documents --recursive
   ```

## Notes

- Scripts are **standalone** - can run from anywhere
- No project dependencies except `requests`
- All operations logged to `upload_progress.log`
- Results saved as JSON for further processing
- Supports Windows, macOS, and Linux
- Safe to run multiple instances (each creates own log)

## Environment Variables

Optional environment variables:

```bash
export UPLOADS_API_URL="http://localhost:8000"
export UPLOADS_TIMEOUT="30"
```

Can be used instead of command-line options for defaults.

## License

Same as parent project.
