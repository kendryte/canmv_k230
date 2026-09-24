from libs.PipeLine import PipeLine
from libs.DisplayConfig import init_display
from libs.AIBase import AIBase
from libs.AI2D import Ai2d
from libs.Utils import *
import nncase_runtime as nn
import ulab.numpy as np
import aidemo
from media.display import *
from media.media import *
from media.sensor import *
import time, os, sys, gc
import lvgl as lv
from machine import TOUCH
from machine import RTC
import _thread
from face_reg_rec import FaceRegAndRec


# 自定义人脸检测类，继承自AIBase基类
class FaceApp():
    def __init__(self, rgb888p_size=[1280, 720], display_size=[800,480], debug_mode=0):
        self.display_size = display_size
        self.rgb888p_size = rgb888p_size
        self.faceregandrec = FaceRegAndRec(rgb888p_size, debug_mode)

    def recognize(self, input_np):
        return self.faceregandrec.recognize(input_np)


    def register(self, input_np, register_name):
        return self.faceregandrec.register(input_np, register_name)
    
    def clear_register_face(self):
        self.faceregandrec.clear_register_face()

    # 绘制检测结果到画面上
    def draw_result(self, osd_img, det_boxes,recg_res):
        osd_img.clear()
        if det_boxes:
            for i,det in enumerate(det_boxes):
                # （1）画人脸框
                x1, y1, w, h = map(lambda x: int(round(x, 0)), det[:4])
                x1 = x1 * self.display_size[0]//self.rgb888p_size[0]
                y1 = y1 * self.display_size[1]//self.rgb888p_size[1]
                w =  w * self.display_size[0]//self.rgb888p_size[0]
                h = h * self.display_size[1]//self.rgb888p_size[1]
                osd_img.draw_rectangle(x1,y1, w, h, color=(255,0, 0, 255), thickness = 4)
                # （2）写人脸识别结果
                recg_text = recg_res[i]
                osd_img.draw_string_advanced(x1,y1,32,recg_text,color=(255, 255, 0, 0))



class touch_screen():
    def __init__(self):
        self.x = 0
        self.y = 0
        self.state = lv.INDEV_STATE.RELEASED
        self.indev_drv = lv.indev_create()
        self.indev_drv.set_type(lv.INDEV_TYPE.POINTER)
        self.indev_drv.set_read_cb(self.callback)
        self.touch = TOUCH(0)

    def callback(self, driver, data):
        x, y, state = self.x, self.y, lv.INDEV_STATE.RELEASED
        tp = self.touch.read(1)
        if tp != (): #发生触摸事件
            for i in range(len(tp)):
                 pass
        if len(tp):
            x, y, event = tp[0].x, tp[0].y, tp[0].event
            if event == 2 or event == 3:
                state = lv.INDEV_STATE.PRESSED
        data.point = lv.point_t({'x': x, 'y': y})
        data.state = state


