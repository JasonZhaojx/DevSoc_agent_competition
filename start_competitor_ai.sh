#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="${COMPETITOR_AI_VENV:-$PROJECT_ROOT/.venv}"
PYTHON_PATH_FILE="$PROJECT_ROOT/.local_python_path.txt"
LOCAL_ENV_FILE="$PROJECT_ROOT/.local_env.sh"
DEFAULT_PORT="${WEB_PORT:-8000}"

RUNTIME_PACKAGES=(
  requests
  openai
  duckduckgo-search
  trafilatura
  beautifulsoup4
  lxml
  playwright
  crawl4ai
  python-dotenv
  tqdm
  pydantic
  python-dateutil
)

DEV_PACKAGES=(
  pytest
  pytest-asyncio
  black
  flake8
  mypy
)

OPTIONAL_PACKAGES=(
  langchain-openai
)

YES=0
DEV=0
OPTIONAL=0
NO_VENV=0
SKIP_PIP_UPGRADE=0
SKIP_PLAYWRIGHT=0
SKIP_CRAWL4AI=0

show_logo() {
  clear 2>/dev/null || true
  cat <<'EOF'
   ____                           _   _ _                  _    ___
  / ___|___  _ __ ___  _ __   ___| |_(_) |_ ___  _ __     / \  |_ _|
 | |   / _ \| '_ ` _ \| '_ \ / _ \ __| | __/ _ \| '__|   / _ \  | |
 | |__| (_) | | | | | | |_) |  __/ |_| | || (_) | |     / ___ \ | |
  \____\___/|_| |_| |_| .__/ \___|\__|_|\__\___/|_|    /_/   \_\___|
                      |_|
EOF
}

write_title() {
  printf '\n== %s ==\n' "$1"
}

wait_return() {
  local prompt="${1:-Press Enter to return to the menu}"
  read -r -p "$prompt" _
}

read_yes_no() {
  local prompt="$1"
  local default="${2:-yes}"
  local suffix
  local answer

  if [[ "$YES" == "1" ]]; then
    if [[ "$default" == "yes" ]]; then
      return 0
    fi
    return 1
  fi

  if [[ "$default" == "yes" ]]; then
    suffix="Y/n"
  else
    suffix="y/N"
  fi

  while true; do
    read -r -p "$prompt [$suffix] " answer
    answer="${answer,,}"
    if [[ -z "$answer" ]]; then
      if [[ "$default" == "yes" ]]; then
        return 0
      fi
      return 1
    fi
    case "$answer" in
      y|yes) return 0 ;;
      n|no) return 1 ;;
      *) echo "Please enter y or n." ;;
    esac
  done
}

run_as_root() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    echo "[warn] Need root permission but sudo is not installed: $*"
    return 1
  fi
}

install_system_packages() {
  write_title "Install system packages"

  if command -v apt-get >/dev/null 2>&1; then
    run_as_root apt-get update
    run_as_root apt-get install -y \
      python3 python3-pip python3-venv python3-dev \
      build-essential curl ca-certificates
    return
  fi

  if command -v dnf >/dev/null 2>&1; then
    run_as_root dnf install -y \
      python3 python3-pip python3-devel \
      gcc gcc-c++ make curl ca-certificates \
      atk at-spi2-atk gtk3 libXcomposite libXcursor libXdamage \
      libXext libXi libXrandr libXScrnSaver libXtst pango \
      alsa-lib mesa-libgbm nss nspr cups-libs libdrm libxkbcommon
    return
  fi

  if command -v yum >/dev/null 2>&1; then
    run_as_root yum install -y \
      python3 python3-pip python3-devel \
      gcc gcc-c++ make curl ca-certificates \
      atk at-spi2-atk gtk3 libXcomposite libXcursor libXdamage \
      libXext libXi libXrandr libXScrnSaver libXtst pango \
      alsa-lib mesa-libgbm nss nspr cups-libs libdrm libxkbcommon
    return
  fi

  echo "[warn] Unsupported package manager. Please install python3, pip3 and python3-venv manually."
}

