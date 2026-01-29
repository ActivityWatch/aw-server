# syntax=docker/dockerfile:1

# Stage 1: Build the WebUI
FROM node:20-alpine AS frontend-builder

WORKDIR /build

# Copy WebUI source
# Note: Context is the monorepo root
COPY aw-server/aw-webui ./aw-server/aw-webui

# Install dependencies and build
WORKDIR /build/aw-server/aw-webui
RUN npm ci && npm run build

# Stage 2: Setup Python environment and run
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Postgres adapter
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and install aw-core (from root context)
COPY aw-core /app/aw-core
RUN pip install /app/aw-core

# Copy and install aw-client (from root context)
COPY aw-client /app/aw-client
RUN pip install /app/aw-client

# Copy aw-server source
COPY aw-server /app/aw-server

# Copy built WebUI assets to the static folder expected by aw-server
COPY --from=frontend-builder /build/aw-server/aw-webui/dist /app/aw-server/aw_server/static

# Install aw-server
RUN pip install /app/aw-server

# Cleanup source files to reduce image size (optional, but good practice)
# We keep them if we want to run tests or run from source, but pip install installed them to site-packages.
# We will run from the installed module.

# Expose the default port
EXPOSE 5600

# Set the entrypoint
# We use shell form to allow expansion of environment variables if needed, 
# but exec form is better for signal handling. 
# We'll default to the module execution.
ENTRYPOINT ["python", "-m", "aw_server"]

# Default command arguments (can be overridden)
CMD ["--host", "0.0.0.0", "--storage", "postgres"]
