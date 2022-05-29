import json
import os

import numpy as np
from PIL import Image

from utils.log import get_logger

""" This file contains classes and functions to manage fonts and make pixel art texts"""

logger = get_logger(__name__)
basepath = os.path.dirname(__file__)
fonts_folder = os.path.abspath(
    os.path.join(basepath, "..", "..", "..", "resources", "fonts")
)

SPACE_WIDTH = 4
# fonts allowed for the table image
ALLOWED_FONTS = ["minecraft", "typewriter", "roman", "3x5", "3x4", "indie", "gravity"]
DEFAULT_FONT = "minecraft"

all_accents = "ÀÁÂÃÄÅÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜàáâãäåèéêëìíîïñòóôõöùúûüÿŸ"
all_special_chars = './-+*&~#’()|_^@[]{}%!?$€:,\\`><;"='
letter_bases = {
    "áàâäãå": "a",
    "ÁÀÂÄÃÅ": "A",
    "éèêë": "e",
    "ÉÈÊË": "E",
    "iíìîï": "ı",
    "İÍÌÎÏ": "I",
    "óòôöõ": "o",
    "ÓÒÔÖÕ": "O",
    "úùûü": "u",
    "ÚÙÛÜ": "U",
    "ÿ": "y",
    "Ÿ": "Y",
    "ñ": "n",
    "Ñ": "N",
}

test_string = 'abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789 ./-+*&~#’()|_^@[]{}%!?$€:,\\`><;"'


def load_font_images():
    """Load all the files needed for the fonts"""
    font_files = {}
    nb_fonts = len(os.listdir(fonts_folder))
    nb_loaded_fonts = 0
    for font_name in os.listdir(fonts_folder):
        # load the font image
        font_img_path = os.path.join(fonts_folder, font_name, font_name + ".png")
        try:
            font_img = Image.open(font_img_path)
            if font_img.mode != "RGB":
                raise ValueError("Unsupported image mode: " + font_img.mode)
        except FileNotFoundError:
            logger.warning(
                f"Couldn't load font '{font_name}': {font_name}.png not found."
            )
            continue

        # load the font json
        font_json_path = os.path.join(fonts_folder, font_name, font_name + ".json")
        try:
            with open(font_json_path, "r") as json_file:
                font_json = json.load(json_file)
        except FileNotFoundError:
            logger.warning(
                f"Couldn't load font '{font_name}': {font_name}.json not found."
            )
            continue
        nb_loaded_fonts += 1
        font_files[font_name] = {"image": font_img, "json": font_json}

    logger.debug(f"{nb_loaded_fonts}/{nb_fonts} Fonts loaded.")
    return font_files


font_files = load_font_images()


