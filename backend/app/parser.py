"""Markdown Prompt Parser.
Parses structured markdown files (like prompts.md) into scenes with beat narasi,
full prompt codeblocks, tags, and dual/merged scene references.
"""

import re
from typing import Any


def parse_markdown_prompts(text: str) -> dict[str, Any]:
    """Parse a markdown prompt document into project title, format, and scene list."""
    # 1. Title Extraction
    title_match = re.search(r"^#\s+(.+)$", text, re.M)
    raw_title = title_match.group(1).strip() if title_match else "Imported Story"
    clean_title = re.sub(r"\\-", "-", raw_title)
    # Strip suffixes like "- Full Prompt per Scene"
    clean_title = re.sub(r"\s*-\s*Full Prompt.*$", "", clean_title, flags=re.I).strip()
    clean_title = clean_title.lstrip("#").strip()

    # 2. Format / Aspect Ratio Detection
    ratio_match = re.search(r"Aspect ratio:\s*(9:16|16:9)", text, re.I)
    detected_format = "16:9"
    if ratio_match:
        detected_format = ratio_match.group(1)
    elif re.search(r"9:16|vertical|portrait|shorts|tiktok|reels", text[:1000], re.I):
        detected_format = "9:16"

    # 3. Scene Extraction
    parts = re.split(r"(?:^|\n)##+\s+Scene\s+", text, flags=re.IGNORECASE)
    scenes = []
    num_to_index: dict[int, int] = {}
    prev_prompt = ""

    for part in parts[1:]:
        lines = part.strip().split("\n")
        if not lines:
            continue
        header_line = lines[0].strip()
        m = re.match(r"^(\d+)(.*)", header_line)
        if not m:
            continue
        scene_num = int(m.group(1))
        raw_tag = m.group(2).strip().replace(r"\-", "-").strip("- ").strip()

        # Narasi from "Beat narasi:" or "Narasi:" or "Voiceover:"
        narasi_m = re.search(
            r"(?:Beat\s+narasi|Narasi|Voiceover|VO)\s*:\s*([^\n]+(?:\n(?!\n|```|CREATE|OUTPUT|FIXED|BACKGROUND|CHARACTER|CAMERA|SCENE|OPTIONAL|NEGATIVE)[^\n]+)*)",
            part,
            re.I,
        )
        narration = narasi_m.group(1).strip() if narasi_m else ""

        # Code block containing prompt
        code_m = re.search(r"```(?:\w+)?\s*\n(.*?)```", part, re.DOTALL)
        prompt = ""
        is_merged = False
        merged_with = None

        if code_m:
            prompt = code_m.group(1).strip()
            prev_prompt = prompt
        else:
            # Check if this scene is merged to another scene (e.g. dual split-screen)
            merge_search = re.search(
                r"(?:digabung\s+ke\s+scene\s+|gabung\s+ke\s+scene\s+|use\s+scene\s+)(\d+)",
                part,
                re.I,
            )
            if merge_search:
                is_merged = True
                target_num = int(merge_search.group(1))
                if target_num in num_to_index:
                    merged_with = num_to_index[target_num]
                prompt = prev_prompt
            elif "gabung" in raw_tag.lower() or "gabung" in part.lower():
                is_merged = True
                prompt = prev_prompt
                # Default to previous scene if not explicitly specified
                if scenes:
                    merged_with = len(scenes) - 1

        idx = len(scenes)
        num_to_index[scene_num] = idx
        scenes.append({
            "scene_num": scene_num,
            "tag": raw_tag,
            "narration": narration,
            "prompt": prompt,
            "is_merged": is_merged,
            "merged_with": merged_with,
        })

    return {
        "title": clean_title,
        "format": detected_format,
        "total_scenes": len(scenes),
        "merged_scenes_count": sum(1 for s in scenes if s["is_merged"]),
        "scenes": scenes,
    }
