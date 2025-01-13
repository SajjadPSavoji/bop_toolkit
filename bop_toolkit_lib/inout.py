# Author: Tomas Hodan (hodantom@cmp.felk.cvut.cz)
# Center for Machine Perception, Czech Technical University in Prague

"""I/O functions."""

import os
import gzip
import struct
import cv2
import numpy as np
import imageio
import png
import json
from collections import defaultdict

from bop_toolkit_lib import misc


def load_im(path, convert_hdr=True):
    """Loads an image from a file.

    :param path: Path to the image file to load.
    :param convert_hdr (bool): 
        Whether to convert HDR images to LDR. Defaults to True.
        If False, HDR images will be returned as is.
        https://github.com/carynbear/ipd/blob/02eb1ad1e66e3a48324c48b4cca563a551dc6771/src/intrinsic_ipd/reader.py#L460
    :return: ndarray with the loaded image.
    """
    if not os.path.exists(path):
        raise ValueError(f"{path} does not exist.")
    if convert_hdr:
        # From       
        im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if len(im.shape)==2:
            im = cv2.cvtColor(im, cv2.COLOR_GRAY2RGB)
        else:
            im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        
        if np.max(im) > 255:
            # Convert HDR to LDR
            gamma = 2.2
            tonemap = cv2.createTonemap(gamma)
            im = tonemap.process(im.astype(np.float32))
            im = cv2.normalize(im, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype=cv2.CV_8UC1)
    else:
        im = imageio.imread(path)

    return im


def save_im(path, im, jpg_quality=95):
    """Saves an image to a file.

    :param path: Path to the output image file.
    :param im: ndarray with the image to save.
    :param jpg_quality: Quality of the saved image (applies only to JPEG).
    """
    ext = os.path.splitext(path)[1][1:]
    if ext.lower() in ["jpg", "jpeg"]:
        imageio.imwrite(path, im, quality=jpg_quality)
    else:
        imageio.imwrite(path, im, compression=3)


def load_depth(path):
    """Loads a depth image from a file.

    :param path: Path to the depth image file to load.
    :return: ndarray with the loaded depth image.
    """
    d = imageio.imread(path)
    return d.astype(np.float32)


def save_depth(path, im):
    """Saves a depth image (16-bit) to a PNG file.

    :param path: Path to the output depth image file.
    :param im: ndarray with the depth image to save.
    """
    if path.split(".")[-1].lower() != "png":
        raise ValueError("Only PNG format is currently supported.")

    im_uint16 = np.round(im).astype(np.uint16)

    # PyPNG library can save 16-bit PNG and is faster than imageio.imwrite().
    w_depth = png.Writer(im.shape[1], im.shape[0], greyscale=True, bitdepth=16)
    with open(path, "wb") as f:
        w_depth.write(f, np.reshape(im_uint16, (-1, im.shape[1])))


def load_json(path, keys_to_int=False):
    """Loads content of a JSON file.

    :param path: Path to the JSON file. If ".json.gz" extension, opens with gzip.
    :return: Content of the loaded JSON file.
    """

    # Keys to integers.
    def convert_keys_to_int(x):
        return {int(k) if k.lstrip("-").isdigit() else k: v for k, v in x.items()}
    
    # Open+decompress with gzip if ".json.gz" file extension
    if path.endswith('.json.gz'):
        f = gzip.open(path, "rt", encoding="utf8")
    else:
        f = open(path, "r")
    if keys_to_int:
        content = json.load(f, object_hook=lambda x: convert_keys_to_int(x))
    else:
        content = json.load(f)

    f.close()

    return content


