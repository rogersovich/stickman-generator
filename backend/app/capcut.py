from __future__ import annotations
import json
import os
import platform
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Long panels (webtoon strips much taller than wide). Tune these by hand.
# ---------------------------------------------------------------------------
#: A panel counts as long when its height is more than this many times its width.
#: Per video shape: on a tall 9:16 screen a panel needs to be much longer to look small.
LONG_PANEL_RATIO = {"16:9": 1.25, "9:16": 4.0}
#: How much of the screen width a long panel fills once zoomed in (0.5 = half the width).
LONG_PANEL_FILL_WIDTH = 0.33
#: Never zoom a long panel in more than this (higher looks blurry).
LONG_PANEL_MAX_ZOOM = 3.0
#: Slow zoom out while the panel scrolls, so more of it shows by the end
#: (1.15 = ends 15% further out than it started; 1.0 = no zoom, only scrolling).
LONG_PANEL_ZOOM_OUT = 1.15
#: Scroll speed, in screen heights per second. Short panels scroll only part of the way.
LONG_PANEL_SCROLL_SPEED = 0.25
#: Set to True if "scroll down" moves up in CapCut (and the other way around).
LONG_PANEL_FLIP_Y = False


class CapCutDraftGenerator:
    """Generates CapCut Desktop drafts with Ken Burns zoom & pan effects."""

    def __init__(self, projects_dir: Optional[Path | str] = None):
        self.projects_dir = Path(projects_dir) if projects_dir else self.default_projects_dir()

    @staticmethod
    def default_projects_dir() -> Path:
        """CapCut Desktop's draft folder for the current OS."""
        if platform.system() == "Windows":
            local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
            return Path(local_appdata) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        return Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"

    @staticmethod
    def _generate_id() -> str:
        return str(uuid.uuid4()).upper()

    @staticmethod
    def _detect_installed_capcut_version() -> Optional[str]:
        """Detects installed CapCut app version on the current machine."""
        if platform.system() == "Darwin":
            plist_path = Path("/Applications/CapCut.app/Contents/Info.plist")
            if plist_path.exists():
                try:
                    import plistlib
                    with open(plist_path, "rb") as f:
                        pl = plistlib.load(f)
                    ver = pl.get("CFBundleShortVersionString")
                    if ver:
                        return str(ver).strip()
                except Exception:
                    pass
        elif platform.system() == "Windows":
            try:
                local_appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
                apps_dir = Path(local_appdata) / "CapCut" / "Apps"
                if apps_dir.exists():
                    vers = []
                    for d in apps_dir.iterdir():
                        if d.is_dir() and re.match(r"^\d+\.\d+", d.name):
                            m = re.match(r"^(\d+\.\d+\.\d+)", d.name)
                            if m:
                                vers.append(m.group(1))
                    if vers:
                        return sorted(vers, key=lambda v: [int(x) for x in v.split(".")])[-1]
            except Exception:
                pass
        return None

    def _detect_device_platform(self) -> Dict[str, Any]:
        """Detects host device identifiers by inspecting existing CapCut projects.
        
        CapCut's draft_load_verifier.cpp strictly compares hard_disk_id, mac_address,
        and device_id. If missing or mismatched, it aborts loading with
        'Current project is from an unusual path and cannot be used currently'.
        """
        installed_ver = self._detect_installed_capcut_version()

        if self.projects_dir.exists():
            for p in sorted(self.projects_dir.glob("*/draft_info.json"), key=lambda f: f.stat().st_mtime, reverse=True):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    lmp = data.get("last_modified_platform") or data.get("platform")
                    if isinstance(lmp, dict) and lmp.get("device_id") and lmp.get("mac_address"):
                        app_version = installed_ver or lmp.get("app_version", "9.1.0")
                        return {
                            "app_id": lmp.get("app_id", 359289),
                            "app_source": lmp.get("app_source", "cc"),
                            "app_version": app_version,
                            "device_id": lmp.get("device_id", "9e14fe0db5d51cc19323675405d9e8c0"),
                            "hard_disk_id": lmp.get("hard_disk_id", "ddead93669b8e36f0f0f650cef509326"),
                            "mac_address": lmp.get("mac_address", "c9981425609d074b6fb7aa6bff185b82"),
                            "os": lmp.get("os", "mac"),
                            "os_version": lmp.get("os_version", "26.3.1"),
                        }
                except Exception:
                    continue

        # Default fallback
        return {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": installed_ver or "9.1.0",
            "device_id": "9e14fe0db5d51cc19323675405d9e8c0",
            "hard_disk_id": "ddead93669b8e36f0f0f650cef509326",
            "mac_address": "c9981425609d074b6fb7aa6bff185b82",
            "os": "windows" if platform.system() == "Windows" else "mac",
            "os_version": platform.release() if platform.system() == "Windows" else "26.3.1",
        }

    @staticmethod
    def format_chapter_title(chap: str) -> str:
        c = (chap or "").strip()
        if "prolog" in c.lower():
            return "PROLOGUE"
        match = re.search(r"(\d+(?:\.\d+)?)", c)
        if match:
            num_str = match.group(1)
            if "." not in num_str:
                try:
                    num_str = str(int(num_str))
                except Exception:
                    pass
            return f"CHAPTER {num_str}"
        return c.upper().replace("-", " ").replace("_", " ")

    def _generate_title_card(
        self, text: str, output_path: Path, width: int = 1080, height: int = 1920
    ) -> Path:
        """Generates a stylish chapter divider image."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (width, height), color=(14, 16, 22))
        draw = ImageDraw.Draw(img)

        # Locate system font
        font_bold = None
        for font_candidate in [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/Library/Fonts/Arial.ttf",
            # Windows
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            # Linux
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            try:
                font_bold = ImageFont.truetype(font_candidate, int(height * 0.04))
                break
            except Exception:
                continue

        if not font_bold:
            font_bold = ImageFont.load_default()

        # Subtle frame border
        margin = int(min(width, height) * 0.08)
        draw.rectangle([margin, margin, width - margin, height - margin], outline=(38, 42, 54), width=2)

        # Title text
        bbox_title = draw.textbbox((0, 0), text, font=font_bold)
        tw = bbox_title[2] - bbox_title[0]
        th = bbox_title[3] - bbox_title[1]

        center_y = height / 2
        draw.text(((width - tw) / 2, center_y - th - 12), text, fill=(255, 255, 255), font=font_bold)

        # Warm amber accent line
        line_w = min(tw, int(width * 0.25))
        draw.rectangle(
            [(width - line_w) / 2, center_y + 14, (width + line_w) / 2, center_y + 17],
            fill=(235, 94, 40),
        )

        img.save(output_path, "JPEG", quality=95)
        return output_path

    @staticmethod
    def _add_panel_drop_shadow(
        image: Image.Image,
        intensity: str = "medium",
    ) -> Image.Image:
        """Adds a soft Gaussian drop shadow around a panel image.

        Returns an RGBA PIL Image with transparent padding and shadow falloff.
        """
        from PIL import ImageFilter, ImageDraw

        src = image.convert("RGBA")
        w, h = src.size

        min_dim = min(w, h)
        if intensity == "subtle":
            size_pct = 0.025
            opacity = 0.55
        elif intensity == "strong":
            size_pct = 0.055
            opacity = 0.90
        else:  # medium
            size_pct = 0.040
            opacity = 0.75

        shadow_size = max(20, min(100, int(min_dim * size_pct)))
        blur_radius = shadow_size * 0.5

        new_w = w + shadow_size * 2
        new_h = h + shadow_size * 2

        mask = Image.new("L", (new_w, new_h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle(
            [shadow_size, shadow_size, shadow_size + w - 1, shadow_size + h - 1],
            fill=int(255 * opacity),
        )
        blurred_mask = mask.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        shadow_layer = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
        shadow_layer.putalpha(blurred_mask)

        result = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
        result.alpha_composite(shadow_layer)
        result.paste(src, (shadow_size, shadow_size), src)

        return result

    def _render_text_watermark(
        self, text: str, output_path: Path, text_color: str = "#FFFFFF", opacity: float = 0.8
    ) -> Path:
        """Renders text watermark to a high-res transparent PNG image."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Find system font
        font = None
        for font_candidate in [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/Library/Fonts/Arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]:
            try:
                font = ImageFont.truetype(font_candidate, 72)
                break
            except Exception:
                continue

        if not font:
            font = ImageFont.load_default()

        # Dummy draw to calculate bounding box
        dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        d_draw = ImageDraw.Draw(dummy_img)
        bbox = d_draw.textbbox((0, 0), text, font=font)
        pad = 24
        tw = bbox[2] - bbox[0] + pad * 2
        th = bbox[3] - bbox[1] + pad * 2

        img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Parse text color (hex)
        c = text_color.lstrip("#")
        try:
            if len(c) == 6:
                r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            else:
                r, g, b = 255, 255, 255
        except Exception:
            r, g, b = 255, 255, 255

        alpha = max(10, min(255, int(255 * opacity)))

        # Soft shadow for readability against dark or bright backgrounds
        shadow_alpha = int(alpha * 0.7)
        draw.text((pad + 2 - bbox[0], pad + 2 - bbox[1]), text, fill=(0, 0, 0, shadow_alpha), font=font)
        # Main text
        draw.text((pad - bbox[0], pad - bbox[1]), text, fill=(r, g, b, alpha), font=font)

        img.save(output_path, "PNG")
        return output_path

    def create_draft(
        self,
        project_name: str,
        image_paths: List[Union[Path, str, Dict[str, Any], tuple]],
        duration_per_panel: float = 2.5,
        ratio: str = "16:9",
        ken_burns: bool = True,
        zoom_ratio: float = 1.15,
        canvas_blur: bool = True,
        canvas_blur_level: float = 0.25,
        panel_shadow: bool = False,
        panel_shadow_intensity: str = "medium",
        ken_burns_types: Optional[List[str]] = None,
        auto_upscale: bool = False,
        include_chapter_divider: bool = False,
        divider_duration: float = 1.5,
        audio_tracks: Optional[List[Dict[str, Any]]] = None,
        long_panels: bool = False,
        enable_zoom: bool = True,
        enable_pan: bool = True,
        watermark: Optional[Dict[str, Any]] = None,
        fade_in_ms: int = 0,
        overlays: Optional[List[Dict[str, Any]]] = None,
        intro_video: Optional[Dict[str, Any]] = None,
        enable_transitions: bool = True,
        transition_duration: float = 0.5,
        allowed_transitions: Optional[List[str]] = None,
    ) -> Path:
        """Creates a CapCut desktop draft folder with all panel images and Ken Burns keyframes.

        Args:
            project_name: Name of the CapCut project.
            image_paths: Ordered list of panel image paths, dicts ({"path": ..., "chapter": ...}), or tuples.
            duration_per_panel: Duration for each panel in seconds.
            ratio: Canvas aspect ratio ('9:16' for Shorts/TikTok, '16:9' for YouTube).
            ken_burns: Whether to apply alternating Ken Burns zoom & pan keyframes.
            zoom_ratio: Max scale for Ken Burns zoom effect (default 1.15 = 115%).
            canvas_blur: Whether to fill background letterbox with blurred panel image (recommended for 16:9).
            canvas_blur_level: CapCut canvas blur intensity (0.0625: Light, 0.125: Med, 0.25: Heavy, 0.375: Deep).
            panel_shadow: Whether to add a soft drop shadow border around panels (ideal for 3D pop effect).
            panel_shadow_intensity: Shadow intensity ('subtle', 'medium', 'strong').
            include_chapter_divider: Whether to insert title card dividers between chapters.
            divider_duration: Duration for each chapter divider title card in seconds.
            long_panels: Zoom long webtoon panels in and scroll them up or down instead of the
                usual Ken Burns move (see the LONG_PANEL_* settings at the top of this file).
            audio_tracks: Optional narration, one dict per chapter: {"path", "chapter", "duration"}
                (seconds). Each starts where that chapter's first panel starts. A panel item may
                carry its own "duration" (seconds) instead of `duration_per_panel`, so panels can
                follow the narration. Chapter start times end up in `self.chapter_starts_us`.
            fade_in_ms: Fade each panel in over this many milliseconds (an alpha keyframe), so a cut
                dissolves through the blurred canvas instead of jumping.
            overlays: Transparent images on their own track above the panels, e.g. burned-in captions:
                {"path", "start" (s), "duration" (s), "x", "y", "scale", "anim": "pop" | "fade" | None}.
                Positions are in half-canvas units (y > 0 is up). `pop` scales and slides the image in and
                fades it out; `fade` only fades.

        Returns:
            Path to the created project directory.
        """
        normalized_items: List[Dict[str, Any]] = []
        for item in image_paths:
            if isinstance(item, (str, Path)):
                p = Path(item)
                if p.exists():
                    normalized_items.append({"path": p, "chapter": None})
            elif isinstance(item, dict):
                if item.get("excluded") is True:
                    continue
                p = Path(item.get("path", ""))
                if p.exists():
                    normalized_items.append({
                        "path": p,
                        "chapter": item.get("chapter"),
                        "duration": item.get("duration"),
                        "is_end_page": bool(item.get("is_end_page")),
                    })
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                chap, p_raw = item
                p = Path(p_raw)
                if p.exists():
                    normalized_items.append({"path": p, "chapter": str(chap) if chap else None})

        if not normalized_items:
            raise ValueError("No valid image files provided for CapCut draft.")

        # Ensure project folder exists
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        project_dir = self.projects_dir / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        materials_dir = project_dir / "materials"
        materials_dir.mkdir(parents=True, exist_ok=True)

        # Microsecond timing
        duration_us = int(duration_per_panel * 1_000_000)
        now_us = int(time.time() * 1_000_000)

        # Canvas config
        if ratio == "9:16":
            canvas_w, canvas_h = 1080, 1920
        elif ratio == "16:9":
            canvas_w, canvas_h = 1920, 1080
        else:
            canvas_w, canvas_h = 1080, 1920

        timeline_id = self._generate_id()
        draft_id = self._generate_id()
        platform_info = self._detect_device_platform()

        video_materials: List[Dict[str, Any]] = []
        speed_materials: List[Dict[str, Any]] = []
        canvas_materials: List[Dict[str, Any]] = []
        placeholder_materials: List[Dict[str, Any]] = []
        sound_channel_materials: List[Dict[str, Any]] = []
        material_color_materials: List[Dict[str, Any]] = []
        vocal_sep_materials: List[Dict[str, Any]] = []
        meta_material_values: List[Dict[str, Any]] = []

        segments: List[Dict[str, Any]] = []
        current_time_us = 0
        #: where each chapter's first panel starts, for audio and subtitles
        self.chapter_starts_us: Dict[str, int] = {}
        total_materials_size = 0
        prev_chapter: Optional[str] = None
        last_ken_burns_anim: Optional[str] = None
        long_count = 0  # long panels so far, to alternate scrolling down and up

        intro_dur_us = 0
        if intro_video and intro_video.get("path"):
            intro_src = Path(intro_video["path"])
            if intro_src.is_file():
                intro_dur_us = max(1, int(round(float(intro_video.get("duration", 0)) * 1_000_000)))
                intro_w = int(intro_video.get("width") or canvas_w)
                intro_h = int(intro_video.get("height") or canvas_h)
                intro_has_audio = bool(intro_video.get("has_audio", True))

                intro_dir = materials_dir / "intro"
                intro_dir.mkdir(parents=True, exist_ok=True)
                dest_intro = intro_dir / intro_src.name
                if intro_src.resolve() != dest_intro.resolve():
                    shutil.copy2(intro_src, dest_intro)
                total_materials_size += dest_intro.stat().st_size

                intro_mat_id = self._generate_id()
                intro_speed_id = self._generate_id()
                intro_canvas_id = self._generate_id()
                intro_placeholder_id = self._generate_id()
                intro_sound_ch_id = self._generate_id()
                intro_color_id = self._generate_id()
                intro_vocal_id = self._generate_id()
                intro_seg_id = self._generate_id()

                video_materials.append(
                    {
                        "id": intro_mat_id,
                        "type": "video",
                        "duration": intro_dur_us,
                        "path": str(dest_intro.resolve()),
                        "width": intro_w,
                        "height": intro_h,
                        "category_id": "",
                        "category_name": "local",
                        "material_name": dest_intro.name,
                        "create_time": int(time.time()),
                        "has_audio": intro_has_audio,
                        "extra_info": "",
                        "local_id": "",
                        "media_path": "",
                        "reverse_path": "",
                        "check_flag": 62978047,
                        "crop": {
                            "upper_left_x": 0.0,
                            "upper_left_y": 0.0,
                            "upper_right_x": 1.0,
                            "upper_right_y": 0.0,
                            "lower_left_x": 0.0,
                            "lower_left_y": 1.0,
                            "lower_right_x": 1.0,
                            "lower_right_y": 1.0,
                        },
                        "crop_ratio": "free",
                        "crop_scale": 1.0,
                    }
                )
                speed_materials.append(
                    {
                        "curve_speed": None,
                        "id": intro_speed_id,
                        "mode": 0,
                        "speed": 1.0,
                        "type": "speed",
                    }
                )
                canvas_materials.append(
                    {
                        "id": intro_canvas_id,
                        "type": "canvas_color",
                        "color": "0xFF000000",
                        "blur": 0.0,
                        "image": "",
                        "album_image": "",
                        "image_id": "",
                        "image_name": "",
                        "source_platform": 0,
                        "team_id": "",
                    }
                )
                placeholder_materials.append(
                    {
                        "id": intro_placeholder_id,
                        "type": "placeholder_info",
                        "meta_type": "none",
                        "res_path": "",
                        "res_text": "",
                        "error_path": "",
                        "error_text": "",
                    }
                )
                sound_channel_materials.append(
                    {
                        "id": intro_sound_ch_id,
                        "type": "",
                        "audio_channel_mapping": 0,
                        "is_config_open": False,
                    }
                )
                material_color_materials.append(
                    {
                        "id": intro_color_id,
                        "is_color_clip": False,
                        "is_gradient": False,
                        "solid_color": "",
                        "gradient_colors": [],
                        "gradient_percents": [],
                        "gradient_angle": 90.0,
                        "width": 0.0,
                        "height": 0.0,
                    }
                )
                vocal_sep_materials.append(
                    {
                        "id": intro_vocal_id,
                        "type": "vocal_separation",
                        "choice": 0,
                        "removed_sounds": [],
                        "time_range": None,
                        "production_path": "",
                        "final_algorithm": "",
                        "enter_from": "",
                    }
                )
                meta_material_values.append(
                    {
                        "ai_group_type": "",
                        "create_time": int(time.time()),
                        "duration": intro_dur_us,
                        "enter_from": 0,
                        "extra_info": dest_intro.name,
                        "file_Path": str(dest_intro.resolve()),
                        "height": intro_h,
                        "id": str(uuid.uuid4()).lower(),
                        "import_time": int(time.time()),
                        "import_time_ms": int(time.time() * 1_000_000),
                        "item_source": 1,
                        "material_color_tag": "",
                        "md5": "",
                        "metetype": "video",
                        "roughcut_time_range": {"duration": -1, "start": -1},
                        "sub_time_range": {"duration": -1, "start": -1},
                        "type": 0,
                        "width": intro_w,
                    }
                )
                segments.append(
                    {
                        "id": intro_seg_id,
                        "material_id": intro_mat_id,
                        "source_timerange": {"start": 0, "duration": intro_dur_us},
                        "target_timerange": {
                            "start": 0,
                            "duration": intro_dur_us,
                        },
                        "render_timerange": {"start": 0, "duration": 0},
                        "speed": 1.0,
                        "volume": 1.0,
                        "last_nonzero_volume": 1.0,
                        "reverse": False,
                        "visible": True,
                        "track_attribute": 0,
                        "track_render_index": 0,
                        "extra_material_refs": [
                            intro_speed_id,
                            intro_placeholder_id,
                            intro_canvas_id,
                            intro_sound_ch_id,
                            intro_color_id,
                            intro_vocal_id,
                        ],
                        "clip": {
                            "alpha": 1.0,
                            "flip": {"horizontal": False, "vertical": False},
                            "rotation": 0.0,
                            "scale": {"x": 1.0, "y": 1.0},
                            "transform": {"x": 0.0, "y": 0.0},
                        },
                        "common_keyframes": [],
                        "keyframe_refs": [],
                        "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
                    }
                )
                current_time_us = intro_dur_us

        for idx, item in enumerate(normalized_items):
            img_path: Path = item["path"]
            chapter: Optional[str] = item.get("chapter")

            # Check if we should insert a chapter divider before this panel
            if include_chapter_divider and chapter and chapter != prev_chapter:
                div_mat_id = self._generate_id()
                div_speed_id = self._generate_id()
                div_seg_id = self._generate_id()
                div_canvas_id = self._generate_id()
                div_placeholder_id = self._generate_id()
                div_sound_ch_id = self._generate_id()
                div_color_id = self._generate_id()
                div_vocal_id = self._generate_id()

                div_dir = materials_dir / str(chapter)
                div_dir.mkdir(parents=True, exist_ok=True)
                divider_file = div_dir / f"{chapter}_divider.jpg"

                title_text = self.format_chapter_title(str(chapter))
                self._generate_title_card(title_text, divider_file, width=canvas_w, height=canvas_h)
                total_materials_size += divider_file.stat().st_size

                # Divider video material
                video_materials.append(
                    {
                        "id": div_mat_id,
                        "type": "photo",
                        "duration": 10800000000,
                        "path": str(divider_file.resolve()),
                        "width": canvas_w,
                        "height": canvas_h,
                        "category_id": "",
                        "category_name": "local",
                        "material_name": divider_file.name,
                        "create_time": int(time.time()),
                        "has_audio": False,
                        "extra_info": "",
                        "local_id": "",
                        "media_path": "",
                        "reverse_path": "",
                        "check_flag": 62978047,
                        "crop": {
                            "upper_left_x": 0.0,
                            "upper_left_y": 0.0,
                            "upper_right_x": 1.0,
                            "upper_right_y": 0.0,
                            "lower_left_x": 0.0,
                            "lower_left_y": 1.0,
                            "lower_right_x": 1.0,
                            "lower_right_y": 1.0,
                        },
                        "crop_ratio": "free",
                        "crop_scale": 1.0,
                    }
                )

                speed_materials.append(
                    {
                        "curve_speed": None,
                        "id": div_speed_id,
                        "mode": 0,
                        "speed": 1.0,
                        "type": "speed",
                    }
                )
                canvas_materials.append(
                    {
                        "id": div_canvas_id,
                        "type": "canvas_color",
                        "color": "0xFF0E1016",
                        "blur": 0.0,
                        "image": "",
                        "album_image": "",
                        "image_id": "",
                        "image_name": "",
                        "source_platform": 0,
                        "team_id": "",
                    }
                )
                placeholder_materials.append(
                    {
                        "id": div_placeholder_id,
                        "type": "placeholder_info",
                        "meta_type": "none",
                        "res_path": "",
                        "res_text": "",
                        "error_path": "",
                        "error_text": "",
                    }
                )
                sound_channel_materials.append(
                    {
                        "id": div_sound_ch_id,
                        "type": "",
                        "audio_channel_mapping": 0,
                        "is_config_open": False,
                    }
                )
                material_color_materials.append(
                    {
                        "id": div_color_id,
                        "is_color_clip": False,
                        "is_gradient": False,
                        "solid_color": "",
                        "gradient_colors": [],
                        "gradient_percents": [],
                        "gradient_angle": 90.0,
                        "width": 0.0,
                        "height": 0.0,
                    }
                )
                vocal_sep_materials.append(
                    {
                        "id": div_vocal_id,
                        "type": "vocal_separation",
                        "choice": 0,
                        "removed_sounds": [],
                        "time_range": None,
                        "production_path": "",
                        "final_algorithm": "",
                        "enter_from": "",
                    }
                )
                meta_material_values.append(
                    {
                        "ai_group_type": "",
                        "create_time": int(time.time()),
                        "duration": 5000000,
                        "enter_from": 0,
                        "extra_info": divider_file.name,
                        "file_Path": str(divider_file.resolve()),
                        "height": canvas_h,
                        "id": str(uuid.uuid4()).lower(),
                        "import_time": int(time.time()),
                        "import_time_ms": int(time.time() * 1_000_000),
                        "item_source": 1,
                        "material_color_tag": "",
                        "md5": "",
                        "metetype": "photo",
                        "roughcut_time_range": {"duration": -1, "start": -1},
                        "sub_time_range": {"duration": -1, "start": -1},
                        "type": 0,
                        "width": canvas_w,
                    }
                )

                div_dur_us = int(divider_duration * 1_000_000)
                segments.append(
                    {
                        "id": div_seg_id,
                        "material_id": div_mat_id,
                        "source_timerange": {"start": 0, "duration": div_dur_us},
                        "target_timerange": {
                            "start": current_time_us,
                            "duration": div_dur_us,
                        },
                        "render_timerange": {"start": 0, "duration": 0},
                        "speed": 1.0,
                        "volume": 1.0,
                        "last_nonzero_volume": 1.0,
                        "reverse": False,
                        "visible": True,
                        "track_attribute": 0,
                        "track_render_index": 0,
                        "extra_material_refs": [
                            div_speed_id,
                            div_placeholder_id,
                            div_canvas_id,
                            div_sound_ch_id,
                            div_color_id,
                            div_vocal_id,
                        ],
                        "clip": {
                            "alpha": 1.0,
                            "flip": {"horizontal": False, "vertical": False},
                            "rotation": 0.0,
                            "scale": {"x": 1.0, "y": 1.0},
                            "transform": {"x": 0.0, "y": 0.0},
                        },
                        "common_keyframes": [],
                        "keyframe_refs": [],
                        "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
                    }
                )
                current_time_us += div_dur_us
                prev_chapter = chapter
            elif chapter:
                prev_chapter = chapter

            if chapter and chapter not in self.chapter_starts_us:
                self.chapter_starts_us[chapter] = current_time_us
            item_duration_us = (
                max(1, int(round(float(item["duration"]) * 1_000_000)))
                if item.get("duration") is not None else duration_us
            )

            mat_id = self._generate_id()
            speed_id = self._generate_id()
            seg_id = self._generate_id()
            canvas_id = self._generate_id()
            placeholder_id = self._generate_id()
            sound_ch_id = self._generate_id()
            color_id = self._generate_id()
            vocal_id = self._generate_id()

            # Copy or process image into project materials directory (with chapter subfolder if chapter specified)
            if chapter:
                target_folder = materials_dir / str(chapter)
                target_folder.mkdir(parents=True, exist_ok=True)
            else:
                target_folder = materials_dir

            # If auto-upscale is enabled, check if panel is low-res (< 700px) and upscale it
            source_for_material = img_path
            if auto_upscale:
                try:
                    with Image.open(img_path) as check_im:
                        chk_w, chk_h = check_im.size
                    if min(chk_w, chk_h) < 700:
                        try:
                            from .utils.upscaler import upscaler
                            upscaled_cache = target_folder / f"{img_path.stem}_ai_upscaled.png"
                            if not upscaled_cache.exists() or upscaled_cache.stat().st_size == 0:
                                upscaler.upscale_image(img_path, output_path=upscaled_cache, scale=2, model="realesr-animevideov3")
                            if upscaled_cache.exists() and upscaled_cache.stat().st_size > 0:
                                source_for_material = upscaled_cache
                        except ImportError:
                            pass
                except Exception as e:
                    print(f"[CapCut] Auto-upscale fallback on {img_path.name}: {e}")

            if panel_shadow:
                dest_img_path = target_folder / f"{img_path.stem}.png"
                try:
                    if not dest_img_path.exists() or dest_img_path.stat().st_size == 0:
                        with Image.open(source_for_material) as src_im:
                            shadowed = self._add_panel_drop_shadow(
                                src_im, intensity=panel_shadow_intensity
                            )
                            shadowed.save(dest_img_path, format="PNG")
                except Exception:
                    dest_img_path = target_folder / source_for_material.name
                    if not dest_img_path.exists() or dest_img_path.stat().st_size != source_for_material.stat().st_size:
                        shutil.copy2(source_for_material, dest_img_path)
            else:
                dest_img_path = target_folder / source_for_material.name
                try:
                    if not dest_img_path.exists() or dest_img_path.stat().st_size != source_for_material.stat().st_size:
                        shutil.copy2(source_for_material, dest_img_path)
                except Exception:
                    dest_img_path = source_for_material

            # Ensure .jpg files are true JPEG format (not PNG bytes with .jpg extension)
            if dest_img_path.exists() and dest_img_path.suffix.lower() in (".jpg", ".jpeg"):
                try:
                    with Image.open(dest_img_path) as chk_im:
                        if chk_im.format != "JPEG":
                            rgb_im = chk_im.convert("RGB") if chk_im.mode != "RGB" else chk_im.copy()
                            rgb_im.save(dest_img_path, format="JPEG", quality=95, subsampling=0)
                except Exception as e:
                    print(f"[CapCut] Warning converting panel to true JPEG: {e}")

            # Read image dimensions & byte size
            try:
                with Image.open(dest_img_path) as img:
                    img_w, img_h = img.size
                file_size = dest_img_path.stat().st_size
            except Exception:
                img_w, img_h = canvas_w, canvas_h
                file_size = 500_000
            total_materials_size += file_size

            # 1. Video Material (photo)
            video_materials.append(
                {
                    "id": mat_id,
                    "type": "photo",
                    "duration": 10800000000,
                    "path": str(dest_img_path.resolve()),
                    "width": img_w,
                    "height": img_h,
                    "category_id": "",
                    "category_name": "local",
                    "material_name": img_path.name,
                    "create_time": int(time.time()),
                    "has_audio": False,
                    "extra_info": "",
                    "local_id": "",
                    "media_path": "",
                    "reverse_path": "",
                    "check_flag": 62978047,
                    "crop": {
                        "upper_left_x": 0.0,
                        "upper_left_y": 0.0,
                        "upper_right_x": 1.0,
                        "upper_right_y": 0.0,
                        "lower_left_x": 0.0,
                        "lower_left_y": 1.0,
                        "lower_right_x": 1.0,
                        "lower_right_y": 1.0,
                    },
                    "crop_ratio": "free",
                    "crop_scale": 1.0,
                }
            )

            # Auxiliary materials
            speed_materials.append(
                {
                    "curve_speed": None,
                    "id": speed_id,
                    "mode": 0,
                    "speed": 1.0,
                    "type": "speed",
                }
            )
            canvas_materials.append(
                {
                    "id": canvas_id,
                    "type": "canvas_blur" if canvas_blur else "canvas_color",
                    "color": "",
                    "blur": canvas_blur_level if canvas_blur else 0.0,
                    "image": "",
                    "album_image": "",
                    "image_id": "",
                    "image_name": "",
                    "source_platform": 0,
                    "team_id": "",
                }
            )
            placeholder_materials.append(
                {
                    "id": placeholder_id,
                    "type": "placeholder_info",
                    "meta_type": "none",
                    "res_path": "",
                    "res_text": "",
                    "error_path": "",
                    "error_text": "",
                }
            )
            sound_channel_materials.append(
                {
                    "id": sound_ch_id,
                    "type": "",
                    "audio_channel_mapping": 0,
                    "is_config_open": False,
                }
            )
            material_color_materials.append(
                {
                    "id": color_id,
                    "is_color_clip": False,
                    "is_gradient": False,
                    "solid_color": "",
                    "gradient_colors": [],
                    "gradient_percents": [],
                    "gradient_angle": 90.0,
                    "width": 0.0,
                    "height": 0.0,
                }
            )
            vocal_sep_materials.append(
                {
                    "id": vocal_id,
                    "type": "vocal_separation",
                    "choice": 0,
                    "removed_sounds": [],
                    "time_range": None,
                    "production_path": "",
                    "final_algorithm": "",
                    "enter_from": "",
                }
            )

            meta_material_values.append(
                {
                    "ai_group_type": "",
                    "create_time": int(time.time()),
                    "duration": 5000000,
                    "enter_from": 0,
                    "extra_info": img_path.name,
                    "file_Path": str(dest_img_path.resolve()),
                    "height": img_h,
                    "id": str(uuid.uuid4()).lower(),
                    "import_time": int(time.time()),
                    "import_time_ms": int(time.time() * 1_000_000),
                    "item_source": 1,
                    "material_color_tag": "",
                    "md5": "",
                    "metetype": "photo",
                    "roughcut_time_range": {"duration": -1, "start": -1},
                    "sub_time_range": {"duration": -1, "start": -1},
                    "type": 0,
                    "width": img_w,
                }
            )

            # 2. Aspect-Ratio-Aware Ken Burns Keyframes
            common_keyframes: List[Dict[str, Any]] = []
            clip_scale = {"x": 1.0, "y": 1.0}
            clip_transform = {"x": 0.0, "y": 0.0}

            if item.get("is_end_page"):
                # End Page: centered card with scale 0.45, no zoom animation, show fade-in 1.0s default
                scale_val = 0.45
                clip_scale = {"x": scale_val, "y": scale_val}
                clip_transform = {"x": 0.0, "y": 0.0}
                show_fade_us = min(1_000_000, max(1, item_duration_us))
                common_keyframes = [
                    self._create_kf_list("KFTypeAlpha", [(0, 0.0), (show_fade_us, 1.0)])
                ]
            else:
                long_kf = (
                    self._long_panel_keyframes(
                        img_w, img_h, canvas_w, canvas_h, ratio, item_duration_us, long_count,
                        zoom_ratio=zoom_ratio if enable_zoom else 1.0,
                    )
                    if ken_burns and long_panels and enable_pan else None
                )
                if long_kf is not None:
                    common_keyframes, clip_scale = long_kf
                    long_count += 1
                elif ken_burns and (enable_zoom or enable_pan):
                    common_keyframes, clip_scale, last_ken_burns_anim = self._generate_ken_burns_keyframes(
                        img_w=img_w,
                        img_h=img_h,
                        idx=idx,
                        duration_us=item_duration_us,
                        zoom_ratio=zoom_ratio,
                        last_anim=last_ken_burns_anim,
                        ken_burns_types=ken_burns_types,
                        enable_zoom=enable_zoom,
                        enable_pan=enable_pan,
                        ratio=ratio,
                        canvas_w=canvas_w,
                        canvas_h=canvas_h,
                    )

            if not item.get("is_end_page") and fade_in_ms > 0 and idx > 0:
                fade_us = min(int(fade_in_ms * 1000), max(1, item_duration_us // 2))
                common_keyframes = list(common_keyframes) + [
                    self._create_kf_list("KFTypeAlpha", [(0, 0.0), (fade_us, 1.0)])
                ]

            # 3. Segment
            segments.append(
                {
                    "id": seg_id,
                    "material_id": mat_id,
                    "source_timerange": {"start": 0, "duration": item_duration_us},
                    "target_timerange": {
                        "start": current_time_us,
                        "duration": item_duration_us,
                    },
                    "render_timerange": {"start": 0, "duration": 0},
                    "speed": 1.0,
                    "volume": 1.0,
                    "last_nonzero_volume": 1.0,
                    "reverse": False,
                    "visible": True,
                    "track_attribute": 0,
                    "track_render_index": 0,
                    "extra_material_refs": [
                        speed_id,
                        placeholder_id,
                        canvas_id,
                        sound_ch_id,
                        color_id,
                        vocal_id,
                    ],
                    "clip": {
                        "alpha": 1.0,
                        "flip": {"horizontal": False, "vertical": False},
                        "rotation": 0.0,
                        "scale": clip_scale,
                        "transform": clip_transform,
                    },
                    "common_keyframes": common_keyframes,
                    "keyframe_refs": [],
                    "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
                }
            )

            current_time_us += item_duration_us

        total_duration_us = current_time_us

        # Apply random transitions between storyboard image panels
        transition_materials: List[Dict[str, Any]] = []
        if enable_transitions and len(segments) > 1:
            try:
                from .capcut_transitions import pick_random_transition, build_transition_material
                start_seg_idx = 1 if intro_dur_us > 0 else 0
                for s_idx in range(start_seg_idx, len(segments) - 1):
                    seg = segments[s_idx]
                    next_seg = segments[s_idx + 1]
                    t_meta = pick_random_transition(allowed=allowed_transitions)
                    if t_meta:
                        t_id = self._generate_id()
                        clip_min_dur = min(
                            seg["target_timerange"]["duration"],
                            next_seg["target_timerange"]["duration"],
                        )
                        t_dur_s = max(0.1, min(float(transition_duration), 1.0))
                        t_dur_us = min(int(round(t_dur_s * 1_000_000)), max(100_000, int(clip_min_dur * 0.9)))
                        t_material = build_transition_material(
                            t_meta,
                            duration_s=t_dur_us / 1_000_000,
                            transition_id=t_id,
                        )
                        transition_materials.append(t_material)
                        seg["extra_material_refs"].append(t_id)
            except Exception as e:
                print(f"[CapCut] Warning applying transitions: {e}")

        audio_materials, audio_segments, audio_aux, audio_meta = self._audio_track(
            audio_tracks or [], materials_dir, total_duration_us
        )
        total_materials_size += sum(Path(m["path"]).stat().st_size for m in audio_materials)
        meta_material_values.extend(audio_meta)

        # Build Main Video Track
        track_id = self._generate_id()
        # Assemble Video Tracks
        track_id = self._generate_id()
        tracks = [
            {
                "id": track_id,
                "type": "video",
                "attribute": 0,
                "flag": 0,
                "name": "",
                "is_default_name": True,
                "segments": segments,
            }
        ]

        # Overlay track (burned-in captions and the like), above the panels and below the watermark
        overlay_segments: List[Dict[str, Any]] = []
        for ov in overlays or []:
            ov_path = Path(ov.get("path", ""))
            if not ov_path.exists():
                continue
            with Image.open(ov_path) as im:
                ov_w, ov_h = im.size
            ov_dir = materials_dir / "overlays"
            ov_dir.mkdir(parents=True, exist_ok=True)
            ov_dest = ov_dir / ov_path.name
            if ov_path.resolve() != ov_dest.resolve():
                shutil.copy2(ov_path, ov_dest)
            total_materials_size += ov_dest.stat().st_size

            ov_ids = {k: self._generate_id() for k in ("mat", "speed", "canvas", "placeholder", "sound", "color", "vocal")}
            video_materials.append({
                "id": ov_ids["mat"], "type": "photo", "duration": 10800000000, "path": str(ov_dest.resolve()),
                "width": ov_w, "height": ov_h, "category_id": "", "category_name": "local",
                "material_name": ov_dest.name, "create_time": int(time.time()), "has_audio": False, "extra_info": "",
                "local_id": "", "media_path": "", "reverse_path": "", "check_flag": 62978047,
                "crop": {"upper_left_x": 0.0, "upper_left_y": 0.0, "upper_right_x": 1.0, "upper_right_y": 0.0,
                         "lower_left_x": 0.0, "lower_left_y": 1.0, "lower_right_x": 1.0, "lower_right_y": 1.0},
                "crop_ratio": "free", "crop_scale": 1.0,
            })
            speed_materials.append({"curve_speed": None, "id": ov_ids["speed"], "mode": 0, "speed": 1.0, "type": "speed"})
            canvas_materials.append({
                "id": ov_ids["canvas"], "type": "canvas_color", "color": "", "blur": 0.0, "image": "",
                "album_image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": "",
            })
            placeholder_materials.append({
                "id": ov_ids["placeholder"], "type": "placeholder_info", "meta_type": "none", "res_path": "",
                "res_text": "", "error_path": "", "error_text": "",
            })
            sound_channel_materials.append(
                {"id": ov_ids["sound"], "type": "", "audio_channel_mapping": 0, "is_config_open": False})
            material_color_materials.append({
                "id": ov_ids["color"], "is_color_clip": False, "is_gradient": False, "solid_color": "",
                "gradient_colors": [], "gradient_percents": [], "gradient_angle": 90.0, "width": 0.0, "height": 0.0,
            })
            vocal_sep_materials.append({
                "id": ov_ids["vocal"], "type": "vocal_separation", "choice": 0, "removed_sounds": [],
                "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": "",
            })
            meta_material_values.append({
                "ai_group_type": "", "create_time": int(time.time()), "duration": 5000000, "enter_from": 0,
                "extra_info": ov_dest.name, "file_Path": str(ov_dest.resolve()), "height": ov_h,
                "id": str(uuid.uuid4()).lower(), "import_time": int(time.time()),
                "import_time_ms": int(time.time() * 1_000_000), "item_source": 1, "material_color_tag": "",
                "md5": "", "metetype": "photo", "roughcut_time_range": {"duration": -1, "start": -1},
                "sub_time_range": {"duration": -1, "start": -1}, "type": 0, "width": ov_w,
            })

            ov_start = max(0, int(round(float(ov.get("start", 0)) * 1_000_000)))
            ov_dur = max(1, int(round(float(ov.get("duration", 1)) * 1_000_000)))
            ov_dur = min(ov_dur, max(1, total_duration_us - ov_start))
            ov_x, ov_y = float(ov.get("x", 0.0)), float(ov.get("y", 0.0))
            ov_scale = float(ov.get("scale", 1.0))
            ov_keyframes: List[Dict[str, Any]] = []
            anim = ov.get("anim")
            if anim in ("pop", "fade"):
                fade_out = min(120_000, ov_dur // 4)
                alpha_pts = [(0, 0.0), (min(110_000, ov_dur // 3), 1.0)]
                if ov_dur > 500_000:
                    alpha_pts += [(ov_dur - fade_out, 1.0), (ov_dur, 0.0)]
                ov_keyframes.append(self._create_kf_list("KFTypeAlpha", alpha_pts))
            if anim == "pop":
                t1, t2 = min(150_000, ov_dur // 3), min(260_000, ov_dur // 2)
                ov_keyframes += [
                    self._create_kf_list("KFTypeScaleX", [(0, ov_scale * 0.80), (t1, ov_scale * 1.06), (t2, ov_scale)]),
                    self._create_kf_list("KFTypeScaleY", [(0, ov_scale * 0.80), (t1, ov_scale * 1.06), (t2, ov_scale)]),
                    self._create_kf_list("KFTypePositionY", [(0, round(ov_y - 0.035, 4)), (t2, round(ov_y, 4))]),
                ]
            overlay_segments.append({
                "id": self._generate_id(), "material_id": ov_ids["mat"],
                "source_timerange": {"start": 0, "duration": ov_dur},
                "target_timerange": {"start": ov_start, "duration": ov_dur},
                "render_timerange": {"start": 0, "duration": 0}, "speed": 1.0, "volume": 1.0,
                "last_nonzero_volume": 1.0, "reverse": False, "visible": True, "track_attribute": 0,
                "track_render_index": 2,
                "extra_material_refs": [ov_ids["speed"], ov_ids["placeholder"], ov_ids["canvas"], ov_ids["sound"],
                                        ov_ids["color"], ov_ids["vocal"]],
                "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False}, "rotation": 0.0,
                         "scale": {"x": ov_scale, "y": ov_scale}, "transform": {"x": ov_x, "y": ov_y}},
                "common_keyframes": ov_keyframes, "keyframe_refs": [],
                "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
            })
        if overlay_segments:
            tracks.append({
                "id": self._generate_id(), "type": "video", "attribute": 0, "flag": 0, "name": "Captions",
                "is_default_name": False, "segments": overlay_segments,
            })

        # Overlay Watermark Track (spanning the full video timeline)
        if watermark:
            try:
                actual_wm = dict(watermark)
                target_ratio = "9:16" if ratio == "9:16" else "16:9"
                if "ratios" in actual_wm and isinstance(actual_wm["ratios"], dict):
                    if target_ratio in actual_wm["ratios"] and isinstance(actual_wm["ratios"][target_ratio], dict):
                        actual_wm = {**actual_wm, **actual_wm["ratios"][target_ratio]}

                if actual_wm.get("enabled", True):
                    wm_type = actual_wm.get("type", "image")
                    wm_opacity = max(0.05, min(1.0, float(actual_wm.get("opacity", 0.8))))
                    wm_scale_factor = max(0.05, min(1.0, float(actual_wm.get("scale", 0.18))))
                    wm_pos = actual_wm.get("position_mode", "top-right")

                    # Coordinate positions in CapCut: (0, 0) is center, [-1.0, 1.0]
                    pos_map = {
                        "top-left": (-0.78, 0.78),
                        "top-right": (0.78, 0.78),
                        "bottom-left": (-0.78, -0.78),
                        "bottom-right": (0.78, -0.78),
                        "center": (0.0, 0.0),
                    }
                    if wm_pos in pos_map:
                        wm_x, wm_y = pos_map[wm_pos]
                    else:
                        wm_x = max(-1.0, min(1.0, float(actual_wm.get("x", 0.78))))
                        wm_y = max(-1.0, min(1.0, float(actual_wm.get("y", 0.78))))

                    wm_img_path: Optional[Path] = None
                    wm_materials_dir = materials_dir / "watermark"
                    wm_materials_dir.mkdir(parents=True, exist_ok=True)

                    if wm_type == "text":
                        wm_text = actual_wm.get("text", "MANHWA RECAP").strip() or "MANHWA RECAP"
                        wm_color = actual_wm.get("text_color", "#FFFFFF")
                        dest_wm = wm_materials_dir / "watermark_text.png"
                        self._render_text_watermark(wm_text, dest_wm, text_color=wm_color, opacity=wm_opacity)
                        wm_img_path = dest_wm
                    else:
                        # Image logo watermark
                        custom_logo = actual_wm.get("logo_path")
                        if custom_logo and Path(custom_logo).exists():
                            src_logo = Path(custom_logo)
                        else:
                            src_logo = None

                        if src_logo and src_logo.exists() and src_logo.stat().st_size > 0:
                            dest_wm = wm_materials_dir / "watermark_logo.png"
                            # Process image with alpha transparency
                            with Image.open(src_logo) as im:
                                rgba_wm = im.convert("RGBA")
                                if wm_opacity < 0.99:
                                    r, g, b, a = rgba_wm.split()
                                    a = a.point(lambda p: int(p * wm_opacity))
                                    rgba_wm = Image.merge("RGBA", (r, g, b, a))
                                rgba_wm.save(dest_wm, "PNG")
                            wm_img_path = dest_wm

                if wm_img_path and wm_img_path.exists():
                    with Image.open(wm_img_path) as im:
                        wm_w, wm_h = im.size
                    wm_size_bytes = wm_img_path.stat().st_size
                    total_materials_size += wm_size_bytes

                    wm_mat_id = self._generate_id()
                    wm_speed_id = self._generate_id()
                    wm_canvas_id = self._generate_id()
                    wm_placeholder_id = self._generate_id()
                    wm_sound_ch_id = self._generate_id()
                    wm_color_id = self._generate_id()
                    wm_vocal_id = self._generate_id()

                    video_materials.append(
                        {
                            "id": wm_mat_id,
                            "type": "photo",
                            "duration": 10800000000,
                            "path": str(wm_img_path.resolve()),
                            "width": wm_w,
                            "height": wm_h,
                            "category_id": "",
                            "category_name": "local",
                            "material_name": wm_img_path.name,
                            "create_time": int(time.time()),
                            "has_audio": False,
                            "extra_info": "",
                            "local_id": "",
                            "media_path": "",
                            "reverse_path": "",
                            "check_flag": 62978047,
                            "crop": {
                                "upper_left_x": 0.0,
                                "upper_left_y": 0.0,
                                "upper_right_x": 1.0,
                                "upper_right_y": 0.0,
                                "lower_left_x": 0.0,
                                "lower_left_y": 1.0,
                                "lower_right_x": 1.0,
                                "lower_right_y": 1.0,
                            },
                            "crop_ratio": "free",
                            "crop_scale": 1.0,
                        }
                    )
                    speed_materials.append(
                        {"curve_speed": None, "id": wm_speed_id, "mode": 0, "speed": 1.0, "type": "speed"}
                    )
                    canvas_materials.append(
                        {
                            "id": wm_canvas_id,
                            "type": "canvas_color",
                            "color": "",
                            "blur": 0.0,
                            "image": "",
                            "album_image": "",
                            "image_id": "",
                            "image_name": "",
                            "source_platform": 0,
                            "team_id": "",
                        }
                    )
                    placeholder_materials.append(
                        {
                            "id": wm_placeholder_id,
                            "type": "placeholder_info",
                            "meta_type": "none",
                            "res_path": "",
                            "res_text": "",
                            "error_path": "",
                            "error_text": "",
                        }
                    )
                    sound_channel_materials.append(
                        {"id": wm_sound_ch_id, "type": "", "audio_channel_mapping": 0, "is_config_open": False}
                    )
                    material_color_materials.append(
                        {
                            "id": wm_color_id,
                            "is_color_clip": False,
                            "is_gradient": False,
                            "solid_color": "",
                            "gradient_colors": [],
                            "gradient_percents": [],
                            "gradient_angle": 90.0,
                            "width": 0.0,
                            "height": 0.0,
                        }
                    )
                    vocal_sep_materials.append(
                        {
                            "id": wm_vocal_id,
                            "type": "vocal_separation",
                            "choice": 0,
                            "removed_sounds": [],
                            "time_range": None,
                            "production_path": "",
                            "final_algorithm": "",
                            "enter_from": "",
                        }
                    )
                    meta_material_values.append(
                        {
                            "ai_group_type": "",
                            "create_time": int(time.time()),
                            "duration": 5000000,
                            "enter_from": 0,
                            "extra_info": wm_img_path.name,
                            "file_Path": str(wm_img_path.resolve()),
                            "height": wm_h,
                            "id": str(uuid.uuid4()).lower(),
                            "import_time": int(time.time()),
                            "import_time_ms": int(time.time() * 1_000_000),
                            "item_source": 1,
                            "material_color_tag": "",
                            "md5": "",
                            "metetype": "photo",
                            "roughcut_time_range": {"duration": -1, "start": -1},
                            "sub_time_range": {"duration": -1, "start": -1},
                            "type": 0,
                            "width": wm_w,
                        }
                    )

                    wm_start_us = intro_dur_us if intro_dur_us > 0 else 0
                    wm_dur_us = max(1, total_duration_us - wm_start_us)
                    wm_segment = {
                        "id": self._generate_id(),
                        "material_id": wm_mat_id,
                        "source_timerange": {"start": 0, "duration": wm_dur_us},
                        "target_timerange": {
                            "start": wm_start_us,
                            "duration": wm_dur_us,
                        },
                        "render_timerange": {"start": 0, "duration": 0},
                        "speed": 1.0,
                        "volume": 1.0,
                        "last_nonzero_volume": 1.0,
                        "reverse": False,
                        "visible": True,
                        "track_attribute": 0,
                        "track_render_index": 1,
                        "render_index": 1,
                        "uniform_scale": {"on": True, "value": 1.0},
                        "enable_video_mask": True,
                        "extra_material_refs": [
                            wm_speed_id,
                            wm_placeholder_id,
                            wm_canvas_id,
                            wm_sound_ch_id,
                            wm_color_id,
                            wm_vocal_id,
                        ],
                        "clip": {
                            "alpha": 1.0,
                            "flip": {"horizontal": False, "vertical": False},
                            "rotation": 0.0,
                            "scale": {"x": wm_scale_factor, "y": wm_scale_factor},
                            "transform": {"x": wm_x, "y": wm_y},
                        },
                        "common_keyframes": [],
                        "keyframe_refs": [],
                        "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
                    }

                    tracks.append(
                        {
                            "id": self._generate_id(),
                            "type": "video",
                            "attribute": 0,
                            "flag": 2,
                            "name": "Watermark",
                            "is_default_name": False,
                            "segments": [wm_segment],
                        }
                    )
            except Exception as e:
                print(f"[CapCut] Watermark overlay track warning: {e}")

        # clips with a different `lane` (e.g. background music) go on their own audio track so they can overlap
        for lane in sorted({sg.get("_lane", 0) for sg in audio_segments}):
            lane_segments = [sg for sg in audio_segments if sg.get("_lane", 0) == lane]
            for sg in lane_segments:
                sg.pop("_lane", None)
            tracks.append(
                {
                    "id": self._generate_id(),
                    "type": "audio",
                    "attribute": 0,
                    "flag": 0,
                    "name": "",
                    "is_default_name": True,
                    "segments": lane_segments,
                }
            )

        # Assemble full draft_info.json payload
        draft_info = {
            "id": timeline_id,
            "version": 360000,
            "new_version": "179.0.0",
            "name": project_name,
            "path": "",
            "duration": total_duration_us,
            "fps": 30.0,
            "create_time": 0,
            "update_time": 0,
            "color_space": 0,
            "canvas_config": {
                "ratio": ratio,
                "width": canvas_w,
                "height": canvas_h,
                "background": None,
            },
            "tracks": tracks,
            "materials": {
                "videos": video_materials,
                "speeds": speed_materials + audio_aux["speeds"],
                "canvases": canvas_materials,
                "placeholder_infos": placeholder_materials + audio_aux["placeholder_infos"],
                "sound_channel_mappings": sound_channel_materials + audio_aux["sound_channel_mappings"],
                "material_colors": material_color_materials,
                "vocal_separations": vocal_sep_materials + audio_aux["vocal_separations"],
                "beats": audio_aux["beats"],
                "loudnesses": audio_aux["loudnesses"],
                "audios": audio_materials,
                "images": [],
                "texts": [],
                "effects": [],
                "stickers": [],
                "transitions": transition_materials,
                "material_animations": [],
            },
            "keyframes": {
                "videos": [],
                "audios": [],
                "texts": [],
                "stickers": [],
            },
            "platform": platform_info,
            "last_modified_platform": platform_info,
            "render_index_track_mode_on": True,
        }

        # Save draft_cover.jpg from the first panel
        cover_file = project_dir / "draft_cover.jpg"
        try:
            with Image.open(normalized_items[0]["path"]) as first_img:
                first_img.convert("RGB").save(cover_file, "JPEG", quality=88)
        except Exception:
            pass

        # Meta info file
        draft_meta_info = {
            "draft_id": draft_id,
            "draft_name": project_name,
            "tm_duration": total_duration_us,
            "tm_draft_create": now_us,
            "tm_draft_modified": now_us,
            "draft_fold_path": str(project_dir.resolve()),
            "draft_root_path": str(self.projects_dir.resolve()),
            "draft_timeline_materials_size_": total_materials_size,
            "draft_type": "",
            "draft_cover": "draft_cover.jpg",
            "draft_materials": [
                {"type": 0, "value": meta_material_values},
                {"type": 1, "value": []},
                {"type": 2, "value": []},
                {"type": 3, "value": []},
                {"type": 6, "value": []},
                {"type": 7, "value": []},
                {"type": 8, "value": []},
            ],
        }

        # 1. draft_info.json
        with open(project_dir / "draft_info.json", "w", encoding="utf-8") as f:
            json.dump(draft_info, f, indent=2)

        # 2. draft_meta_info.json
        with open(project_dir / "draft_meta_info.json", "w", encoding="utf-8") as f:
            json.dump(draft_meta_info, f, indent=2)

        # 3. draft_biz_config.json
        with open(project_dir / "draft_biz_config.json", "w", encoding="utf-8") as f:
            json.dump({"timeline_settings": {timeline_id: {"linkage_enabled": False}}}, f, indent=2)

        # 4. timeline_layout.json
        with open(project_dir / "timeline_layout.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "dockItems": [
                        {
                            "dockIndex": 0,
                            "ratio": 1,
                            "timelineIds": [timeline_id],
                            "timelineNames": ["Timeline 01"],
                        }
                    ],
                    "layoutOrientation": 1,
                },
                f,
                indent=2,
            )

        # 5. draft_virtual_store.json
        with open(project_dir / "draft_virtual_store.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "draft_materials": [],
                    "draft_virtual_store": [
                        {"type": 0, "value": []},
                        {"type": 1, "value": []},
                        {"type": 2, "value": []},
                    ],
                },
                f,
            )

        # 6. attachment_pc_common.json
        with open(project_dir / "attachment_pc_common.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "ai_packaging_infos": [],
                    "ai_packaging_report_info": {
                        "caption_id_list": [],
                        "commercial_material": "",
                        "material_source": "",
                        "method": "",
                        "page_from": "",
                        "style": "",
                        "task_id": "",
                        "text_style": "",
                        "tos_id": "",
                        "video_category": "",
                    },
                    "broll": {"ai_packaging_infos": [], "ai_packaging_report_info": {"caption_id_list": []}},
                },
                f,
            )

        # 7. Clean up stale legacy root draft_content.json if present
        stale_dc = project_dir / "draft_content.json"
        if stale_dc.exists():
            try:
                stale_dc.unlink()
            except OSError:
                pass

        # 8. Register in root_meta_info.json if present
        self._register_in_root_meta(
            draft_id=draft_id,
            project_name=project_name,
            project_dir=project_dir,
            duration_us=total_duration_us,
            materials_size=total_materials_size,
            now_us=now_us,
        )

        return project_dir

    def _audio_track(
        self, audio_tracks: List[Dict[str, Any]], materials_dir: Path, total_duration_us: int
    ) -> tuple:
        """Narration clips: copied into the draft, each placed at its chapter's first panel.

        Returns (audio materials, audio segments, auxiliary materials by kind, meta values).
        The material and segment fields mirror what CapCut Desktop writes for a local audio file.
        """
        aux: Dict[str, List[Dict[str, Any]]] = {
            k: [] for k in ("speeds", "placeholder_infos", "beats", "sound_channel_mappings",
                            "loudnesses", "vocal_separations")
        }
        materials: List[Dict[str, Any]] = []
        segments: List[Dict[str, Any]] = []
        meta: List[Dict[str, Any]] = []
        if not audio_tracks:
            return materials, segments, aux, meta

        audio_dir = materials_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        for track in audio_tracks:
            src = Path(track["path"])
            if not src.exists():
                continue
            dest = audio_dir / src.name
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            dur_us = max(1, int(round(float(track["duration"]) * 1_000_000)))
            if "start_s" in track:
                start_us = max(0, int(round(float(track["start_s"]) * 1_000_000)))
            elif "start_us" in track:
                start_us = max(0, int(track["start_us"]))
            else:
                start_us = self.chapter_starts_us.get(track.get("chapter") or "", 0)
            dur_us = min(dur_us, max(1, total_duration_us - start_us))

            mat_id = self._generate_id()
            ids = {k: self._generate_id() for k in aux}
            materials.append(
                {
                    "id": mat_id,
                    "unique_id": uuid.uuid4().hex,
                    "type": "extract_music",
                    "name": dest.name,
                    "duration": dur_us,
                    "path": str(dest.resolve()),
                    "category_name": "local",
                    "wave_points": [],
                    "music_id": str(uuid.uuid4()),
                    "app_id": 0,
                    "text_id": "",
                    "tone_type": "",
                    "source_platform": 0,
                    "video_id": "",
                    "effect_id": "",
                    "resource_id": "",
                    "third_resource_id": "",
                    "category_id": "",
                    "intensifies_path": "",
                    "formula_id": "",
                    "check_flag": 1,
                    "team_id": "",
                    "local_material_id": str(uuid.uuid4()),
                    "copyright_limit_type": "none",
                }
            )
            aux["speeds"].append({"id": ids["speeds"], "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
            aux["placeholder_infos"].append(
                {"id": ids["placeholder_infos"], "type": "placeholder_info", "meta_type": "none",
                 "res_path": "", "res_text": "", "error_path": "", "error_text": ""}
            )
            aux["beats"].append(
                {"id": ids["beats"], "type": "beats", "enable_ai_beats": False, "gear": 404, "gear_count": 0,
                 "mode": 404, "user_beats": [], "user_delete_ai_beats": None,
                 "ai_beats": {"melody_url": "", "melody_path": "", "beats_url": "", "beats_path": "",
                              "melody_percents": [0.0], "beat_speed_infos": []}}
            )
            aux["sound_channel_mappings"].append(
                {"id": ids["sound_channel_mappings"], "type": "none", "audio_channel_mapping": 0, "is_config_open": False}
            )
            aux["loudnesses"].append(
                {"id": ids["loudnesses"], "enable": False, "time_range": None, "file_id": "",
                 "target_loudness": 0.0, "loudness_param": None}
            )
            aux["vocal_separations"].append(
                {"id": ids["vocal_separations"], "type": "vocal_separation", "choice": 0, "removed_sounds": [],
                 "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": ""}
            )
            segments.append(
                {
                    "id": self._generate_id(),
                    "source_timerange": {"start": 0, "duration": dur_us},
                    "target_timerange": {"start": start_us, "duration": dur_us},
                    "render_timerange": {"start": 0, "duration": 0},
                    "desc": "",
                    "state": 0,
                    "speed": 1.0,
                    "is_loop": False,
                    "is_tone_modify": False,
                    "reverse": False,
                    "intensifies_audio": False,
                    "cartoon": False,
                    "volume": float(track.get("volume", 1.0)),
                    "last_nonzero_volume": float(track.get("volume", 1.0)) or 1.0,
                    "clip": None,
                    "uniform_scale": None,
                    "material_id": mat_id,
                    "_lane": int(track.get("lane", 0)),
                    "extra_material_refs": [ids["speeds"], ids["placeholder_infos"], ids["beats"],
                                            ids["sound_channel_mappings"], ids["loudnesses"],
                                            ids["vocal_separations"]],
                    "render_index": 0,
                    "keyframe_refs": [],
                    "visible": True,
                    "group_id": "",
                    "track_render_index": 1,
                    "hdr_settings": None,
                    "track_attribute": 0,
                    "is_placeholder": False,
                    "template_id": "",
                    "template_scene": "default",
                    "common_keyframes": [],
                    "caption_info": None,
                    "source": "segmentsourcenormal",
                }
            )
            meta.append(
                {
                    "ai_group_type": "",
                    "create_time": int(time.time()),
                    "duration": dur_us,
                    "enter_from": 0,
                    "extra_info": dest.name,
                    "file_Path": str(dest.resolve()),
                    "height": 0,
                    "id": str(uuid.uuid4()).lower(),
                    "import_time": int(time.time()),
                    "import_time_ms": int(time.time() * 1_000_000),
                    "item_source": 1,
                    "material_color_tag": "",
                    "md5": "",
                    "metetype": "music",
                    "roughcut_time_range": {"duration": dur_us, "start": 0},
                    "sub_time_range": {"duration": -1, "start": -1},
                    "type": 0,
                    "width": 0,
                }
            )
        return materials, segments, aux, meta

    def _register_in_root_meta(
        self,
        draft_id: str,
        project_name: str,
        project_dir: Path,
        duration_us: int,
        materials_size: int,
        now_us: int,
    ) -> None:
        """Appends or updates the project entry inside root_meta_info.json."""
        root_meta_file = self.projects_dir / "root_meta_info.json"
        if not root_meta_file.exists():
            return

        try:
            with open(root_meta_file, "r", encoding="utf-8") as f:
                root_data = json.load(f)

            all_drafts = root_data.get("all_draft_store", [])
            # Look for existing entry with same folder or name
            entry = next(
                (
                    d
                    for d in all_drafts
                    if d.get("draft_name") == project_name
                    or d.get("draft_fold_path") == str(project_dir.resolve())
                ),
                None,
            )

            cover_path = str(project_dir / "draft_cover.jpg")
            if not entry:
                entry = {
                    "cloud_draft_cover": False,
                    "cloud_draft_sync": False,
                    "draft_cloud_last_action_download": False,
                    "draft_cloud_purchase_info": "",
                    "draft_cloud_template_id": "",
                    "draft_cloud_tutorial_info": "",
                    "draft_cloud_videocut_purchase_info": "",
                    "draft_cover": cover_path,
                    "draft_fold_path": str(project_dir.resolve()),
                    "draft_id": draft_id,
                    "draft_is_ai_shorts": False,
                    "draft_is_cloud_temp_draft": False,
                    "draft_is_invisible": False,
                    "draft_is_pippit_draft": False,
                    "draft_is_web_article_video": False,
                    "draft_json_file": str(project_dir / "draft_info.json"),
                    "draft_name": project_name,
                    "draft_new_version": "",
                    "draft_root_path": str(self.projects_dir.resolve()),
                    "draft_timeline_materials_size": materials_size,
                    "draft_type": "",
                    "draft_web_article_video_enter_from": "",
                    "pippit_avatar_url": "",
                    "pippit_extra_info": "",
                    "pippit_id": "",
                    "pippit_user_name": "",
                    "streaming_edit_draft_ready": True,
                    "tm_draft_cloud_completed": "",
                    "tm_draft_cloud_entry_id": -1,
                    "tm_draft_cloud_modified": 0,
                    "tm_draft_cloud_parent_entry_id": -1,
                    "tm_draft_cloud_space_id": -1,
                    "tm_draft_cloud_user_id": -1,
                    "tm_draft_create": now_us,
                    "tm_draft_modified": now_us,
                    "tm_draft_removed": 0,
                    "tm_duration": duration_us,
                }
                all_drafts.insert(0, entry)
            else:
                entry["draft_id"] = draft_id
                entry["draft_cover"] = cover_path
                entry["draft_fold_path"] = str(project_dir.resolve())
                entry["draft_json_file"] = str(project_dir / "draft_info.json")
                entry["draft_type"] = ""
                entry["draft_timeline_materials_size"] = materials_size
                entry["tm_duration"] = duration_us
                entry["tm_draft_modified"] = now_us

            root_data["all_draft_store"] = all_drafts
            with open(root_meta_file, "w", encoding="utf-8") as f:
                json.dump(root_data, f, indent=2)
        except Exception:
            pass

    def _create_kf_list(
        self, property_type: str, time_value_pairs: List[tuple[int, float]]
    ) -> Dict[str, Any]:
        """Creates a KeyframeList dictionary for a given property and timing points."""
        kf_list_id = self._generate_id()
        keyframes = []
        for time_offset, value in time_value_pairs:
            keyframes.append(
                {
                    "curveType": "Line",
                    "graphID": "",
                    "left_control": {"x": 0.0, "y": 0.0},
                    "right_control": {"x": 0.0, "y": 0.0},
                    "id": self._generate_id(),
                    "time_offset": time_offset,
                    "values": [float(value)],
                }
            )

        return {
            "id": kf_list_id,
            "property_type": property_type,
            "material_id": "",
            "keyframe_list": keyframes,
        }

    @staticmethod
    def is_long_panel(img_w: int, img_h: int, ratio: str) -> bool:
        """Taller than LONG_PANEL_RATIO times its width for this video shape."""
        limit = LONG_PANEL_RATIO.get(ratio, LONG_PANEL_RATIO["16:9"])
        return img_w > 0 and img_h / img_w > limit

    def _long_panel_keyframes(
        self,
        img_w: int,
        img_h: int,
        canvas_w: int,
        canvas_h: int,
        ratio: str,
        duration_us: int,
        nth: int,
        zoom_ratio: float = 1.0,
    ) -> Optional[tuple[List[Dict[str, Any]], Dict[str, float]]]:
        """Zoom a long panel in until it fills LONG_PANEL_FILL_WIDTH of the screen, then
        scroll it down (even ones) or up (odd ones) while slowly zooming in (never zoom out).

        At scale 1 CapCut fits the photo inside the canvas, so a long panel fills the
        height and `fill` of the width. Positions are in half-canvas units: at scale s
        the panel overflows the canvas by (s - 1) of them above and below.
        Returns None for panels that aren't long, which keep the usual Ken Burns move.
        """
        if not self.is_long_panel(img_w, img_h, ratio):
            return None
        fill = min(1.0, (img_w / img_h) * (canvas_h / canvas_w))  # share of the width at scale 1
        start = max(1.0, min(LONG_PANEL_MAX_ZOOM, LONG_PANEL_FILL_WIDTH / max(fill, 1e-6)))
        if start <= 1.0:
            return None  # already big enough on screen: the usual move suits it
        # Long panels zoom in smoothly during vertical scroll when zoom_ratio > 1.0 (never zoom out)
        if zoom_ratio > 1.0:
            end = min(LONG_PANEL_MAX_ZOOM, round(start * zoom_ratio, 4))
        else:
            end = start
        reach = (min(start, end) - 1.0) * 0.95
        seconds = duration_us / 1_000_000
        travel = min(2 * reach, LONG_PANEL_SCROLL_SPEED * seconds * 2)
        down = nth % 2 == 0
        # y > 0 moves the panel up on screen, so the top of the panel shows at y = -reach
        y0, y1 = (-reach, -reach + travel) if down else (reach, reach - travel)
        if LONG_PANEL_FLIP_Y:
            y0, y1 = -y0, -y1
        keyframes = [
            self._create_kf_list("KFTypeScaleX", [(0, start), (duration_us, end)]),
            self._create_kf_list("KFTypeScaleY", [(0, start), (duration_us, end)]),
            self._create_kf_list("KFTypePositionY", [(0, round(y0, 4)), (duration_us, round(y1, 4))]),
        ]
        return keyframes, {"x": start, "y": start}

    def _generate_ken_burns_keyframes(
        self,
        img_w: int,
        img_h: int,
        idx: int,
        duration_us: int,
        zoom_ratio: float = 1.15,
        last_anim: Optional[str] = None,
        ken_burns_types: Optional[List[str]] = None,
        enable_zoom: bool = True,
        enable_pan: bool = True,
        ratio: str = "16:9",
        canvas_w: int = 1920,
        canvas_h: int = 1080,
    ) -> tuple[List[Dict[str, Any]], Dict[str, float], str]:
        """
        Generates aspect-ratio-aware Ken Burns keyframes.
        Classifies panels into Horizontal (>=1.25), Vertical (<=0.8), and Square (0.8-1.25),
        providing tailored movement pools while preventing consecutive duplicate animations.
        Supports selective enable_zoom and enable_pan, and combines Pan with Zoom for Square panels.

        For Shorts (ratio == '9:16'):
        - Zoom out is strictly prohibited across all panel types (must always zoom in).
        - Portrait panels (aspect_ratio < 0.82 with reasonable fill ratio) are scaled to full 9:16
          so no empty space or background blur appears.
        - Square / wide panels that cannot be cropped without losing critical content keep their
          original ratio with blur on top/bottom, but still strictly zoom in.
        """
        aspect_ratio = img_w / max(1, img_h)
        is_portrait = aspect_ratio < 1.0  # img_h > img_w
        is_short = (ratio == "9:16")

        valid_types = [
            "zoom_in",
            "zoom_out",
            "pan_left_to_right",
            "pan_right_to_left",
            "pan_top_to_bottom",
            "pan_bottom_to_top",
            "pan_zoom_in_left_to_right",
            "pan_zoom_out_right_to_left",
            "pan_zoom_in_top_to_bottom",
            "pan_zoom_out_bottom_to_top",
            "pan_zoom_in_right_to_left",
            "pan_zoom_out_left_to_right",
            "pan_zoom_in_bottom_to_top",
            "pan_zoom_out_top_to_bottom",
        ]
        allowed = [t for t in ken_burns_types if t in valid_types] if ken_burns_types else valid_types
        if not allowed:
            allowed = valid_types

        # 1. Determine movement pool based on aspect ratio and enabled animation types
        if aspect_ratio >= 1.25:
            # Horizontal / Wide panel (e.g. 16:9, panoramic battle, double-spread)
            # Rule Strict Horizontal Axis: Cukup pan left atau right saja, tanpa zoom in atau zoom out
            if enable_pan:
                raw_pool = ["pan_left_to_right", "pan_right_to_left"]
            else:
                raw_pool = ["zoom_in"] if is_short else ["zoom_in", "zoom_out"]
        elif aspect_ratio <= 0.8:
            # Vertical / Tall panel (e.g. classic webtoon vertical action)
            # Portrait: zoom_out is strictly prohibited; always zoom_in when zooming
            if enable_pan:
                raw_pool = [
                    "pan_zoom_in_top_to_bottom",
                    "pan_zoom_in_bottom_to_top",
                ]
            else:
                raw_pool = ["zoom_in"]
        elif is_portrait:
            # Standard Portrait panel (0.8 < aspect_ratio < 1.0, e.g. medium reaction, character bust)
            # Portrait: zoom_out is strictly prohibited; always zoom_in when zooming; pan strictly vertical (atas/bawah)
            if enable_pan:
                raw_pool = [
                    "pan_zoom_in_top_to_bottom",
                    "pan_zoom_in_bottom_to_top",
                ]
            else:
                raw_pool = ["zoom_in"]
        else:
            # Square / Standard Wide panel (1.0 <= aspect_ratio < 1.25, e.g. dialog, 1:1, close-up)
            if is_short:
                # Shorts: Square panels must strictly zoom in (zoom out prohibited)
                if enable_pan and enable_zoom:
                    raw_pool = [
                        "zoom_in",
                        "pan_zoom_in_left_to_right",
                        "pan_zoom_in_top_to_bottom",
                        "pan_zoom_in_right_to_left",
                        "pan_zoom_in_bottom_to_top",
                    ]
                elif enable_pan:
                    raw_pool = [
                        "pan_left_to_right",
                        "pan_top_to_bottom",
                        "pan_right_to_left",
                        "pan_bottom_to_top",
                    ]
                else:
                    raw_pool = ["zoom_in"]
            else:
                if enable_pan and enable_zoom:
                    raw_pool = [
                        "zoom_in",
                        "zoom_out",
                        "pan_zoom_in_left_to_right",
                        "pan_zoom_out_right_to_left",
                        "pan_zoom_in_top_to_bottom",
                        "pan_zoom_out_bottom_to_top",
                        "pan_zoom_in_right_to_left",
                        "pan_zoom_out_left_to_right",
                        "pan_zoom_in_bottom_to_top",
                        "pan_zoom_out_top_to_bottom",
                    ]
                elif enable_pan:
                    raw_pool = [
                        "pan_left_to_right",
                        "pan_right_to_left",
                        "pan_top_to_bottom",
                        "pan_bottom_to_top",
                    ]
                else:
                    raw_pool = ["zoom_in", "zoom_out"]

        pool = [p for p in raw_pool if p in allowed]
        if not pool:
            pool = allowed

        # Strict constraint: portrait panels OR any panel in Shorts (9:16) must NEVER zoom out, always zoom in
        if is_portrait or is_short:
            cleaned_pool = []
            for p in pool:
                if p == "zoom_out":
                    if "zoom_in" not in cleaned_pool:
                        cleaned_pool.append("zoom_in")
                elif p == "pan_zoom_out_right_to_left":
                    if "pan_zoom_in_right_to_left" not in cleaned_pool:
                        cleaned_pool.append("pan_zoom_in_right_to_left")
                elif p == "pan_zoom_out_left_to_right":
                    if "pan_zoom_in_left_to_right" not in cleaned_pool:
                        cleaned_pool.append("pan_zoom_in_left_to_right")
                elif p == "pan_zoom_out_bottom_to_top":
                    if "pan_zoom_in_bottom_to_top" not in cleaned_pool:
                        cleaned_pool.append("pan_zoom_in_bottom_to_top")
                elif p == "pan_zoom_out_top_to_bottom":
                    if "pan_zoom_in_top_to_bottom" not in cleaned_pool:
                        cleaned_pool.append("pan_zoom_in_top_to_bottom")
                elif "zoom_out" in p:
                    replacement = p.replace("zoom_out", "zoom_in")
                    if replacement in valid_types and replacement not in cleaned_pool:
                        cleaned_pool.append(replacement)
                    elif "zoom_in" not in cleaned_pool:
                        cleaned_pool.append("zoom_in")
                else:
                    cleaned_pool.append(p)
            pool = cleaned_pool if cleaned_pool else ["zoom_in"]

        # 2. Select animation from pool, avoiding consecutive duplicates
        chosen_idx = idx % len(pool)
        chosen_anim = pool[chosen_idx]
        if chosen_anim == last_anim and len(pool) > 1:
            chosen_anim = pool[(chosen_idx + 1) % len(pool)]

        # Extra safety enforcement: if portrait or short, never allow zoom_out
        if (is_portrait or is_short) and "zoom_out" in chosen_anim:
            chosen_anim = chosen_anim.replace("zoom_out", "zoom_in")
            if chosen_anim not in valid_types:
                chosen_anim = "zoom_in"

        # Calculate base scale: in Shorts (9:16), scale portrait panels to cover 9:16 completely
        # so no empty gaps or background blur appear. Square/wide panels keep 1.0 (they allow blur on top/bottom).
        base_scale = 1.0
        if is_short and canvas_w > 0 and canvas_h > 0 and img_w > 0 and img_h > 0:
            r_canvas = canvas_w / canvas_h  # 1080 / 1920 = 0.5625
            r_img = img_w / img_h
            if r_img >= r_canvas:
                fill_scale = r_img / r_canvas
            else:
                fill_scale = r_canvas / r_img

            # Panel portrait yang memungkinkan full 9:16:
            # - Gambar adalah portrait (r_img < 0.82)
            # - Dan fill_scale <= 1.45 (crop tidak lebih dari 30%)
            # Panel square (r_img >= 0.82) atau landscape (r_img >= 1.25) TIDAK di-force fill 9:16
            if r_img < 0.82 and fill_scale <= 1.45:
                base_scale = round(fill_scale, 4)

        common_keyframes: List[Dict[str, Any]] = []

        scale_start = base_scale
        scale_end = round(base_scale * zoom_ratio, 4)

        # Dynamic proportional pan distance guaranteeing safety margins:
        pan_delta = max(0.015, round((zoom_ratio - 1.0) * 0.40, 4))
        # For combined pan + zoom:
        start_scale = max(1.03, round(1.0 + (zoom_ratio - 1.0) * 0.30, 4))
        start_pan_delta = max(0.010, round((start_scale - 1.0) * 0.40, 4))

        scale_pz_start = round(base_scale * start_scale, 4)
        scale_pz_end = scale_end
        scale_pan = scale_end

        clip_scale = {"x": scale_start, "y": scale_start}

        # 3. Build keyframes for chosen animation
        if chosen_anim == "zoom_in":
            clip_scale = {"x": scale_start, "y": scale_start}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_start), (duration_us, scale_end)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_start), (duration_us, scale_end)]),
            ])
        elif chosen_anim == "zoom_out":
            clip_scale = {"x": scale_end, "y": scale_end}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_end), (duration_us, scale_start)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_end), (duration_us, scale_start)]),
            ])
        elif chosen_anim == "pan_left_to_right":
            clip_scale = {"x": scale_pan, "y": scale_pan}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pan), (duration_us, scale_pan)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pan), (duration_us, scale_pan)]),
                self._create_kf_list("KFTypePositionX", [(0, -pan_delta), (duration_us, pan_delta)]),
            ])
        elif chosen_anim == "pan_right_to_left":
            clip_scale = {"x": scale_pan, "y": scale_pan}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pan), (duration_us, scale_pan)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pan), (duration_us, scale_pan)]),
                self._create_kf_list("KFTypePositionX", [(0, pan_delta), (duration_us, -pan_delta)]),
            ])
        elif chosen_anim == "pan_top_to_bottom":
            clip_scale = {"x": scale_pz_start, "y": scale_pz_start}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypePositionY", [(0, start_pan_delta), (duration_us, -pan_delta)]),
            ])
        elif chosen_anim == "pan_bottom_to_top":
            clip_scale = {"x": scale_pz_start, "y": scale_pz_start}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypePositionY", [(0, -start_pan_delta), (duration_us, pan_delta)]),
            ])
        elif chosen_anim == "pan_zoom_in_left_to_right":
            clip_scale = {"x": scale_pz_start, "y": scale_pz_start}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypePositionX", [(0, -start_pan_delta), (duration_us, pan_delta)]),
            ])
        elif chosen_anim == "pan_zoom_out_right_to_left":
            clip_scale = {"x": scale_pz_end, "y": scale_pz_end}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_end), (duration_us, scale_pz_start)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_end), (duration_us, scale_pz_start)]),
                self._create_kf_list("KFTypePositionX", [(0, pan_delta), (duration_us, -start_pan_delta)]),
            ])
        elif chosen_anim == "pan_zoom_in_top_to_bottom":
            clip_scale = {"x": scale_pz_start, "y": scale_pz_start}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypePositionY", [(0, start_pan_delta), (duration_us, -pan_delta)]),
            ])
        elif chosen_anim == "pan_zoom_out_bottom_to_top":
            clip_scale = {"x": scale_pz_end, "y": scale_pz_end}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_end), (duration_us, scale_pz_start)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_end), (duration_us, scale_pz_start)]),
                self._create_kf_list("KFTypePositionY", [(0, -pan_delta), (duration_us, start_pan_delta)]),
            ])
        elif chosen_anim == "pan_zoom_in_right_to_left":
            clip_scale = {"x": scale_pz_start, "y": scale_pz_start}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypePositionX", [(0, start_pan_delta), (duration_us, -pan_delta)]),
            ])
        elif chosen_anim == "pan_zoom_out_left_to_right":
            clip_scale = {"x": scale_pz_end, "y": scale_pz_end}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_end), (duration_us, scale_pz_start)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_end), (duration_us, scale_pz_start)]),
                self._create_kf_list("KFTypePositionX", [(0, -pan_delta), (duration_us, start_pan_delta)]),
            ])
        elif chosen_anim == "pan_zoom_in_bottom_to_top":
            clip_scale = {"x": scale_pz_start, "y": scale_pz_start}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_start), (duration_us, scale_pz_end)]),
                self._create_kf_list("KFTypePositionY", [(0, -start_pan_delta), (duration_us, pan_delta)]),
            ])
        elif chosen_anim == "pan_zoom_out_top_to_bottom":
            clip_scale = {"x": scale_pz_end, "y": scale_pz_end}
            common_keyframes.extend([
                self._create_kf_list("KFTypeScaleX", [(0, scale_pz_end), (duration_us, scale_pz_start)]),
                self._create_kf_list("KFTypeScaleY", [(0, scale_pz_end), (duration_us, scale_pz_start)]),
                self._create_kf_list("KFTypePositionY", [(0, pan_delta), (duration_us, -start_pan_delta)]),
            ])

        return common_keyframes, clip_scale, chosen_anim
