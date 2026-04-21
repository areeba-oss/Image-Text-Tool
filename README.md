# Monday Motivation - Dynamic Text Renderer

## Setup (one time only)

```
pip install -r requirements.txt
```

## API mode (FastAPI)

Run API server:

```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Endpoint:

- `POST /render-text-monday-motivation`
- `POST /render-text-review`
- `POST /render-text-funfact`
- `POST /render-text` (alias for Monday motivation)
- `GET /health`
- `GET /registry`
- `GET /image-info?image=...`
- `GET /media/images/{file_name}` (read source images)
- `GET /media/output/{file_name}` (read rendered outputs)
- `GET /media/root-images/{file_name}` (read images stored next to code files)

### Fetch image files via API

Examples:

```bash
curl "http://localhost:8000/media/images/post.jpg" --output post.jpg
curl "http://localhost:8000/media/output/post_api_output.jpg" --output rendered.jpg
curl "http://localhost:8000/media/root-images/SPC-Fun.jpg" --output root_image.jpg
```

### How to choose `start_xy`

- Coordinates are in pixels by default (`start_xy_mode: "px"`).
- `x` grows left to right, `y` grows top to bottom.
- Use `align` to decide what `x` means:
    - `left`: text starts at `x`
    - `center`: `x` is center anchor
    - `right`: `x` is right edge anchor

To avoid guessing, call:

```bash
curl "http://localhost:8000/image-info?image=post"
```

It returns image width/height and sample pixel anchors.

To see allowed image/font keys from backend registry:

```bash
curl "http://localhost:8000/registry"
```

You can also use percentage mode for responsive placement:

- `start_xy_mode: "percent"`
- `start_xy: [50, 20]` means 50% width, 20% height

Example request body:

```json
{
    "image": "post",
    "output_path": "output/post_api_output.jpg",
    "lines": [
        { "text": "Mondays may not ", "bold": false, "font_size": 42, "color": "#1E1E1E" },
        {
            "text": "SMELL",
            "bold": true,
            "highlighted": true,
            "font_size": 42,
            "color_codes": ["#1E1E1E", "#1E1E1E"],
            "highlight_text_color": "#FFFFFF"
        },
        { "text": " nice", "bold": false, "font_size": 42, "color": "#1E1E1E" }
    ],
    "start_xy": [540, 220],
    "start_xy_mode": "px",
    "text_box": {
        "width": 900,
        "height": 360
    },
    "fonts": {
        "regular": "Poppins-Regular",
        "bold": "Poppins-Bold"
    },
    "default_font_size": 36,
    "line_height": 56,
    "default_color": "#111111",
    "default_highlight_text_color": "#FFFFFF",
    "default_highlight_colors": ["#FF6B00", "#F54800"],
    "highlight_padding": [10, 6],
    "highlight_radius": 10,
    "align": "center",
    "auto_fit": true,
    "auto_fit_min_font_size": 28,
    "auto_fit_max_font_size": 96,
    "auto_fit_line_height_ratio": 1.25,
    "auto_fit_step": 1
}
```

Review endpoint example:

```json
{
    "image_path": "final post .jpg",
    "output_path": "post_review_output",
    "text": "This is a great product. It is clean, fast, and easy to use.",
    "start_xy": [5, 35],
    "reviewer_name": "Areeba",
    "reviewer_name_xy": [5, 75],
    "start_xy_mode": "percent",
    "text_box": {
        "width": 900,
        "height": 300
    },
    "reviewer_name_box": {
        "width": 500,
        "height": 80
    },
    "align": "center",
    "reviewer_name_align": "left",
    "fonts": {
        "regular": "Poppins-Regular.ttf",
        "bold": "Poppins-Bold.ttf"
    },
    "font_size": 54,
    "line_height": 66,
    "reviewer_name_font_size": 36,
    "font_color": "#1E1E1E",
    "reviewer_name_font_color": "#1E1E1E"
}
```

Funfact endpoint example:

```json
{
    "image_path": "Chic-Testimonial.jpg",
    "output_path": "post_funfact_output",
    "text": "Fun Fact: Consistency beats intensity when you are building habits.",
    "start_xy": [15, 43],
    "text_box": {
        "width": 775,
        "height": 300
    },
    "align": "center",
    "font_color": "#FFFFFF",
    "font_size": 40,
    "line_height": 52,
    "start_xy_mode": "percent",
    "fonts": {
        "regular": "PlayfairDisplay-Regular.ttf",
        "bold": "PLAYFAIRDISPLAY-BLACK.ttf"
    }
}
```

PowerShell example:

```powershell
$body = @'
{
    "image": "post",
    "output_path": "output/post_api_output.jpg",
    "lines": [{"text":"Hello ","bold":false},{"text":"WORLD","bold":true,"highlighted":true,"color_codes":["#FF7A00","#D64E00"]}],
    "start_xy": [50, 20],
    "start_xy_mode": "percent",
    "fonts": {"regular":"Poppins-Regular","bold":"Poppins-Bold"},
    "align": "center"
}
'@