def save_json(path, content, compress=False):
    """Saves the provided content to a JSON file.

    :param path: Path to the output JSON file.
    :param content: Dictionary/list to save.
    :param compress: Saves as a gzip archive, appends ".gz" extension to filepath.
    """
    if compress:
        path += ".gz"
        f = gzip.open(path, "wt", encoding="utf8")
    else:
        f = open(path, "w")

    if isinstance(content, dict):
        f.write("{\n")
        content_sorted = sorted(content.items(), key=lambda x: x[0])
        for elem_id, (k, v) in enumerate(content_sorted):
            f.write('  "{}": {}'.format(k, json.dumps(v, sort_keys=True)))
            if elem_id != len(content) - 1:
                f.write(",")
            f.write("\n")
        f.write("}")

    elif isinstance(content, list):
        f.write("[\n")
        for elem_id, elem in enumerate(content):
            f.write("  {}".format(json.dumps(elem, sort_keys=True)))
            if elem_id != len(content) - 1:
                f.write(",")
            f.write("\n")
        f.write("]")

    else:
        json.dump(content, f, sort_keys=True)

    f.close()


def load_cam_params(path):
    """Loads camera parameters from a JSON file.

    :param path: Path to the JSON file.
    :return: Dictionary with the following items:
     - 'im_size': (width, height).
     - 'K': 3x3 intrinsic camera matrix.
     - 'depth_scale': Scale factor to convert the depth images to mm (optional).
    """
    c = load_json(path)

    cam = {
        "im_size": (c["width"], c["height"]),
        "K": np.array(
            [[c["fx"], 0.0, c["cx"]], [0.0, c["fy"], c["cy"]], [0.0, 0.0, 1.0]]
        ),
    }

    if "depth_scale" in c.keys():
        cam["depth_scale"] = float(c["depth_scale"])

    return cam


def _camera_as_numpy(camera):
    """Convert fields from scene camera from native python to numpy.

    See docs/bop_datasets_format.md for details.
    Note: "cam_K" and "cam_model" are mutually exclusive and raise a ValueError.

    :param camera: Dictionnary containing
    - 'cam_R_w2c': orientation of world frame in camera frame
    - 'cam_t_w2c': position of world frame in camera frame
    - 'cam_K': IF BOP19 format, camera pinhole intrinsics parameters
    - 'cam_model': IF BOP24 format
    :return: Dictionnary with same keys and flat lists field as numpy arrays 
    """
    if "cam_K" in camera and "cam_model" in camera:
        raise ValueError("Only one of 'cam_K', 'cam_model' field should be present in a scene camera configuration")
    if "cam_K" in camera.keys():
        camera["cam_K"] = np.array(camera["cam_K"], np.float64).reshape((3, 3))
    if "cam_R_w2c" in camera.keys():
        camera["cam_R_w2c"] = np.array(camera["cam_R_w2c"], np.float64).reshape((3, 3))
    if "cam_t_w2c" in camera.keys():
        camera["cam_t_w2c"] = np.array(camera["cam_t_w2c"], np.float64).reshape((3, 1))
    if "cam_model" in camera:
        camera["cam_model"]["projection_params"] = np.array(camera["cam_model"]["projection_params"], np.float64)
    return camera


def _camera_as_json(camera):
    """Convert fields from scene camera from numpy to native python.

    See docs/bop_datasets_format.md for details.
    Note: "cam_K" and "cam_model" are mutually exclusive and raise a ValueError.

    :param camera: Dictionnary containing
    - 'cam_R_w2c': orientation of world frame in camera frame
    - 'cam_t_w2c': position of world frame in camera frame
    - 'cam_K': IF BOP19 format, camera pinhole intrinsics parameters
    - 'cam_model': IF BOP24 format
    :return: Dictionnary with same keys and numpy arrays field as flat lists 
    """
    if "cam_K" in camera and "cam_model" in camera:
        raise ValueError("Only one of 'cam_K', 'cam_model' field should be present in a scene camera configuration")
    if "cam_K" in camera.keys():
        camera["cam_K"] = camera["cam_K"].flatten().tolist()
    if "cam_R_w2c" in camera.keys():
        camera["cam_R_w2c"] = camera["cam_R_w2c"].flatten().tolist()
    if "cam_t_w2c" in camera.keys():
        camera["cam_t_w2c"] = camera["cam_t_w2c"].flatten().tolist()
    if "cam_model" in camera:
        camera["cam_model"]["projection_params"] = camera["cam_model"]["projection_params"].flatten().tolist() 
    return camera


