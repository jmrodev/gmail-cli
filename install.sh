#!/usr/bin/env bash
set -e
INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/gmail_cli.py"

mkdir -p "${INSTALL_DIR}"
cat << WRAPPEREOF > "${INSTALL_DIR}/gmail-cli"
#!/usr/bin/env bash
python3 "${SCRIPT_SRC}" "\$@"
WRAPPEREOF

chmod +x "${INSTALL_DIR}/gmail-cli"
chmod +x "${SCRIPT_SRC}"
echo "✅ gmail-cli instalado en ${INSTALL_DIR}/gmail-cli"
