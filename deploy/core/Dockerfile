# cave-core: the CAVE server with the console built in. Built by compose.yaml; by hand, from the repository root:
#   docker build -f deploy/core/Dockerfile -t cave-core:local .

# ---- the console (React), built once and copied into the Python image ----
FROM node:24-trixie-slim@sha256:54f84b4cf8432b21aaffd5d3ce8d41e12cea0d10d33c09d2f3c9879d49d6b446 AS console
WORKDIR /src
# schemas/ is read by the recipe tests; vite writes the build to ../core/cave/web/console
COPY schemas schemas
COPY console console
WORKDIR /src/console
RUN corepack enable && pnpm install --frozen-lockfile && pnpm build

# ---- the server ----
FROM python:3.13-slim-trixie@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb
COPY core /src/core
COPY --from=console /src/core/cave/web/console /src/core/cave/web/console
RUN pip install --no-cache-dir /src/core && rm -rf /src \
    && groupadd --gid 10001 cave && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin cave \
    && mkdir -p /data /config && chown cave:cave /data /config
ENV PYTHONUNBUFFERED=1 CAVE_IN_CONTAINER=1
USER cave
WORKDIR /data
EXPOSE 8443
HEALTHCHECK --interval=30s --timeout=6s --start-period=20s CMD ["python", "-m", "cave", "health"]
ENTRYPOINT ["python", "-m", "cave", "serve", "--host", "0.0.0.0", "--port", "8443", "--data", "/data", \
            "--config", "/config"]