def load_scene_camera(path):
    """Loads content of a JSON file with information about the scene camera.

    See docs/bop_datasets_format.md for details.

    :param path: Path to the JSON file.
    :return: Dictionary with the loaded content.
    """
    scene_camera = load_json(path, keys_to_int=True)

    for im_id in scene_camera.keys():
        scene_camera[im_id] = _camera_as_numpy(scene_camera[im_id])
    return scene_camera


def save_scene_camera(path, scene_camera):
    """Saves information about the scene camera to a JSON file.

    See docs/bop_datasets_format.md for details.

    :param path: Path to the output JSON file.
    :param scene_camera: Dictionary to save to the JSON file.
    """
    for im_id in sorted(scene_camera.keys()):
        scene_camera[im_id] = _camera_as_json(scene_camera[im_id])
    save_json(path, scene_camera)


def _gt_as_numpy(gt):
    if "cam_R_m2c" in gt.keys():
        gt["cam_R_m2c"] = np.array(gt["cam_R_m2c"], np.float64).reshape((3, 3))
    if "cam_t_m2c" in gt.keys():
        gt["cam_t_m2c"] = np.array(gt["cam_t_m2c"], np.float64).reshape((3, 1))
    return gt


def _gt_as_json(gt):
    if "cam_R_m2c" in gt.keys():
        gt["cam_R_m2c"] = gt["cam_R_m2c"].flatten().tolist()
    if "cam_t_m2c" in gt.keys():
        gt["cam_t_m2c"] = gt["cam_t_m2c"].flatten().tolist()
    if "obj_bb" in gt.keys():
        gt["obj_bb"] = [int(x) for x in gt["obj_bb"]]
    return gt


def load_scene_gt(path):
    """Loads content of a JSON file with ground-truth annotations.

    See docs/bop_datasets_format.md for details.

    :param path: Path to the JSON file.
    :return: Dictionary with the loaded content.
    """
    scene_gt = load_json(path, keys_to_int=True)

    for im_id, im_gt in scene_gt.items():
        for gt in im_gt:
            if "cam_R_m2c" in gt.keys():
                gt["cam_R_m2c"] = np.array(gt["cam_R_m2c"], np.float64).reshape((3, 3))
            if "cam_t_m2c" in gt.keys():
                gt["cam_t_m2c"] = np.array(gt["cam_t_m2c"], np.float64).reshape((3, 1))
    return scene_gt


def save_scene_gt(path, scene_gt):
    """Saves ground-truth annotations to a JSON file.

    See docs/bop_datasets_format.md for details.

    :param path: Path to the output JSON file.
    :param scene_gt: Dictionary to save to the JSON file.
    """
    for im_id in sorted(scene_gt.keys()):
        im_gts = scene_gt[im_id]
        for gt in im_gts:
            if "cam_R_m2c" in gt.keys():
                gt["cam_R_m2c"] = gt["cam_R_m2c"].flatten().tolist()
            if "cam_t_m2c" in gt.keys():
                gt["cam_t_m2c"] = gt["cam_t_m2c"].flatten().tolist()
            if "obj_bb" in gt.keys():
                gt["obj_bb"] = [int(x) for x in gt["obj_bb"]]
    save_json(path, scene_gt)


