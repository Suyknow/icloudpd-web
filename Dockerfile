# Stage 1: Build Frontend
FROM node:20-slim AS frontend

WORKDIR /app/web

# Copy package files and install dependencies
COPY web/package*.json ./
RUN npm ci

# Copy the rest of the frontend source
COPY web/ .

# Build: outputs to ../src/icloudpd_web/web_dist (relative to /app/web)
RUN npm run build

# Stage 2: Runtime
FROM python:3.12.8-slim

# curl is used by HEALTHCHECK; gosu drops root -> appuser in the entrypoint.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl gosu \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend source and metadata
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

# Copy built frontend assets to a temp location OUTSIDE src/ so hatchling's
# `packages` directive won't also include them (causing duplicate-path error
# with force-include when .git is absent in Docker).
COPY --from=frontend /app/src/icloudpd_web/web_dist ./web_dist

# Point wheel force-include at the temp location, then build & install.
RUN sed -i 's|"src/icloudpd_web/web_dist" = "icloudpd_web/web_dist"|"web_dist" = "icloudpd_web/web_dist"|' pyproject.toml
RUN pip install --no-cache-dir .

# Install entrypoint with execute bit BEFORE switching to non-root user.
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Non-root user. Data lives under /data (mounted volume); downloads under
# /downloads (user-mounted). Both directories are pre-created and chown'd
# so a simple `-v host:/data` works without host-side `chown` gymnastics.
# The container starts as root: the entrypoint remaps appuser to PUID/PGID,
# chowns the mount points, then drops privileges via gosu.
RUN useradd -m -u 1000 appuser \
 && mkdir -p /data /downloads \
 && chown -R appuser:appuser /data /downloads

WORKDIR /home/appuser

# Declare volumes so users see them in `docker inspect` and orchestrators
# auto-create host paths.
VOLUME ["/data", "/downloads"]

EXPOSE 5000

# Defaults. The entrypoint only forwards flags for vars that are set, so
# unsetting any of these returns you to the CLI's built-in defaults.
ENV HOST=0.0.0.0 \
    PORT=5000 \
    DATA_DIR=/data

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/auth/status" >/dev/null || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
