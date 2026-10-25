import os
import sys
import time
import socket
import subprocess
import urllib.request
import webbrowser

PORT = 5000
URL = f"http://localhost:{PORT}/"

def get_wifi_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def is_evntra_running():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1.5) as res:
            body = res.read().decode("utf-8", errors="ignore")
            return "EVNTRA" in body or "Evntra" in body
    except Exception:
        return False

def free_port_5000():
    try:
        output = subprocess.check_output("netstat -ano", shell=True).decode()
        for line in output.splitlines():
            if f":{PORT}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid.isdigit() and int(pid) > 0:
                    print(f"Freeing port {PORT} from conflicting process (PID {pid})...")
                    subprocess.call(f"taskkill /F /PID {pid}", shell=True)
                    time.sleep(1)
    except Exception as e:
        print(f"Port check notice: {e}")

def start_server():
    if is_evntra_running():
        print("✓ Evntra server is already active and healthy!")
        return True

    free_port_5000()
    print("Starting Evntra Python Server...")
    root_dir = os.path.dirname(os.path.abspath(__file__))
    app_py = os.path.join(root_dir, "app.py")

    # Start detached in background
    subprocess.Popen([sys.executable, app_py], cwd=root_dir, creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)

    # Wait for server to become responsive
    for _ in range(12):
        time.sleep(0.5)
        if is_evntra_running():
            print("✓ Evntra server initialized successfully!")
            return True

    print("⚠️ Server starting up...")
    return False

def open_app():
    edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    if os.path.exists(edge_path):
        subprocess.Popen([edge_path, f"--app={URL}"])
        return
    if os.path.exists(chrome_path):
        subprocess.Popen([chrome_path, f"--app={URL}"])
        return
    webbrowser.open(URL)

if __name__ == "__main__":
    print("\n===================================================")
    print("             EVNTRA — LIVE EXPERIENCES")
    print("===================================================\n")
    start_server()
    
    server_only = "--server-only" in sys.argv
    if not server_only:
        open_app()
        wifi_ip = get_wifi_ip()
        print("\n" + "="*51)
        print(f"🎉 Evntra is now OPEN:")
        print(f"   💻 On this PC:     {URL}")
        print(f"   📱 On your Phone:  http://{wifi_ip}:{PORT}/")
        print("="*51 + "\n")
        time.sleep(1)
