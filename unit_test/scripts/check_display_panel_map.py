#!/usr/bin/env python3
"""Compile the production panel table and selector to check HDMI defaults."""

import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "port/modules/modmedia.display.c").read_text()
table = source[source.index("typedef struct _py_display_panel_map"):
               source.index("\nenum {\n    ST7701_368X544_APP_SIZE")]
selector = source[source.index("static int py_display_map_panel("):
                  source.index("static int py_display_get_connector_resolution(")]
panel_types = "\n".join(re.findall(r"^#define PY_PANEL_TYPE_.*$", source, re.M))
connectors = sorted(set(re.findall(r"\b(?:LT9611_\w+|ST7701_\w+|VIRTUAL_DISPLAY_DEVICE)\b", table))
                    | {"LT9611_HDMI_AUTO"})
prefix = """
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef int k_connector_type;
#define CONFIG_MPP_DSI_ENABLE_HDMI_LT9611 1
#define CONFIG_MPP_DSI_ENABLE_LCD_ST7701 1
#define CONFIG_MPP_DSI_ENABLE_VIRT 1
#define hal_rvv_memset memset
#define hal_rvv_memcpy memcpy
"""
constants = "enum { " + ", ".join(f"{name} = {1000 + i}" for i, name in enumerate(connectors)) + " };\n"
checks = r"""
static void check_hdmi(int width, int height, int fps, k_connector_type expected)
{
    py_display_panel_map_t panel;
    assert(py_display_map_panel(&panel, PY_PANEL_TYPE_LT9611, width, height, fps) == 0);
    assert(panel.type == expected);
}
int main(void)
{
    py_display_panel_map_t panel;
    check_hdmi(0, 0, 60, LT9611_HDMI_AUTO);
    check_hdmi(0, 0, 0, LT9611_HDMI_AUTO);
    assert(py_display_map_panel(&panel, PY_PANEL_TYPE_LT9611, 0, 0, 60) == 0);
    assert(panel.width == 0 && panel.height == 0 && panel.fps == 0);
    int defaults = 0;
    for (size_t i = 0; i < MAP_SIZE; ++i)
        defaults += py_display_panel_map[i].py_type == PY_PANEL_TYPE_LT9611 &&
                    py_display_panel_map[i].board_default;
    assert(defaults == 1);
    check_hdmi(1920, 1080, 60, LT9611_1920_1080_HDMI_V2);
    check_hdmi(1920, 1080, 30, LT9611_1920_1080_HDMI_V1);
    check_hdmi(1920, 1080, 59, LT9611_1920_1080_HDMI_V4);
    check_hdmi(1920, 1080, 29, LT9611_1920_1080_HDMI_V3);
    check_hdmi(1280, 720, 60, LT9611_1280_720_HDMI_V1);
    check_hdmi(1280, 720, 50, LT9611_1280_720_HDMI_V2);
    check_hdmi(1280, 720, 30, LT9611_1280_720_HDMI_V3);
    check_hdmi(640, 480, 60, LT9611_640_480_HDMI_V1);
    assert(py_display_map_panel(&panel, PY_PANEL_TYPE_LT9611, 800, 480, 60) != 0);
    assert(py_display_map_panel(&panel, PY_PANEL_TYPE_LT9611, 1920, 1080, 25) != 0);
    assert(py_display_map_panel(&panel, PY_PANEL_TYPE_ST7701, 0, 0, 60) == 0);
    assert(panel.width == 800 && panel.height == 480);
    assert(py_display_map_panel(&panel, PY_PANEL_TYPE_VIRT, 0, 0, 60) == 0);
    assert(panel.width == 640 && panel.height == 480 && panel.fps == 60);
    puts("PASS HDMI AUTO default, explicit fixed timings, invalid modes, LCD and virtual defaults");
}
"""

with tempfile.TemporaryDirectory(prefix="canmv-display-panel-map-") as directory:
    c_file = Path(directory) / "panel_map.c"
    binary = Path(directory) / "panel_map"
    c_file.write_text(prefix + panel_types + "\n" + constants + table + selector + checks)
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(c_file), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
