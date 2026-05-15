#!/usr/bin/env bash
set -euo pipefail

LABEL="ai.openclaw.findmy.geopulse-stack"
LABEL_BRIDGE="ai.openclaw.findmy.geopulse-bridge"
ROOT="/Users/mh/Documents/Playground/openclaw-apple-findmy-skill"
STATE="/Users/mh/.openclaw/workspace/state/apple-find-my/geopulse"
LAUNCH="$HOME/Library/LaunchAgents"
COMPOSE="$STATE/docker-compose.yml"
ENV="$STATE/.env"
BRIDGE_ENV="$STATE/bridge.env"
PYTHON="/Users/mh/.openclaw/workspace/.venvs/findmy-key-extractor/bin/python"
BRIDGE="$ROOT/scripts/geopulse_findmy_bridge.py"
BOOTSTRAP="$ROOT/scripts/geopulse_bootstrap_local.py"

mkdir -p "$STATE/keys" "$STATE/import-drop" "$LAUNCH"
chmod +x "$BRIDGE"
chmod +x "$BOOTSTRAP"

if [[ ! -f "$ENV" ]]; then
  POSTGRES_PASSWORD="$(openssl rand -base64 24 | tr -d '\n')"
  cat > "$ENV" <<ENV
GEOPULSE_VERSION=1.29.1
GEOPULSE_UI_URL=http://localhost:18085
GEOPULSE_CORS_ENABLED=false
GEOPULSE_AUTH_SECURE_COOKIES=false
GEOPULSE_BACKEND_URL=http://geopulse-backend:8080
GEOPULSE_POSTGRES_HOST=geopulse-postgres
GEOPULSE_POSTGRES_PORT=5432
GEOPULSE_POSTGRES_DB=geopulse
GEOPULSE_POSTGRES_USERNAME=geopulse-user
GEOPULSE_POSTGRES_PASSWORD=$POSTGRES_PASSWORD
GEOPULSE_ADMIN_EMAIL=
GEOPULSE_MQTT_ENABLED=false
GEOPULSE_AUTH_GUEST_ROOT_REDIRECT_TO_LOGIN_ENABLED=false
CLIENT_MAX_BODY_SIZE=1000M
OSM_RESOLVER="127.0.0.11 8.8.8.8"
ENV
  chmod 0600 "$ENV"
fi

if [[ ! -f "$BRIDGE_ENV" ]]; then
  SOURCE_PASSWORD="$(openssl rand -base64 24 | tr -d '\n')"
  cat > "$BRIDGE_ENV" <<ENV
GEOPULSE_OWNTRACKS_ENDPOINT=http://127.0.0.1:18085/api/owntracks
GEOPULSE_OWNTRACKS_USERNAME=findmy
GEOPULSE_OWNTRACKS_PASSWORD=$SOURCE_PASSWORD
ENV
  chmod 0600 "$BRIDGE_ENV"
fi

cat > "$COMPOSE" <<'YAML'
services:
  geopulse-keygen:
    image: alpine:latest
    container_name: openclaw-geopulse-keygen
    restart: "no"
    volumes:
      - /Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/keys:/keys
    command:
      - sh
      - -ec
      - |
        set -e
        mkdir -p /keys
        if [ ! -f /keys/jwt-private-key.pem ] || [ ! -f /keys/jwt-public-key.pem ]; then
          command -v openssl >/dev/null 2>&1 || apk add --no-cache openssl
          openssl genpkey -algorithm RSA -out /keys/jwt-private-key.pem
          openssl rsa -pubout -in /keys/jwt-private-key.pem -out /keys/jwt-public-key.pem
          chmod 600 /keys/jwt-private-key.pem /keys/jwt-public-key.pem
        fi
        if [ ! -f /keys/ai-encryption-key.txt ]; then
          command -v openssl >/dev/null 2>&1 || apk add --no-cache openssl
          openssl rand -base64 32 > /keys/ai-encryption-key.txt
          chmod 600 /keys/ai-encryption-key.txt
        fi

  geopulse-postgres:
    image: imresamu/postgis:17-3.5-alpine
    container_name: openclaw-geopulse-postgres
    restart: unless-stopped
    env_file:
      - /Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/.env
    environment:
      POSTGRES_USER: ${GEOPULSE_POSTGRES_USERNAME:-geopulse-user}
      POSTGRES_PASSWORD: ${GEOPULSE_POSTGRES_PASSWORD:-change-me}
      POSTGRES_DB: ${GEOPULSE_POSTGRES_DB:-geopulse}
    volumes:
      - /Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${GEOPULSE_POSTGRES_USERNAME:-geopulse-user} -d ${GEOPULSE_POSTGRES_DB:-geopulse}"]
      interval: 5s
      timeout: 5s
      retries: 20

  geopulse-backend:
    image: tess1o/geopulse-backend:1.29.1-native-compat
    container_name: openclaw-geopulse-backend
    restart: unless-stopped
    mem_limit: 512m
    mem_reservation: 128m
    env_file:
      - /Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/.env
    environment:
      GEOPULSE_POSTGRES_URL: jdbc:postgresql://geopulse-postgres:5432/geopulse
    volumes:
      - /Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/keys:/app/keys
      - /Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/import-drop:/data/geopulse-import
    depends_on:
      geopulse-keygen:
        condition: service_completed_successfully
      geopulse-postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8080/api/health || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 30
      start_period: 10s

  geopulse-ui:
    image: tess1o/geopulse-ui:1.29.1
    container_name: openclaw-geopulse-ui
    restart: unless-stopped
    env_file:
      - /Users/mh/.openclaw/workspace/state/apple-find-my/geopulse/.env
    ports:
      - "127.0.0.1:18085:80"
    depends_on:
      geopulse-backend:
        condition: service_healthy
YAML

set -a
source "$ENV"
set +a
docker compose -f "$COMPOSE" up -d

cat > "$LAUNCH/$LABEL.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/homebrew/bin/docker</string>
    <string>compose</string>
    <string>-f</string>
    <string>$COMPOSE</string>
    <string>up</string>
    <string>-d</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$STATE/stack-launch.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$STATE/stack-launch.stderr.log</string>
  <key>WorkingDirectory</key>
  <string>$STATE</string>
</dict>
</plist>
PLIST

plutil -lint "$LAUNCH/$LABEL.plist"
launchctl bootout "gui/$(id -u)" "$LAUNCH/$LABEL.plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH/$LABEL.plist"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

cat > "$LAUNCH/$LABEL_BRIDGE.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL_BRIDGE</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$BRIDGE</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>StandardOutPath</key>
  <string>$STATE/bridge-launch.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$STATE/bridge-launch.stderr.log</string>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
</dict>
</plist>
PLIST

plutil -lint "$LAUNCH/$LABEL_BRIDGE.plist"
launchctl bootout "gui/$(id -u)" "$LAUNCH/$LABEL_BRIDGE.plist" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH/$LABEL_BRIDGE.plist"
sleep 2
"$PYTHON" "$BOOTSTRAP" --print-summary
launchctl kickstart -k "gui/$(id -u)/$LABEL_BRIDGE"
echo "GeoPulse UI: http://127.0.0.1:18085"
