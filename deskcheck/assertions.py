"""Assertions, done honestly.

* window-visible: the driver reports this window as foreground.
* screenshot-saved: the file exists and is non-empty.
* pixel-diff: per-pixel tolerance + max-diff-ratio knobs, diff-image
  artifact on failure, and a clear error when the baseline is missing
  (the fix is --update-baselines, which copies the current screenshot
  into place as the accepted baseline — the Playwright accept flow).

Tolerance is 0..1: a pixel differs when its largest RGB channel gap
exceeds tolerance * 255. max_diff_ratio is the largest fraction of
differing pixels still counted as a pass (Playwright-style default 0.01).
"""
from __future__ import annotations

import os
import shutil

from .errors import AssertionFailed
from .pngutil import decode_png, encode_png


class DiffResult:
    def __init__(self, diff_pixels, total_pixels, ratio, passed, diff_path=None):
        self.diff_pixels = diff_pixels
        self.total_pixels = total_pixels
        self.ratio = ratio
        self.passed = passed
        self.diff_path = diff_path


def assert_window_visible(driver, window: str):
    fg = driver.foreground_window()
    if fg != window and not (fg and window in fg):
        raise AssertionFailed(
            f"window-visible failed: expected foreground window '{window}', "
            f"got {fg!r}")
    return True


def assert_screenshot_saved(path: str):
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise AssertionFailed(
            f"screenshot-saved failed: '{path}' is missing or empty")
    return True


def pixel_diff(actual_path: str, baseline_path: str, tolerance: float = 0.0,
               max_diff_ratio: float = 0.01, diff_path: str | None = None) -> DiffResult:
    if not os.path.isfile(baseline_path):
        raise AssertionFailed(
            f"pixel-diff failed: baseline missing: '{baseline_path}'. "
            "Run with --update-baselines to accept the current screenshot "
            "as the baseline, then re-run.")
    aw, ah, arows = decode_png(open(actual_path, "rb").read())
    bw, bh, brows = decode_png(open(baseline_path, "rb").read())
    if (aw, ah) != (bw, bh):
        raise AssertionFailed(
            f"pixel-diff failed: size mismatch actual {aw}x{ah} vs "
            f"baseline {bw}x{bh}")
    thresh = tolerance * 255.0
    diff_pixels, diff_rows = 0, []
    for y in range(ah):
        row = []
        for x in range(aw):
            a, b = arows[y][x], brows[y][x]
            gap = max(abs(a[i] - b[i]) for i in range(3))
            if gap > thresh:
                diff_pixels += 1
                row.append((255, 0, 0))
            else:
                row.append((0, 0, 0))
        diff_rows.append(row)
    total = aw * ah
    ratio = diff_pixels / total if total else 0.0
    passed = ratio <= max_diff_ratio
    out = None
    if diff_path and (not passed or diff_pixels):
        os.makedirs(os.path.dirname(os.path.abspath(diff_path)), exist_ok=True)
        with open(diff_path, "wb") as fh:
            fh.write(encode_png(aw, ah, diff_rows))
        out = diff_path
    return DiffResult(diff_pixels, total, ratio, passed, out)


def assert_pixel_diff(actual_path, baseline_path, tolerance=0.0,
                      max_diff_ratio=0.01, diff_path=None):
    result = pixel_diff(actual_path, baseline_path, tolerance,
                        max_diff_ratio, diff_path)
    if not result.passed:
        raise AssertionFailed(
            f"pixel-diff failed: {result.diff_pixels}/{result.total_pixels} "
            f"pixels differ (ratio {result.ratio:.4f} > max {max_diff_ratio})"
            + (f"; diff image: {result.diff_path}" if result.diff_path else ""))
    return result
