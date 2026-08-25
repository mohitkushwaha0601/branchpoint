FROM node:20-slim

WORKDIR /app

# Install Python3 and curl (needed for setup script and API calls)
RUN apt-get update && apt-get install -y \
    python3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create volume directory for SQLite persistence
RUN mkdir -p /data

# TrueForge will store SQLite here (configure via environment if supported)
ENV TRUEFORGE_DATA_DIR=/data

# Pre-install TrueForge to cache the download
RUN npx @truefoundry/trueforge@0.1.4 --version || true

# Copy initialization script
COPY scripts/railway_init.sh /app/railway_init.sh
COPY config/branchpoint-mcp-server.json /app/config/branchpoint-mcp-server.json
RUN chmod +x /app/railway_init.sh

EXPOSE 8790

# Simple start - just run TrueForge
# Initialization script can be run manually after deployment if needed
CMD ["npx", "@truefoundry/trueforge@0.1.4"]
