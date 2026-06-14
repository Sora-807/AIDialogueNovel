"""AINovelInDialogue — 一键启动。

用法:
    python main.py              → 启动 Vite 前端(5173) + 后端(8000)
    python main.py --backend-only → 仅启动后端(8000)，前端需自行启动
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND_DIR = ROOT / "frontend"


def check_deps():
    try:
        import fastapi  # noqa
        import uvicorn  # noqa
    except ImportError:
        print("请先安装: pip install fastapi uvicorn")
        sys.exit(1)


def start_vite():
    print("[dev] 启动 Vite 开发服务器...")
    npm = "npx.cmd" if sys.platform == "win32" else "npx"
    return subprocess.Popen([npm, "vite"], cwd=FRONTEND_DIR)


def main():
    check_deps()
    backend_only = "--backend-only" in sys.argv

    vite_proc = None
    if not backend_only:
        vite_proc = start_vite()
        # 等 Vite 启动
        for _ in range(15):
            time.sleep(0.4)
            try:
                import urllib.request
                urllib.request.urlopen("http://localhost:5173")
                break
            except Exception:
                pass
        print(f"\n  AINovelInDialogue")
        print(f"  前端: http://localhost:5173")
        print(f"  后端: http://localhost:8000\n")

    try:
        import uvicorn
        sys.path.insert(0, str(ROOT))
        from backend.server import create_app
        uvicorn.run(create_app(), host="0.0.0.0", port=8000, log_level="info")
    finally:
        if vite_proc:
            vite_proc.terminate()
            vite_proc.wait()


if __name__ == "__main__":
    main()