class XiaoZhi_UI:
    def __init__(self):
        print("LVGL UI init start")
        self.src = None
        self.disp_img1 = None
        self.disp_img2 = None
        self.tp = None
        self.sensor = None
        self.osd_img = None
        self.register_btn = None
        self.display_mode = "auto"
        self.requested_display_size = None
        self.DISPLAY_WIDTH = 0
        self.DISPLAY_HEIGHT = 0
        self.rgb888p_size=[1280,720]
        self.img_joke_path = "A:/sdcard/examples/26-xiaozhi/resource/img_joke.png"
        self.img_naughty_path = "A:/sdcard/examples/26-xiaozhi/resource/img_naughty.png"
        self.img_think_path = "A:/sdcard/examples/26-xiaozhi/resource/img_think.png"
        self.face_detect_run = True
        self.ui_status = 0
        self.face_det = None
        self.chinese_font = None
        self.msg_box = None
        self.have_person = False
        self.have_reg_person = False
        self.reg_person_name = ""
        self.tts_playing = False
        self.ui_alive = True
        self.face_thread_done = True
        self.img_0 = None
        self.img_2 = None
        self.sensor = None
        # 跨线程 UI 更新队列：只在主循环 flush，避免 dirty areas in render
        self._ui_lock = _thread.allocate_lock()
        self._ui_pending = {}
        self._go_normal_at = None
        
    def get_person(self):
        return self.have_person

    def set_tts_playing(self, playing):
        self.tts_playing = playing

    def media_init(self):
        self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT = init_display(
            self.display_mode, self.requested_display_size, to_ide=True, osd_num=1)
        self.sensor = Sensor(fps=30)
        self.sensor.reset()
        self.sensor.set_framesize(w = self.DISPLAY_WIDTH, h = self.DISPLAY_HEIGHT, chn=CAM_CHN_ID_0)
        self.sensor.set_pixformat(Sensor.YUV420SP)
        
        self.sensor.set_framesize(w = self.rgb888p_size[0], h = self.rgb888p_size[1], chn=CAM_CHN_ID_2)
        self.sensor.set_pixformat(Sensor.RGBP888, chn=CAM_CHN_ID_2)
        
        bind_info = self.sensor.bind_info(x = 0, y = 0, chn = CAM_CHN_ID_0)
        Display.bind_layer(**bind_info, layer = Display.LAYER_VIDEO1)
        self.sensor.run()
        self.face_detect_run = True
        self.face_thread_done = False
        _thread.start_new_thread(self.face_det_thread,())

    def media_deinit(self):
        if not self.face_thread_done:
            print("media_deinit: face thread still running, skip")
            return
        # snapshot 缓冲不要 clear，只丢引用；与 ai_lvgl 一致：sensor.stop → Display.deinit
        self.img_0 = None
        self.img_2 = None
        if self.sensor:
            try:
                self.sensor.stop()
            except:
                pass
            self.sensor = None
        try:
            Display.deinit()
        except:
            pass
        time.sleep_ms(50)

    def face_det_thread(self):
        time.sleep_ms(500)
        try:
            self.face_det = FaceApp(rgb888p_size=self.rgb888p_size, display_size=[self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT], debug_mode=0)
            self.img_0 = image.Image(self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT, image.ARGB8888)
            while self.face_detect_run:
                if self.ui_status == 0:
                    if self.sensor is None:
                        break
                    self.img_2 = self.sensor.snapshot(chn = CAM_CHN_ID_2)
                    if not self.face_detect_run:
                        break
                    img_np = self.img_2.to_numpy_ref()
                    det_boxes, recg_res, results= self.face_det.recognize(img_np)
                    if not self.face_detect_run:
                        break
                    self.face_det.draw_result(self.img_0, det_boxes,recg_res)
                    if det_boxes:
                        self.have_person = True
                    else:
                        self.have_person = False
                    if 0 in results:
                        for name in recg_res:
                            if name == "unknown":
                                continue
                            self.reg_person_name = name
                            self.have_reg_person = True
                    else:
                        self.reg_person_name = ""
                        self.have_reg_person = False
                    if self.face_detect_run and self.img_0 is not None:
                        Display.show_image(self.img_0, 0, 0, Display.LAYER_OSD1)
                    # 运行期需要定期 gc：回收 WS poll/临时对象的 fd，否则会 DFS fd 耗尽
                    # 退出时 begin_exit 会先等本线程结束，再拆 media/LVGL，故此处 gc 不再与 teardown 并发
                    if self.tts_playing:
                        time.sleep_ms(200)
                    else:
                        gc.collect()
                        time.sleep_ms(10)
                else:
                    time.sleep_ms(50)
        except Exception as e:
            print("人脸检测线程异常: %s" % e)
        finally:
            self.face_thread_done = True
            print("人脸检测线程结束")

    def get_reg_result(self):
        return self.have_reg_person, self.reg_person_name

    def _wait_face_thread(self, timeout_s=5.0):
        deadline = time.time() + timeout_s
        while not self.face_thread_done and time.time() < deadline:
            time.sleep(0.05)
    
    def Update_llm(self, llm_status="joke"):
        if not self.ui_alive:
            return
        with self._ui_lock:
            self._ui_pending["llm"] = llm_status

    def Update_text(self, talk_text):
        if not self.ui_alive:
            return
        with self._ui_lock:
            self._ui_pending["text"] = talk_text

    def Update_status(self, status):
        if not self.ui_alive:
            return
        with self._ui_lock:
            self._ui_pending["status"] = status

    def _apply_llm(self, llm_status):
        try:
            if llm_status in ["thinking", "confused"]:
                src = self.img_think_path
            elif llm_status in ["neutral", "surprised", "crying", "angry", "sad", "silly"]:
                src = self.img_naughty_path
            else:
                src = self.img_joke_path
            self.llm_img.set_src(src)
            self.llm_img.clear_flag(lv.obj.FLAG.HIDDEN)
        except Exception as e:
            print("更新情绪图片失败(%s): %s" % (llm_status, e))

    def flush_ui_updates(self):
        """仅主线程在 lv.task_handler 之前调用。"""
        if not self.ui_alive:
            return
        with self._ui_lock:
            pending = self._ui_pending
            self._ui_pending = {}
        if "status" in pending:
            try:
                self.xiaozhi_status_text.set_text(pending["status"])
            except:
                pass
        if "text" in pending:
            try:
                self.speak_text.set_text(pending["text"])
            except:
                pass
        if "llm" in pending:
            try:
                self._apply_llm(pending["llm"])
            except:
                pass
        if "msgbox" in pending:
            try:
                title, body = pending["msgbox"]
                if self.msg_box is not None:
                    try:
                        self.msg_box.delete()
                    except:
                        pass
                self.msg_box = lv.msgbox(self.scr, title, body, None, None)
                self.msg_box.set_size(min(400, self.DISPLAY_WIDTH - 24), min(200, self.DISPLAY_HEIGHT - 24))
                self.msg_box.center()
                self.msg_box.set_style_text_font(self.chinese_font, lv.PART.MAIN)
            except:
                pass
        if "go_normal_at" in pending:
            self._go_normal_at = pending["go_normal_at"]
        if self._go_normal_at is not None and time.time() >= self._go_normal_at:
            self._go_normal_at = None
            try:
                if self.msg_box is not None:
                    self.msg_box.delete()
                    self.msg_box = None
                self.ui_status = 0
                self.show_normal_ui()
                self.hide_register_ui()
            except:
                pass

    def btn_clicked_register_face(self, event):
        self.ui_status = 1
        self.xiaozhi_status_text.set_text("人脸注册中")
        self.hide_normal_ui()
        self.show_register_ui()

    def btn_clicked_clear_database(self, evt):
        self.face_det.clear_register_face()

    def disp_drv_flush_cb(self, disp_drv, area, color):
        if not self.ui_alive:
            disp_drv.flush_ready()
            return
        if disp_drv.flush_is_last() == True:
            if self.disp_img1.virtaddr() == uctypes.addressof(color.__dereference__()):
                self.disp_img2.bytearray()[:]=bytearray(0)
                Display.show_image(self.disp_img1,layer=Display.LAYER_OSD2)
            else:
                self.disp_img1.bytearray()[:]=bytearray(0)
                Display.show_image(self.disp_img2,layer=Display.LAYER_OSD2)
            time.sleep(0.01)
        disp_drv.flush_ready()

    def lvgl_init(self):

        lv.init()

        disp_drv = lv.disp_create(self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT)
        disp_drv.set_flush_cb(self.disp_drv_flush_cb)
        disp_drv.set_color_format(lv.COLOR_FORMAT.ARGB8888)
        self.disp_img1 = image.Image(self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT, image.BGRA8888)
        self.disp_img2 = image.Image(self.DISPLAY_WIDTH, self.DISPLAY_HEIGHT, image.BGRA8888)
        self.disp_img1.clear()
        self.disp_img2.clear()
        disp_drv.set_draw_buffers(self.disp_img1.bytearray(), self.disp_img2.bytearray(), self.disp_img1.size(), lv.DISP_RENDER_MODE.FULL)
        self.tp = touch_screen()

    def lvgl_deinit(self):
        try:
            if getattr(self, "disp_img1", None) is not None:
                self.disp_img1.clear()
            if getattr(self, "disp_img2", None) is not None:
                self.disp_img2.clear()
        except:
            pass
        try:
            lv.deinit()
        except Exception as e:
            print("lv.deinit: %s" % e)
        self.disp_img1 = None
        self.disp_img2 = None

    def hide_normal_ui(self):
        self.register_btn.add_flag(lv.obj.FLAG.HIDDEN)
        self.clear_database_btn.add_flag(lv.obj.FLAG.HIDDEN)
        self.llm_img.add_flag(lv.obj.FLAG.HIDDEN)
        self.speak_text.add_flag(lv.obj.FLAG.HIDDEN)

    def show_normal_ui(self):

        self.xiaozhi_status_text.set_text("等待按键唤醒")

        self.register_btn.clear_flag(lv.obj.FLAG.HIDDEN)
        self.clear_database_btn.clear_flag(lv.obj.FLAG.HIDDEN)
        self.llm_img.clear_flag(lv.obj.FLAG.HIDDEN)
        self.speak_text.clear_flag(lv.obj.FLAG.HIDDEN)

    def hide_register_ui(self):
        self.main_cont.add_flag(lv.obj.FLAG.HIDDEN)

    def show_register_ui(self):
        # 清空输入框，准备下次注册
        self.name_input.set_text("")
        self.main_cont.clear_flag(lv.obj.FLAG.HIDDEN)

    def create_register_ui(self):
        panel_w = min(600, self.DISPLAY_WIDTH - 24)
        panel_h = min(420, self.DISPLAY_HEIGHT - 24)
        inner_w = panel_w - 16
        input_h = min(60, max(36, panel_h // 6))
        buttons_h = min(60, max(40, panel_h // 7))
        keyboard_h = panel_h - 16 - 12 - input_h - buttons_h

        self.main_cont = lv.obj(self.scr)
        self.main_cont.set_size(panel_w, panel_h)
        self.main_cont.center()
        self.main_cont.set_flex_flow(lv.FLEX_FLOW.COLUMN)  # 垂直排列
        self.main_cont.set_flex_align(
            lv.FLEX_ALIGN.CENTER,    # 水平居中
            lv.FLEX_ALIGN.START,     # 垂直顶部开始
            lv.FLEX_ALIGN.CENTER     # 子元素居中
        )
        # 容器样式（大屏美化）
        self.main_cont.set_style_bg_color(lv.color_hex(0xF5F5F5), lv.PART.MAIN)
        self.main_cont.set_style_radius(16, lv.PART.MAIN)          # 更大圆角
        self.main_cont.set_style_shadow_color(lv.color_hex(0xDDDDDD), lv.PART.MAIN)
        self.main_cont.set_style_shadow_width(8, lv.PART.MAIN)     # 阴影效果
        self.main_cont.set_style_pad_all(8, lv.PART.MAIN)
        self.main_cont.set_style_pad_row(6, lv.PART.MAIN)
        self.main_cont.set_style_border_width(0, lv.PART.MAIN)

        # 5. 创建姓名输入框（大屏尺寸）
        self.name_input = lv.textarea(self.main_cont)
        self.name_input.set_size(inner_w, input_h)
        self.name_input.set_max_length(10)                         # 最大输入长度（姓名最多10个字）
        self.name_input.set_placeholder_text("请输入姓名（如：Jerry）")  # 更清晰的占位提示
        # 输入框样式（大屏优化）
        self.name_input.set_style_text_font(self.chinese_font, lv.PART.MAIN)  # 输入文字放大
        self.name_input.set_style_bg_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        self.name_input.set_style_border_color(lv.color_hex(0xCCCCCC), lv.PART.MAIN)
        self.name_input.set_style_border_width(3, lv.PART.MAIN)                   # 更粗边框
        self.name_input.set_style_radius(12, lv.PART.MAIN)                         # 更大圆角
        self.name_input.set_style_pad_all(4, lv.PART.MAIN)                        # 更大内边距
        # 输入框聚焦样式（大屏醒目）
        self.name_input.set_style_border_color(lv.color_hex(0x4CAF50), lv.PART.MAIN | lv.STATE.FOCUSED)

        # 6. 创建虚拟键盘（800x480全屏宽度适配）
        kb = lv.keyboard(self.main_cont)
        kb.set_size(inner_w, keyboard_h)
        # 键盘样式（大屏优化）
        kb.set_style_bg_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)
        kb.set_style_text_font(self.chinese_font, lv.PART.MAIN)  # 键盘文字放大
        kb.set_textarea(self.name_input)

        btn_cont = lv.obj(self.main_cont)
        btn_cont.set_size(inner_w, buttons_h)
        btn_cont.set_style_pad_all(6, lv.PART.MAIN)
        btn_cont.set_style_pad_column(8, lv.PART.MAIN)
        btn_cont.set_style_border_width(0, lv.PART.MAIN)
        btn_cont.set_flex_flow(lv.FLEX_FLOW.ROW)  # 水平排列按钮
        btn_cont.set_flex_align(
            lv.FLEX_ALIGN.CENTER,    # 水平居中
            lv.FLEX_ALIGN.CENTER,    # 垂直居中
            lv.FLEX_ALIGN.CENTER     # 子元素居中
        )

        confirm_btn = lv.btn(btn_cont)
        confirm_btn.set_size(min(120, (inner_w - 20) // 2), buttons_h - 12)
        confirm_btn.set_style_pad_all(0, lv.PART.MAIN)
        confirm_btn.set_style_bg_color(lv.color_hex(0x4CAF50), lv.PART.MAIN)  # 绿色主色
        confirm_btn.set_style_bg_color(lv.color_hex(0x388E3C), lv.PART.MAIN | lv.STATE.PRESSED)  # 按下颜色
        confirm_btn.set_style_radius(12, lv.PART.MAIN)                             # 更大圆角
        confirm_btn.set_style_shadow_color(lv.color_hex(0xAAAAAA), lv.PART.MAIN)
        confirm_btn.set_style_shadow_width(6, lv.PART.MAIN)

        btn_label = lv.label(confirm_btn)
        btn_label.set_text("确定")
        btn_label.set_style_text_font(self.chinese_font, lv.PART.MAIN)  # 按钮文字放大
        btn_label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)     # 白色文字
        btn_label.center()  # 文字居中

        exit_btn = lv.btn(btn_cont)
        exit_btn.set_size(min(120, (inner_w - 20) // 2), buttons_h - 12)
        exit_btn.set_style_pad_all(0, lv.PART.MAIN)
        exit_btn.set_style_bg_color(lv.color_hex(0x4CAF50), lv.PART.MAIN)  # 绿色主色
        exit_btn.set_style_bg_color(lv.color_hex(0x388E3C), lv.PART.MAIN | lv.STATE.PRESSED)  # 按下颜色
        exit_btn.set_style_radius(12, lv.PART.MAIN)                             # 更大圆角
        exit_btn.set_style_shadow_color(lv.color_hex(0xAAAAAA), lv.PART.MAIN)
        exit_btn.set_style_shadow_width(6, lv.PART.MAIN)

        btn_label = lv.label(exit_btn)
        btn_label.set_text("取消")
        btn_label.set_style_text_font(self.chinese_font, lv.PART.MAIN)  # 按钮文字放大
        btn_label.set_style_text_color(lv.color_hex(0xFFFFFF), lv.PART.MAIN)     # 白色文字
        btn_label.center()  # 文字居中

        # 绑定点击事件
        confirm_btn.add_event(self.on_confirm_click, lv.EVENT.CLICKED, None)

        exit_btn.add_event(self.on_exit_click, lv.EVENT.CLICKED, None)

    def run_register_face_thread(self, register_name):
        img_np = self.img_2.to_numpy_ref()
        img_return=img_np.reshape((1,img_np.shape[0],img_np.shape[1],img_np.shape[2]))
        result, ret_message = self.face_det.register(img_return, register_name)
        if result == 0:
            display_message = "注册成功"
        else:
            display_message = "注册失败"
        if not self.ui_alive:
            return
        with self._ui_lock:
            self._ui_pending["msgbox"] = (display_message, ret_message)
            self._ui_pending["go_normal_at"] = time.time() + 2

    def on_exit_click(self, evt):
        self.ui_status = 0
        self.xiaozhi_status_text.set_text("等待按键唤醒")
        self.show_normal_ui()
        self.hide_register_ui()

    def on_confirm_click(self, evt):

        register_name = self.name_input.get_text()

        # 校验输入（非空）
        if not register_name:
            self.msg_box = lv.msgbox(self.scr, "提示", "姓名不能为空！", None, None)
            self.msg_box.set_size(min(400, self.DISPLAY_WIDTH - 24), min(200, self.DISPLAY_HEIGHT - 24))
            self.msg_box.center()
            self.msg_box.set_style_text_font(self.chinese_font, lv.PART.MAIN)
            with self._ui_lock:
                self._ui_pending["go_normal_at"] = time.time() + 2
            return

        _thread.start_new_thread(self.run_register_face_thread,(register_name,))

    def hide_and_go_normal(self):
        # 兼容旧调用：改走主线程队列
        if not self.ui_alive:
            return
        with self._ui_lock:
            self._ui_pending["go_normal_at"] = time.time() + 2


    def user_gui_init(self):

        self.media_init()

        self.lvgl_init()

        # 优先使用例程自带字体，失败再回退系统字体
        try:
            self.chinese_font = lv.freetype_font_create(
                "/sdcard/examples/26-xiaozhi/resource/Source_Han_Sans_CN_Regular.ttf", 20, 0)
        except Exception as e:
            print("加载例程字体失败: %s，尝试系统字体" % e)
            self.chinese_font = lv.freetype_font_create(
                "/sdcard/res/font/SourceHanSansSC-Normal-Min.ttf", 20, 0)

        self.scr = lv.scr_act()

        # 设置屏幕背景完全透明
        lv.scr_act().set_style_bg_opa(lv.OPA.TRANSP, lv.PART.MAIN)

        # 创建一个半透明的侧边栏
        label = lv.obj(lv.layer_sys())
        label.set_size(self.DISPLAY_WIDTH, 30)
        label.set_pos(0, 0)
        label.set_style_bg_color(lv.color_hex(0xa0a0a0), lv.PART.MAIN)
        label.set_style_bg_opa(50, lv.PART.MAIN)
        label.set_style_border_width(0, lv.PART.MAIN)

        self.xiaozhi_status_text = lv.label(self.scr)
        self.xiaozhi_status_text.set_text("系统初始化，请稍后")
        self.xiaozhi_status_text.set_style_text_font(self.chinese_font, 0)
        self.xiaozhi_status_text.set_width(min(310, self.DISPLAY_WIDTH - 16))
        self.xiaozhi_status_text.align(lv.ALIGN.TOP_MID, 0, 0)
        # 人脸检测按钮
        self.register_btn = lv.btn(lv.layer_sys())
        self.register_btn.set_size(120, 45)
        self.register_btn.set_pos(self.DISPLAY_WIDTH - 120, 75)
        self.register_btn.set_style_radius(20, lv.PART.MAIN)
        self.register_btn.set_style_bg_color(lv.color_hex(0x0000FF), lv.PART.MAIN)
        self.register_btn.set_style_bg_opa(255, lv.PART.MAIN)  # 不透明背景
        self.register_btn.add_event(self.btn_clicked_register_face, lv.EVENT.CLICKED, None)
        label2 = lv.label(self.register_btn)
        label2.set_style_text_font(self.chinese_font, 0)
        label2.set_text("注册")
        label2.align(lv.ALIGN.CENTER, 0, 0)

                # 人脸检测按钮
        self.clear_database_btn = lv.btn(lv.layer_sys())
        self.clear_database_btn.set_size(120, 45)
        self.clear_database_btn.set_pos(self.DISPLAY_WIDTH - 120, 140)
        self.clear_database_btn.set_style_radius(20, lv.PART.MAIN)
        self.clear_database_btn.set_style_bg_color(lv.color_hex(0x0000FF), lv.PART.MAIN)
        self.clear_database_btn.set_style_bg_opa(255, lv.PART.MAIN)  # 不透明背景
        self.clear_database_btn.add_event(self.btn_clicked_clear_database, lv.EVENT.CLICKED, None)
        label3 = lv.label(self.clear_database_btn)
        label3.set_style_text_font(self.chinese_font, 0)
        label3.set_text("清空数据库")
        label3.align(lv.ALIGN.CENTER, 0, 0)

        self.llm_img = lv.img(self.scr)
        self.llm_img.set_src(self.img_joke_path)
        self.llm_img.set_size(50, 50)  # 宽120px，高90px
        img_x = (self.DISPLAY_WIDTH - 50) // 2
        self.llm_img.set_pos(img_x, self.DISPLAY_HEIGHT - 90)
        self.llm_img.set_style_img_opa(255, lv.PART.MAIN)

        self.speak_text = lv.label(self.scr)
        self.speak_text.set_text("Hi，你好小智")
        self.speak_text.set_style_text_font(self.chinese_font, 0)
        self.speak_text.set_pos(img_x, self.DISPLAY_HEIGHT - 30)
        self.speak_text.set_width(min(310, self.DISPLAY_WIDTH - 16))
        self.speak_text.align(lv.ALIGN.BOTTOM_MID, 0, 0)

        self.create_register_ui()
        self.hide_register_ui()

        lv.scr_load(self.scr)

    def begin_exit(self):
        """先停人脸线程并禁止再碰 LVGL；设备/音频应在此之后释放。"""
        self.ui_alive = False
        self.face_detect_run = False
        self._wait_face_thread(5.0)
        if not self.face_thread_done:
            print("等待人脸线程超时，继续退出")
        time.sleep_ms(100)

    def user_gui_deinit(self, release_display=False):
        """
        release_display=False（run.py / IDE 默认）：只停人脸，不调 lv.deinit/Display.deinit。
        CanMV 脚本结束会 [mpy] exit, reset 再清一次，重复 lv.deinit 会报 already deinited。
        release_display=True：独立跑本文件时需要主动释放。
        """
        self.ui_alive = False
        self.face_detect_run = False
        self._wait_face_thread(2.0)
        if not release_display:
            return
        try:
            self.lvgl_deinit()
        except Exception as e:
            print("lvgl_deinit: %s" % e)
        time.sleep_ms(50)
        try:
            self.media_deinit()
        except Exception as e:
            print("media_deinit: %s" % e)

if __name__ == "__main__":
    xiaozhi_gui = XiaoZhi_UI()
    xiaozhi_gui.user_gui_init()
    try:
        while True:
            time.sleep_ms(lv.task_handler())
    except BaseException as e:
        import sys
        sys.print_exception(e)
        cur_state=0
        time.sleep_ms(100)
    xiaozhi_gui.user_gui_deinit(release_display=True)
