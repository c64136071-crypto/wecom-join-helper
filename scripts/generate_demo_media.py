from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets"


def font(size: int, bold: bool = False):
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    path = Path("C:/Windows/Fonts") / name
    return ImageFont.truetype(path, size) if path.exists() else ImageFont.load_default()


def draw_frame(status: str, detail: str, active: str) -> Image.Image:
    image = Image.new("RGB", (1200, 720), "#eef1f2")
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, 690, 720), fill="#ffffff")
    draw.rectangle((0, 0, 690, 64), fill="#243238")
    draw.text((28, 18), "Team lounge", font=font(22, True), fill="white")
    draw.text((34, 102), "Office coordinator", font=font(16, True), fill="#26343a")
    draw.text((34, 135), "Friday snack sign-up", font=font(21, True), fill="#17252f")
    draw.text((34, 171), "Choose your item when collecting.", font=font(15), fill="#66767d")

    draw.rounded_rectangle((34, 220, 650, 432), radius=6, fill="#f7f8f8", outline="#d6dcde")
    draw.rounded_rectangle((68, 258, 112, 302), radius=6, fill="#f2b719")
    draw.line((80, 280, 89, 289, 103, 269), fill="white", width=5, joint="curve")
    draw.text((134, 250), "Friday afternoon tea", font=font(22, True), fill="#17252f")
    draw.text((134, 291), "Join list", font=font(15), fill="#68777d")
    draw.rounded_rectangle((454, 354, 614, 408), radius=6, fill="#ffffff", outline="#aab5b9")
    draw.text((494, 369), "Participate", font=font(16, True), fill="#245e8a")

    draw.rounded_rectangle((740, 92, 1160, 614), radius=8, fill="#ffffff", outline="#c7ced1", width=2)
    draw.rectangle((740, 92, 1160, 160), fill="#1f765a")
    draw.text((770, 112), "Join Helper", font=font(24, True), fill="white")
    draw.text((774, 212), status, font=font(26, True), fill="#17252f")
    draw.multiline_text((774, 264), detail, font=font(17), fill="#617177", spacing=8)
    draw.text((774, 410), "Keyword", font=font(14), fill="#748288")
    draw.rounded_rectangle((774, 438, 1118, 488), radius=6, fill="#ffffff", outline="#b9c2c6")
    draw.text((792, 451), "afternoon tea", font=font(17), fill="#243238")

    buttons = [
        (774, 524, 916, 574, "Test", "test"),
        (934, 524, 1118, 574, "Enable live", "live"),
    ]
    for left, top, right, bottom, label, key in buttons:
        selected = active == key
        fill = "#1f765a" if selected else "#ffffff"
        color = "white" if selected else "#1f765a"
        draw.rounded_rectangle((left, top, right, bottom), radius=6, fill=fill, outline="#7f918a")
        width = draw.textlength(label, font=font(16, True))
        draw.text(((left + right - width) / 2, top + 14), label, font=font(16, True), fill=color)

    draw.text((34, 670), "Synthetic demonstration - no account or company data", font=font(14), fill="#7a878c")
    return image


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    frames = [
        draw_frame("First-run setup", "Open the target group, then run a\nno-input recognition test.", "test"),
        draw_frame("Recognition passed", "The title and card matched. No mouse\ninput was sent.", "test"),
        draw_frame("Live mode ready", "One insertion attempt will stop on\nsuccess or any unsafe state.", "live"),
    ]
    frames[1].save(OUTPUT / "join-helper-main.png", optimize=True)
    frames[0].save(
        OUTPUT / "join-helper-demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=[1200, 1400, 1800],
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    main()
