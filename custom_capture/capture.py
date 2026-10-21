from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mss import mss
from PIL import Image, ImageStat
from PySide6.QtCore import QRect


@dataclass(slots=True)
class _DxOutput:
    camera: object
    left: int
    top: int
    right: int
    bottom: int


@dataclass(slots=True)
class DesktopSnapshot:
    image: Image.Image
    left: int
    top: int

    def crop(self, rect: QRect) -> Image.Image:
        left, top, right, bottom, width, height = _rect_parts(rect)
        crop_box = (
            left - self.left,
            top - self.top,
            right - self.left,
            bottom - self.top,
        )
        return self.image.crop(crop_box).resize((width, height))


_DX_LOCK = threading.RLock()
_DX_OUTPUTS: list[_DxOutput] | None = None
_DX_INIT_FAILED = False
_LAST_GOOD_OUTPUTS: dict[tuple[int, int, int, int], Image.Image] = {}


def make_unique_screenshot_path(save_dir: Path) -> Path:
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = save_dir / f"Screenshot_{timestamp}.png"
    if not base.exists():
        return base

    index = 1
    while True:
        candidate = save_dir / f"Screenshot_{timestamp}_{index}.png"
        if not candidate.exists():
            return candidate
        index += 1


def warm_up_capture_engines() -> None:
    """Create DXGI duplication objects before the overlay changes the screen."""
    try:
        outputs = _get_dx_outputs()
    except Exception:
        return

    for output in outputs:
        _grab_output_image(output)


def grab_desktop_snapshot() -> DesktopSnapshot | None:
    try:
        outputs = _get_dx_outputs()
    except Exception:
        outputs = []

    if outputs:
        left = min(output.left for output in outputs)
        top = min(output.top for output in outputs)
        right = max(output.right for output in outputs)
        bottom = max(output.bottom for output in outputs)
        snapshot = Image.new("RGB", (right - left, bottom - top), "black")
        pasted = 0

        for output in outputs:
            image = _grab_output_image(output)
            if image is None:
                continue
            snapshot.paste(image, (output.left - left, output.top - top))
            pasted += 1

        if pasted:
            return DesktopSnapshot(snapshot, left, top)

    image = _grab_virtual_desktop_mss()
    if image is None:
        return None

    left, top = _mss_virtual_origin()
    return DesktopSnapshot(image, left, top)


def grab_region(rect: QRect) -> Image.Image:
    image = _grab_region_dxcam(rect)
    if image is not None:
        return image

    return _grab_region_mss(rect)


def save_region_from_snapshot(
    snapshot: DesktopSnapshot,
    rect: QRect,
    save_dir: Path,
) -> tuple[Path, Image.Image]:
    image = snapshot.crop(rect)
    output_path = make_unique_screenshot_path(save_dir)
    image.save(output_path, "PNG")
    return output_path, image


def _rect_parts(rect: QRect) -> tuple[int, int, int, int, int, int]:
    left = int(rect.x())
    top = int(rect.y())
    width = max(1, int(rect.width()))
    height = max(1, int(rect.height()))
    return left, top, left + width, top + height, width, height


def _grab_region_dxcam(rect: QRect) -> Image.Image | None:
    left, top, right, bottom, width, height = _rect_parts(rect)
    try:
        outputs = _get_dx_outputs()
    except Exception:
        return None

    if not outputs:
        return None

    result = Image.new("RGB", (width, height), "black")
    covered_pixels = 0

    for output in outputs:
        inter_left = max(left, output.left)
        inter_top = max(top, output.top)
        inter_right = min(right, output.right)
        inter_bottom = min(bottom, output.bottom)

        if inter_right <= inter_left or inter_bottom <= inter_top:
            continue

        local_region = (
            inter_left - output.left,
            inter_top - output.top,
            inter_right - output.left,
            inter_bottom - output.top,
        )

        frame = _grab_dx_frame(output.camera, local_region)
        if frame is None:
            continue

        piece = Image.fromarray(frame)
        result.paste(piece, (inter_left - left, inter_top - top))
        covered_pixels += (inter_right - inter_left) * (inter_bottom - inter_top)

    if covered_pixels <= 0:
        return None

    return result