Invoke-RestMethod -Uri "http://localhost:8000/render-text" -Method Post -ContentType "application/json" -Body $body
```

## Usage

1. Drop your image into the `images/` folder (PNG or JPG)
2. Open `replace_text.py` and edit `text_blocks` plus the `add_dynamic_text(...)` call
3. Run:

```
python replace_text.py
```

4. Find the result in the  `output/`  folder

## Data format (flat array of objects)

```python
text_blocks = [
    {"text": "Your normal text ", "bold": False, "color": "#1E1E1E", "font_size": 36},
    {
        "text": "HIGHLIGHT",
        "bold": True,
        "highlighted": True,
        "font_size": 36,
        "color_codes": ["#FF7A00", "#D64E00"],
        "highlight_text_color": "#FFFFFF"
    },
    {"text": "Second part...", "bold": False, "color": "#222222", "font_size": 30},
]
```

- If `text_box` is provided, the renderer wraps text inside the box and stops when height is exhausted.
- If `text_box` is omitted, the renderer keeps the old one-line continuous behavior.
- The review and funfact endpoints now support unified keys: `text`, `start_xy`, `text_box`, `align`, `font_size`, `line_height`, `font_color`.
- Backward compatibility is kept: old keys like `review_text_*` and `funfact_*` still work.
- The review endpoint still supports reviewer-specific controls (`reviewer_name`, `reviewer_name_xy`, `reviewer_name_box`, `reviewer_name_align`, `reviewer_name_font_size`, `reviewer_name_font_color`).
- Auto-fitting is supported on all 3 render endpoints when `text_box` is provided:
    - `auto_fit`: enable/disable automatic resize
    - `auto_fit_min_font_size`: lower bound for shrink
    - `auto_fit_max_font_size`: upper bound for grow (if omitted, renderer auto-picks a reasonable max)
    - `auto_fit_line_height_ratio`: line-height scale factor relative to selected font size
    - `auto_fit_step`: search step (1 gives best precision)
- `text`: required text segment.
- `bold`: chooses bold font file (`fonts['bold']`).
- `highlighted`: if `True`, draws a rounded highlight behind text.
- `color`: text color hex for non-highlighted text.
- `font_size`: optional size override per segment.
- `color_codes`: hex array for highlighted background. One value gives solid color, multiple values create left-to-right gradient.
- `highlight_text_color`: optional text color for highlighted segment.

## Function signature

`add_dynamic_text(image_path, output_path, lines, start_xy, fonts, ...)`

- `fonts` must include:
  - `regular`: path to regular `.ttf`
  - `bold`: path to bold `.ttf`
- Supports `align="left" | "center" | "right"`.
- Supports global controls like `line_height`, `highlight_padding`, `highlight_radius`, and default colors.
