#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.kityhello.renxiao.local"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$PROJECT_DIR/.venv/bin/python"
APP="$PROJECT_DIR/app.py"
URL="http://127.0.0.1:8000/"
HEALTH_URL="http://127.0.0.1:8000/health"
LOG_DIR="$PROJECT_DIR/output/logs"
OUT_LOG="$LOG_DIR/renxiao-local.out.log"
ERR_LOG="$LOG_DIR/renxiao-local.err.log"
usage() {
  cat <<EOF
Usage: $0 <install|start|stop|restart|status|open|logs|uninstall>
本机访问地址: $URL
EOF
}
ensure_project() { [[ -f "$APP" ]] || { echo "Project app not found: $APP" >&2; exit 1; }; }
ensure_python() { [[ -x "$PYTHON" ]] || { echo "Virtualenv python not found: $PYTHON" >&2; exit 1; }; }
ensure_logs() { mkdir -p "$LOG_DIR" "$HOME/Library/LaunchAgents"; }
write_plist() {
  ensure_logs
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PYTHON</string><string>$APP</string></array>
  <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$OUT_LOG</string>
  <key>StandardErrorPath</key><string>$ERR_LOG</string>
  <key>EnvironmentVariables</key><dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
</dict>
</plist>
EOF
}
launchctl_print() { launchctl print "gui/$UID/$LABEL" >/dev/null 2>&1; }
stop_manual_project_process() {
  local pids pid cwd
  pids="$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"
  [[ -z "$pids" ]] && return 0
  for pid in $pids; do
    cwd="$(lsof -p "$pid" 2>/dev/null | awk '$4 == "cwd" {print $9; exit}')"
    if [[ "$cwd" == "$PROJECT_DIR" ]]; then
      echo "Stopping existing renxiao process on port 8000: $pid"
      kill "$pid" 2>/dev/null || true
    else
      echo "Port 8000 is used by another process ($pid, cwd=$cwd). Stop it first." >&2
      exit 1
    fi
  done
}
wait_for_health() {
  local i
  for i in 1 2 3 4 5; do
    curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}
local_lan_ipv4() {
  local iface ip
  iface="$(route get default 2>/dev/null | awk '/interface:/{print $2; exit}')"
  if [[ -n "${iface:-}" ]]; then
    ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
    if [[ -n "$ip" && "$ip" != 127.* ]]; then
      echo "$ip"
      return 0
    fi
  fi
  ip="$(python3 - <<'PY' 2>/dev/null || true
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    if ip and not ip.startswith("127."):
        print(ip)
except OSError:
    pass
PY
)"
  [[ -n "$ip" ]] && echo "$ip"
}
print_access_addresses() {
  local lan_ip
  lan_ip="$(local_lan_ipv4 || true)"
  echo "本机访问地址: $URL"
  if [[ -n "$lan_ip" ]]; then
    echo "局域网访问地址: http://$lan_ip:8000/"
  else
    echo "局域网访问地址: 未检测到可用的局域网 IPv4 地址"
  fi
}
print_firewall_help() {
  cat <<EOF

如果同一 Wi-Fi 设备无法访问 8000 端口：
1. 打开 系统设置 > 网络 > 防火墙 > 选项，允许 Python 或本服务接收入站连接。
2. 或在终端执行：
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --add "$PYTHON"
   sudo /usr/libexec/ApplicationFirewall/socketfilterfw --unblockapp "$PYTHON"
EOF
}
install_agent() { ensure_project; ensure_python; write_plist; launchctl_print && launchctl bootout "gui/$UID" "$PLIST" >/dev/null 2>&1 || true; stop_manual_project_process; launchctl bootstrap "gui/$UID" "$PLIST"; launchctl kickstart -k "gui/$UID/$LABEL"; wait_for_health; status; }
start_agent() { ensure_project; ensure_python; [[ -f "$PLIST" ]] || write_plist; launchctl_print || { stop_manual_project_process; launchctl bootstrap "gui/$UID" "$PLIST"; }; launchctl kickstart -k "gui/$UID/$LABEL"; wait_for_health; status; }
stop_agent() { launchctl_print && launchctl bootout "gui/$UID" "$PLIST" || echo "LaunchAgent is not loaded."; }
restart_agent() { launchctl_print && launchctl kickstart -k "gui/$UID/$LABEL" || { start_agent; return; }; wait_for_health; status; }
status() {
  echo "LaunchAgent: $LABEL"
  launchctl_print && echo "Loaded: yes" || echo "Loaded: no"
  echo; echo "Port 8000:"; lsof -nP -iTCP:8000 -sTCP:LISTEN || true
  echo; echo "Health:"
  if curl -fsS --max-time 5 "$HEALTH_URL"; then
    echo
    echo
    print_access_addresses
    print_firewall_help
  else
    echo
    echo "Health check failed. Run: $0 logs" >&2
    return 1
  fi
}
open_dashboard() { status >/dev/null; open "$URL"; print_access_addresses; }
show_logs() { echo "STDOUT: $OUT_LOG"; tail -n 80 "$OUT_LOG" 2>/dev/null || true; echo; echo "STDERR: $ERR_LOG"; tail -n 120 "$ERR_LOG" 2>/dev/null || true; }
uninstall_agent() { stop_agent || true; rm -f "$PLIST"; echo "Removed: $PLIST"; }
case "${1:-}" in
  install) install_agent ;;
  start) start_agent ;;
  stop) stop_agent ;;
  restart) restart_agent ;;
  status) status ;;
  open) open_dashboard ;;
  logs) show_logs ;;
  uninstall) uninstall_agent ;;
  *) usage; exit 2 ;;
esac
