from pathlib import Path
from typing import Any
import re
import unicodedata

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent
EMOJI_FONT_SCALE = 0.94
EMOJI_BASELINE_SHIFT = -2


def _is_emoji(char: str) -> bool:
    """Check if character is an emoji."""
    return unicodedata.category(char) in ('So', 'Sk', 'Sm')


def _contains_emoji(text: str) -> bool:
    """Check if text contains any emoji characters."""
    return any(_is_emoji(char) for char in text)


def _iter_text_runs(text: str) -> list[tuple[str, bool]]:
    runs: list[tuple[str, bool]] = []
    current = ""
    current_is_emoji: bool | None = None

    for char in text:
        is_emoji = _is_emoji(char)
        if current_is_emoji is None:
            current = char
            current_is_emoji = is_emoji
            continue

        if is_emoji == current_is_emoji:
            current += char
            continue

        runs.append((current, current_is_emoji))
        current = char
        current_is_emoji = is_emoji

    if current:
        runs.append((current, bool(current_is_emoji)))

    return runs


def _resolve_font_for_text(text: str, is_bold: bool, fonts: dict[str, Path]) -> str:
    if _contains_emoji(text) and "emoji" in fonts:
        return "emoji"
    return "bold" if is_bold else "regular"


def _render_font_size(size: int, is_emoji: bool) -> int:
    if is_emoji:
        return max(1, int(round(size * EMOJI_FONT_SCALE)))
    return max(1, int(size))


def _measure_text_runs(
    draw: ImageDraw.ImageDraw,
    text: str,
    fonts: dict[str, Path],
    size: int,
    is_bold: bool,
) -> tuple[int, int, int]:
    total_width = 0
    max_height = 0
    top_offset = 0

    for run_text, _ in _iter_text_runs(text):
        if not run_text:
            continue
        font_key = _resolve_font_for_text(run_text, is_bold, fonts)
        font = _load_font(fonts[font_key], _render_font_size(size, font_key == "emoji"))
        run_width, run_height, run_top = _measure_text(draw, run_text, font)
        total_width += run_width
        max_height = max(max_height, run_height)
        top_offset = min(top_offset, run_top)

    return total_width, max_height, top_offset


def _text_run_metrics(
    draw: ImageDraw.ImageDraw,
    text: str,
    fonts: dict[str, Path],
    size: int,
    is_bold: bool,
    is_italic: bool = False,
) -> list[tuple[str, ImageFont.FreeTypeFont, int, int, bool]]:
    metrics: list[tuple[str, ImageFont.FreeTypeFont, int, int, bool]] = []

    for run_text, is_emoji in _iter_text_runs(text):
        if not run_text:
            continue

        if is_emoji and "emoji" in fonts:
            font_key = "emoji"
        elif is_italic and "italic" in fonts:
            font_key = "italic"
        else:
            font_key = "bold" if is_bold else "regular"

        font_size = _render_font_size(size, font_key == "emoji")
        font = _load_font(fonts[font_key], font_size)
        run_width, run_height, run_top = _measure_text(draw, run_text, font)
        metrics.append((run_text, font, run_width, run_top, font_key == "emoji"))

    return metrics


def _draw_text_runs(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    text: str,
    position: tuple[int, int],
    fonts: dict[str, Path],
    size: int,
    is_bold: bool,
    is_italic: bool,
    fill: tuple[int, int, int],
    embedded_color_for_emoji: bool,
) -> int:
    x, y = position
    total_width = 0
    run_metrics = _text_run_metrics(draw, text, fonts, size, is_bold, is_italic)
    baseline_offset = 0

    for _, _, _, run_top, _ in run_metrics:
        baseline_offset = min(baseline_offset, run_top)

    for run_text, font, run_width, run_top, is_emoji_font in run_metrics:
        draw_y = y - run_top + baseline_offset + (EMOJI_BASELINE_SHIFT if is_emoji_font else 0)
        if is_italic and not is_emoji_font:
            shear = 0.22
            temp_height = _font_line_height(font) + 8
            temp_width = run_width + int(abs(shear) * temp_height) + 8
            temp = Image.new("RGBA", (max(1, temp_width), max(1, temp_height)), (0, 0, 0, 0))
            temp_draw = ImageDraw.Draw(temp)
            temp_draw.text((0, 0), run_text, font=font, fill=fill)
            sheared = temp.transform(
                (max(1, temp_width), max(1, temp_height)),
                Image.AFFINE,
                (1, -shear, 0, 0, 1, 0),
                resample=Image.Resampling.BICUBIC,
            )
            image.alpha_composite(sheared, (x, draw_y))
        else:
            draw.text(
                (x, draw_y),
                run_text,
                font=font,
                fill=fill,
                embedded_color=embedded_color_for_emoji and is_emoji_font,
            )
        x += run_width
        total_width += run_width

    return total_width


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    code = value.strip().lstrip("#")
    if len(code) != 6:
        raise ValueError(f"Invalid color hex: {value}")
    return tuple(int(code[i:i + 2], 16) for i in (0, 2, 4))


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    if not font_path.exists():
        raise FileNotFoundError(f"Font not found: {font_path}")
    return ImageFont.truetype(str(font_path), size)


