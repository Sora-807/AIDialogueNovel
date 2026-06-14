"""打包脚本 — 构建可分发压缩包。

用法:
    python build.py          → 构建 frontend + PyInstaller exe + 压缩
    python build.py --skip-frontend → 跳过前端构建（已手动构建）
    python build.py --skip-exe      → 跳过 PyInstaller（仅压缩已有文件）

输出: dist/AINovelInDialogue_v{version}.zip
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
PACKAGE_NAME = "AINovelInDialogue"
VERSION = "0.1.0"
DIST_DIR = ROOT / "dist"
BUILD_DIR = DIST_DIR / PACKAGE_NAME


def build_frontend():
    print("[1/4] 构建前端...")
    frontend = ROOT / "frontend"
    dist = frontend / "dist"
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    try:
        subprocess.run([npm, "install"], cwd=frontend, check=True)
        subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
        print("  ✓ 前端构建完成")
        return dist
    except subprocess.CalledProcessError as e:
        print(f"  ✗ 前端构建失败: {e}")
        sys.exit(1)


def build_exe():
    print("[2/4] PyInstaller 打包...")
    # 确保 pyinstaller 已安装
    try:
        import PyInstaller  # noqa
    except ImportError:
        print("  安装 PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",  # 目录模式（比单文件启动快）
        "--name", PACKAGE_NAME,
        "--add-data", f"src{';' if sys.platform == 'win32' else ':'}src",
        "--add-data", f"backend{';' if sys.platform == 'win32' else ':'}backend",
        "--add-data", f"frontend/dist{';' if sys.platform == 'win32' else ':'}frontend/dist",
        "--hidden-import", "langchain_openai",
        "--hidden-import", "langchain_core.messages",
        "--hidden-import", "dotenv",
        "--hidden-import", "yaml",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "fastapi",
        "main.py",
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    print("  ✓ PyInstaller 完成")


def assemble():
    print("[3/4] 组装分发包...")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir(parents=True)

    exe_dir = ROOT / "dist" / PACKAGE_NAME  # PyInstaller 输出目录
    if exe_dir.exists():
        for item in exe_dir.iterdir():
            dest = BUILD_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        print(f"  ✓ 已复制 exe 文件")
    else:
        print("  ⚠ PyInstaller 输出目录不存在，将使用源码运行模式")
        # 复制源码
        for src_dir in ["src", "backend", "stories"]:
            shutil.copytree(ROOT / src_dir, BUILD_DIR / src_dir)
        shutil.copy2(ROOT / "main.py", BUILD_DIR / "main.py")

    # 复制前端 dist
    frontend_dist_src = ROOT / "frontend" / "dist"
    frontend_dist_dst = BUILD_DIR / "frontend" / "dist"
    if frontend_dist_src.exists():
        frontend_dist_dst.parent.mkdir(parents=True, exist_ok=True)
        if frontend_dist_dst.exists():
            shutil.rmtree(frontend_dist_dst)
        shutil.copytree(frontend_dist_src, frontend_dist_dst)
        print("  ✓ 已复制前端文件")

    # 创建启动脚本
    bat = '@echo off\r\ncd /d "%~dp0"\r\nstart "" AINovelInDialogue.exe\r\n'
    (BUILD_DIR / "启动.bat").write_text(bat)
    sh_path = '#!/bin/bash\ncd "$(dirname "$0")"\n./AINovelInDialogue &\n'
    (BUILD_DIR / "start.sh").write_text(sh_path)
    (BUILD_DIR / "start.sh").chmod(0o755)

    # 清理 PyInstaller 临时文件
    pyi_build = ROOT / "build"
    pyi_spec = ROOT / f"{PACKAGE_NAME}.spec"
    if pyi_build.exists():
        shutil.rmtree(pyi_build)
    # spec 文件保留用于调试

    print("  ✓ 组装完成")


def create_zip():
    print("[4/4] 创建压缩包...")
    zip_name = DIST_DIR / f"{PACKAGE_NAME}_v{VERSION}"
    shutil.make_archive(str(zip_name), "zip", DIST_DIR, PACKAGE_NAME)
    print(f"  ✓ {zip_name}.zip")


def main():
    skip_frontend = "--skip-frontend" in sys.argv
    skip_exe = "--skip-exe" in sys.argv

    # 确保 dist 目录存在
    DIST_DIR.mkdir(exist_ok=True)

    if not skip_frontend:
        build_frontend()
    else:
        # 检查前端是否已构建
        if not (ROOT / "frontend" / "dist" / "index.html").exists():
            print("  ⚠ 前端未构建！请先运行: cd frontend && npm run build")
            print("  或移除 --skip-frontend 参数")
            sys.exit(1)

    if not skip_exe:
        build_exe()

    assemble()
    create_zip()

    print(f"\n✓ 打包完成: dist/{PACKAGE_NAME}_v{VERSION}.zip")
    print("  解压后双击 '启动.bat' 即可运行")


if __name__ == "__main__":
    main()