ensure_python_tools() {
  if command -v python3 >/dev/null 2>&1 && command -v pip3 >/dev/null 2>&1; then
    return
  fi

  echo "[info] python3 or pip3 is missing."
  if read_yes_no "Install system Python packages now?" "yes"; then
    install_system_packages
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "[error] python3 was not found. Please install Python 3 first."
    exit 1
  fi

  if ! command -v pip3 >/dev/null 2>&1; then
    echo "[error] pip3 was not found. Please install python3-pip first."
    exit 1
  fi
}

resolve_python_executable() {
  local candidate="$1"
  local resolved

  [[ -n "${candidate// }" ]] || return 1
  candidate="${candidate%\"}"
  candidate="${candidate#\"}"

  if ! resolved="$("$candidate" -c 'import sys; print(sys.executable)' 2>/dev/null)"; then
    return 1
  fi

  [[ -n "$resolved" ]] || return 1
  printf '%s\n' "$resolved"
}

write_local_python_config() {
  local python_path="$1"
  local venv_path="${2:-}"

  cat >"$LOCAL_ENV_FILE" <<EOF
#!/usr/bin/env bash
export COMPETITOR_AI_PROJECT_ROOT="$PROJECT_ROOT"
export COMPETITOR_AI_PYTHON="$python_path"
export COMPETITOR_AI_VENV="$venv_path"
EOF

  if [[ -n "$venv_path" ]]; then
    cat >>"$LOCAL_ENV_FILE" <<EOF
export VIRTUAL_ENV="$venv_path"
export PATH="$venv_path/bin:\$PATH"
EOF
  fi

  printf '%s\n' "$python_path" >"$PYTHON_PATH_FILE"
  chmod +x "$LOCAL_ENV_FILE" 2>/dev/null || true

  echo "Saved local environment:"
  echo "  $LOCAL_ENV_FILE"
  echo "Saved Python path:"
  echo "  $python_path"
}

read_configured_python() {
  local saved

  if [[ -f "$PYTHON_PATH_FILE" ]]; then
    saved="$(tr -d '\r\n' <"$PYTHON_PATH_FILE")"
    if [[ -n "$saved" && -x "$saved" ]]; then
      printf '%s\n' "$saved"
      return
    fi
  fi

  if [[ -x "$VENV_DIR/bin/python" ]]; then
    printf '%s\n' "$VENV_DIR/bin/python"
    return
  fi

  if [[ -x "$VENV_DIR/bin/python3" ]]; then
    printf '%s\n' "$VENV_DIR/bin/python3"
    return
  fi
}

ensure_venv_pip3() {
  local python_bin="$1"
  local pip_bin="$2"

  if [[ -x "$pip_bin" ]]; then
    return
  fi

  "$python_bin" -m ensurepip --upgrade

  if [[ ! -x "$pip_bin" && -x "$VENV_DIR/bin/pip" ]]; then
    ln -sf "$VENV_DIR/bin/pip" "$pip_bin"
  fi

  if [[ ! -x "$pip_bin" ]]; then
    echo "[error] Could not find $pip_bin after creating the virtual environment."
    exit 1
  fi
}

install_packages() {
  local python_bin
  local pip_bin
  local venv_for_config=""

  ensure_python_tools

  if [[ "$NO_VENV" == "0" ]]; then
    write_title "Create or update virtual environment"
    if [[ ! -d "$VENV_DIR" ]]; then
      python3 -m venv "$VENV_DIR"
    fi
    python_bin="$VENV_DIR/bin/python"
    pip_bin="$VENV_DIR/bin/pip3"
    ensure_venv_pip3 "$python_bin" "$pip_bin"
    venv_for_config="$VENV_DIR"
  else
    python_bin="$(resolve_python_executable python3)"
    pip_bin="$(command -v pip3)"
  fi

  write_title "Install Python dependencies with pip3"
  echo "Python: $python_bin"
  echo "pip3:   $pip_bin"

  if [[ "$SKIP_PIP_UPGRADE" == "0" ]]; then
    "$pip_bin" install --upgrade pip setuptools wheel
  fi

  "$pip_bin" install --upgrade "${RUNTIME_PACKAGES[@]}"

  if [[ "$DEV" == "1" ]] || read_yes_no "Install development and test dependencies?" "no"; then
    "$pip_bin" install --upgrade "${DEV_PACKAGES[@]}"
  fi

  if [[ "$OPTIONAL" == "1" ]] || read_yes_no "Install optional enhancement dependencies?" "no"; then
    "$pip_bin" install --upgrade "${OPTIONAL_PACKAGES[@]}"
  fi

  write_local_python_config "$python_bin" "$venv_for_config"
}