def load_bop_results(path, version="bop19", max_num_estimates_per_image=None):
    """Loads 6D object pose estimates from a file.

    :param path: Path to a file with pose estimates.
    :param version: Version of the results.
    :return: List of loaded poses.
    """
    results = []

    # See docs/bop_challenge_2019.md for details.
    if version == "bop19":
        header = "scene_id,im_id,obj_id,score,R,t,time"
        with open(path, "r") as f:
            line_id = 0
            for line in f:
                line_id += 1
                if line_id == 1 and header in line:
                    continue
                else:
                    elems = line.split(",")
                    if len(elems) != 7:
                        raise ValueError(
                            "A line does not have 7 comma-sep. elements: {}".format(
                                line
                            )
                        )

                    result = {
                        "scene_id": int(elems[0]),
                        "im_id": int(elems[1]),
                        "obj_id": int(elems[2]),
                        "score": float(elems[3]),
                        "R": np.array(
                            list(map(float, elems[4].split())), np.float64
                        ).reshape((3, 3)),
                        "t": np.array(
                            list(map(float, elems[5].split())), np.float64
                        ).reshape((3, 1)),
                        "time": float(elems[6]),
                    }

                    results.append(result)
    else:
        raise ValueError("Unknown version of BOP results.")

    # Keep only the top max_num_estimates_per_image estimates for each image.
    if max_num_estimates_per_image is not None:
        # Group the results by image
        im_results = defaultdict(list)
        for res in results:
            im_signature = (res["scene_id"], res["im_id"])
            im_results[im_signature].append(res)
        # Keep only the top n_top estimates for each image
        filtered_results = []
        num_ignored_estimates = 0
        for im_signature in im_results.keys():
            im_results[im_signature] = sorted(
                im_results[im_signature], key=lambda x:x["score"], reverse=True
            )
            num_ignored_estimates += max(0, len(im_results[im_signature]) - max_num_estimates_per_image)
            filtered_results.extend(im_results[im_signature][:max_num_estimates_per_image])
        results = filtered_results
        misc.log("Ignored {} estimates.".format(num_ignored_estimates))
    return results


def save_bop_results(path, results, version="bop19"):
    """Saves 6D object pose estimates to a file.

    :param path: Path to the output file.
    :param results: Dictionary with pose estimates.
    :param version: Version of the results.
    """
    # See docs/bop_challenge_2019.md for details.
    if version == "bop19":
        lines = ["scene_id,im_id,obj_id,score,R,t,time"]
        for res in results:
            if "time" in res:
                run_time = res["time"]
            else:
                run_time = -1

            lines.append(
                "{scene_id},{im_id},{obj_id},{score},{R},{t},{time}".format(
                    scene_id=res["scene_id"],
                    im_id=res["im_id"],
                    obj_id=res["obj_id"],
                    score=res["score"],
                    R=" ".join(map(str, res["R"].flatten().tolist())),
                    t=" ".join(map(str, res["t"].flatten().tolist())),
                    time=run_time,
                )
            )

        with open(path, "w") as f:
            f.write("\n".join(lines))

    else:
        raise ValueError("Unknown version of BOP results.")


def check_bop_results(path, version="bop19"):
    """Checks if the format of BOP results is correct.

    :param result_filenames: Path to a file with pose estimates.
    :param version: Version of the results.
    :return: True if the format is correct, False if it is not correct.
    """
    check_passed = True
    check_msg = "OK"
    try:
        results = load_bop_results(path, version)

        if version == "bop19":
            # Check if the time for all estimates from the same image are the same.
            times = {}
            for result in results:
                result_key = "{:06d}_{:06d}".format(result["scene_id"], result["im_id"])
                if result_key in times:
                    if abs(times[result_key] - result["time"]) > 0.001:
                        check_passed = False
                        check_msg = (
                            "The running time for scene {} and image {} is not the same for"
                            " all estimates.".format(
                                result["scene_id"], result["im_id"]
                            )
                        )
                        misc.log(check_msg)
                        break
                else:
                    times[result_key] = result["time"]

    except Exception as e:
        check_passed = False
        check_msg = "Error when loading BOP results: {}".format(e)
        misc.log(check_msg)

    return check_passed, check_msg


