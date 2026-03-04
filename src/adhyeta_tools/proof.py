# SPDX-License-Identifier: MPL-2.0
import sys
import uuid
from pathlib import Path

import aiofiles
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from adhyeta_tools.config import Config

STATIC_DIR = Path(__file__).parent / "reader-static"
IMAGE_EXTS = (".jpg", ".jpeg", ".png")
HTTP_HEADERS = {"Cache-Control": "no-cache"}
SESSION_TOKEN = uuid.uuid4().hex


def create_app(images_dir: Path, output_dir: Path) -> Starlette:

    def uncached_json_response(x):
        return JSONResponse(x, headers=HTTP_HEADERS)

    def get_image_path(stem: str) -> Path | None:
        for ext in IMAGE_EXTS:
            p = images_dir / f"{stem}{ext}"
            if p.exists():
                return p
        return None

    def get_sorted_stems() -> list[str]:
        return sorted(p.stem for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)

    _stems_cache: list[str] | None = None

    def stems() -> list[str]:
        nonlocal _stems_cache
        if _stems_cache is None:
            _stems_cache = get_sorted_stems()
        return _stems_cache

    async def pages(request: Request):
        return uncached_json_response({"pages": stems(), "session": SESSION_TOKEN})

    async def get_image(request: Request):
        stem = request.path_params["stem"]
        path = get_image_path(stem)
        if not path:
            return Response("Not found", status_code=404)
        return FileResponse(path)

    async def get_text(request: Request):
        stem = request.path_params["stem"]
        md_path = output_dir / f"{stem}.md"
        if not md_path.exists():
            return uncached_json_response({"content": ""})
        async with aiofiles.open(md_path, "r", encoding="utf-8") as f:
            content = await f.read()
        return uncached_json_response({"content": content})

    async def save_text(request: Request):
        stem = request.path_params["stem"]
        if stem not in stems():
            return Response("Not found", status_code=404)
        body = await request.json()
        content = body.get("content", "")
        md_path = output_dir / f"{stem}.md"
        async with aiofiles.open(md_path, "w", encoding="utf-8") as f:
            await f.write(content)
        return uncached_json_response({"ok": True})

    routes = [
        Route("/pages", pages),
        Route("/image/{stem}", get_image),
        Route("/text/{stem}", get_text),
        Route("/text/{stem}", save_text, methods=["POST"]),
        Mount("/", StaticFiles(directory=STATIC_DIR, html=True)),
    ]

    return Starlette(routes=routes)


def process(project_dir: Path, cfg: Config):
    images_dir = project_dir / "images"
    output_dir = project_dir / "output"

    for d, name in [
        (project_dir, "project"),
        (images_dir, "images"),
        (output_dir, "output"),
    ]:
        if not d.is_dir():
            print(f"Error: {name} directory not found: {d}", file=sys.stderr)
            sys.exit(1)

    image_stems = sorted(p.stem for p in images_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    for stem in image_stems:
        if not (output_dir / f"{stem}.md").exists():
            print(f"Warning: no .md for {stem} — will be created on first save")

    print(f"Loaded {len(image_stems)} pages from {project_dir}")
    print(f"Open {cfg.proof_host}:{cfg.proof_port}")

    app = create_app(images_dir, output_dir)
    uvicorn.run(app, host=cfg.proof_host, port=cfg.proof_port)
    return 0
