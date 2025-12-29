# Docker Setup Guide

## Quick Start

### 1. Prerequisites
- Docker Desktop installed and running
- Docker Compose v2.0+ (included in Docker Desktop)
- At least 4GB RAM available for containers

### 2. Start All Services
```bash
# From repository root
docker-compose up -d

# Or with build (if you made changes to the app)
docker-compose up -d --build
```

### 3. Verify Services are Running
```bash
# Check all containers
docker ps

# Should show:
# - final-bi-mysql (running)
# - final-bi-qdrant (running)
# - final-bi-api (running)
```

### 4. Verify Health
```bash
# FastAPI health check
curl http://localhost:8000/docs

# MySQL health check
mysql -h 127.0.0.1 -u bi_user -pbi_password_123 documents -e "SELECT 1;"

# Qdrant health check
curl http://localhost:6333/health
```

### 5. Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| FastAPI | http://localhost:8000 | API endpoints |
| FastAPI Docs | http://localhost:8000/docs | Swagger UI |
| FastAPI ReDoc | http://localhost:8000/redoc | ReDoc UI |
| MySQL | localhost:3306 | Database |
| Qdrant | http://localhost:6333 | Vector DB |

## Service Details

### MySQL (Docker Service: `mysql`)
- **Container Name**: final-bi-mysql
- **Port**: 3306
- **Root Password**: root_password_123
- **User**: bi_user
- **Password**: bi_password_123
- **Database**: documents
- **Volumes**: mysql_data (persistent storage)
- **Health Check**: Every 10 seconds, max 10 retries

### Qdrant (Docker Service: `qdrant`)
- **Container Name**: final-bi-qdrant
- **Ports**: 6333 (REST API), 6334 (gRPC)
- **Volumes**: qdrant_storage (persistent storage)
- **Health Check**: Every 5 seconds, max 5 retries

### FastAPI App (Docker Service: `fastapi-app`)
- **Container Name**: final-bi-api
- **Port**: 8000
- **Environment Variables**: Set from docker-compose.yml
- **Health Check**: Every 30 seconds (checks /docs endpoint)
- **Volume Mount**: ./src (hot reload enabled)

## Common Commands

### Start Services
```bash
# Start all services in background
docker-compose up -d

# Start with logs visible
docker-compose up

# Start specific service
docker-compose up -d mysql qdrant
```

### View Logs
```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f fastapi-app
docker-compose logs -f mysql
docker-compose logs -f qdrant

# Tail last 100 lines
docker-compose logs -f --tail=100 fastapi-app
```

### Stop Services
```bash
# Stop all services (containers remain)
docker-compose stop

# Stop and remove containers
docker-compose down

# Remove containers, networks, and volumes
docker-compose down -v
```

### Rebuild and Restart
```bash
# Rebuild image and restart
docker-compose up -d --build fastapi-app

# Rebuild all images
docker-compose build --no-cache

# Then restart
docker-compose up -d
```

### Access Container Shell
```bash
# FastAPI container
docker-compose exec fastapi-app bash

# MySQL container
docker-compose exec mysql bash

# Qdrant container (no bash, minimal image)
docker-compose exec qdrant /bin/sh
```

## Database Initialization

### First Time Setup
When MySQL starts for the first time, it automatically:
1. Creates the `documents` database
2. Creates tables (via your Python code on first app startup)

### Manual Database Access
```bash
# Connect to MySQL
docker-compose exec mysql mysql -u bi_user -pbi_password_123 documents

# Example queries:
# SHOW TABLES;
# DESCRIBE files;
# SELECT COUNT(*) FROM files;
```

### Backup Database
```bash
# Dump database to file
docker-compose exec mysql mysqldump -u bi_user -pbi_password_123 documents > backup.sql

# Restore from backup
docker-compose exec -T mysql mysql -u bi_user -pbi_password_123 documents < backup.sql
```

## Testing the Setup

### 1. Upload a File
```bash
curl -X POST "http://localhost:8000/files/upload" \
  -F "file=@/path/to/test.pdf"

# Response: {"file_id": 1, "parsing_scheduled": true, ...}
```

### 2. Check Parsing Status
```bash
curl "http://localhost:8000/files/1/parsing-status"

# Response: {"file_id": 1, "parsing_state": "done"}
```