def check_coco_results(path, version="bop22", ann_type="segm", enforce_no_segm_if_bbox=False):
    """Checks if the format of extended COCO results is correct.

    :param path: Path to a file with coco estimates. If ".json.gz" extension, opens with gzip.
    :param version: Version of the results.
    :param ann_type: type of annotation expected in the file.
        "bbox" -> bounding boxes
        "segm" -> segmentation mask
    :param enforce_no_segm_if_bbox: prevent the presence of segmentation mask in the file if ann_type is "bbox"
    :return: True if the format is correct, False if it is not correct.
    """

    misc.log("Checking coco result format...")
    check_passed = True
    check_msg = "OK"
    try:
        results = load_json(path, keys_to_int=True)
    except Exception as e:
        check_passed = False
        check_msg = "Error when loading COCO results: {}".format(e)
        misc.log(check_msg)
        raise

    if version == "bop22":
        try:
            for result in results:
                assert "scene_id" in result, "scene_id key missing"
                assert "image_id" in result, "image_id key missing"
                assert "category_id" in result, "category_id key missing"
                assert "score" in result, "score key missing"
                assert isinstance(result["scene_id"], int)
                assert isinstance(result["image_id"], int)
                assert isinstance(result["category_id"], int)
                assert isinstance(result["score"], float)
                if enforce_no_segm_if_bbox:
                    assert not (ann_type == "bbox" and "segmentation" in result), \
                           "'segmentation' key should not be present in coco result file for 2D detection annotation ('bbox' annotation type)"
                if "bbox" in result:
                    assert isinstance(result["bbox"], list)
                if "segmentation" in result and ann_type == "segm":
                    assert isinstance(
                        result["segmentation"], dict
                    ), "Segmentation not in RLE format!"
                    assert "counts" in result["segmentation"], "Incorrect RLE format!"
                    assert "size" in result["segmentation"], "Incorrect RLE format!"
                if "time" in result:
                    assert isinstance(result["time"], (float, int))
        except AssertionError as msg:
            check_msg = "Error when checking keys and types: {}".format(msg)
            check_passed = False
            misc.log(check_msg)
    return check_passed, check_msg


def save_coco_results(path, results, version="bop22", compress=False):
    """Saves detections/instance segmentations for each scene in coco format.

    "bbox" should be [x,y,w,h] in pixels
    "segmentation" should be an RLE encoded mask, use pycoco_utils.binary_mask_to_rle(binary_mask)

    :param path: Path to the output file.
    :param results: Dictionary with detection results
    :param version: Version of the results.
    """

    if version == "bop22":
        coco_results = []
        for res in results:
            coco_results.append(
                {
                    "scene_id": res["scene_id"],
                    "image_id": res["im_id"],
                    "category_id": res["obj_id"],
                    "score": res["score"],
                    "bbox": list(res["bbox"]) if "bbox" in res else [],
                    "segmentation": res["segmentation"]
                    if "segmentation" in res
                    else {},
                    "time": res["run_time"] if "run_time" in res else -1,
                }
            )
        save_json(path, coco_results, compress)
    else:
        raise ValueError("Unknown version of BOP detection results.")