class FontNotFound(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class FontManager:
    """Class to manage a font"""

    def __init__(self, font_name, font_color=None, background_color=None) -> None:
        self.font_name = font_name
        self.image = self.get_image()
        self.json = self.get_json()

        self.image_background_color = self.json["background"]
        self.image_background_color = list(self.image_background_color)
        self.image_background_color.append(255)
        self.image = self.image.convert("RGBA")

        self.max_width = self.json["width"]
        self.max_height = self.json["height"]

        self.set_font_color(font_color)
        self.set_background_color(background_color)

        if self.font_color:
            if self.font_color == self.background_color:
                raise ValueError("The font color and background color can't be the same.")

    def set_font_color(self, font_color):
        if not font_color:
            self.font_color = None
            return
        font_color = list(font_color)
        if len(font_color) != 4:
            font_color.append(255)
        self.font_color = font_color

    def set_background_color(self, background_color):
        if not background_color:
            self.background_color = self.image_background_color
            return
        background_color = list(background_color)
        if len(background_color) != 4:
            background_color.append(255)
        self.background_color = background_color

    def get_image(self):
        files = font_files.get(self.font_name)
        if files is None:
            raise FontNotFound(f"Font '{self.font_name}' was not found.")
        image = files.get("image")
        if image is None:
            raise FontNotFound(f"Font '{self.font_name}' was not found.")
        return image

    def get_json(self):
        files = font_files.get(self.font_name)
        if files is None:
            raise FontNotFound(f"Font '{self.font_name}' was not found.")
        json = files.get("json")
        if json is None:
            raise FontNotFound(f"Font '{self.font_name}' was not found.")
        return json

    def char_exists(self, char):
        try:
            self.json[char]
            return True
        except KeyError:
            return None

    def get_char_array(self, char):
        """return a numpy array of the character pixels
        or None if the character isn't in the font"""
        try:
            char_coords = self.json[char]
        except KeyError:
            return None

        x0 = char_coords[0]
        y0 = char_coords[1]
        max_x = char_coords[2]
        max_y = char_coords[3]

        array = np.zeros((self.max_height, max_x, 4), dtype=np.uint8)
        array[:, :] = self.background_color
        for y in range(max_y):
            for x in range(max_x):
                pixel_color = self.image.getpixel((x0 + x, y0 + y))
                if list(pixel_color) != self.image_background_color:
                    if self.font_color:
                        array[y, x] = list(self.font_color)
                    else:
                        array[y, x] = list(pixel_color)
                else:
                    array[y, x] = list(self.background_color)

        return array


class PixelText:
    """Class to make a pixel text"""

    def __init__(self, text, font_name, font_color=None, background_color=None) -> None:
        self.text = text
        self.font = FontManager(font_name, font_color, background_color)
        self.background_color = self.font.background_color
        self.font_color = self.font.font_color

        self.image_array = []

    def make_array(self, accept_empty=False):
        """Change the self.array object to have the numpy array of the text
        by concatenating numpy arrays of each characters"""
        self.image_array = np.zeros((self.font.max_height, 1, 4), dtype=np.uint8)
        self.image_array[:, :] = self.background_color or [255, 255, 255, 255]

        empty = True
        for char in self.text:
            font_char = self.get_char(char)
            if font_char is not None:
                empty = False
                char_array = self.font.get_char_array(font_char)
                self.image_array = np.concatenate((self.image_array, char_array), axis=1)
                self.add_space()

            elif char == " ":
                self.add_space(SPACE_WIDTH)

            elif char == "\t":
                self.add_space(2 * 4)

            elif char == ".":
                empty = False
                self.add_dot()
                self.add_space()

        if empty and not accept_empty:
            return None
        else:
            return self.image_array

    def get_image(self):
        """Create an image of the class text,
        the image is made by converting the generated numpy array to PIL Image"""
        if self.make_array() is None:
            return None
        # remove excessive space around chars
        while (self.image_array[0, :] == self.background_color).all():
            self.image_array = np.delete(self.image_array, 0, 0)
        while (self.image_array[-1, :] == self.background_color).all():
            self.image_array = np.delete(self.image_array, -1, 0)

        # add an outline at the top and bottom
        if not (self.image_array[0, :] == self.background_color).all():
            self.add_top_line()

        if not (self.image_array[-1, :] == self.background_color).all():
            self.add_bottom_line()

        im = Image.fromarray(self.image_array)
        return im

    def get_char(self, char, from_case=False):

        if char is None:
            return None
        # if the char is valid, we return it
        res = self.font.char_exists(char)
        if res:
            return char

        # check on accent
        if char in all_accents:
            for key in letter_bases:
                if char in key:
                    letter_base = letter_bases[key]
                    return self.get_char(letter_base)

        # check on case
        if not from_case:  # to avoid infinite recursion
            if char.isupper():
                return self.get_char(char.lower(), True)
            if char.islower():
                return self.get_char(char.upper(), True)
        else:
            return None

    def add_space(self, width=1):
        space = np.zeros((self.font.max_height, 1, 4), dtype=np.uint8)
        space[:, :] = self.background_color
        for i in range(width):
            self.image_array = np.concatenate((self.image_array, space), axis=1)

    def add_bottom_line(self):
        space = np.zeros((1, self.image_array.shape[1], 4), dtype=np.uint8)
        space[:, :] = self.background_color
        self.image_array = np.concatenate((self.image_array, space), axis=0)

    def add_top_line(self):
        space = np.zeros((1, self.image_array.shape[1], 4), dtype=np.uint8)
        space[:, :] = self.background_color
        self.image_array = np.concatenate((space, self.image_array), axis=0)

    def add_dot(self):
        dot_array = np.zeros(
            (self.font.max_height, self.font.max_width // 3, 4), dtype=np.uint8
        )
        dot_array[:, :] = self.background_color
        for i in range(1, (self.font.max_width // 3) + 1):
            dot_array[-i, :] = self.font_color or [255, 255, 255, 255]
        self.image_array = np.concatenate((self.image_array, dot_array), axis=1)


def get_all_fonts():
    """Return a list with all the available fonts"""
    return list(font_files.keys())


def get_allowed_fonts():
    """Return a list with all the fonts 'allowed' to make tables"""
    return [f for f in get_all_fonts() if f in ALLOWED_FONTS]
