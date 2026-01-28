"""
Script to create ICO file from PNG for Windows EXE.
Run this before building the EXE.
"""

from PIL import Image
import os

def create_ico():
    """Create .ico file from tray_idle.png for Windows EXE."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    png_path = os.path.join(script_dir, 'src', 'resources', 'icons', 'tray_idle.png')
    ico_path = os.path.join(script_dir, 'src', 'resources', 'icons', 'app.ico')

    if not os.path.exists(png_path):
        print(f"Error: PNG file not found at {png_path}")
        return False

    try:
        # Open the PNG image
        img = Image.open(png_path)

        # Convert to RGBA if necessary
        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        # Create multiple sizes for ICO (Windows uses different sizes)
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

        # Resize images for each size
        images = []
        for size in sizes:
            resized = img.resize(size, Image.Resampling.LANCZOS)
            images.append(resized)

        # Save as ICO with multiple sizes
        images[0].save(
            ico_path,
            format='ICO',
            sizes=[(s[0], s[1]) for s in sizes],
            append_images=images[1:]
        )

        print(f"ICO file created successfully at {ico_path}")
        return True

    except Exception as e:
        print(f"Error creating ICO file: {e}")
        return False


if __name__ == "__main__":
    create_ico()
