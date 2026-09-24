"""Host checks for shared display policy and AI example geometry."""
import ast
from pathlib import Path
import types
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "resources/examples"


def functions(path, namespace):
    nodes = [n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)


class Canvas:
    def __init__(self, width, height, *args, **kwargs):
        self.width_value, self.height_value = width, height
        self.draws = []
        self.data = kwargs.get('data')
    def width(self): return self.width_value
    def height(self): return self.height_value
    def to_numpy_ref(self): return self
    def clear(self): self.draws.append("clear")
    def draw_image(self, img, *args, **kwargs): self.draws.append((img, kwargs))
    def draw_string_advanced(self, *args, **kwargs): pass


class Display:
    LT9611,ST7701,HX8399,NT35516,NT35532,GC9503,AML020T,JD9852,ILI9806,VIRT=range(10)
    LAYER_VIDEO1,LAYER_VIDEO2,LAYER_OSD1,LAYER_OSD2=1,2,3,4
    def __init__(self, width, height):
        self.size = [width, height]
        self.calls, self.binds, self.shown = [], [], []
    def init(self, panel, **kwargs):
        self.calls.append((panel, kwargs))
    def width(self): return self.size[0]
    def height(self): return self.size[1]
    def bind_layer(self, **kwargs): self.binds.append(kwargs)
    def show_image(self, img, *args, **kwargs): self.shown.append(img)