### 3. Check Vectors Stored
```bash
curl "http://localhost:8000/search/files/1/vector-count"

# Response: {"file_id": 1, "vector_count": 5}
```

### 4. Semantic Search
```bash
curl "http://localhost:8000/search/semantic?q=your+search+query&limit=5"

# Returns matching documents with semantic similarity scores
```

### 5. Hybrid Search
```bash
curl "http://localhost:8000/search/hybrid?q=your+search+query&limit=10"

# Returns combined semantic + keyword results
```

## Environment Variables

Create a `.env` file (copy from `.env.example`) to override defaults:

```bash
cp .env.example .env
# Edit .env as needed
docker-compose --env-file .env up -d
```

Or set directly in `docker-compose.yml` environment section.

## Troubleshooting

### Container Won't Start
```bash
# Check logs
docker-compose logs -f fastapi-app

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

### MySQL Connection Error
```bash
# Verify MySQL is healthy
docker-compose ps

# Check MySQL logs
docker-compose logs mysql

# Wait longer for MySQL to be ready (~30 seconds on first start)
docker-compose up -d
sleep 30
docker-compose logs fastapi-app
```

### Qdrant Connection Error
```bash
# Check Qdrant health
curl http://localhost:6333/health

# Check Qdrant logs
docker-compose logs qdrant

# Restart Qdrant
docker-compose restart qdrant
```

### Port Already in Use
```bash
# Change port in docker-compose.yml
# Find the service and change the port mapping:
# ports:
#   - "3307:3306"  # Use 3307 instead of 3306
```

### Reset Everything
```bash
# Remove all containers, volumes, and networks
docker-compose down -v

# Remove images
docker image rm final-bi-mysql final-bi-qdrant final-bi-api:latest

# Start fresh
docker-compose up -d --build
```

## Performance Tuning

### MySQL
- **memory**: Increase in docker-compose if you have large datasets
- **max_connections**: Adjust in environment if needed

### Qdrant
- **storage**: Mounted as volume for persistence
- **snapshot_interval**: For backup strategies

### FastAPI
- **workers**: Adjust WORKERS environment variable
- **reload**: Disable in production (set RELOAD=false)

## Production Considerations

### Before Deploying to Production

1. **Security**
   - Change MySQL root password
   - Set MYSQL_PASSWORD to a strong value
   - Enable Qdrant API key (set QDRANT_API_KEY)
   - Use environment secrets instead of env files

2. **Performance**
   - Set RELOAD=false in FastAPI
   - Increase WORKERS (e.g., 4 or 8)
   - Add more resources (CPU, memory)

3. **Persistence**
   - Ensure volumes are backed up
   - Use named volumes (already configured)
   - Consider external storage (AWS EBS, etc.)

4. **Monitoring**
   - Add health checks for all services
   - Set up logging aggregation
   - Monitor disk usage for mysql_data and qdrant_storage volumes

5. **Networking**
   - Don't expose ports directly; use reverse proxy
   - Use environment secrets for credentials
   - Enable TLS/HTTPS

### Production docker-compose.yml Adjustments
```yaml
# Disable reload, set workers
command: uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4

# Add resource limits
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 4G
    reservations:
      cpus: '1'
      memory: 2G

# Use secrets instead of environment variables
environment:
  MYSQL_PASSWORD_FILE: /run/secrets/mysql_password
secrets:
  mysql_password:
    file: ./secrets/mysql_password.txt
```

## Cleaning Up

### Remove Stopped Containers
```bash
docker container prune -f
```

### Remove Unused Volumes
```bash
docker volume prune -f
```

### Remove Unused Images
```bash
docker image prune -f
```

### Remove Everything (WARNING: Deletes data!)
```bash
docker-compose down -v
docker system prune -a -f
```

## Additional Resources

- Docker Compose Docs: https://docs.docker.com/compose/
- Docker Best Practices: https://docs.docker.com/develop/dev-best-practices/
- MySQL Docker Image: https://hub.docker.com/_/mysql
- Qdrant Docker: https://hub.docker.com/r/qdrant/qdrant

## Support

If you encounter issues:
1. Check service logs: `docker-compose logs -f <service>`
2. Verify health: `docker-compose ps`
3. Check port availability: `lsof -i :6333`, `lsof -i :3306`, `lsof -i :8000`
4. Rebuild fresh: `docker-compose down -v && docker-compose up -d --build`
