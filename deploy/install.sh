#!/usr/bin/env bash
# Installs CAVE on Debian 13 with Docker Compose. Run it from the repository root:
#   deploy/install.sh [--profiles mqtt,scripts] [--yes] [--dry-run]
# A re-run changes nothing that exists: data, config, secrets, Mosquitto users and .env are all kept.
# --dry-run writes .env, secrets/ and the first config, and touches no Docker (the tests use it).
# Test hooks: CAVE_INSTALL_ROOT (where to install, default the repository root), CAVE_SKIP_CHOWN=1.
set -euo pipefail

PROFILES="mqtt,scripts"
YES=0
DRY=0
CORE_UID=10001       # cave inside its container
MOSQUITTO_UID=1883   # mosquitto inside the eclipse-mosquitto image

usage() { sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; }
say() { printf '%s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profiles) PROFILES="${2:?--profiles needs a value, like mqtt,scripts}"; shift 2 ;;
    --yes) YES=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option $1 (try --help)" ;;
  esac
done
for p in ${PROFILES//,/ }; do
  [[ $p == mqtt || $p == scripts ]] || die "unknown profile $p: use mqtt, scripts or both"
done
has_profile() { [[ ",$PROFILES," == *",$1,"* ]]; }

ROOT="${CAVE_INSTALL_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT"

as_root() { if [[ $(id -u) -eq 0 ]]; then "$@"; else sudo "$@"; fi; }
own() {  # own UID MODE PATH...: ownership the containers need (Review Focus 3)
  local uid=$1 mode=$2; shift 2
  if [[ -n ${CAVE_SKIP_CHOWN:-} ]]; then
    [[ $mode == - ]] || chmod "$mode" "$@"
    return 0
  fi
  # as root: on a re-run, or after mosquitto_passwd, the file already belongs to the container's uid
  [[ $mode == - ]] || as_root chmod "$mode" "$@"
  as_root chown -R "$uid:$uid" "$@"
}

# ---- 1. Docker ----
if [[ $DRY -eq 0 ]] && ! docker compose version >/dev/null 2>&1; then
  die "Docker Compose isn't installed. On Debian 13: sudo apt install docker.io docker-compose, then add yourself
to the docker group (sudo usermod -aG docker \$USER) and sign in again. See docs/install/debian.md."
fi
if [[ $YES -eq 0 ]]; then
  read -r -p "Install CAVE in $ROOT with profiles $PROFILES? [y/N] " answer
  [[ $answer == [yY]* ]] || exit 1
fi

# ---- 2. The LAN, for "Local network only" and the certificate ----
ip2int() { local IFS=.; local a b c d; read -r a b c d <<<"$1"; echo $(( (a << 24) | (b << 16) | (c << 8) | d )); }
int2ip() { local n=$1; echo "$(( (n >> 24) & 255 )).$(( (n >> 16) & 255 )).$(( (n >> 8) & 255 )).$(( n & 255 ))"; }

detect_lan() {
  local route src dev cidr prefix mask
  route=$(ip -4 route get 192.0.2.1 2>/dev/null) || die "can't find this machine's network address (no route)."
  src=$(sed -n 's/.* src \([0-9.]*\).*/\1/p' <<<"$route")
  dev=$(sed -n 's/.* dev \([^ ]*\).*/\1/p' <<<"$route")
  case "$dev" in
    docker*|br-*|veth*)
      die "this machine's default route goes through a Docker network ($dev), which isn't your LAN. Set
CAVE_LOCAL_RANGES to your LAN range, like 192.168.1.0/24, and CAVE_HOST_IPS to this machine's LAN address,
then run this again, for example: CAVE_LOCAL_RANGES=192.168.1.0/24 CAVE_HOST_IPS=192.168.1.20 deploy/install.sh" ;;
  esac
  cidr=$(ip -4 -o addr show dev "$dev" | awk -v s="$src" '{ split($4, a, "/"); if (a[1] == s) print $4 }' | head -n 1)
  [[ -n $src && -n $cidr ]] || die "can't read the address of $dev; set CAVE_LOCAL_RANGES and CAVE_HOST_IPS by hand."
  prefix=${cidr#*/}
  mask=$(( prefix == 0 ? 0 : (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF ))
  LAN_RANGE="$(int2ip $(( $(ip2int "$src") & mask )))/$prefix"
  HOST_IP=$src
}

if [[ ! -f .env ]]; then
  if [[ -n ${CAVE_LOCAL_RANGES:-} && -n ${CAVE_HOST_IPS:-} ]]; then
    LAN_RANGE=$CAVE_LOCAL_RANGES HOST_IP=$CAVE_HOST_IPS
  else
    detect_lan
  fi
fi

# ---- 3. Folders ----
mkdir -p data config/scripts secrets
has_profile mqtt && mkdir -p data/mosquitto

# ---- 4. Secrets: random, private, never in .env ----
secret() { od -An -tx1 -N32 /dev/urandom | tr -d ' \n'; }  # 32 random bytes as 64 hex characters
new_secret() {  # new_secret FILE UID: only if missing
  [[ -e $1 ]] && return 0
  (umask 077; secret >"$1")
  own "$2" 0400 "$1"
}
new_secret secrets/runner_token "$CORE_UID"
new_secret secrets/mqtt_password "$CORE_UID"
if [[ ! -e secrets/mosquitto_passwd ]]; then
  : >secrets/mosquitto_passwd
  own "$MOSQUITTO_UID" 0400 secrets/mosquitto_passwd
fi

# ---- 5. .env: settings only, no secrets. First, because compose.yaml reads it (env_file) ----
if [[ ! -f .env ]]; then
  runner_url=""
  has_profile scripts && runner_url="http://script-runner:8099"
  cat >.env <<EOF
# Written by deploy/install.sh. Settings only: secrets live in secrets/. Edit and run docker compose up -d.
COMPOSE_PROFILES=$PROFILES
CAVE_LOCAL_RANGES=$LAN_RANGE
CAVE_HOST_IPS=$HOST_IP
CAVE_HOSTNAMES=$(hostname) $(hostname).local localhost
CAVE_RUNNER_URL=$runner_url
EOF
else
  say "Keeping the existing .env (edit it to change profiles or ranges)."
fi

# ---- 6. MQTT ----
if has_profile mqtt && [[ ! -e config/mqtt.yaml ]]; then
  cat >config/mqtt.yaml <<'EOF'
# The broker CAVE signs in to. The password is in secrets/mqtt_password, never here.
broker:
  host: mosquitto
  port: 1883
  username: cave
EOF
fi
[[ -n ${CAVE_SKIP_CHOWN:-} ]] || as_root chown -R "$CORE_UID:$CORE_UID" data config
has_profile mqtt && own "$MOSQUITTO_UID" - data/mosquitto

if has_profile mqtt && [[ $DRY -eq 0 ]] && ! as_root grep -q '^cave:' secrets/mosquitto_passwd; then
  # The same pinned image Compose runs. The password goes in on stdin and is hashed in a scratch file
  # (mosquitto_passwd -U), so it's never a command-line argument that ps or docker inspect would show.
  image=$(docker compose config --images mosquitto)
  [[ -n $image ]] || die "can't read the Mosquitto image from compose.yaml."
  printf 'cave:%s\n' "$(as_root cat secrets/mqtt_password)" |
    as_root docker run --rm -i -v "$ROOT/secrets/mosquitto_passwd:/passwd" "$image" \
      sh -c 'umask 077 && cat >/tmp/p && mosquitto_passwd -U /tmp/p && cat /tmp/p >>/passwd'
  own "$MOSQUITTO_UID" 0400 secrets/mosquitto_passwd
fi

if [[ $DRY -eq 1 ]]; then
  say "Dry run: wrote .env, secrets/ and config/ in $ROOT. Docker wasn't touched."
  exit 0
fi

# ---- 7. Build and start ----
docker compose build
docker compose up -d
say "Waiting for CAVE to start…"
for _ in $(seq 1 60); do
  state=$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q cave)" 2>/dev/null || true)
  [[ $state == healthy ]] && break
  sleep 2
done
[[ ${state:-} == healthy ]] || die "CAVE didn't become healthy within 2 minutes. See: docker compose logs cave"

docker compose logs cave | grep -E "running at|fingerprint|setup code" | sed 's/^[^|]*| //' || true
say "Done. Open the address above, check the certificate fingerprint matches, and enter the setup code."
has_profile mqtt && say "Devices sign in to MQTT at this machine, port 1883. Add a user per device:
  docker run --rm -it -v \"$ROOT/secrets/mosquitto_passwd:/passwd\" $(docker compose config --images mosquitto) mosquitto_passwd /passwd <device-name>
  then: docker compose restart mosquitto"
exit 0
