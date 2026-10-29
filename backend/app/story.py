"""Story generation via 9router (OpenAI-compatible chat completions)."""

import json
import re

import httpx

from . import config, settings
from pydantic import BaseModel

from .models import Scene
from .styles import get_style


class StoryError(Exception):
    pass


class StoryDraft(BaseModel):
    title: str
    model: str = ""
    core_answer: str = ""
    scenes: list[Scene]

    def to_llm_json(self) -> str:
        return json.dumps(
            {
                "core_answer": self.core_answer,
                "title": self.title,
                "scenes": [s.model_dump(include={"narration", "scene_description", "title_text"}) for s in self.scenes],
            },
            ensure_ascii=False,
        )


def scene_count_for(duration_sec: int) -> int:
    return max(1, round(duration_sec / settings.load().seconds_per_scene))


WORDS_PER_SECOND = 2.5  # typical narration pace


def narration_word_range() -> tuple[int, int]:
    target = settings.load().seconds_per_scene * WORDS_PER_SECOND
    return round(target * 0.85), round(target * 1.15)


def _avg_words(scenes: list[Scene]) -> float:
    return sum(len(s.narration.split()) for s in scenes) / max(1, len(scenes))


def _build_messages(topic: str, scene_count: int, language: str, style: dict) -> list[dict]:
    min_words, max_words = narration_word_range()
    system = (
        "You write scripts for narrated educational YouTube explainer videos. "
        "Every scene is one illustration shown while one chunk of narration is read aloud. "
        "You are careful with facts: you only state what mainstream science/history supports, "
        "and you never contradict yourself between scenes. "
        "Respond with JSON only, no markdown."
    )
    example = style.get("example_scene_description", "")
    example_block = f"\nExample of the level of detail expected for one scene_description:\n\"{example}\"\n" if example else ""
    user = f"""Topic: {topic}

Write an explainer story with EXACTLY {scene_count} scenes.

Plan first, inside the JSON, in this order:
1. "core_answer": the correct answer to the topic in 1-2 sentences of {language}, based on scientific/historical consensus. If the topic's question contains a wrong assumption or a popular misconception, the core_answer must say so plainly.
2. "outline": exactly {scene_count} short bullet points, one per scene, each adding ONE new step toward the core_answer.
3. Then write the scenes following the outline.

Story structure: hook question -> the common assumption -> the surprising correction (if any) -> the real explanation step by step -> the final scene restates the core_answer clearly as the payoff.
- Every scene must support the core_answer. No scene may offer a competing explanation.
- No two scenes may say the same thing; each scene moves the explanation forward.
- If several causes combine, name them as parts of ONE answer ("ada dua alasan: ... dan ...") instead of presenting them as separate answers.

Narration rules ("narration"):
- Written in {language}. LENGTH IS STRICT: every narration has {min_words}-{max_words} words (count them), usually 2 sentences. It is read aloud for about {settings.load().seconds_per_scene:g} seconds, so a 10-word narration is TOO SHORT.
- Natural spoken style, like a storyteller talking to the viewer. Add a concrete detail, number, or comparison to fill the length instead of padding.
- Facts must be accurate and consistent across ALL scenes. A later scene must never contradict an earlier one.
- Use the scientific consensus. If something is debated or uncertain, say so ("para ilmuwan menduga ...") instead of stating it as fact.
- Do not oversimplify into something false.

Image rules ("scene_description"):
- Written in English, 3-5 sentences, describes ONLY what is visible in that scene's illustration.
- Must include: the setting/background, how many characters and where they are in the frame (left/right/center), what each wears or holds, their poses and facial expressions, the main subject and where it sits in the frame, and 2-4 concrete props or details.
- Show the narration's idea visually (maps, arrows on a path, before/after, comparison side by side) rather than people just standing around.
- {style.get('llm_hint', '')}
{example_block}
Caption rules ("title_text"):
- Short hand-lettered caption in {language} shown on the image, 1-4 words, UPPERCASE. Use "" if the scene works better without text.

Return this JSON shape:
{{"core_answer": "...", "outline": ["..."], "title": "video title in {language}", "scenes": [{{"narration": "...", "scene_description": "...", "title_text": "..."}}]}}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_story(content: str) -> StoryDraft:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise StoryError("LLM response contains no JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise StoryError(f"LLM returned invalid JSON: {e}") from e
    raw_scenes = data.get("scenes") or []
    if not raw_scenes:
        raise StoryError("LLM returned no scenes")
    scenes = [
        Scene(
            narration=str(s.get("narration", "")).strip(),
            scene_description=str(s.get("scene_description", "")).strip(),
            title_text=str(s.get("title_text", "")).strip(),
        )
        for s in raw_scenes
    ]
    return StoryDraft(
        title=str(data.get("title", "")).strip(),
        core_answer=str(data.get("core_answer", "")).strip(),
        scenes=scenes,
    )


def generate_story(topic: str, scene_count: int, language: str, style_id: str, model: str | None = None) -> StoryDraft:
    """Try `model` (or the configured main model) first, then the fallbacks."""
    main_model = model or settings.load().default_model or config.NINEROUTER_MODEL
    models = list(dict.fromkeys(m for m in [main_model, *config.NINEROUTER_FALLBACK_MODELS] if m))
    if not models:
        raise StoryError("NINEROUTER_MODEL is not set in backend/.env")
    messages = _build_messages(topic, scene_count, language, get_style(style_id))
    errors = []
    min_words, max_words = narration_word_range()
    for model in models:
        try:
            draft = _complete_story(model, messages)
        except StoryError as e:
            errors.append(f"[{model}] {e}")
            continue
        draft.model = model
        avg = _avg_words(draft.scenes)
        if avg >= min_words * 0.85:
            return draft
        # too short: ask the same model once to lengthen, keep the better result
        feedback = [
            {"role": "assistant", "content": draft.to_llm_json()},
            {"role": "user", "content": f"The narrations average only {avg:.0f} words. Rewrite every narration to {min_words}-{max_words} words, keeping the same core_answer, facts, order, scene count, scene_description and title_text. Return the full JSON again."},
        ]
        try:
            longer = _complete_story(model, messages + feedback)
            if len(longer.scenes) == len(draft.scenes) and _avg_words(longer.scenes) > avg:
                longer.model = model
                return longer
        except StoryError:
            pass
        return draft
    raise StoryError("all models failed: " + " | ".join(errors))


def _chat(model: str, messages: list[dict], temperature: float = 0.6) -> str:
    """One chat completion via 9router; returns the assistant text."""
    headers = {"Content-Type": "application/json"}
    if config.NINEROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {config.NINEROUTER_API_KEY}"
    body = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
    try:
        r = httpx.post(f"{config.NINEROUTER_BASE_URL}/chat/completions", json=body, headers=headers, timeout=config.LLM_TIMEOUT_SECONDS)
    except httpx.HTTPError as e:
        raise StoryError(f"cannot reach 9router at {config.NINEROUTER_BASE_URL}: {e}") from e
    if r.status_code >= 400:
        raise StoryError(f"9router error {r.status_code}: {r.text[:300]}")
    return _extract_content(r.text)


def _complete_story(model: str, messages: list[dict]) -> StoryDraft:
    return parse_story(_chat(model, messages))


# ---------- rewriting one scene's narration ----------

# mode -> (instruction, min ratio, max ratio) of the current word count
REWRITE_MODES = {
    "shorter": (
        "Make it SHORTER. Drop filler and secondary details, keep the main point and the exact meaning.",
        0.6, 0.78,
    ),
    "longer": (
        "Make it LONGER by adding ONE concrete, factually correct detail (a number, an example or a comparison) "
        "that fits this scene. Keep the original point.",
        1.3, 1.55,
    ),
    "simpler": (
        "Make it SIMPLER: everyday words a 12-year-old understands, short sentences, no jargon. "
        "Same meaning, similar length.",
        0.85, 1.15,
    ),
    "reword": (
        "REWORD it: the SAME meaning, the same facts and the same sentence purpose (a question stays a question, "
        "a hook stays a hook), with fresh wording and a lively spoken rhythm.",
        0.9, 1.12,
    ),
}


def _word_range(words: int, mode: str | None) -> tuple[int, int] | None:
    if mode not in REWRITE_MODES:
        return None
    _, lo, hi = REWRITE_MODES[mode]
    low, high = max(3, round(words * lo)), max(4, round(words * hi))
    if high - low < 3:  # give short narrations some room
        low, high = max(3, low - 1), high + 1
    return low, high


def _json_object(content: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise StoryError("LLM response contains no JSON object")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise StoryError(f"LLM returned invalid JSON: {e}") from e


def _story_outline(narrations: list[str], index: int) -> str:
    lines = []
    for i, text in enumerate(narrations):
        marker = "  <-- THE SCENE YOU ARE EDITING" if i == index else ""
        lines.append(f"{i + 1}. {text}{marker}")
    return "\n".join(lines)


def rewrite_narration(
    *,
    title: str,
    topic: str,
    core_answer: str,
    language: str,
    narrations: list[str],
    index: int,
    scene_description: str = "",
    title_text: str = "",
    mode: str | None,
    instruction: str = "",
    model: str | None = None,
) -> tuple[list[str], str]:
    """Return 3 alternative narrations for scene `index` and the model that wrote them."""
    if not mode and not instruction.strip():
        raise StoryError("choose a mode or write an instruction")
    if mode and mode not in REWRITE_MODES:
        raise StoryError(f"unknown mode: {mode}")

    narration = narrations[index]
    words = len(narration.split())
    word_range = _word_range(words, mode)
    tasks = []
    if mode:
        tasks.append(REWRITE_MODES[mode][0])
    if word_range:
        tasks.append(f"LENGTH: every option must have {word_range[0]}-{word_range[1]} words (the current one has {words}). Count them.")
    if instruction.strip():
        tasks.append(f"Extra instruction from the user: {instruction.strip()}")
    task_text = "\n".join(f"- {t}" for t in tasks)
    position = "the opening hook" if index == 0 else "the closing scene" if index == len(narrations) - 1 else f"scene {index + 1} of {len(narrations)}"

    user = f"""You are editing ONE scene of a narrated educational explainer video.

