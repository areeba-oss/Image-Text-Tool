from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from PIL import Image
from pydantic import AliasChoices, BaseModel, Field

from replace_text import BASE_DIR, render_dynamic_text

app = FastAPI(title="Dynamic Text Renderer API", version="1.0.0")

FONTS_DIR = BASE_DIR / "fonts"
IMAGES_DIR = BASE_DIR / "images"


def _build_font_registry() -> dict[str, Path]:
    registry: dict[str, Path] = {}
    for pattern in ("*.ttf", "*.otf"):
        for file_path in FONTS_DIR.glob(pattern):
            stem = file_path.stem
            file_name = file_path.name
            registry[stem] = file_path
            registry[stem.lower()] = file_path
            registry[stem.upper()] = file_path
            registry[file_name] = file_path
            registry[file_name.lower()] = file_path
            registry[file_name.upper()] = file_path
    return registry


def _build_image_registry() -> dict[str, Path]:
    registry: dict[str, Path] = {}
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for file_path in IMAGES_DIR.glob(pattern):
            file_name = file_path.name
            stem = file_path.stem
            registry[file_name] = file_path
            registry[file_name.lower()] = file_path
            registry[stem] = file_path
            registry[stem.lower()] = file_path
    return registry


FONT_REGISTRY = _build_font_registry()
IMAGE_REGISTRY = _build_image_registry()


class SegmentModel(BaseModel):
    text: str
    bold: bool = False
    highlighted: bool = False
    color: str | None = None
    color_codes: list[str] | None = None
    highlight_text_color: str | None = None
    font_size: int | None = None


class TextBoxModel(BaseModel):
    width: int
    height: int


class RenderRequest(BaseModel):
    image: str = Field(
        ...,
        description="Image key configured on backend (example: post or post.jpg)",
        validation_alias=AliasChoices("image", "image_path"),
    )
    output_path: str | None = Field(None, description="Optional output path")
    lines: list[SegmentModel]
    start_xy: tuple[float, float]
    start_xy_mode: Literal["px", "percent"] = "px"
    text_box: TextBoxModel | None = Field(None, description="Optional fixed text box size")
    fonts: dict[str, str]
    default_font_size: int = 30
    line_height: int = 44
    default_color: str = "#1E1E1E"
    default_highlight_text_color: str = "#FFFFFF"
    default_highlight_colors: list[str] | None = None
    highlight_padding: tuple[int, int] = (8, 4)
    highlight_radius: int = 8
    align: Literal["left", "center", "right"] = "left"


class ReviewRequest(BaseModel):
    image: str = Field(
        ...,
        description="Image key configured on backend (example: post or post.jpg)",
        validation_alias=AliasChoices("image", "image_path"),
    )
    output_path: str | None = Field(None, description="Optional output path")
    review_text: str
    review_text_xy: tuple[float, float]
    reviewer_name: str | None = None
    reviewer_name_xy: tuple[float, float] | None = None
    start_xy_mode: Literal["px", "percent"] = "px"
    review_text_box: TextBoxModel | None = Field(None, description="Optional fixed box for review text")
    reviewer_name_box: TextBoxModel | None = Field(None, description="Optional fixed box for reviewer name")
    review_text_align: Literal["left", "center", "right"] = Field(
        "left",
        validation_alias=AliasChoices("review_text_align", "align"),
    )
    reviewer_name_align: Literal["left", "center", "right"] = "left"
    fonts: dict[str, str]
    review_text_font_size: int = 32
    reviewer_name_font_size: int = 28
    review_text_font_color: str = Field(
        "#1E1E1E",
        validation_alias=AliasChoices("review_text_font_color", "review_text_color"),
    )
    reviewer_name_font_color: str = Field(
        "#1E1E1E",
        validation_alias=AliasChoices("reviewer_name_font_color", "reviewer_name_color"),
    )
    default_highlight_colors: list[str] | None = None
    highlight_padding: tuple[int, int] = (8, 4)
    highlight_radius: int = 8


class FunFactRequest(BaseModel):
    image: str = Field(
        ...,
        description="Image key configured on backend (example: post or post.jpg)",
        validation_alias=AliasChoices("image", "image_path"),
    )
    output_path: str | None = Field(None, description="Optional output path")
    funfact_text: str
    funfact_xy: tuple[float, float]
    start_xy_mode: Literal["px", "percent"] = "px"
    funfact_box: TextBoxModel
    funfact_align: Literal["left", "center", "right"] = Field(
        "left",
        validation_alias=AliasChoices("funfact_align", "align"),
    )
    fonts: dict[str, str]
    funfact_font_size: int = 32
    funfact_font_color: str = Field(
        "#1E1E1E",
        validation_alias=AliasChoices("funfact_font_color", "funfact_color"),
    )
    default_highlight_colors: list[str] | None = None
    highlight_padding: tuple[int, int] = (8, 4)
    highlight_radius: int = 8