def load_ply(path):
    """Loads a 3D mesh model from a PLY file.

    :param path: Path to a PLY file.
    :return: The loaded model given by a dictionary with items:
     - 'pts' (nx3 ndarray)
     - 'normals' (nx3 ndarray), optional
     - 'colors' (nx3 ndarray), optional
     - 'faces' (mx3 ndarray), optional
     - 'texture_uv' (nx2 ndarray), optional
     - 'texture_uv_face' (mx6 ndarray), optional
     - 'texture_file' (string), optional
    """
    f = open(path, "rb")

    # Only triangular faces are supported.
    face_n_corners = 3

    n_pts = 0
    n_faces = 0
    pt_props = []
    face_props = []
    is_binary = False
    header_vertex_section = False
    header_face_section = False
    texture_file = None

    # Read the header.
    while True:
        # Strip the newline character(s).
        line = f.readline().decode("utf8").rstrip("\n").rstrip("\r")

        if line.startswith("comment TextureFile"):
            texture_file = line.split()[-1]
        elif line.startswith("element vertex"):
            n_pts = int(line.split()[-1])
            header_vertex_section = True
            header_face_section = False
        elif line.startswith("element face"):
            n_faces = int(line.split()[-1])
            header_vertex_section = False
            header_face_section = True
        elif line.startswith("element"):  # Some other element.
            header_vertex_section = False
            header_face_section = False
        elif line.startswith("property") and header_vertex_section:
            # (name of the property, data type)
            pt_props.append((line.split()[-1], line.split()[-2]))
        elif line.startswith("property list") and header_face_section:
            elems = line.split()
            if elems[-1] == "vertex_indices" or elems[-1] == "vertex_index":
                # (name of the property, data type)
                face_props.append(("n_corners", elems[2]))
                for i in range(face_n_corners):
                    face_props.append(("ind_" + str(i), elems[3]))
            elif elems[-1] == "texcoord":
                # (name of the property, data type)
                face_props.append(("texcoord", elems[2]))
                for i in range(face_n_corners * 2):
                    face_props.append(("texcoord_ind_" + str(i), elems[3]))
            else:
                misc.log("Warning: Not supported face property: " + elems[-1])
        elif line.startswith("format"):
            if "binary" in line:
                is_binary = True
        elif line.startswith("end_header"):
            break

    # Prepare data structures.
    model = {}
    if texture_file is not None:
        model["texture_file"] = texture_file
    model["pts"] = np.zeros((n_pts, 3), np.float64)
    if n_faces > 0:
        model["faces"] = np.zeros((n_faces, face_n_corners), np.float64)

    pt_props_names = [p[0] for p in pt_props]
    face_props_names = [p[0] for p in face_props]

    is_normal = False
    if {"nx", "ny", "nz"}.issubset(set(pt_props_names)):
        is_normal = True
        model["normals"] = np.zeros((n_pts, 3), np.float64)

    is_color = False
    if {"red", "green", "blue"}.issubset(set(pt_props_names)):
        is_color = True
        model["colors"] = np.zeros((n_pts, 3), np.float64)

    is_texture_pt = False
    if {"texture_u", "texture_v"}.issubset(set(pt_props_names)):
        is_texture_pt = True
        model["texture_uv"] = np.zeros((n_pts, 2), np.float64)

    is_texture_face = False
    if {"texcoord"}.issubset(set(face_props_names)):
        is_texture_face = True
        model["texture_uv_face"] = np.zeros((n_faces, 6), np.float64)

    # Formats for the binary case.
    formats = {
        "float": ("f", 4),
        "double": ("d", 8),
        "int": ("i", 4),
        "uint": ("I", 4),
        "uchar": ("B", 1),
    }

    # Load vertices.
    for pt_id in range(n_pts):
        prop_vals = {}
        load_props = [
            "x",
            "y",
            "z",
            "nx",
            "ny",
            "nz",
            "red",
            "green",
            "blue",
            "texture_u",
            "texture_v",
        ]
        if is_binary:
            for prop in pt_props:
                format = formats[prop[1]]
                read_data = f.read(format[1])
                val = struct.unpack(format[0], read_data)[0]
                if prop[0] in load_props:
                    prop_vals[prop[0]] = val
        else:
            elems = f.readline().decode("utf8").rstrip("\n").rstrip("\r").split()
            for prop_id, prop in enumerate(pt_props):
                if prop[0] in load_props:
                    prop_vals[prop[0]] = elems[prop_id]

        model["pts"][pt_id, 0] = float(prop_vals["x"])
        model["pts"][pt_id, 1] = float(prop_vals["y"])
        model["pts"][pt_id, 2] = float(prop_vals["z"])

        if is_normal:
            model["normals"][pt_id, 0] = float(prop_vals["nx"])
            model["normals"][pt_id, 1] = float(prop_vals["ny"])
            model["normals"][pt_id, 2] = float(prop_vals["nz"])

        if is_color:
            model["colors"][pt_id, 0] = float(prop_vals["red"])
            model["colors"][pt_id, 1] = float(prop_vals["green"])
            model["colors"][pt_id, 2] = float(prop_vals["blue"])

        if is_texture_pt:
            model["texture_uv"][pt_id, 0] = float(prop_vals["texture_u"])
            model["texture_uv"][pt_id, 1] = float(prop_vals["texture_v"])

    # Load faces.
    for face_id in range(n_faces):
        prop_vals = {}
        if is_binary:
            for prop in face_props:
                format = formats[prop[1]]
                val = struct.unpack(format[0], f.read(format[1]))[0]
                if prop[0] == "n_corners":
                    if val != face_n_corners:
                        raise ValueError("Only triangular faces are supported.")
                elif prop[0] == "texcoord":
                    if val != face_n_corners * 2:
                        raise ValueError("Wrong number of UV face coordinates.")
                else:
                    prop_vals[prop[0]] = val
        else:
            elems = f.readline().decode("utf8").rstrip("\n").rstrip("\r").split()
            for prop_id, prop in enumerate(face_props):
                if prop[0] == "n_corners":
                    if int(elems[prop_id]) != face_n_corners:
                        raise ValueError("Only triangular faces are supported.")
                elif prop[0] == "texcoord":
                    if int(elems[prop_id]) != face_n_corners * 2:
                        raise ValueError("Wrong number of UV face coordinates.")
                else:
                    prop_vals[prop[0]] = elems[prop_id]

        model["faces"][face_id, 0] = int(prop_vals["ind_0"])
        model["faces"][face_id, 1] = int(prop_vals["ind_1"])
        model["faces"][face_id, 2] = int(prop_vals["ind_2"])

        if is_texture_face:
            for i in range(6):
                model["texture_uv_face"][face_id, i] = float(
                    prop_vals["texcoord_ind_{}".format(i)]
                )

    f.close()

    return model


