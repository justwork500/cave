# cave-script-runner: runs PowerShell 7, Python 3 and Bash scripts for CAVE, and nothing else.
# Build from the repository root:  docker build -f deploy/script-runner/Dockerfile -t cave-script-runner .
#
# The runner runs as root inside the container only so it can start each script as the separate `script`
# user (uid 10002): scripts then can't read the runner's memory, environment or token file.
# Compose (Phase 1 plan 7) must add: read_only: true, tmpfs: [/tmp, /work], cap_drop: [ALL],
# cap_add: [SETUID, SETGID, KILL, CHOWN], mem_limit, cpus, a read-only ./config/scripts:/scripts mount,
# no Docker socket, and the runner token as a Compose secret at /run/secrets/cave_runner_token (mode 0400),
# shared with cave-core. Only cave-core should be able to reach port 8099.
#
# shortcut: not built or smoke-tested yet (no Docker on the dev machine); Phase 1 plan 7 builds it,
# pins the base image digest, and checks arm64 (Microsoft documents amd64 packages for Debian 13).

FROM python:3.13-slim-trixie

# PowerShell 7 from Microsoft's package repository, as Microsoft Learn's "Install PowerShell on Debian" describes
RUN apt-get update \
    && apt-get install -y --no-install-recommends bash wget ca-certificates \
    && . /etc/os-release \
    && wget -q "https://packages.microsoft.com/config/debian/${VERSION_ID}/packages-microsoft-prod.deb" \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends powershell \
    && apt-get purge -y wget \
    && rm -rf /var/lib/apt/lists/*

COPY core /src/core
RUN pip install --no-cache-dir /src/core && rm -rf /src

RUN useradd --uid 10002 --no-create-home --shell /usr/sbin/nologin script
WORKDIR /work
EXPOSE 8099
ENTRYPOINT ["python", "-m", "cave.runner", "--scripts", "/scripts", "--script-uid", "10002", \
            "--token-file", "/run/secrets/cave_runner_token"]