initialize_playwright() {
  local python_bin="$1"

  [[ "$SKIP_PLAYWRIGHT" == "0" ]] || return
  read_yes_no "Install Playwright Chromium browser?" "yes" || return

  write_title "Initialize Playwright Chromium"
  "$python_bin" -m playwright install chromium || true

  if read_yes_no "Install Playwright Linux system dependencies?" "yes"; then
    run_as_root "$python_bin" -m playwright install-deps chromium || true
  fi
}

find_env_cli() {
  local name="$1"
  local venv_cli="$VENV_DIR/bin/$name"

  if [[ -x "$venv_cli" ]]; then
    printf '%s\n' "$venv_cli"
    return
  fi

  command -v "$name" 2>/dev/null || true
}

initialize_crawl4ai() {
  local setup_cli
  local doctor_cli

  [[ "$SKIP_CRAWL4AI" == "0" ]] || return
  read_yes_no "Initialize Crawl4AI browser/runtime environment?" "yes" || return

  write_title "Initialize Crawl4AI"
  setup_cli="$(find_env_cli crawl4ai-setup)"
  if [[ -n "$setup_cli" ]]; then
    "$setup_cli" || true
  else
    echo "[warn] crawl4ai-setup was not found; Playwright Chromium install is used as fallback."
  fi

  doctor_cli="$(find_env_cli crawl4ai-doctor)"
  if [[ -n "$doctor_cli" ]] && read_yes_no "Run crawl4ai-doctor diagnostics?" "no"; then
    "$doctor_cli" || true
  fi
}

verify_imports() {
  local python_bin="$1"

  write_title "Verify Python imports"
  "$python_bin" <<'PY'
import importlib

mods = [
    ("requests", "requests"),
    ("openai", "openai"),
    ("duckduckgo-search", "duckduckgo_search"),
    ("trafilatura", "trafilatura"),
    ("beautifulsoup4", "bs4"),
    ("lxml", "lxml"),
    ("playwright", "playwright"),
    ("crawl4ai", "crawl4ai"),
    ("python-dotenv", "dotenv"),
    ("tqdm", "tqdm"),
    ("pydantic", "pydantic"),
    ("python-dateutil", "dateutil"),
]

missing = []
for package, module in mods:
    try:
        importlib.import_module(module)
    except Exception as exc:
        missing.append((package, module, exc))

if missing:
    print("Missing or broken packages:")
    for package, module, exc in missing:
        print(f"  - {package} ({module}): {exc}")
    raise SystemExit(1)

print("All required imports are available.")
PY
}

invoke_install_env() {
  show_logo
  echo
  echo "Starting Linux server environment installation."

  install_packages

  local python_bin
  python_bin="$(read_configured_python)"
  initialize_playwright "$python_bin"
  initialize_crawl4ai
  verify_imports "$python_bin"

  echo
  echo "Installation completed."
}

set_existing_python() {
  local input_text
  local resolved

  show_logo
  echo
  echo "Enter an existing Python interpreter with dependencies installed."
  echo "You can enter a full path, python3, or python."
  echo

  read -r -p "Python path or command: " input_text
  if ! resolved="$(resolve_python_executable "$input_text")"; then
    echo
    echo "Could not run this Python interpreter:"
    echo "  $input_text"
    wait_return
    return
  fi

  echo
  write_local_python_config "$resolved" ""
  wait_return
}