class RenderResponse(BaseModel):
    output_path: str
    message: str


class ImageInfoResponse(BaseModel):
    image_key: str
    image_path: str
    width: int
    height: int
    center_xy_px: tuple[int, int]
    sample_positions_px: dict[str, tuple[int, int]]


class RegistryResponse(BaseModel):
    image_keys: list[str]
    font_keys: list[str]


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _ensure_image_suffix(path: Path) -> Path:
    if path.suffix:
        return path
    return path.with_suffix(".jpg")


def _resolve_font_key(font_key: str) -> Path:
    global FONT_REGISTRY
    font_key = font_key.strip()
    matched = FONT_REGISTRY.get(font_key) or FONT_REGISTRY.get(font_key.lower())
    if matched is None:
        FONT_REGISTRY = _build_font_registry()
        matched = FONT_REGISTRY.get(font_key) or FONT_REGISTRY.get(font_key.lower())
    if matched is None:
        raise HTTPException(status_code=400, detail=f"Font key not found: {font_key}")
    return matched


def _resolve_image_key(image_key: str) -> Path:
    global IMAGE_REGISTRY
    image_key = image_key.strip()
    matched = IMAGE_REGISTRY.get(image_key) or IMAGE_REGISTRY.get(image_key.lower())
    if matched is None:
        IMAGE_REGISTRY = _build_image_registry()
        matched = IMAGE_REGISTRY.get(image_key) or IMAGE_REGISTRY.get(image_key.lower())
    if matched is None:
        raise HTTPException(status_code=400, detail=f"Image key not found: {image_key}")
    return matched


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/registry", response_model=RegistryResponse)
def registry() -> RegistryResponse:
    return RegistryResponse(
        image_keys=sorted({key for key in IMAGE_REGISTRY.keys() if key == key.lower() or "." in key}),
        font_keys=sorted({key for key in FONT_REGISTRY.keys() if key == key.lower() or "-" in key or "_" in key or "." in key}),
    )