def _font_line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top, top


def _build_horizontal_gradient(size: tuple[int, int], colors: list[str]) -> Image.Image:
    width, height = size
    if not colors:
        raise ValueError("highlight_colors cannot be empty for highlighted text")

    rgb_colors = [_hex_to_rgb(code) for code in colors]
    gradient = Image.new("RGBA", (width, height), rgb_colors[0] + (255,))

    if len(rgb_colors) == 1:
        return gradient

    px = gradient.load()
    steps = len(rgb_colors) - 1

    for x in range(width):
        pos = x / max(width - 1, 1)
        zone = min(int(pos * steps), steps - 1)
        local_start = zone / steps
        local_end = (zone + 1) / steps
        local_ratio = 0.0 if local_end == local_start else (pos - local_start) / (local_end - local_start)

        c1 = rgb_colors[zone]
        c2 = rgb_colors[zone + 1]
        r = int(c1[0] + (c2[0] - c1[0]) * local_ratio)
        g = int(c1[1] + (c2[1] - c1[1]) * local_ratio)
        b = int(c1[2] + (c2[2] - c1[2]) * local_ratio)

        for y in range(height):
            px[x, y] = (r, g, b, 255)

    return gradient


def _paste_rounded_gradient(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    colors: list[str],
) -> None:
    x1, y1, x2, y2 = box
    width = max(1, x2 - x1)
    height = max(1, y2 - y1)

    gradient = _build_horizontal_gradient((width, height), colors)
    mask = Image.new("L", (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=radius, fill=255)

    canvas.paste(gradient, (x1, y1), mask)


def _line_width(
    draw: ImageDraw.ImageDraw,
    segments: list[dict[str, Any]],
    fonts: dict[str, Path],
    default_font_size: int,
    highlight_padding: tuple[int, int],
) -> int:
    pad_x, _ = highlight_padding
    total = 0

    for segment in segments:
        text = segment.get("text", "")
        if not text:
            continue

        size = int(segment.get("font_size", default_font_size))
        is_bold = bool(segment.get("bold", False))
        text_w, _, _ = _measure_text_runs(draw, text, fonts, size, is_bold)
        total += text_w + (2 * pad_x if segment.get("highlighted", False) else 0)

    return total


def _tokenize_text(text: str) -> list[str]:
    tokens = re.findall(r"\n|\s+|\S+", text)
    return tokens


def _chunk_text_to_width(
    text: str,
    measure_width: Any,
    max_width: int,
) -> list[str]:
    if max_width <= 0:
        return [text]

    chunks: list[str] = []
    current = ""

    for token in _tokenize_text(text):
        if token == "\n":
            if current:
                chunks.append(current)
                current = ""
            else:
                chunks.append("")
            continue

        candidate = current + token
        candidate_width = measure_width(candidate)
        if current and candidate_width > max_width:
            chunks.append(current)
            current = token.lstrip() if token.isspace() else token
            continue

        if not current and candidate_width > max_width and not token.isspace():
            partial = ""
            for char in token:
                if not partial:
                    trial = char
                else:
                    trial = partial + char
                trial_width = measure_width(trial)
                if partial and trial_width > max_width:
                    chunks.append(partial)
                    partial = char
                else:
                    partial = trial
            current = partial
            continue

        current = candidate

    if current:
        chunks.append(current)

    return chunks


def _build_wrapped_lines(
    draw: ImageDraw.ImageDraw,
    segments: list[dict[str, Any]],
    fonts: dict[str, Path],
    default_font_size: int,
    box_width: int,
) -> list[list[dict[str, Any]]]:
    wrapped_lines: list[list[dict[str, Any]]] = []
    current_line: list[dict[str, Any]] = []
    current_width = 0

    for segment in segments:
        text = segment.get("text", "")
        if not text:
            continue

        size = int(segment.get("font_size", default_font_size))
        is_bold = bool(segment.get("bold", False))
        measure_width = lambda candidate: _measure_text_runs(draw, candidate, fonts, size, is_bold)[0]

        for chunk in _chunk_text_to_width(text, measure_width, box_width):
            if chunk == "\n":
                continue

            chunk_segment = dict(segment)
            chunk_segment["text"] = chunk
            chunk_width = measure_width(chunk)

            if current_line and current_width + chunk_width > box_width:
                wrapped_lines.append(current_line)
                current_line = [chunk_segment]
                current_width = chunk_width
            else:
                current_line.append(chunk_segment)
                current_width += chunk_width

        if "\n" in text:
            if current_line:
                wrapped_lines.append(current_line)
                current_line = []
                current_width = 0

    if current_line:
        wrapped_lines.append(current_line)

    return wrapped_lines


def _get_base_font_size(lines: list[dict[str, Any]], fallback_size: int) -> int:
    sizes: list[int] = []
    for segment in lines:
        value = segment.get("font_size")
        if value is None:
            continue
        sizes.append(int(value))
    if not sizes:
        return max(1, int(fallback_size))
    return max(1, int(round(sum(sizes) / len(sizes))))


def _scale_lines_font_size(lines: list[dict[str, Any]], target_size: int, base_size: int) -> list[dict[str, Any]]:
    safe_base = max(1, int(base_size))
    safe_target = max(1, int(target_size))
    scaled: list[dict[str, Any]] = []

    for segment in lines:
        next_segment = dict(segment)
        source_size = int(segment.get("font_size", safe_base))
        next_segment["font_size"] = max(1, int(round(source_size * (safe_target / safe_base))))
        scaled.append(next_segment)

    return scaled


def render_dynamic_text(
    image: Image.Image,
    lines: list[dict[str, Any]],
    start_xy: tuple[int, int],
    text_box: dict[str, int] | None,
    fonts: dict[str, Path],
    default_font_size: int = 30,
    line_height: int = 44,
    default_color: str = "#1E1E1E",
    default_highlight_text_color: str = "#FFFFFF",
    default_highlight_colors: list[str] | None = None,
    highlight_padding: tuple[int, int] = (8, 4),
    highlight_radius: int = 8,
    align: str = "left",
    auto_fit: bool = False,
    auto_fit_min_font_size: int = 18,
    auto_fit_max_font_size: int | None = None,
    auto_fit_line_height_ratio: float | None = None,
    auto_fit_step: int = 1,
) -> Image.Image:
    if default_highlight_colors is None:
        default_highlight_colors = ["#FF7A00"]

    if "regular" not in fonts or "bold" not in fonts:
        raise ValueError("fonts must contain 'regular' and 'bold' keys (emoji key is optional)")

    image = image.convert("RGBA")
    draw = ImageDraw.Draw(image)

    start_x, y = start_xy
    pad_x, pad_y = highlight_padding

    if text_box is not None:
        box_width = int(text_box.get("width", 0))
        box_height = int(text_box.get("height", 0))
        if box_width <= 0 or box_height <= 0:
            raise ValueError("text_box width and height must be greater than 0")
        effective_lines = lines
        effective_default_font_size = default_font_size
        effective_line_height = line_height

        if auto_fit:
            base_size = _get_base_font_size(lines, default_font_size)
            min_size = max(1, int(auto_fit_min_font_size))
            computed_max = max(base_size * 2, base_size)
            max_size = max(min_size, int(auto_fit_max_font_size or computed_max))
            step = max(1, int(auto_fit_step))
            line_height_ratio = (
                float(auto_fit_line_height_ratio)
                if auto_fit_line_height_ratio is not None
                else float(line_height) / float(max(base_size, 1))
            )

            best_lines: list[dict[str, Any]] | None = None
            best_wrapped: list[list[dict[str, Any]]] | None = None
            best_target_size: int | None = None

            def _fits_with_margin(wrapped_lines: list[list[dict[str, Any]]], candidate_line_height: int) -> bool:
                total_height = 0
                for wrapped_line in wrapped_lines:
                    line_height_px = 0
                    for segment in wrapped_line:
                        text = segment.get("text", "")
                        if not text:
                            continue
                        size = int(segment.get("font_size", candidate_line_height))
                        is_bold = bool(segment.get("bold", False))
                        for run_text, run_is_emoji in _iter_text_runs(text):
                            if not run_text:
                                continue
                            font_key = _resolve_font_for_text(run_text, is_bold, fonts)
                            font = _load_font(fonts[font_key], _render_font_size(size, font_key == "emoji"))
                            line_height_px = max(line_height_px, _font_line_height(font))

                    line_height_px = max(candidate_line_height, line_height_px + (pad_y * 2))
                    total_height += line_height_px

                # Keep a little headroom when the content already fills most of the box.
                safety_margin = candidate_line_height if total_height >= int(box_height * 0.85) else 0
                return (total_height + safety_margin) <= box_height

            for target_size in range(max_size, min_size - 1, -step):
                candidate_lines = _scale_lines_font_size(lines, target_size, base_size)
                wrapped = _build_wrapped_lines(draw, candidate_lines, fonts, target_size, box_width)
                candidate_line_height = max(1, int(round(target_size * line_height_ratio)))

                if wrapped and _fits_with_margin(wrapped, candidate_line_height):
                    best_lines = candidate_lines
                    best_wrapped = wrapped
                    best_target_size = target_size
                    break

            if best_lines is None:
                for target_size in range(min_size - 1, 0, -step):
                    candidate_lines = _scale_lines_font_size(lines, target_size, base_size)
                    wrapped = _build_wrapped_lines(draw, candidate_lines, fonts, target_size, box_width)
                    candidate_line_height = max(1, int(round(target_size * line_height_ratio)))

                    if wrapped and _fits_with_margin(wrapped, candidate_line_height):
                        best_lines = candidate_lines
                        best_wrapped = wrapped
                        best_target_size = target_size
                        break

            if best_lines is not None and best_wrapped is not None and best_target_size is not None:
                effective_lines = best_lines
                effective_default_font_size = best_target_size
                effective_line_height = max(1, int(round(best_target_size * line_height_ratio)))

        render_lines = _build_wrapped_lines(draw, effective_lines, fonts, effective_default_font_size, box_width)
        lines = effective_lines
        default_font_size = effective_default_font_size
        line_height = effective_line_height
    else:
        render_lines = [lines]

    rendered_height = 0
    for line_segments in render_lines:
        line_w = _line_width(draw, line_segments, fonts, default_font_size, highlight_padding)
        line_h = 0
        for segment in line_segments:
            text = segment.get("text", "")
            if not text:
                continue
            size = int(segment.get("font_size", default_font_size))
            is_bold = bool(segment.get("bold", False))
            for run_text, run_is_emoji in _iter_text_runs(text):
                if not run_text:
                    continue
                font_key = _resolve_font_for_text(run_text, is_bold, fonts)
                font = _load_font(fonts[font_key], _render_font_size(size, font_key == "emoji"))
                line_h = max(line_h, _font_line_height(font))

        line_h = max(line_height, line_h + (pad_y * 2))

        if text_box is not None and rendered_height + line_h > box_height:
            break

        if text_box is not None:
            if align == "center":
                x = start_x + (box_width - line_w) // 2
            elif align == "right":
                x = start_x + box_width - line_w
            else:
                x = start_x
        else:
            if align == "center":
                x = start_x - (line_w // 2)
            elif align == "right":
                x = start_x - line_w
            else:
                x = start_x

        for segment in line_segments:
            text = segment.get("text", "")
            if not text:
                continue

            size = int(segment.get("font_size", default_font_size))
            is_bold = bool(segment.get("bold", False))
            is_highlighted = bool(segment.get("highlighted", False))
            text_w, text_h, top_offset = _measure_text_runs(draw, text, fonts, size, is_bold)

            color_hex = segment.get("color", default_color)
            text_color = _hex_to_rgb(color_hex)

            if is_highlighted:
                colors = segment.get("color_codes", default_highlight_colors)
                if not isinstance(colors, list) or not colors:
                    raise ValueError("For highlighted text, color_codes must be a non-empty array of hex codes")

                highlight_box = (
                    x,
                    y - pad_y,
                    x + text_w + 2 * pad_x,
                    y + text_h + pad_y,
                )
                _paste_rounded_gradient(image, highlight_box, highlight_radius, colors)

                highlight_text_hex = segment.get("highlight_text_color", default_highlight_text_color)
                highlight_text_color = _hex_to_rgb(highlight_text_hex)
                _draw_text_runs(
                    draw=draw,
                    image=image,
                    text=text,
                    position=(x + pad_x, y - top_offset),
                    fonts=fonts,
                    size=size,
                    is_bold=is_bold,
                    is_italic=bool(segment.get("italic", False)),
                    fill=highlight_text_color,
                    embedded_color_for_emoji=True,
                )

                if bool(segment.get("underline", False)):
                    ux = x + pad_x
                    uy = y + text_h - max(1, int(size * 0.12))
                    line_w = max(1, int(size / 14))
                    draw.line((ux, uy, ux + text_w, uy), fill=highlight_text_color, width=line_w)

                x += text_w + 2 * pad_x
            else:
                _draw_text_runs(
                    draw=draw,
                    image=image,
                    text=text,
                    position=(x, y - top_offset),
                    fonts=fonts,
                    size=size,
                    is_bold=is_bold,
                    is_italic=bool(segment.get("italic", False)),
                    fill=text_color,
                    embedded_color_for_emoji=True,
                )

                if bool(segment.get("underline", False)):
                    ux = x
                    uy = y + text_h - max(1, int(size * 0.12))
                    line_w = max(1, int(size / 14))
                    draw.line((ux, uy, ux + text_w, uy), fill=text_color, width=line_w)

                x += text_w

        y += line_h
        rendered_height += line_h

    return image


def add_dynamic_text(
    image_path: Path,
    output_path: Path,
    lines: list[dict[str, Any]],
    start_xy: tuple[int, int],
    text_box: dict[str, int] | None,
    fonts: dict[str, Path],
    default_font_size: int = 30,
    line_height: int = 44,
    default_color: str = "#1E1E1E",
    default_highlight_text_color: str = "#FFFFFF",
    default_highlight_colors: list[str] | None = None,
    highlight_padding: tuple[int, int] = (8, 4),
    highlight_radius: int = 8,
    align: str = "left",
    auto_fit: bool = False,
    auto_fit_min_font_size: int = 18,
    auto_fit_max_font_size: int | None = None,
    auto_fit_line_height_ratio: float | None = None,
    auto_fit_step: int = 1,
) -> None:
    image = Image.open(image_path)
    rendered_image = render_dynamic_text(
        image=image,
        lines=lines,
        start_xy=start_xy,
        text_box=text_box,
        fonts=fonts,
        default_font_size=default_font_size,
        line_height=line_height,
        default_color=default_color,
        default_highlight_text_color=default_highlight_text_color,
        default_highlight_colors=default_highlight_colors,
        highlight_padding=highlight_padding,
        highlight_radius=highlight_radius,
        align=align,
        auto_fit=auto_fit,
        auto_fit_min_font_size=auto_fit_min_font_size,
        auto_fit_max_font_size=auto_fit_max_font_size,
        auto_fit_line_height_ratio=auto_fit_line_height_ratio,
        auto_fit_step=auto_fit_step,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered_image.convert("RGB").save(output_path)


if __name__ == "__main__":
    text_blocks = [
        {"text": "Mondays may not ", "bold": False, "color": "#1E1E1E", "font_size": 42},
        {
            "text": "SMELL",
            "bold": True,
            "highlighted": True,
            "font_size": 42,
            "color_codes": ["#1E1E1E", "#1E1E1E"],
        },
        {"text": " nice", "bold": False, "color": "#1E1E1E", "font_size": 42},
        {"text": " But ", "bold": False, "color": "#1E1E1E", "font_size": 42},
        {
            "text": "YOU",
            "bold": True,
            "highlighted": True,
            "font_size": 42,
            "color_codes": ["#1E1E1E", "#1E1E1E"],
        },
        {"text": " can", "bold": False, "color": "#1E1E1E", "font_size": 42},
    ]

    add_dynamic_text(
        image_path=BASE_DIR / "images" / "post.jpg",
        output_path=BASE_DIR / "output" / "post_text_output.jpg",
        lines=text_blocks,
        start_xy=(540, 220),
        text_box={"width": 900, "height": 360},
        fonts={
            "regular": BASE_DIR / "fonts" / "Poppins-Regular.ttf",
            "bold": BASE_DIR / "fonts" / "Poppins-Bold.ttf",
        },
        default_font_size=36,
        line_height=56,
        default_color="#111111",
        default_highlight_text_color="#FFFFFF",
        default_highlight_colors=["#FF6B00", "#F54800"],
        highlight_padding=(10, 6),
        highlight_radius=10,
        align="center",
    )

    print("Dynamic text rendering complete: output/post_text_output.jpg")