VIDEO
Title: {title}
Topic: {topic}
Core answer (every scene supports this): {core_answer or "(not given)"}

FULL SCRIPT (one line per scene, read aloud in order)
{_story_outline(narrations, index)}

THE SCENE YOU ARE EDITING
Position: {position}
Its illustration shows: {scene_description or "(no description)"}
Caption on the illustration: {title_text or "(none)"}
Current narration ({words} words): {narration}

TASK
{task_text}

RULES
- Write in {language}, exactly the same language as the script.
- Keep the meaning. Do not make claims stronger or weaker (e.g. "not complete yet" must NOT become "wrong"), and do not add new facts unless the task asks for a detail.
- Stay consistent with the core answer and with every other scene; do not repeat what the neighbouring scenes already say.
- It must flow naturally from the previous scene into the next one and still match the illustration.
- Natural spoken style, meant to be read aloud.
- Give 3 options that differ from each other in wording.

Return JSON only: {{"options": ["...", "...", "..."]}}"""
    messages = [
        {"role": "system", "content": "You are a careful script editor for educational videos. Respond with JSON only, no markdown."},
        {"role": "user", "content": user},
    ]

    def in_range(text: str) -> bool:
        n = len(text.split())
        return word_range is None or word_range[0] - 1 <= n <= word_range[1] + 1

    main_model = model or settings.load().default_model or config.NINEROUTER_MODEL
    models = list(dict.fromkeys(m for m in [main_model, *config.NINEROUTER_FALLBACK_MODELS] if m))
    errors = []
    for m in models:
        try:
            options = _rewrite_options(m, messages)
            if word_range and sum(map(in_range, options)) < 2:
                # most options missed the length: ask once more with concrete feedback, keep the better set
                counts = ", ".join(str(len(o.split())) for o in options)
                retry = messages + [
                    {"role": "assistant", "content": json.dumps({"options": options}, ensure_ascii=False)},
                    {"role": "user", "content": f"Your options have {counts} words, but each must have {word_range[0]}-{word_range[1]} words. Rewrite all 3 to fit, same rules. JSON only."},
                ]
                try:
                    second = _rewrite_options(m, retry)
                    if sum(map(in_range, second)) > sum(map(in_range, options)):
                        options = second
                except StoryError:
                    pass
            return options[:3], m
        except StoryError as e:
            errors.append(f"[{m}] {e}")
    raise StoryError("all models failed: " + " | ".join(errors))


def _rewrite_options(model: str, messages: list[dict]) -> list[str]:
    data = _json_object(_chat(model, messages, temperature=0.8))
    options = [str(o).strip() for o in data.get("options", []) if str(o).strip()]
    if not options:
        raise StoryError("LLM returned no options")
    return options


def _extract_content(body: str) -> str:
    """Accept a normal completion or an SSE stream (9router may stream regardless)."""
    try:
        if not body.lstrip().startswith("data:"):
            return json.loads(body)["choices"][0]["message"]["content"]
        parts = []
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            delta = json.loads(line[5:])["choices"][0].get("delta", {})
            parts.append(delta.get("content") or "")
        return "".join(parts)
    except (KeyError, IndexError, ValueError) as e:
        raise StoryError(f"unexpected 9router response: {body[:500]}") from e