@app.get("/image-info", response_model=ImageInfoResponse)
def image_info(image: str = Query(..., description="Image key from backend registry")) -> ImageInfoResponse:
    resolved = _resolve_image_key(image)
    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"Image not found: {resolved}")

    with Image.open(resolved) as image_file:
        width, height = image_file.size

    return ImageInfoResponse(
        image_key=image,
        image_path=str(resolved),
        width=width,
        height=height,
        center_xy_px=(width // 2, height // 2),
        sample_positions_px={
            "top_left": (int(width * 0.1), int(height * 0.1)),
            "top_center": (width // 2, int(height * 0.15)),
            "middle_center": (width // 2, height // 2),
            "bottom_center": (width // 2, int(height * 0.85)),
        },
    )


def _resolve_point(width: int, height: int, point: tuple[float, float], mode: str) -> tuple[int, int]:
    if mode == "percent":
        px, py = point
        if px < 0 or px > 100 or py < 0 or py > 100:
            raise HTTPException(status_code=400, detail="Percent coordinates expect values between 0 and 100")
        return int(width * (px / 100.0)), int(height * (py / 100.0))
    return int(point[0]), int(point[1])


def _render_segments(
    image_path: Path,
    output_path: Path,
    lines: list[dict[str, object]],
    start_xy: tuple[int, int],
    text_box: dict[str, int] | None,
    fonts: dict[str, Path],
    default_font_size: int,
    line_height: int,
    default_color: str,
    default_highlight_text_color: str,
    default_highlight_colors: list[str] | None,
    highlight_padding: tuple[int, int],
    highlight_radius: int,
    align: str,
) -> None:
    with Image.open(image_path) as image:
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


def _build_plain_segment(text: str, color: str, font_size: int, bold: bool = False) -> dict[str, object]:
    return {
        "text": text,
        "bold": bold,
        "font_size": font_size,
        "color": color,
    }


@app.post("/render-text-monday-motivation", response_model=RenderResponse)
@app.post("/render-text", response_model=RenderResponse)
def render_text(payload: RenderRequest) -> RenderResponse:
    try:
        image_path = _resolve_image_key(payload.image)
        if not image_path.exists():
            raise HTTPException(status_code=400, detail=f"Image not found: {image_path}")

        with Image.open(image_path) as image:
            width, height = image.size

        start_xy_px = _resolve_point(width, height, payload.start_xy, payload.start_xy_mode)

        output_path = (
            _ensure_image_suffix(_resolve_path(payload.output_path))
            if payload.output_path
            else BASE_DIR / "output" / f"render_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        )

        resolved_fonts = {key: _resolve_font_key(value) for key, value in payload.fonts.items()}
        lines = [segment.model_dump(exclude_none=True) for segment in payload.lines]

        _render_segments(
            image_path=image_path,
            output_path=output_path,
            lines=lines,
            start_xy=start_xy_px,
            text_box=(payload.text_box.model_dump() if payload.text_box else None),
            fonts=resolved_fonts,
            default_font_size=payload.default_font_size,
            line_height=payload.line_height,
            default_color=payload.default_color,
            default_highlight_text_color=payload.default_highlight_text_color,
            default_highlight_colors=payload.default_highlight_colors,
            highlight_padding=payload.highlight_padding,
            highlight_radius=payload.highlight_radius,
            align=payload.align,
        )

        return RenderResponse(
            output_path=str(output_path),
            message="Image rendered successfully",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/render-text-review", response_model=RenderResponse)
def render_text_review(payload: ReviewRequest) -> RenderResponse:
    try:
        image_path = _resolve_image_key(payload.image)
        if not image_path.exists():
            raise HTTPException(status_code=400, detail=f"Image not found: {image_path}")

        with Image.open(image_path) as image:
            width, height = image.size

            review_text_xy = _resolve_point(width, height, payload.review_text_xy, payload.start_xy_mode)
            resolved_fonts = {key: _resolve_font_key(value) for key, value in payload.fonts.items()}
            rendered_image = render_dynamic_text(
                image=image,
                lines=[_build_plain_segment(payload.review_text, payload.review_text_font_color, payload.review_text_font_size)],
                start_xy=review_text_xy,
                text_box=(payload.review_text_box.model_dump() if payload.review_text_box else None),
                fonts=resolved_fonts,
                default_font_size=payload.review_text_font_size,
                line_height=payload.review_text_font_size + 12,
                default_color=payload.review_text_font_color,
                default_highlight_text_color=payload.review_text_font_color,
                default_highlight_colors=payload.default_highlight_colors,
                highlight_padding=payload.highlight_padding,
                highlight_radius=payload.highlight_radius,
                align=payload.review_text_align,
            )

            if payload.reviewer_name and payload.reviewer_name.strip():
                if payload.reviewer_name_xy is None:
                    raise HTTPException(status_code=400, detail="reviewer_name_xy is required when reviewer_name is provided")

                reviewer_name_xy = _resolve_point(width, height, payload.reviewer_name_xy, payload.start_xy_mode)
                rendered_image = render_dynamic_text(
                    image=rendered_image,
                    lines=[_build_plain_segment(payload.reviewer_name, payload.reviewer_name_font_color, payload.reviewer_name_font_size)],
                    start_xy=reviewer_name_xy,
                    text_box=(payload.reviewer_name_box.model_dump() if payload.reviewer_name_box else None),
                    fonts=resolved_fonts,
                    default_font_size=payload.reviewer_name_font_size,
                    line_height=payload.reviewer_name_font_size + 12,
                    default_color=payload.reviewer_name_font_color,
                    default_highlight_text_color=payload.reviewer_name_font_color,
                    default_highlight_colors=payload.default_highlight_colors,
                    highlight_padding=payload.highlight_padding,
                    highlight_radius=payload.highlight_radius,
                    align=payload.reviewer_name_align,
                )

        output_path = (
            _ensure_image_suffix(_resolve_path(payload.output_path))
            if payload.output_path
            else BASE_DIR / "output" / f"review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rendered_image.convert("RGB").save(output_path)

        return RenderResponse(
            output_path=str(output_path),
            message="Review image rendered successfully",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/render-text-funfact", response_model=RenderResponse)
def render_text_funfact(payload: FunFactRequest) -> RenderResponse:
    try:
        image_path = _resolve_image_key(payload.image)
        if not image_path.exists():
            raise HTTPException(status_code=400, detail=f"Image not found: {image_path}")

        with Image.open(image_path) as image:
            width, height = image.size

            funfact_xy = _resolve_point(width, height, payload.funfact_xy, payload.start_xy_mode)
            resolved_fonts = {key: _resolve_font_key(value) for key, value in payload.fonts.items()}
            rendered_image = render_dynamic_text(
                image=image,
                lines=[_build_plain_segment(payload.funfact_text, payload.funfact_font_color, payload.funfact_font_size)],
                start_xy=funfact_xy,
                text_box=payload.funfact_box.model_dump(),
                fonts=resolved_fonts,
                default_font_size=payload.funfact_font_size,
                line_height=payload.funfact_font_size + 12,
                default_color=payload.funfact_font_color,
                default_highlight_text_color=payload.funfact_font_color,
                default_highlight_colors=payload.default_highlight_colors,
                highlight_padding=payload.highlight_padding,
                highlight_radius=payload.highlight_radius,
                align=payload.funfact_align,
            )

        output_path = (
            _ensure_image_suffix(_resolve_path(payload.output_path))
            if payload.output_path
            else BASE_DIR / "output" / f"funfact_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rendered_image.convert("RGB").save(output_path)

        return RenderResponse(
            output_path=str(output_path),
            message="Funfact image rendered successfully",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
