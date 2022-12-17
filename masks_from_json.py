# coding=utf-8
# Copyright 2021 UNT Geography.
#
# Wrote by George Mihaila: georgemihaila@my.unt.edu
"""
Read image masks from Label-Studio json labels. This can be ran as a script or as a package file.

Example running script:
$ python irrigation/data/masks_from_json.py \
                            --json data/json_labels/AR_121.json \
                            --path ./

"""
import json
import numpy as np
from PIL import Image, ImageDraw
import argparse
import os
import glob

# Label encoder.
LABEL_ENCODER = {
    'u': 1,
    'c': 2,
    's': 3,
    'p': 4,
    'z': 5,
    'f': 6
}


def percent_to_coordinates(use_points, use_with, use_height, scale=0.01):
    """
    Label-Studio uses % coordinates. Need to convert them in raw coordinates.
    """
    # Make sure points format is correct.
    if isinstance(use_points, list) and all([isinstance(point, list) for point in use_points]) and all(
            [isinstance(point[0], (int, float)) and isinstance(point[1], (int, float)) for point in use_points]):
        return [[use_with * point[0] * scale, use_height * point[1] * scale] for point in use_points]
    else:
        raise ValueError("Points '{}' is not correct format of list(list)".format(use_points))


def get_shapes_array(json_data, line_color=None, fill_color=None):
    """
  Get shapes from json data.
  """
    return [[result['value']['polygonlabels'][0],
             percent_to_coordinates(result['value']['points'], result['original_width'],
                                    result['original_height']),
             line_color,
             fill_color,
             ]
            for result in json_data['annotations'][0]['result']]


def json_to_mask(name):
    """
    Read image polygons from json.

    Args:
        name: Path + json file name to be used.

    Returns:
        numpy array of mask.
    """
    # Read json file.
    with open(name, "rb") as f:
        label_data = json.load(f)
    # Get image shapes.
    shapes = get_shapes_array(json_data=label_data[0])
    n_x = 5000
    n_y = 5000
    array = np.zeros((n_x, n_y), dtype=np.uint8)
    img_mask = Image.fromarray(array, mode='L')
    draw = ImageDraw.Draw(img_mask)

    polygon_coordinates = []

    for ploygon in shapes:
        Coordinates = ploygon[1]
        polygon_coordinates.append(Coordinates)
        xy_list = []
        for xy_pair in Coordinates:
            xy_list.append(xy_pair[0])
            xy_list.append(xy_pair[1])
        xy_list = tuple(xy_list)
        if ploygon[0] == "Copy of z":
            code = LABEL_ENCODER['z']
        else: 
            code = LABEL_ENCODER[ploygon[0]]
        #if code == LABEL_ENCODER['c']:
            
        draw.polygon(xy_list, code, code)

    img_mask = np.array(img_mask.getdata()).reshape(img_mask.size[0], img_mask.size[1])
    return img_mask


def parse_args() -> argparse.ArgumentParser:
    """
    Parsing input script arguments.
    Returns:
        argparse.ArgumentParser: Parsed arguments.
    """

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Convert json file in compressed .npz format.",
    )
    parser.add_argument(
        "--json",
        help="Json file form Label-Studio format.",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--path",
        help="Path to save numpy. If set to 'None' it will save in current path.",
        required=False,
        default="./",
        type=str,
    )


    return parser.parse_args()


def main():
    """
    Main function.
    """
    # Parse arguments.
    for file in glob.glob('/Volumes/Research/CropContour/JSON Files/*.json'):

        print("Running for '{}' file!".format(file))
        mask_numpy = json_to_mask(name=file)

        # Get file name without extension.
        filename = os.path.splitext(os.path.basename(file))[0]

        # Get npz path and filename
        maskpath = os.path.join('/Volumes/Research/CropContour/UnfilteredJsonMasks', "{}.npz".format(filename))

        # Save to npz.
        np.savez_compressed(file=maskpath, mask=mask_numpy)
        print("Mask was saved as npz in '{}' file!".format(maskpath))

        # If you want to load numpy back.
        # loaded_mask = np.load(file='path/to/file.npz')['mask']


if __name__ == "__main__":
    print("Program started!")
    main()
    print("Program finished!")
