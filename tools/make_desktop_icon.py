from pathlib import Path

from PIL import Image


def main():
    project_dir = Path(__file__).resolve().parent.parent
    source_image = project_dir.parent / 'attendance.png'
    output_dir = project_dir / 'build_assets'
    output_dir.mkdir(parents=True, exist_ok=True)
    icon_path = output_dir / 'attendance.ico'

    image = Image.open(source_image).convert('RGBA')
    image.save(
        icon_path,
        format='ICO',
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(icon_path)


if __name__ == '__main__':
    main()