def save_ply(path, model, extra_header_comments=None):
    """Saves a 3D mesh model to a PLY file.

    :param path: Path to a PLY file.
    :param model: 3D model given by a dictionary with items:
     - 'pts' (nx3 ndarray)
     - 'normals' (nx3 ndarray, optional)
     - 'colors' (nx3 ndarray, optional)
     - 'faces' (mx3 ndarray, optional)
     - 'texture_uv' (nx2 ndarray, optional)
     - 'texture_uv_face' (mx6 ndarray, optional)
     - 'texture_file' (string, optional)
    :param extra_header_comments: Extra header comment (optional).
    """
    pts = model["pts"]
    pts_colors = model["colors"] if "colors" in model.keys() else None
    pts_normals = model["normals"] if "normals" in model.keys() else None
    faces = model["faces"] if "faces" in model.keys() else None
    texture_uv = model["texture_uv"] if "texture_uv" in model.keys() else None
    texture_uv_face = (
        model["texture_uv_face"] if "texture_uv_face" in model.keys() else None
    )
    texture_file = model["texture_file"] if "texture_file" in model.keys() else None

    save_ply2(
        path,
        pts,
        pts_colors,
        pts_normals,
        faces,
        texture_uv,
        texture_uv_face,
        texture_file,
        extra_header_comments,
    )


