#include "lvgl.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static void clear_box(lv_obj_t *obj) {
    lv_obj_set_style_pad_all(obj, 0, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_clear_flag(obj, LV_OBJ_FLAG_SCROLLABLE);
}

int main(void) {
    int width, height, card_w, card_h, icon_y, text_h, text_y, font_size, footer_h;
    assert(scanf("%d%d%d%d%d%d%d%d%d", &width, &height, &card_w, &card_h,
                 &icon_y, &text_h, &text_y, &font_size, &footer_h) == 9);
    lv_init();
    lv_disp_t *display = lv_disp_create(width, height);
    assert(display);
    lv_obj_t *screen = lv_obj_create(NULL);
    clear_box(screen);
    lv_obj_t *card = lv_obj_create(screen);
    clear_box(card);
    lv_obj_set_size(card, card_w, card_h);
    const char *titles[] = {"Face", "Face recognition", "Long application title for wrapping"};
    for (unsigned i = 0; i < sizeof(titles) / sizeof(titles[0]); ++i) {
        lv_obj_t *label = lv_label_create(card);
        lv_obj_set_style_text_font(label, font_size == 16 ? &lv_font_montserrat_16 :
                                  &lv_font_montserrat_20, 0);
        lv_label_set_text(label, titles[i]);
        lv_label_set_long_mode(label, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(label, card_w - 12);
        lv_obj_set_style_text_line_space(label, 0, 0);
        lv_obj_set_height(label, LV_SIZE_CONTENT);
        lv_obj_set_style_max_height(label, text_h, 0);
        lv_obj_align(label, LV_ALIGN_BOTTOM_MID, 0, text_y);
        lv_obj_update_layout(screen);
        assert(lv_obj_get_y(label) >= icon_y + 48 + 4);
        assert(lv_obj_get_y(label) + lv_obj_get_height(label) == card_h + text_y);
        assert(lv_obj_get_height(label) <= text_h);
        lv_obj_del(label);
    }
    lv_obj_t *footer = lv_obj_create(screen);
    clear_box(footer);
    lv_obj_set_size(footer, width, footer_h);
    lv_obj_set_pos(footer, 0, height - footer_h);
    for (int i = 0; i < 5; ++i) {
        int x, y, w, h;
        assert(scanf("%d%d%d%d", &x, &y, &w, &h) == 4);
        lv_obj_t *label = lv_label_create(footer);
        lv_label_set_text(label, "status");
        lv_obj_align(label, LV_ALIGN_RIGHT_MID, 0, 0);
        lv_obj_set_size(label, w, h);
        if (i != 0) {
            lv_obj_set_style_text_font(label, i == 4 ? &lv_font_montserrat_16 :
                                      &lv_font_montserrat_20, 0);
            lv_label_set_text(label, i == 4 ? LV_SYMBOL_WIFI : "status");
            int line_h = lv_font_get_line_height(lv_obj_get_style_text_font(label, 0));
            lv_obj_set_style_pad_top(label, h > line_h ? (h - line_h) / 2 : 0, 0);
        }
        lv_obj_align(label, LV_ALIGN_TOP_LEFT, x, y);
        lv_obj_update_layout(screen);
        assert(lv_obj_get_x(label) == x);
        assert(lv_obj_get_y(label) == y);
        assert(lv_obj_get_width(label) == w);
        assert(lv_obj_get_height(label) == h);
        if (i != 0) {
            lv_area_t content;
            lv_obj_get_content_coords(label, &content);
            int line_h = lv_font_get_line_height(lv_obj_get_style_text_font(label, 0));
            int center_delta = 2 * (content.y1 - (height - footer_h + y)) + line_h - h;
            assert(abs(center_delta) <= 1);
        }
    }
    lv_obj_del(screen);
    lv_disp_remove(display);
    lv_deinit();
    puts("native layout OK");
    return 0;
}
