import json
from functools import lru_cache

from . import config
from .models import Project, Scene

PROMPT_PREFIX = "Create Image:"  # Flow is an agent; this keyword makes it generate an image

ORIENTATION = {"16:9": "16:9 landscape", "9:16": "9:16 vertical portrait"}


@lru_cache
def load_styles() -> dict[str, dict]:
    styles = {}
    for f in sorted(config.STYLES_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        styles[data["id"]] = data
    return styles


def get_style(style_id: str) -> dict:
    styles = load_styles()
    if style_id not in styles:
        raise KeyError(f"unknown style: {style_id}")
    return styles[style_id]


def build_prompt(project: Project, scene: Scene) -> str:
    # If the scene already has a dedicated full prompt (e.g. from markdown import), use it directly!
    if scene.prompt and scene.prompt.strip():
        p = scene.prompt.strip()
        if not p.lower().startswith("create image"):
            p = f"{PROMPT_PREFIX}\n\n{p}"
        return p

    style = get_style(project.style_id)
    parts = [
        PROMPT_PREFIX,
        "",
        style["intro"],
        "",
        f"Scene: {scene.scene_description.strip()}",
        "",
        f"Style: {style['style']}",
    ]
    if scene.title_text.strip():
        parts += ["", "Text: " + style["text"].replace("{title_text}", scene.title_text.strip())]
    else:
        parts += ["", "Text: no text in the image."]
    parts += ["", f"Composition: {ORIENTATION[project.format]}, {style['composition']}"]
    return "\n".join(parts)