def _grab_output_image(output: _DxOutput) -> Image.Image | None:
    region = (0, 0, output.right - output.left, output.bottom - output.top)
    output_key = (output.left, output.top, output.right, output.bottom)
    candidates: list[Image.Image] = []

    for _ in range(3):
        frame = _grab_dx_frame(output.camera, region)
        if frame is not None:
            candidates.append(Image.fromarray(frame).copy())
        time.sleep(0.025)

    best = _best_image(candidates)
    if best is not None and not _is_probably_blank(best):
        _LAST_GOOD_OUTPUTS[output_key] = best
        return best

    # Never silently return a previous capture: it could contain an unrelated page.
    fallback = _grab_region_mss(
        QRect(output.left, output.top, output.right - output.left, output.bottom - output.top)
    )
    if not _is_probably_blank(fallback):
        _LAST_GOOD_OUTPUTS[output_key] = fallback
    return fallback


def _grab_dx_frame(camera: object, region: tuple[int, int, int, int]):
    for attempt in range(8):
        try:
            frame = camera.grab(region=region, new_frame_only=(attempt == 0))
        except Exception:
            return None

        if frame is not None:
            return frame

        time.sleep(0.03)

    return None


def _get_dx_outputs() -> list[_DxOutput]:
    global _DX_OUTPUTS, _DX_INIT_FAILED

    with _DX_LOCK:
        if _DX_OUTPUTS is not None:
            return _DX_OUTPUTS
        if _DX_INIT_FAILED:
            return []

        try:
            import dxcam
        except Exception:
            _DX_INIT_FAILED = True
            return []

        outputs: list[_DxOutput] = []

        factory = dxcam.__dict__.get("__factory")
        device_outputs = list(getattr(factory, "outputs", []))

        for device_idx, output_group in enumerate(device_outputs):
            for output_idx in range(len(output_group)):
                try:
                    camera = dxcam.create(
                        device_idx=device_idx,
                        output_idx=output_idx,
                        output_color="RGB",
                        backend="dxgi",
                        processor_backend="numpy",
                    )
                except Exception:
                    continue

                desc = camera._output.desc
                coords = desc.DesktopCoordinates
                outputs.append(
                    _DxOutput(
                        camera=camera,
                        left=int(coords.left),
                        top=int(coords.top),
                        right=int(coords.right),
                        bottom=int(coords.bottom),
                    )
                )

        _DX_OUTPUTS = outputs
        return outputs


def _grab_region_mss(rect: QRect) -> Image.Image:
    left, top, _, _, width, height = _rect_parts(rect)

    with mss() as screen:
        shot = screen.grab(
            {
                "left": left,
                "top": top,
                "width": width,
                "height": height,
            }
        )
        return Image.frombytes("RGB", shot.size, shot.rgb)


def _grab_virtual_desktop_mss() -> Image.Image | None:
    try:
        with mss() as screen:
            monitor = screen.monitors[0]
            shot = screen.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.rgb)
    except Exception:
        return None


def _mss_virtual_origin() -> tuple[int, int]:
    try:
        with mss() as screen:
            monitor = screen.monitors[0]
            return int(monitor["left"]), int(monitor["top"])
    except Exception:
        return 0, 0


def _best_image(images: list[Image.Image]) -> Image.Image | None:
    if not images:
        return None
    return max(images, key=_image_detail_score)


def _image_detail_score(image: Image.Image) -> float:
    sample = image.convert("L")
    sample.thumbnail((320, 320))
    stat = ImageStat.Stat(sample)
    mean = stat.mean[0]
    stddev = stat.stddev[0]
    return stddev + min(mean, 255 - mean) * 0.02


def _is_probably_blank(image: Image.Image) -> bool:
    sample = image.convert("L")
    sample.thumbnail((320, 320))
    stat = ImageStat.Stat(sample)
    mean = stat.mean[0]
    stddev = stat.stddev[0]
    return stddev < 2.0 and (mean > 248 or mean < 7)


def save_region(rect: QRect, save_dir: Path) -> tuple[Path, Image.Image]:
    image = grab_region(rect)
    output_path = make_unique_screenshot_path(save_dir)
    image.save(output_path, "PNG")
    return output_path, image
