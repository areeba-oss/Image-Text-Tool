from pathlib import Path
from typing import Any
import re

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    code = value.strip().lstrip("#")
    if len(code) != 6:
        raise ValueError(f"Invalid color hex: {value}")
    return tuple(int(code[i:i + 2], 16) for i in (0, 2, 4))


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    if not font_path.exists():
        raise FileNotFoundError(f"Font not found: {font_path}")
    return ImageFont.truetype(str(font_path), size)


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
        font_key = "bold" if is_bold else "regular"
        font = _load_font(fonts[font_key], size)

        text_w, _, _ = _measure_text(draw, text, font)
        total += text_w + (2 * pad_x if segment.get("highlighted", False) else 0)

    return total


def _tokenize_text(text: str) -> list[str]:
    tokens = re.findall(r"\n|\s+|\S+", text)
    return tokens


def _chunk_text_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
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
        candidate_width, _, _ = _measure_text(draw, candidate, font)
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
                trial_width, _, _ = _measure_text(draw, trial, font)
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
        font_key = "bold" if is_bold else "regular"
        font = _load_font(fonts[font_key], size)

        for chunk in _chunk_text_to_width(draw, text, font, box_width):
            if chunk == "\n":
                continue

            chunk_segment = dict(segment)
            chunk_segment["text"] = chunk
            chunk_width, _, _ = _measure_text(draw, chunk, font)

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
) -> Image.Image:
    if default_highlight_colors is None:
        default_highlight_colors = ["#FF7A00"]

    if "regular" not in fonts or "bold" not in fonts:
        raise ValueError("fonts must contain 'regular' and 'bold' keys")

    image = image.convert("RGBA")
    draw = ImageDraw.Draw(image)

    start_x, y = start_xy
    pad_x, pad_y = highlight_padding

    if text_box is not None:
        box_width = int(text_box.get("width", 0))
        box_height = int(text_box.get("height", 0))
        if box_width <= 0 or box_height <= 0:
            raise ValueError("text_box width and height must be greater than 0")
        render_lines = _build_wrapped_lines(draw, lines, fonts, default_font_size, box_width)
    else:
        render_lines = [lines]

    rendered_height = 0
    for line_segments in render_lines:
        if text_box is not None and rendered_height + line_height > box_height:
            break

        line_w = _line_width(draw, line_segments, fonts, default_font_size, highlight_padding)
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

            font_key = "bold" if is_bold else "regular"
            font = _load_font(fonts[font_key], size)
            text_w, text_h, top_offset = _measure_text(draw, text, font)

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
                draw.text((x + pad_x, y - top_offset), text, font=font, fill=highlight_text_color)
                x += text_w + 2 * pad_x
            else:
                draw.text((x, y - top_offset), text, font=font, fill=text_color)
                x += text_w

        y += line_height
        rendered_height += line_height

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