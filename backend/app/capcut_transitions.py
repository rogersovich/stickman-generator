"""CapCut Desktop transition effects catalogue and draft material helpers."""

from __future__ import annotations

import random
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# 13 Favorite CapCut transitions extracted from user's CapCut library
CAPCUT_FAVORITE_TRANSITIONS: List[Dict[str, Any]] = [
    {
        "id": "anime_speed",
        "name": "Anime Speed",
        "effect_id": "7527993768037928253",
        "resource_id": "7527993768037928253",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7527993768037928253/12abe6e80ddad0ed4c0aad19fa2e9ca4",
        "is_overlap": True,
        "default_duration": 0.5,
    },
    {
        "id": "spread_morph",
        "name": "Spread Morph",
        "effect_id": "7548325465702845749",
        "resource_id": "7548325465702845749",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7548325465702845749/ac7ac0c7288bf7fae01f9d023d7a2bcb",
        "is_overlap": True,
        "default_duration": 2.0,
    },
    {
        "id": "push_away",
        "name": "Push Away",
        "effect_id": "7607836203265625349",
        "resource_id": "7607836203265625349",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7607836203265625349/100cd699154db5a1818ff48cad24ea89",
        "is_overlap": True,
        "default_duration": 2.0,
    },
    {
        "id": "pop_switch",
        "name": "Pop Switch",
        "effect_id": "7653726954247539988",
        "resource_id": "7653726954247539988",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7653726954247539988/046f2343dcc641c391b6ec5eed66a71f",
        "is_overlap": True,
        "default_duration": 2.0,
    },
    {
        "id": "stretch_down",
        "name": "Stretch Down",
        "effect_id": "7600325103435402549",
        "resource_id": "7600325103435402549",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7600325103435402549/7e0b5eb6058546af3d7551a479e7a9ca",
        "is_overlap": True,
        "default_duration": 1.94,
    },
    {
        "id": "left",
        "name": "Left",
        "effect_id": "6724227717195108867",
        "resource_id": "6724227717195108867",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/6724227717195108867/d623e56c3ec69ac4920fac8740b456ae",
        "is_overlap": False,
        "default_duration": 0.5,
    },
    {
        "id": "stretch_left",
        "name": "Stretch Left",
        "effect_id": "7620344224734629138",
        "resource_id": "7620344224734629138",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7620344224734629138/11a4f53df0e49e1ce7a5736a7ccac0c2",
        "is_overlap": True,
        "default_duration": 2.0,
    },
    {
        "id": "right",
        "name": "Right",
        "effect_id": "6724227599616184836",
        "resource_id": "6724227599616184836",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/6724227599616184836/94ddc5b44c66c523dbf70622efb612d3",
        "is_overlap": False,
        "default_duration": 1.0,
    },
    {
        "id": "push_up",
        "name": "Push Up",
        "effect_id": "7688719966387834132",
        "resource_id": "7688719966387834132",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7688719966387834132/dc10f27efaaaa43c97919cdc47d57acf",
        "is_overlap": True,
        "default_duration": 2.0,
    },
    {
        "id": "pull_in",
        "name": "Pull In",
        "effect_id": "6724226861666144779",
        "resource_id": "6724226861666144779",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/6724226861666144779/4d5a316f2eae582e7d0604b47feb8c32",
        "is_overlap": False,
        "default_duration": 1.0,
    },
    {
        "id": "pull_out",
        "name": "Pull Out",
        "effect_id": "6724226338418332167",
        "resource_id": "6724226338418332167",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/6724226338418332167/8d97f1c1a60d9393c97ff4e9da0669ae",
        "is_overlap": False,
        "default_duration": 1.0,
    },
    {
        "id": "shake_away",
        "name": "Shake Away",
        "effect_id": "7610582290304929031",
        "resource_id": "7610582290304929031",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7610582290304929031/a13b4bd55806acf1d908bc56cf837711",
        "is_overlap": True,
        "default_duration": 1.97,
    },
    {
        "id": "shake",
        "name": "Shake",
        "effect_id": "7198424967803834881",
        "resource_id": "7198424967803834881",
        "path": "/Users/rogersovich/Library/Containers/com.lemon.lvoverseas/Data/Movies/CapCut/User Data/Cache/effect/7198424967803834881/3a0fd76188f0955a96b967a9cce139b3",
        "is_overlap": True,
        "default_duration": 1.0,
    },
]


def list_transitions() -> List[Dict[str, Any]]:
    """Returns the list of transitions with availability status."""
    result = []
    for t in CAPCUT_FAVORITE_TRANSITIONS:
        p = Path(t["path"])
        result.append(
            {
                "id": t["id"],
                "name": t["name"],
                "is_overlap": t["is_overlap"],
                "available": p.exists(),
                "default_duration": t.get("default_duration", 0.5),
            }
        )
    return result


def pick_random_transition(allowed: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Picks a random transition from the allowed list.
    
    If `allowed` is None, all catalog transitions are candidates.
    If `allowed` is specified, matches by transition 'id' or 'name' (case-insensitive).
    """
    if allowed is not None:
        normalized_allowed = {str(a).strip().lower().replace(" ", "_") for a in allowed}
        name_allowed = {str(a).strip().lower() for a in allowed}
        candidates = [
            t
            for t in CAPCUT_FAVORITE_TRANSITIONS
            if t["id"].lower() in normalized_allowed
            or t["name"].lower() in name_allowed
            or t["name"].lower().replace(" ", "_") in normalized_allowed
        ]
    else:
        candidates = list(CAPCUT_FAVORITE_TRANSITIONS)

    if not candidates:
        return None

    return random.choice(candidates)


def build_transition_material(
    trans_meta: Dict[str, Any],
    duration_s: float = 0.5,
    transition_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds a CapCut transition material dict for draft_info.json."""
    dur_s = max(0.1, min(1.0, float(duration_s)))
    dur_us = int(round(dur_s * 1_000_000))
    uid = transition_id or str(uuid.uuid4()).upper()

    return {
        "id": uid,
        "type": "transition",
        "name": trans_meta["name"],
        "effect_id": str(trans_meta["effect_id"]),
        "resource_id": str(trans_meta["resource_id"]),
        "third_resource_id": str(trans_meta.get("third_resource_id", trans_meta["resource_id"])),
        "source_platform": 1,
        "path": str(trans_meta["path"]),
        "duration": dur_us,
        "is_overlap": bool(trans_meta.get("is_overlap", False)),
        "platform": "all",
        "category_id": "100000",
        "category_name": "",
        "request_id": "",
        "is_ai_transition": False,
        "video_path": "",
        "task_id": "",
    }
