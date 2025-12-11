#!/usr/bin/env python3
"""
Modular CPU AI Stack - Version 0.1.6 generator

This script (re)creates the v0.1.6 stack layout with:
- Modular installer (LLM, Image Gen, TTS)
- Ollama model manager
- Health check + clean scripts
- docker-compose.yml
- README, CHANGELOG, session restart prompt
- setup_oauth.sh helper
- ZIP archive of the generated directory

All actions/errors are logged to:
- create_stack_actions.log
- create_stack_errors.log
"""

import datetime
import textwrap
import traceback
from pathlib import Path
import os
import stat
import zipfile
import sys

VERSION = "0.1.6"
STACK_DIR_NAME = "modular_cpu_ai_stack_v0_1_6"

ROOT_DIR = Path(__file__).resolve().parent
ACTIONS_LOG = ROOT_DIR / "create_stack_actions.log"
ERRORS_LOG = ROOT_DIR / "create_stack_errors.log"


def timestamp_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _append_log(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def log_info(message: str) -> None:
    ts = timestamp_utc()
    line = f"{ts} [INFO] [setup_stack.py]: {message}\n"
    _append_log(ACTIONS_LOG, line)
    print(line, end="")


def log_error(message: str) -> None:
    ts = timestamp_utc()
    line = (
        f"{ts} [ERROR] [setup_stack.py]: {message} "
        f"(see {ERRORS_LOG} for details)\n"
    )
    _append_log(ERRORS_LOG, line)
    print(line, end="", file=sys.stderr)


def safe_write(path: Path, content: str) -> None:
    """Write a text file, creating parents. Content is dedented and stripped."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = textwrap.dedent(content).lstrip("\n")
        path.write_text(text, encoding="utf-8")
        log_info(f"Wrote file: {path}")
    except Exception as exc:
        log_error(f"Failed to write {path}: {exc}")
        raise


def make_executable(path: Path) -> None:
    """Mark a file as executable for user/group/others."""
    try:
        mode = path.stat().st_mode
        path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        log_info(f"Marked executable: {path}")
    except Exception as exc:
        log_error(f"Failed to chmod +x {path}: {exc}")
        raise


def create_stack_files(stack_root: Path) -> None:
    # scripts/common.sh
    safe_write(
        stack_root / "scripts" / "common.sh",
        r"""
        #!/usr/bin/env bash
        # Common utilities for Modular CPU AI Stack v0.1.6
        # Provides logging and dependency checks.

        set -Eeuo pipefail

        ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
        LOG_DIR="${ROOT_DIR}/logs"
        mkdir -p "${LOG_DIR}"

        ACTION_LOG="${LOG_DIR}/stack_actions.log"
        ERROR_LOG="${LOG_DIR}/stack_errors.log"

        timestamp_utc() {
            date -u +"%Y-%m-%dT%H:%M:%SZ"
        }

        log_info() {
            local subsystem="$1"
            local message="$2"
            local ts
            ts="$(timestamp_utc)"
            echo "${ts} [INFO] [${subsystem}]: ${message}" | tee -a "${ACTION_LOG}"
        }

        log_error() {
            local subsystem="$1"
            local message="$2"
            local ts
            ts="$(timestamp_utc)"
            local formatted="${ts} [ERROR] [${subsystem}]: ${message} (see ${ERROR_LOG} for details)"
            echo "${formatted}" | tee -a "${ERROR_LOG}" >&2
        }

        require_command() {
            local cmd="$1"
            local subsystem="${2:-env-check}"
            if ! command -v "${cmd}" >/dev/null 2>&1; then
                log_error "${subsystem}" "Required command '${cmd}' is not available on PATH."
                exit 1
            fi
        }

        require_docker() {
            require_command "docker" "docker-check"
            if ! docker info >/dev/null 2>&1; then
                log_error "docker-check" "Docker is not running or not accessible by the current user."
                exit 1
            fi
        }

        require_docker_compose() {
            if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
                export COMPOSE_BIN="docker compose"
            elif command -v docker-compose >/dev/null 2>&1; then
                export COMPOSE_BIN="docker-compose"
            else
                log_error "compose-check" "Neither 'docker compose' nor 'docker-compose' is available."
                exit 1
            fi
        }

        compose_up() {
            local subsystem="$1"
            shift
            local services=("$@")
            require_docker
            require_docker_compose
            log_info "${subsystem}" "Launching services via docker compose: ${services[*]}"
            if ! ${COMPOSE_BIN} -f "${ROOT_DIR}/docker-compose.yml" up -d "${services[@]}"; then
                log_error "${subsystem}" "Failed to start services: ${services[*]}"
                exit 1
            fi
        }

        compose_down_all() {
            local subsystem="$1"
            require_docker
            require_docker_compose
            log_info "${subsystem}" "Stopping all stack services via docker compose down."
            if ! ${COMPOSE_BIN} -f "${ROOT_DIR}/docker-compose.yml" down; then
                log_error "${subsystem}" "Failed to stop stack services."
                exit 1
            fi
        }
        """,
    )

    # scripts/install_llm.sh (with Ollama data dir fix)
    safe_write(
        stack_root / "scripts" / "install_llm.sh",
        r"""
        #!/usr/bin/env bash
        # Install / launch LLM + Open WebUI subsystem

        set -Eeuo pipefail
        SCRIPT_NAME="install_llm.sh"

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        # shellcheck source=/dev/null
        source "${SCRIPT_DIR}/common.sh"

        log_info "${SCRIPT_NAME}" "Starting LLM + Open WebUI installation / launch sequence."

        # Ensure host data directory for Ollama exists (fixes mkdir /root/.ollama/models errors)
        OLLAMA_DATA_DIR="${ROOT_DIR}/data/ollama"
        if [[ ! -d "${OLLAMA_DATA_DIR}" ]]; then
            log_info "${SCRIPT_NAME}" "Creating Ollama data directory at ${OLLAMA_DATA_DIR}"
            mkdir -p "${OLLAMA_DATA_DIR}"
            chmod 700 "${OLLAMA_DATA_DIR}" || true
        fi

        compose_up "llm-subsystem" "ollama" "open-webui"

        log_info "${SCRIPT_NAME}" "LLM + Open WebUI subsystem is up. Access Open WebUI via http://<docker-host-ip>:3000"
        """,
    )

    # scripts/install_image_gen.sh
    safe_write(
        stack_root / "scripts" / "install_image_gen.sh",
        r"""
        #!/usr/bin/env bash
        # Install / launch Image Generation (e.g., ComfyUI) subsystem

        set -Eeuo pipefail
        SCRIPT_NAME="install_image_gen.sh"

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        # shellcheck source=/dev/null
        source "${SCRIPT_DIR}/common.sh"

        log_info "${SCRIPT_NAME}" "Starting Image Generation subsystem."

        compose_up "image-gen-subsystem" "comfyui"

        log_info "${SCRIPT_NAME}" "Image Generation subsystem is up. Access ComfyUI via http://<docker-host-ip>:8188"
        """,
    )

    # scripts/install_tts.sh (still only Wyoming-Piper; HTTP adapter can be added later)
    safe_write(
        stack_root / "scripts" / "install_tts.sh",
        r"""
        #!/usr/bin/env bash
        # Install / launch TTS subsystem (Wyoming-Piper)

        set -Eeuo pipefail
        SCRIPT_NAME="install_tts.sh"

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        # shellcheck source=/dev/null
        source "${SCRIPT_DIR}/common.sh"

        log_info "${SCRIPT_NAME}" "Starting TTS subsystem (Wyoming-Piper only)."

        compose_up "tts-subsystem" "wyoming-piper"

        log_info "${SCRIPT_NAME}" "TTS subsystem is up on tcp://<docker-host-ip>:10200"
        """,
    )

    # scripts/download_ollama_models.sh (with cleaned list + index handling)
    safe_write(
        stack_root / "scripts" / "download_ollama_models.sh",
        r"""
        #!/usr/bin/env bash
        # Interactive Ollama model manager for the Modular CPU AI Stack

        set -Eeuo pipefail
        SCRIPT_NAME="download_ollama_models.sh"

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        # shellcheck source=/dev/null
        source "${SCRIPT_DIR}/common.sh"

        ROOT_DIR="${ROOT_DIR:-"$(cd "${SCRIPT_DIR}/.." && pwd)"}"
        MODEL_LIST_FILE="${ROOT_DIR}/config/ollama_models.txt"

        ensure_model_list() {
            if [[ ! -f "${MODEL_LIST_FILE}" ]]; then
                log_info "${SCRIPT_NAME}" "Model list file missing. Creating default list at ${MODEL_LIST_FILE}."
                mkdir -p "$(dirname "${MODEL_LIST_FILE}")"
                cat > "${MODEL_LIST_FILE}" <<EOF
        # One model per line. Lines starting with # are comments.
        # Some sensible CPU-friendly defaults:
        mistral
        llama3
        llama3.1
        phi3
        qwen2.5
        gemma2
        EOF
            fi
        }

        ensure_ollama_service() {
            require_docker
            require_docker_compose
            if ! docker ps --format '{{.Names}}' | grep -q '^ollama$'; then
                log_info "${SCRIPT_NAME}" "Ollama container not detected, attempting to start via docker compose."
                if ! ${COMPOSE_BIN} -f "${ROOT_DIR}/docker-compose.yml" up -d ollama >/dev/null 2>&1; then
                    log_error "${SCRIPT_NAME}" "Failed to start Ollama container. Ensure docker-compose.yml is correct and try again."
                    exit 1
                fi
            fi
        }

        pull_model() {
            local model="$1"
            ensure_ollama_service
            log_info "${SCRIPT_NAME}" "Requesting Ollama to pull model '${model}'."
            if ! docker exec -it ollama ollama pull "${model}"; then
                log_error "${SCRIPT_NAME}" "Failed to pull model '${model}' via Ollama."
                return 1
            fi
            log_info "${SCRIPT_NAME}" "Model '${model}' pulled successfully."
        }

        list_models() {
            echo ""
            echo "Available Ollama models (defined in ${MODEL_LIST_FILE}):"
            echo "-------------------------------------------------------"
            local n=0
            while IFS= read -r line; do
                # Skip comments and blank lines
                if [[ "${line}" =~ ^[[:space:]]*# ]] || [[ -z "${line//[[:space:]]/}" ]]; then
                    continue
                fi
                n=$((n + 1))
                printf "    %d  %s\n" "${n}" "${line}"
            done < "${MODEL_LIST_FILE}"
            echo ""
        }

        get_model_by_index() {
            local idx="$1"
            # Filter out comments and blank lines, then pick Nth line
            grep -v '^[[:space:]]*#' "${MODEL_LIST_FILE}" \
                | sed '/^[[:space:]]*$/d' \
                | sed -n "${idx}p" \
                | xargs
        }

        interactive_menu() {
            ensure_model_list
            while true; do
                echo "================================"
                echo "  Ollama Model Management Menu"
                echo "================================"
                echo "1) List configured models"
                echo "2) Pull a model by number"
                echo "3) Pull a model by name"
                echo "4) Edit model list file"
                echo "5) Exit"
                read -rp "Enter choice [1-5]: " choice || true

                case "${choice}" in
                    1)
                        list_models
                        ;;
                    2)
                        list_models
                        read -rp "Enter model number to pull: " num || true
                        if [[ -z "${num}" ]]; then
                            echo "No selection made."
                            continue
                        fi
                        if ! [[ "${num}" =~ ^[0-9]+$ ]]; then
                            echo "Invalid selection (not a number)."
                            continue
                        fi
                        model="$(get_model_by_index "${num}")"
                        if [[ -z "${model}" ]]; then
                            echo "Invalid selection (no model at that index)."
                            continue
                        fi
                        pull_model "${model}"
                        ;;
                    3)
                        read -rp "Enter full model name (e.g., mistral, llama3): " model || true
                        if [[ -z "${model}" ]]; then
                            echo "No model specified."
                            continue
                        fi
                        pull_model "${model}"
                        ;;
                    4)
                        echo "Opening ${MODEL_LIST_FILE} in ${EDITOR:-nano}."
                        ${EDITOR:-nano} "${MODEL_LIST_FILE}"
                        ;;
                    5)
                        echo "Exiting Ollama Model Manager."
                        break
                        ;;
                    *)
                        echo "Invalid choice."
                        ;;
                esac
            done
        }

        log_info "${SCRIPT_NAME}" "Starting Ollama model manager."
        interactive_menu
        """,
    )

    # scripts/health_check.sh
    safe_write(
        stack_root / "scripts" / "health_check.sh",
        r"""
        #!/usr/bin/env bash
        # Health check for Modular CPU AI Stack v0.1.6

        set -Eeuo pipefail
        SCRIPT_NAME="health_check.sh"

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        # shellcheck source=/dev/null
        source "${SCRIPT_DIR}/common.sh"

        require_docker

        SERVICES=(
            "ollama"
            "open-webui"
            "comfyui"
            "wyoming-piper"
        )

        log_info "${SCRIPT_NAME}" "Running health checks for core services."

        overall_ok=0

        for svc in "${SERVICES[@]}"; do
            if docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
                status="running"
                log_info "${SCRIPT_NAME}" "Service '${svc}' is running."
            else
                status="not-running"
                log_error "${SCRIPT_NAME}" "Service '${svc}' is NOT running."
                overall_ok=1
            fi
            echo " - ${svc}: ${status}"
        done

        if [[ "${overall_ok}" -eq 0 ]]; then
            echo "All monitored services are running."
            exit 0
        else
            echo "One or more services are not running. Check ${ERROR_LOG} for details."
            exit 1
        fi
        """,
    )

    # scripts/clean_stack.sh
    safe_write(
        stack_root / "scripts" / "clean_stack.sh",
        r"""
        #!/usr/bin/env bash
        # Clean up Modular CPU AI Stack containers (and optionally volumes)

        set -Eeuo pipefail
        SCRIPT_NAME="clean_stack.sh"

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        # shellcheck source=/dev/null
        source "${SCRIPT_DIR}/common.sh"

        ROOT_DIR="${ROOT_DIR:-"$(cd "${SCRIPT_DIR}/.." && pwd)"}"

        require_docker
        require_docker_compose

        echo "This will stop and remove all containers defined in docker-compose.yml."
        read -rp "Also remove volumes? This will delete stored data. [y/N]: " remove_vols || true
        remove_vols="${remove_vols:-N}"

        log_info "${SCRIPT_NAME}" "User requested stack cleanup. Remove volumes: ${remove_vols}."

        if [[ "${remove_vols}" =~ ^[Yy]$ ]]; then
            if ! ${COMPOSE_BIN} -f "${ROOT_DIR}/docker-compose.yml" down -v; then
                log_error "${SCRIPT_NAME}" "Failed to run 'docker compose down -v' for cleanup."
                exit 1
            fi
            log_info "${SCRIPT_NAME}" "Stack containers and volumes have been removed."
        else
            if ! ${COMPOSE_BIN} -f "${ROOT_DIR}/docker-compose.yml" down; then
                log_error "${SCRIPT_NAME}" "Failed to run 'docker compose down' for cleanup."
                exit 1
            fi
            log_info "${SCRIPT_NAME}" "Stack containers have been removed (volumes preserved)."
        fi
        """,
    )

    # scripts/setup_oauth.sh (helper you provided, wired into logging)
    safe_write(
        stack_root / "scripts" / "setup_oauth.sh",
        r"""
        #!/usr/bin/env bash
        # Helper to configure OAuth secrets and load them into a selected container/image.

        set -Eeuo pipefail
        SCRIPT_NAME="setup_oauth.sh"

        SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        # shellcheck source=/dev/null
        source "${SCRIPT_DIR}/common.sh"

        log_info "${SCRIPT_NAME}" "Starting OAuth configuration helper."

        # Prompt user to input required secrets and keys
        read -rp "Enter Google Client ID: " GOOGLE_CLIENT_ID
        read -rp "Enter Google Client Secret: " GOOGLE_CLIENT_SECRET
        read -rp "Enter GitHub Client ID: " GITHUB_CLIENT_ID
        read -rp "Enter GitHub Client Secret: " GITHUB_CLIENT_SECRET

        echo ""
        echo "Select a container or image name from the following list:"
        docker ps -a --format "table {{.ID}}\t{{.Names}}"
        echo ""
        read -rp "Enter the selected container ID or name: " CONTAINER_OR_PULL_NAME

        if docker ps -q --filter id="${CONTAINER_OR_PULL_NAME}" | grep -q .; then
            log_info "${SCRIPT_NAME}" "Selected container: ${CONTAINER_OR_PULL_NAME}"
            docker inspect "${CONTAINER_OR_PULL_NAME}" >/dev/null
        elif docker images -q --filter reference="${CONTAINER_OR_PULL_NAME}" | grep -q .; then
            log_info "${SCRIPT_NAME}" "Selected image: ${CONTAINER_OR_PULL_NAME}"
            docker inspect "${CONTAINER_OR_PULL_NAME}" >/dev/null
        else
            log_error "${SCRIPT_NAME}" "Container or image '${CONTAINER_OR_PULL_NAME}' not found."
            echo "Error: Container or image not found."
            exit 1
        fi

        echo ""
        echo "Select an option for loading the configuration files into the container:"
        echo "1. Automatically load the config files into the container"
        echo "2. Manually load the config files into the container (for advanced users)"
        read -rp "Enter your selection [1-2]: " SELECTED_OPTION

        case "${SELECTED_OPTION}" in
          1)
            docker exec "${CONTAINER_OR_PULL_NAME}" mkdir -p /app/config/oauth
            log_info "${SCRIPT_NAME}" "Created /app/config/oauth inside the container."

            if [[ ! -f "${ROOT_DIR}/config/oauth/config.json" ]]; then
                log_error "${SCRIPT_NAME}" "Expected ${ROOT_DIR}/config/oauth/config.json to exist."
                echo "Error: ${ROOT_DIR}/config/oauth/config.json does not exist. Create it and rerun."
                exit 1
            fi

            docker cp "${ROOT_DIR}/config/oauth/config.json" \
                "${CONTAINER_OR_PULL_NAME}:/app/config/oauth/config.json"
            log_info "${SCRIPT_NAME}" "Copied config.json into container /app/config/oauth/config.json."
            ;;

          2)
            read -rp "Enter path on host to your custom configuration file: " CUSTOM_CONFIG_FILE_PATH
            if [[ ! -f "${CUSTOM_CONFIG_FILE_PATH}" ]]; then
                log_error "${SCRIPT_NAME}" "Custom configuration file '${CUSTOM_CONFIG_FILE_PATH}' not found."
                echo "Error: custom configuration file not found."
                exit 1
            fi
            docker exec "${CONTAINER_OR_PULL_NAME}" mkdir -p /app/config/oauth
            docker cp "${CUSTOM_CONFIG_FILE_PATH}" \
                "${CONTAINER_OR_PULL_NAME}:/app/config/oauth/config.json"
            log_info "${SCRIPT_NAME}" "Copied custom config file into container /app/config/oauth/config.json."
            ;;

          *)
            echo "Invalid selection. Exiting..."
            log_error "${SCRIPT_NAME}" "Invalid menu selection '${SELECTED_OPTION}'."
            exit 1
            ;;
        esac

        echo "Configuration files have been successfully loaded into the container."
        log_info "${SCRIPT_NAME}" "OAuth configuration helper completed."
        """,
    )

    # install.sh main menu
    safe_write(
        stack_root / "install.sh",
        r"""
        #!/usr/bin/env bash
        # Modular CPU AI Stack v0.1.6 - Main installer / launcher menu

        set -Eeuo pipefail
        SCRIPT_NAME="install.sh"

        ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        SCRIPT_DIR="${ROOT_DIR}/scripts"
        # shellcheck source=/dev/null
        source "${SCRIPT_DIR}/common.sh"

        main_menu() {
            while true; do
                echo "==== Modular CPU AI Stack v0.1.6 ===="
                echo "1) Install / launch LLM + Open WebUI"
                echo "2) Install / launch Image Generation"
                echo "3) Install / launch TTS"
                echo "4) Ollama model manager"
                echo "5) Health check"
                echo "6) Clean up stack"
                echo "7) OAuth helper (setup_oauth.sh)"
                echo "8) Exit"
                read -rp "Choose [1-8]: " choice || true

                case "${choice}" in
                    1)
                        "${SCRIPT_DIR}/install_llm.sh"
                        ;;
                    2)
                        "${SCRIPT_DIR}/install_image_gen.sh"
                        ;;
                    3)
                        "${SCRIPT_DIR}/install_tts.sh"
                        ;;
                    4)
                        "${SCRIPT_DIR}/download_ollama_models.sh"
                        ;;
                    5)
                        "${SCRIPT_DIR}/health_check.sh"
                        ;;
                    6)
                        "${SCRIPT_DIR}/clean_stack.sh"
                        ;;
                    7)
                        "${SCRIPT_DIR}/setup_oauth.sh"
                        ;;
                    8)
                        echo "Exiting Modular CPU AI Stack menu."
                        break
                        ;;
                    *)
                        echo "Invalid choice."
                        ;;
                esac
            done
        }

        log_info "${SCRIPT_NAME}" "Launching main installer menu."
        main_menu
        """,
    )

    # docker-compose.yml
    safe_write(
        stack_root / "docker-compose.yml",
        r"""
        services:
          ollama:
            image: ollama/ollama:latest
            container_name: ollama
            restart: unless-stopped
            volumes:
              - ./data/ollama:/root/.ollama
            ports:
              - "11434:11434"

          open-webui:
            image: ghcr.io/open-webui/open-webui:main
            container_name: open-webui
            restart: unless-stopped
            environment:
              - OLLAMA_BASE_URL=http://ollama:11434
            ports:
              - "3000:8080"
            volumes:
              - ./data/open-webui:/app/backend/data
            depends_on:
              - ollama

          comfyui:
            image: zhangp365/comfyui:latest
            container_name: comfyui
            restart: unless-stopped
            ports:
              - "8188:8188"
            volumes:
              - ./models/comfyui:/app/ComfyUI/models
              - ./workflows:/app/ComfyUI/user/default/workflows
              - ./output:/app/ComfyUI/output

          wyoming-piper:
            image: rhasspy/wyoming-piper:latest
            container_name: wyoming-piper
            restart: unless-stopped
            # Note: image's default entrypoint runs the piper server; we only pass args here.
            command: >
              --voice en_US-lessac-medium
              --data-dir /data
              --uri tcp://0.0.0.0:10200
            ports:
              - "10200:10200"
            volumes:
              - ./data/piper:/data
        """,
    )

    # README.md
    safe_write(
        stack_root / "README.md",
        f"""
        # Modular CPU AI Stack v{VERSION}

        This version corresponds to the modular, menu-driven stack that we are using
        as the stable baseline.

        It provides a CPU-only, Docker-based stack with separate modules for:

        - LLM + Open WebUI (`ollama`, `open-webui`)
        - Image Generation (`comfyui`)
        - TTS (`wyoming-piper`)
        - Ollama model management (interactive menu)
        - Health checks
        - Cleanup
        - OAuth helper (`scripts/setup_oauth.sh`)

        ## Quick start

        ```bash
        cd {STACK_DIR_NAME}
        chmod +x install.sh scripts/*.sh
        ./install.sh
        ```

        Then use the menu to start individual subsystems or manage Ollama models.

        ## Logging

        All stack scripts log to:

        - `logs/stack_actions.log`
        - `logs/stack_errors.log`

        Every error message references `logs/stack_errors.log` for easier debugging.
        """,
    )

    # CHANGELOG.md
    safe_write(
        stack_root / "CHANGELOG.md",
        """
        # Changelog - Modular CPU AI Stack

        ## 0.1.6
        - Restored modular, menu-driven architecture.
        - Added per-subsystem installers:
          - LLM + Open WebUI
          - Image Generation (ComfyUI)
          - TTS (Wyoming-Piper)
        - Added interactive Ollama model manager (`download_ollama_models.sh`).
        - Added health check script for all core services.
        - Added cleanup script to stop containers and optionally remove volumes.
        - Centralized logging via `scripts/common.sh` with explicit error log reference.
        - Added OAuth helper script (`scripts/setup_oauth.sh`).
        - Fixed Ollama data directory handling to avoid 400 errors on `ollama pull`.
        """,
    )

    # session restart prompt
    safe_write(
        stack_root / "session_restart_prompt_v0_1_6.md",
        """
        # Session Restart Prompt - Modular CPU AI Stack v0.1.6

        You are helping with the Modular CPU AI Stack v0.1.6, a CPU-only Docker stack
        with modular installers for:

        - LLM + Open WebUI
        - Image Generation (ComfyUI)
        - TTS (Wyoming-Piper)
        - Ollama model management
        - Health checks
        - Cleanup
        - OAuth helper

        The code and scripts live in a directory named `modular_cpu_ai_stack_v0_1_6` and include:

        - `install.sh` main menu
        - `scripts/common.sh` for logging / helpers
        - `scripts/install_llm.sh`
        - `scripts/install_image_gen.sh`
        - `scripts/install_tts.sh`
        - `scripts/download_ollama_models.sh`
        - `scripts/health_check.sh`
        - `scripts/clean_stack.sh`
        - `scripts/setup_oauth.sh`
        - `docker-compose.yml`
        - `config/ollama_models.txt` (created on first run of the model manager)

        The user expects:

        - Defensive Bash scripting (`set -Eeuo pipefail`)
        - Explicit logging with timestamps and subsystem names
        - Every error message to reference `logs/stack_errors.log`
        - Deterministic, idempotent behavior
        - No GPU assumptions (CPU-only where possible)

        When continuing work, assume this version is the "good" baseline and new versions
        should build on it without losing modularity or tooling.
        """,
    )


def create_zip(stack_root: Path) -> Path:
    zip_path = ROOT_DIR / f"{stack_root.name}.zip"
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for folder, _, files in os.walk(stack_root):
                for name in files:
                    full = Path(folder) / name
                    rel = full.relative_to(ROOT_DIR)
                    zf.write(full, arcname=rel)
        log_info(f"Created ZIP archive: {zip_path}")
        return zip_path
    except Exception as exc:
        log_error(f"Failed to create zip {zip_path}: {exc}")
        raise


def main() -> None:
    log_info(f"Generating stack version {VERSION} in {ROOT_DIR}")

    stack_root = ROOT_DIR / STACK_DIR_NAME

    if stack_root.exists():
        log_info(
            f"Target directory already exists: {stack_root} (will overwrite files)."
        )
    else:
        stack_root.mkdir(parents=True, exist_ok=True)
        log_info(f"Created stack root directory: {stack_root}")

    try:
        create_stack_files(stack_root)

        # Mark scripts executable
        scripts_dir = stack_root / "scripts"
        for sh in scripts_dir.glob("*.sh"):
            make_executable(sh)
        make_executable(stack_root / "install.sh")

        # Make empty logs dir
        (stack_root / "logs").mkdir(parents=True, exist_ok=True)

        # Create zip archive
        zip_path = create_zip(stack_root)

        log_info(f"Stack files generation complete for {VERSION}.")
        log_info(f"Root directory: {stack_root}")
        log_info(f"ZIP archive: {zip_path}")
        print(f"\nDone.\nRoot: {stack_root}\nZIP:  {zip_path}\n")
    except Exception:
        tb = traceback.format_exc()
        log_error(f"Unhandled exception during stack generation:\n{tb}")
        raise


if __name__ == "__main__":
    main()