class DisplayTests(unittest.TestCase):
    def namespace(self, size=(640,480)):
        display = Display(*size)
        sensors = []
        class Sensor:
            RGB888,YUV420SP,RGBP888=1,2,3
            def __init__(self, **kwargs):
                self.frames = []
                sensors.append(self)
            def reset(self): pass
            def width(self, *args): return 1920
            def height(self, *args): return 1080
            def set_framesize(self, **kwargs): self.frames.append(kwargs)
            def set_pixformat(self, *args, **kwargs): pass
            def bind_info(self, **kwargs): return kwargs
            def run(self): pass
        ns = dict(Display=display, Sensor=Sensor, sensors=sensors,
                  os=types.SimpleNamespace(uname=lambda: ("k230_canmv_01studio",), stat=lambda p: ()),
                  image=types.SimpleNamespace(Image=Canvas, RGB888=1, ARGB8888=2, ALLOC_REF=0),
                  time=types.SimpleNamespace(sleep=lambda x: None),
                  MediaManager=types.SimpleNamespace(init=lambda: None),
                  CAM_CHN_ID_0=0, CAM_CHN_ID_1=1, CAM_CHN_ID_2=2,
                  display_mode="auto", requested_display_size=None, display_size=None,
                  rgb888p_size=[1280,720], DISPLAY_WIDTH=0, DISPLAY_HEIGHT=0,
                  VIDEO_WIDTH=640, VIDEO_HEIGHT=480, IMG_SAVE_PATH="/unused",
                  cal_grab_rect=lambda: None, osd_size=None)
        functions(ROOT / "resources/libs/DisplayConfig.py", ns)
        return ns

    def test_init_preserves_options_and_uses_actual_dimensions(self):
        ns = self.namespace()
        size = ns["init_display"]("auto", to_ide=True, osd_num=4)
        self.assertEqual(size, [640,480])
        self.assertEqual(ns["Display"].calls[-1], (Display.ST7701, {"to_ide": True,"osd_num":4}))
        size = ns["init_display"](Display.LT9611, [800,480], fps=30)
        self.assertEqual(size, [640,480])
        self.assertEqual(ns["Display"].calls[-1], (Display.LT9611, {"width":800,"height":480,"fps":30}))

    def test_standalone_sensor_geometry_follows_display(self):
        for name in ("ai_multi_thread.py", "ai_lvgl.py", "ai_two_camera.py"):
            for size in ((320,240),(640,480),(800,480),(960,536),(1920,1080)):
                with self.subTest(name=name, size=size):
                    ns = self.namespace(size)
                    functions(EXAMPLES / "21-AI-With-Others" / name, ns)
                    ns["media_init"]()
                    self.assertEqual(ns["display_size"], list(size))
                    self.assertEqual((ns["DISPLAY_WIDTH"], ns["DISPLAY_HEIGHT"]), size)
                    for sensor in ns["sensors"]:
                        frame = sensor.frames[0]
                        expected = ns["osd_size"] if name == "ai_two_camera.py" else size
                        self.assertEqual((frame["w"],frame["h"]), tuple(expected))
                    if name == "ai_two_camera.py":
                        w,h = ns["osd_size"]
                        self.assertEqual(w % 16, 0)
                        self.assertEqual(ns["second_x"]+w, size[0])
                        self.assertEqual(ns["second_y"]+h, size[1])
                        self.assertEqual(ns["Display"].binds[1]["x"], ns["second_x"])
                        self.assertEqual(ns["Display"].binds[1]["y"], ns["second_y"])
                        self.assertEqual(ns["face_osd_img"].width(), w)
                        self.assertEqual(ns["yolo_osd_img"].height(), h)

    def test_capture_resolution_is_not_changed_by_preview(self):
        for name, folder in (("DataCollectionCamera.py","16-AI-Cube"),("save_image.py","22-Others")):
            ns = self.namespace((320,240))
            tree = ast.parse((EXAMPLES / folder / name).read_text())
            node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="media_init")
            exec(compile(ast.Module(body=[node],type_ignores=[]),name,"exec"), ns)
            ns["media_init"]()
            self.assertEqual(ns["sensors"][0].frames[0]["w"],640)
            self.assertEqual(ns["sensors"][0].frames[0]["h"],480)
            self.assertEqual((ns["DISPLAY_WIDTH"],ns["DISPLAY_HEIGHT"]),(320,240))

    def test_uvc_resizes_annotated_frame_and_reuses_pipeline(self):
        for name in ("ai_uvc_hard_decode.py","ai_uvc_soft_decode.py"):
            tree = ast.parse((EXAMPLES/"21-AI-With-Others"/name).read_text())
            branch = next(n for n in ast.walk(tree) if isinstance(n,ast.If)
                          and ast.unparse(n.test)=="[img.width(), img.height()] == display_size")
            code = compile(ast.Module(body=[branch],type_ignores=[]),name,"exec")
            ns = self.namespace((320,240))
            class Resizer:
                def __init__(self,size): self.size=size
                def run(self,array): return Canvas(*self.size)
            ns.update(img=Canvas(640,480),display_resize=None,display_size=[320,240],
                      DisplayImage=Resizer)
            exec(code,ns)
            resizer = ns["display_resize"]
            self.assertEqual(ns["Display"].shown[-1].width(),320)
            exec(code,ns)
            self.assertIs(ns["display_resize"],resizer)
            ns["display_size"]=[640,480]
            exec(code,ns)
            self.assertIs(ns["Display"].shown[-1],ns["img"])

    def test_mp4_binding_uses_native_path_only_for_matching_sizes(self):
        path=EXAMPLES/"21-AI-With-Others/face_detect_yunet_from_mp4.py"
        fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="demuxer_mp4")
        start=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=="panel_type")
        end=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=="vdec_link")
        code=compile(ast.Module(body=fn.body[start:end],type_ignores=[]),str(path),"exec")
        for size,panel,requested in (((640,480),None,None),((1280,720),None,None),
                                     ((1280,720),Display.VIRT,None),((320,240),Display.VIRT,[320,240])):
            ns=self.namespace(size)
            ns.update(display_type=panel,requested_display_size=requested,
                      video_info=types.SimpleNamespace(width=1280,height=720),
                      vdec=types.SimpleNamespace(create=lambda:None,get_vdec_channel=lambda:0,
                                                bind_info=lambda **kw:kw))
            exec(code,ns)
            self.assertEqual(bool(ns["Display"].binds),size==(1280,720))
            if panel==Display.VIRT:
                args=ns["Display"].calls[-1][1]
                self.assertEqual([args["width"],args["height"]], requested or [1280,720])
                self.assertEqual(args["fps"],30)

    def test_mp4_scaled_frame_is_copied_before_csc_release(self):
        ns=self.namespace((320,240))
        functions(EXAMPLES/"21-AI-With-Others/face_detect_yunet_from_mp4.py",ns)
        events=[]
        class Array:
            shape=(3,720,1280)
            def reshape(self, shape): return self
        class Frame:
            def to_numpy_ref(self): return Array()
        class Model:
            def __init__(self,*args,**kw):
                self.size=kw["display_size"]
                events.append(("model",self.size))
            def config_preprocess(self): pass
            def run(self,img): return []
            def draw_result(self,canvas,res): events.append("draw")
        def get_frame(**kw):
            ns["sub_thread_flag"]=False
            return types.SimpleNamespace(v_frame=types.SimpleNamespace(to_image=lambda:Frame()))
        class Resizer:
            def __init__(self,size,planar=False): self.size=size
            def run(self,array):
                events.append("copy")
                return Canvas(*self.size)
            def deinit(self): events.append("deinit")
        ns.update(sub_thread_flag=True,FaceDetectionApp=Model,DisplayImage=Resizer,
                  csc=types.SimpleNamespace(get_frame=get_frame,release_frame=lambda f:events.append("release")),
                  chw2hwc=lambda a:events.append("copy") or object(),
                  gc=types.SimpleNamespace(collect=lambda:None))
        ns["ai_detect_thread"](1280,720)
        self.assertEqual(events,[("model",[320,240]),"copy","release","draw","deinit"])
        canvas=ns["Display"].shown[-1]
        self.assertEqual((canvas.width(),canvas.height()),(320,240))

    def test_display_resizer_formats_rebuilds_and_output_ownership(self):
        nodes = ast.parse((ROOT/"resources/libs/DisplayConfig.py").read_text()).body
        node = next(n for n in nodes if isinstance(n,ast.ClassDef) and n.name=="DisplayImage")
        ns={}
        exec(compile(ast.Module(body=[node],type_ignores=[]),"DisplayConfig.py","exec"),ns)
        instances=[]
        class Native:
            def __init__(self):
                self.builds=[]
                self.releases=0
                instances.append(self)
            def set_ai2d_dtype(self,*args): self.formats=args
            def resize(self,*args): pass
            def build(self,src,dst): self.builds.append((src,dst))
            def run(self,src): return types.SimpleNamespace(to_numpy=lambda:object())
            def deinit(self): self.releases+=1
        modules={
            "libs":types.ModuleType("libs"),
            "libs.AI2D":types.SimpleNamespace(Ai2d=Native),
            "nncase_runtime":types.SimpleNamespace(
                ai2d_format=types.SimpleNamespace(NCHW_FMT=0,RGB_packed=1),
                interp_method=types.SimpleNamespace(tf_bilinear=0),
                interp_mode=types.SimpleNamespace(half_pixel=0)),
            "ulab":types.ModuleType("ulab"),
            "ulab.numpy":types.SimpleNamespace(uint8=0),
            "image":types.SimpleNamespace(Image=Canvas,RGB888=1,ALLOC_REF=0),
        }
        modules["ulab"].numpy=modules["ulab.numpy"]
        with patch.dict("sys.modules",modules):
            for planar,shape in ((False,(480,640,3)),(True,(3,480,640))):
                obj=ns["DisplayImage"]([320,240],planar=planar)
                arr=types.SimpleNamespace(shape=shape)
                first=obj.run(arr)
                second=obj.run(arr)
                self.assertEqual(len(instances[-1].builds),1)
                self.assertEqual(instances[-1].builds[0],([1]+list(shape),[1,240,320,3]))
                self.assertEqual(instances[-1].formats[:2],(0 if planar else 1,1))
                self.assertIsNot(first.data,second.data)
                obj.deinit()
                self.assertEqual(instances[-1].releases,1)
            class Failing(Native):
                def set_ai2d_dtype(self,*args): raise RuntimeError("dtype")
            modules["libs.AI2D"].Ai2d=Failing
            with self.assertRaisesRegex(RuntimeError,"dtype"):
                ns["DisplayImage"]([320,240])
            self.assertEqual(instances[-1].releases,1)

    def test_app_center_auto_and_explicit_display_config(self):
        path=EXAMPLES/"28-APP_CENTER/main.py"
        fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="main")
        block=next(n for n in fn.body if isinstance(n,ast.Try)).body
        end=next(i for i,n in enumerate(block) if isinstance(n,ast.Assign)
                 and ast.unparse(n.targets[0])=="config.ui_layout")
        code=compile(ast.Module(body=block[:end],type_ignores=[]),str(path),"exec")
        for panel in (None,Display.LT9611):
            ns=self.namespace((640,480))
            ns.update(config=types.SimpleNamespace(DISPLAY_TYPE=panel,DISPLAY_WIDTH=0,DISPLAY_HEIGHT=0),
                      i18n=types.SimpleNamespace(init=lambda:None))
            exec(code,ns)
            self.assertEqual(ns["Display"].calls[-1][0],Display.ST7701 if panel is None else panel)
            self.assertEqual((ns["config"].DISPLAY_WIDTH,ns["config"].DISPLAY_HEIGHT),(640,480))
            self.assertTrue(ns["display_ready"])

    def test_lvgl_sidebar_stays_inside_actual_screen(self):
        path=EXAMPLES/"21-AI-With-Others/ai_lvgl.py"
        fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)
                and n.name=="user_gui_init")
        for w,h in ((320,240),(640,480),(800,480),(1920,1080)):
            sidebar,first,second=MagicMock(),MagicMock(),MagicMock()
            lv=MagicMock()
            lv.obj.return_value=sidebar
            lv.btn.side_effect=[first,second]
            ns=dict(lv=lv,DISPLAY_WIDTH=w,DISPLAY_HEIGHT=h,
                    btn_clicked_yolo_det=lambda:None,btn_clicked_face_det=lambda:None)
            exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),"exec"),ns)
            ns["user_gui_init"]()
            sidebar.set_size.assert_called_once_with(100,h)
            sidebar.set_pos.assert_called_once_with(w-100,0)
            first.set_pos.assert_called_once_with(w-95,20)
            second.set_pos.assert_called_once_with(w-95,75)

    def test_xiaozhi_initializes_display_before_sensor_and_bounds_keyboard(self):
        path=EXAMPLES/"26-xiaozhi/lvgl_ai.py"
        cls=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.ClassDef) and n.name=="XiaoZhi_UI")
        methods=[n for n in cls.body if isinstance(n,ast.FunctionDef)
                 and n.name in ("media_init","create_register_ui")]
        for size in ((320,240),(640,480),(800,480),(480,800),(1920,1080)):
            ns=self.namespace(size)
            ns["_thread"]=types.SimpleNamespace(start_new_thread=lambda *a:None)
            exec(compile(ast.Module(body=methods,type_ignores=[]),str(path),"exec"),ns)
            ui=types.SimpleNamespace(display_mode="auto",requested_display_size=None,
                                     rgb888p_size=[1280,720],face_det_thread=lambda:None,
                                     scr=None,chinese_font=None,on_confirm_click=lambda:None,
                                     on_exit_click=lambda:None)
            ns["media_init"](ui)
            self.assertEqual((ui.DISPLAY_WIDTH,ui.DISPLAY_HEIGHT),size)
            self.assertEqual((ns["sensors"][0].frames[0]["w"],ns["sensors"][0].frames[0]["h"]),size)
            panel,buttons,input_box,keyboard=MagicMock(),MagicMock(),MagicMock(),MagicMock()
            lv=MagicMock()
            lv.obj.side_effect=[panel,buttons]
            lv.textarea.return_value=input_box
            lv.keyboard.return_value=keyboard
            ns["lv"]=lv
            ns["create_register_ui"](ui)
            panel_w,panel_h=panel.set_size.call_args.args
            self.assertLessEqual(panel_w,size[0]-24)
            self.assertLessEqual(panel_h,size[1]-24)
            input_w,input_h=input_box.set_size.call_args.args
            kb_w,kb_h=keyboard.set_size.call_args.args
            buttons_w,buttons_h=buttons.set_size.call_args.args
            self.assertEqual((input_w,kb_w,buttons_w),(panel_w-16,)*3)
            self.assertGreater(kb_h,0)
            self.assertEqual(input_h+kb_h+buttons_h+16+12,panel_h)

    def test_logo_resizes_before_display_and_releases_helper(self):
        path=EXAMPLES/"16-AI-Cube/DataCollectionCamera.py"
        fn=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="show_logo")
        ns=self.namespace((320,240))
        events=[]
        class Logo(Canvas):
            def __init__(self,path): super().__init__(800,480)
            def to_rgb888(self): return self
        class Resize:
            def __init__(self,size): self.size=size
            def run(self,array): return Canvas(*self.size)
            def deinit(self): events.append("deinit")
        ns.update(DISPLAY_WIDTH=320,DISPLAY_HEIGHT=240,LOGO_FILE="/logo",
                  image=types.SimpleNamespace(Image=Logo),DisplayImage=Resize)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),"exec"),ns)
        ns["show_logo"]()
        self.assertEqual(ns["Display"].shown[-1].width(),320)
        self.assertEqual(events,["deinit"])

    def test_all_pipeline_examples_share_configuration(self):
        count=0
        for folder in EXAMPLES.iterdir():
            if folder.name[:2] not in ("05","16","18","19","20","21","22","28"):
                continue
            for path in folder.glob("*.py"):
                tree=ast.parse(path.read_text())
                pipelines=[n for n in ast.walk(tree) if isinstance(n,ast.Call)
                           and isinstance(n.func,ast.Name) and n.func.id=="PipeLine"]
                if not pipelines: continue
                count+=1
                modes=[n.value.value for n in ast.walk(tree) if isinstance(n,ast.Assign)
                       and any(isinstance(t,ast.Name) and t.id=="display_mode" for t in n.targets)
                       and isinstance(n.value,ast.Constant)]
                self.assertEqual(modes,["auto"],path.name)
                for call in pipelines:
                    self.assertIn("display_size",[k.arg for k in call.keywords],path.name)
        self.assertEqual(count,68)


if __name__=="__main__":
    unittest.main()
