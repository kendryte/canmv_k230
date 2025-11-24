import time, os, urandom, sys

from media.display import *
from media.media import *

#DISPLAY_FLAG = None
DISPLAY_FLAG = Display.FLAG_ROTATION_90

def gcd(a, b):
    """Calculate Greatest Common Divisor of two numbers"""
    while b:
        a, b = b, a % b
    return a

def display_test():
    print("display test")

    Display.init(Display.DEBUGGER, to_ide = True, flag = DISPLAY_FLAG)

    display_width = Display.width()
    display_height = Display.height()

    print(f"Display widht: {display_width}, height {display_height}")

    # create image for drawing
    img = image.Image(display_width, display_height, image.ARGB8888)
    img.clear()

    # Use GCD of width and height as block size
    block_size = gcd(display_width, display_height)
    print(f"Block size (GCD): {block_size}")

    # Calculate number of blocks in rows and columns
    cols = display_width // block_size
    rows = display_height // block_size

    print(f"Grid: {cols} columns x {rows} rows")

    # Two distinct color schemes for alternating blocks
    color_scheme1 = [(255, 0, 0), (0, 255, 0)]    # Red/Green
    color_scheme2 = [(0, 0, 255), (255, 255, 255)]  # Blue/Yellow

    # Fill with highly distinct colorbar pattern
    for y in range(rows):
        for x in range(cols):
            # Choose color scheme based on block position for high contrast
            if (x + y) % 2 == 0:
                # Use red/green scheme for even positions
                bg_color = color_scheme1[0] if x % 2 == 0 else color_scheme1[1]
                text_color = color_scheme2[0] if x % 2 == 0 else color_scheme2[1]
            else:
                # Use blue/yellow scheme for odd positions  
                bg_color = color_scheme2[0] if x % 2 == 0 else color_scheme2[1]
                text_color = color_scheme1[0] if x % 2 == 0 else color_scheme1[1]

            # Draw colored background rectangle
            img.draw_rectangle(
                x * block_size,
                y * block_size,
                block_size,
                block_size,
                color = bg_color,
                fill = True
            )
            
            # Draw position text using draw_string_advanced
            font_size = block_size // 3
            img.draw_string_advanced(
                x * block_size + block_size // 6,
                y * block_size + block_size // 3,
                font_size,
                f"{x},{y}",
                color = text_color,
            )

    # draw result to screen
    Display.show_image(img)

    print(f"Column sequence: 0 to {cols-1} (left to right)")
    print(f"Row sequence: 0 to {rows-1} (top to bottom)")
    print("Color pattern:")
    print("- Even positions: Red/Green blocks with Blue/Yellow text")
    print("- Odd positions: Blue/Yellow blocks with Red/Green text")
    print("- High contrast between adjacent blocks")

    while True:
        time.sleep(5)

    # deinit display
    Display.deinit()
    time.sleep_ms(100)
    # release media buffer
    MediaManager.deinit()

if __name__ == "__main__":
    display_test()