def save_ply2(
    path,
    pts,
    pts_colors=None,
    pts_normals=None,
    faces=None,
    texture_uv=None,
    texture_uv_face=None,
    texture_file=None,
    extra_header_comments=None,
):
    """Saves a 3D mesh model to a PLY file.

    :param path: Path to the resulting PLY file.
    :param pts: nx3 ndarray with vertices.
    :param pts_colors: nx3 ndarray with vertex colors (optional).
    :param pts_normals: nx3 ndarray with vertex normals (optional).
    :param faces: mx3 ndarray with mesh faces (optional).
    :param texture_uv: nx2 ndarray with per-vertex UV texture coordinates
      (optional).
    :param texture_uv_face: mx6 ndarray with per-face UV texture coordinates
      (optional).
    :param texture_file: Path to a texture image -- relative to the resulting
      PLY file (optional).
    :param extra_header_comments: Extra header comment (optional).
    """
    if pts_colors is not None:
        pts_colors = np.array(pts_colors)
        assert len(pts) == len(pts_colors)

    valid_pts_count = 0
    for pt_id, pt in enumerate(pts):
        if not np.isnan(np.sum(pt)):
            valid_pts_count += 1

    f = open(path, "w")
    f.write(
        "ply\n"
        "format ascii 1.0\n"
        # 'format binary_little_endian 1.0\n'
    )

    if texture_file is not None:
        f.write("comment TextureFile {}\n".format(texture_file))

    if extra_header_comments is not None:
        for comment in extra_header_comments:
            f.write("comment {}\n".format(comment))

    f.write(
        "element vertex " + str(valid_pts_count) + "\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
    )
    if pts_normals is not None:
        f.write("property float nx\n" "property float ny\n" "property float nz\n")
    if pts_colors is not None:
        f.write("property uchar red\n" "property uchar green\n" "property uchar blue\n")
    if texture_uv is not None:
        f.write("property float texture_u\n" "property float texture_v\n")
    if faces is not None:
        f.write(
            "element face " + str(len(faces)) + "\n"
            "property list uchar int vertex_indices\n"
        )
    if texture_uv_face is not None:
        f.write("property list uchar float texcoord\n")
    f.write("end_header\n")

    format_float = "{:.4f}"
    format_2float = " ".join((format_float for _ in range(2)))
    format_3float = " ".join((format_float for _ in range(3)))
    format_int = "{:d}"
    format_3int = " ".join((format_int for _ in range(3)))

    # Save vertices.
    for pt_id, pt in enumerate(pts):
        if not np.isnan(np.sum(pt)):
            f.write(format_3float.format(*pts[pt_id].astype(float)))
            if pts_normals is not None:
                f.write(" ")
                f.write(format_3float.format(*pts_normals[pt_id].astype(float)))
            if pts_colors is not None:
                f.write(" ")
                f.write(format_3int.format(*pts_colors[pt_id].astype(int)))
            if texture_uv is not None:
                f.write(" ")
                f.write(format_2float.format(*texture_uv[pt_id].astype(float)))
            f.write("\n")

    # Save faces.
    if faces is not None:
        for face_id, face in enumerate(faces):
            line = " ".join(map(str, map(int, [len(face)] + list(face.squeeze()))))
            if texture_uv_face is not None:
                uv = texture_uv_face[face_id]
                line += " " + " ".join(
                    map(str, [len(uv)] + list(map(float, list(uv.squeeze()))))
                )
            f.write(line)
            f.write("\n")

    f.close()


def get_im_targets(im_gt, im_gt_info, visib_gt_min, eval_mode="localization"):
    im_targets = {}
    for gt_id, gt in enumerate(im_gt):
        gt_info = im_gt_info[gt_id]
        obj_id = gt["obj_id"]

        # for 6D localization: keep only GT objects having visib_fract > p["visib_gt_min"]
        # for 6D detection: keep all GT objects
        if gt_info["visib_fract"] < visib_gt_min and eval_mode == "localization":
            continue
        
        if obj_id not in im_targets:
            im_targets[obj_id] = {"inst_count": 0}
        im_targets[obj_id]["inst_count"] += 1
    return im_targets