start_web_server() {
  local requested_port="${1:-}"
  local python_bin
  local port

  python_bin="$(read_configured_python || true)"
  if [[ -z "$python_bin" ]]; then
    echo
    echo "No local Python configuration was found."
    echo "Please install/update the environment first, or specify an existing Python."
    wait_return
    return
  fi

  if [[ ! -x "$python_bin" ]]; then
    echo
    echo "Saved Python path does not exist or is not executable:"
    echo "  $python_bin"
    wait_return
    return
  fi

  if [[ -n "$requested_port" ]]; then
    port="$requested_port"
  else
    echo
    read -r -p "Enter service port, press Enter to use $DEFAULT_PORT: " port
    port="${port:-$DEFAULT_PORT}"
  fi

  show_logo
  echo
  echo "Using Python:"
  echo "  $python_bin"
  echo
  echo "Starting Web server:"
  echo "  http://0.0.0.0:$port"
  echo
  echo "Set API keys through environment variables before startup, for example:"
  echo "  export ARK_API_KEY=\"...\""
  echo "  export BOCHA_API_KEY=\"...\""
  echo

  export WEB_PORT="$port"
  exec "$python_bin" "$PROJECT_ROOT/backend/server.py" "$port"
}

print_help() {
  cat <<EOF
Usage:
  ./start_competitor_ai.sh
  ./start_competitor_ai.sh install [options]
  ./start_competitor_ai.sh start [port]
  ./start_competitor_ai.sh python

Options for install:
  -y, --yes              Use default yes/no answers
  --dev                  Install development/test dependencies
  --optional             Install optional enhancement dependencies
  --no-venv              Install into system/user Python instead of .venv
  --skip-pip-upgrade     Do not upgrade pip/setuptools/wheel
  --skip-playwright      Do not install Playwright Chromium
  --skip-crawl4ai        Do not run Crawl4AI setup
  -h, --help             Show this help

All Python package installation commands use pip3.
EOF
}

parse_common_options() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -y|--yes) YES=1 ;;
      --dev) DEV=1 ;;
      --optional) OPTIONAL=1 ;;
      --no-venv) NO_VENV=1 ;;
      --skip-pip-upgrade) SKIP_PIP_UPGRADE=1 ;;
      --skip-playwright) SKIP_PLAYWRIGHT=1 ;;
      --skip-crawl4ai) SKIP_CRAWL4AI=1 ;;
      -h|--help) print_help; exit 0 ;;
      *) echo "Unknown option: $1"; print_help; exit 1 ;;
    esac
    shift
  done
}

main_menu() {
  while true; do
    show_logo
    echo
    echo "[1] Install/update Python environment"
    echo "[2] Start Web server with local Python"
    echo "[3] Use an existing Python"
    echo "[4] Install/update environment and start"
    echo "[5] Exit"
    echo

    read -r -p "Choose an action: " choice
    case "${choice// /}" in
      1)
        invoke_install_env
        wait_return
        ;;
      2)
        start_web_server
        ;;
      3)
        set_existing_python
        ;;
      4)
        invoke_install_env
        start_web_server
        ;;
      5)
        exit 0
        ;;
      *)
        echo
        echo "Invalid input, please choose again."
        wait_return
        ;;
    esac
  done
}

cmd="${1:-menu}"
case "$cmd" in
  menu)
    shift || true
    parse_common_options "$@"
    main_menu
    ;;
  install)
    shift
    parse_common_options "$@"
    invoke_install_env
    ;;
  start)
    shift
    if [[ $# -gt 0 ]]; then
      DEFAULT_PORT="$1"
    fi
    start_web_server "$DEFAULT_PORT"
    ;;
  python)
    set_existing_python
    ;;
  -h|--help|help)
    print_help
    ;;
  *)
    echo "Unknown command: $cmd"
    print_help
    exit 1
    ;;
esac
