"""AINovelInDialogue — 一键启动。

用法:
    python main.py                  → 开发模式: Vite(5173) + 后端(8000)
    python main.py --backend-only   → 仅后端(8000)
    python main.py --prod           → 生产模式: 后端服务前端静态文件(8000)
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


def build_frontend():
    """构建前端到 frontend/dist/。"""
    dist = FRONTEND_DIR / "dist"
    if dist.exists():
        print("[prod] 前端已构建，跳过。如需重新构建请删除 frontend/dist/")
        return True
    print("[prod] 构建前端...")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    try:
        subprocess.run([npm, "install"], cwd=FRONTEND_DIR, check=True)
        subprocess.run([npm, "run", "build"], cwd=FRONTEND_DIR, check=True)
        print("[prod] 前端构建完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[prod] 前端构建失败: {e}")
        return False


def start_vite():
    print("[dev] 启动 Vite 开发服务器...")
    npm = "npx.cmd" if sys.platform == "win32" else "npx"
    return subprocess.Popen([npm, "vite"], cwd=FRONTEND_DIR)


def main():
    check_deps()
    backend_only = "--backend-only" in sys.argv
    prod_mode = "--prod" in sys.argv

    vite_proc = None
    if prod_mode:
        if not build_frontend():
            print("[prod] 前端构建失败，请先安装 Node.js 或使用 --dev 模式")
            sys.exit(1)
        print(f"\n  AINovelInDialogue [生产模式]")
        print(f"  访问: http://localhost:8000\n")
    elif not backend_only:
        vite_proc = start_vite()
        for _ in range(15):
            time.sleep(0.4)
            try:
                import urllib.request
                urllib.request.urlopen("http://localhost:5173")
                break
            except Exception:
                pass
        print(f"\n  AINovelInDialogue [开发模式]")
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
