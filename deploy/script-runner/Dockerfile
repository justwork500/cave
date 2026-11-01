# cave-script-runner: runs PowerShell 7, Python 3 and Bash scripts for CAVE, and nothing else.
# Built by compose.yaml (profile `scripts`); by hand, from the repository root:
#   docker build -f deploy/script-runner/Dockerfile -t cave-script-runner:local .
#
# The runner runs as root inside the container only so it can start each script as the separate `script`
# user (uid 10002): scripts then can't read the runner's memory, environment or token file. compose.yaml
# adds the rest: read-only root, cap_drop ALL plus SETUID/SETGID/KILL/CHOWN, memory and CPU limits,
# scripts mounted read-only, no Docker socket, the token as a secret file, and a network only cave shares.

FROM python:3.13-slim-trixie@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

# PowerShell 7.6 (LTS) from its GitHub release, the same way on amd64 and arm64, checked before unpacking.
# The SHA-256 values are the release assets' digests.
ARG TARGETARCH
ARG PWSH_VERSION=7.6.9
ARG PWSH_SHA256_AMD64=1da6d6d6035d651f20e70ddee7c4c15ac6ab8b9fb40ee92240d91263f28a884b
ARG PWSH_SHA256_ARM64=02eb9991af447c7e7fe881acde195961afd397c40b8eb1c2b3856b84ec2d85f2
RUN set -eu; \
    case "$TARGETARCH" in \
      amd64) arch=x64; sum="$PWSH_SHA256_AMD64" ;; \
      arm64) arch=arm64; sum="$PWSH_SHA256_ARM64" ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac; \
    apt-get update; \
    apt-get install -y --no-install-recommends bash curl ca-certificates libicu76 libgssapi-krb5-2 zlib1g; \
    curl -fsSLo /tmp/pwsh.tar.gz \
      "https://github.com/PowerShell/PowerShell/releases/download/v${PWSH_VERSION}/powershell-${PWSH_VERSION}-linux-${arch}.tar.gz"; \
    echo "${sum}  /tmp/pwsh.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/microsoft/powershell/7; \
    tar -xzf /tmp/pwsh.tar.gz -C /opt/microsoft/powershell/7; \
    chmod +x /opt/microsoft/powershell/7/pwsh; \
    ln -s /opt/microsoft/powershell/7/pwsh /usr/bin/pwsh; \
    rm /tmp/pwsh.tar.gz; \
    apt-get purge -y curl; apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

COPY core /src/core
RUN pip install --no-cache-dir /src/core && rm -rf /src

RUN useradd --uid 10002 --no-create-home --shell /usr/sbin/nologin script
WORKDIR /work
EXPOSE 8099
ENTRYPOINT ["python", "-m", "cave.runner", "--scripts", "/scripts", "--script-uid", "10002", \
            "--token-file", "/run/secrets/runner_token"]
