from libs.PipeLine import ScopedTiming
import nncase_runtime as nn
import ulab.numpy as np

class Ai2d:
    """Manage AI2D preprocessing configuration, tensors and native resources."""
    def __init__(self,debug_mode=0):
        # 预处理ai2d
        """Create a native AI2D configuration with no built pipeline.

        Args:
            debug_mode (int): Enable timing output when greater than zero.

        Notes:
            Configure operations and call build() before run(). Call deinit()
            when preprocessing is no longer needed.
        """
        self.debug_mode = debug_mode
        self._output_type = np.uint8
        self._pending_release = []
        self.ai2d = None
        self.ai2d=nn.ai2d()
        # ai2d计算过程中的输入输出数据类型，输入输出数据格式
        # self.ai2d.set_dtype(nn.ai2d_format.NCHW_FMT,nn.ai2d_format.NCHW_FMT,np.uint8, np.uint8)
        # ai2d构造器
        self.ai2d_builder=None
        # ai2d输入tensor对象
        self.ai2d_input_tensor=None
        # ai2d输出tensor对象
        self.ai2d_output_tensor=None
        self.debug_mode=debug_mode

    # 设置ai2d计算过程中的输入输出数据类型，输入输出数据格式
    def set_ai2d_dtype(self,input_format,output_format,input_type,output_type):
        """Set input/output layouts and dtypes for subsequent builds.

        Args:
            input_format (int): nncase_runtime AI2D input format constant.
            output_format (int): nncase_runtime AI2D output format constant.
            input_type (type): ulab.numpy input dtype.
            output_type (type): ulab.numpy output dtype.

        Returns:
            None.
        """
        self.ai2d.set_dtype(input_format,output_format,input_type,output_type)
        self._output_type = output_type

    # 预处理crop函数
    # start_x：宽度方向的起始像素,int类型
    # start_y: 高度方向的起始像素,int类型
    # width: 宽度方向的crop长度,int类型
    # height: 高度方向的crop长度,int类型
    def crop(self,start_x,start_y,width,height):
        """Enable cropping for subsequent builds.

        Args:
            start_x (int): Left crop coordinate in input pixels.
            start_y (int): Top crop coordinate in input pixels.
            width (int): Crop width in pixels.
            height (int): Crop height in pixels.

        Returns:
            None.
        """
        with ScopedTiming("init ai2d crop",self.debug_mode > 0):
            self.ai2d.set_crop_param(True,start_x,start_y,width,height)

    # 预处理shift函数
    # shift_val:右移的比特数,int类型
    def shift(self,shift_val):
        """Enable shifting for subsequent builds.

        Args:
            shift_val (int): Native AI2D shift value.

        Returns:
            None.
        """
        with ScopedTiming("init ai2d shift",self.debug_mode > 0):
            self.ai2d.set_shift_param(True,shift_val)

    # 预处理pad函数
    # paddings:各个维度的padding, size=8，分别表示dim0到dim4的前后padding的个数，其中dim0/dim1固定配置{0, 0},list类型
    # pad_mode:只支持pad constant，配置0即可,int类型
    # pad_val:每个channel的padding value,list类型
    def pad(self,paddings,pad_mode,pad_val):
        """Enable padding for subsequent builds.

        Args:
            paddings (list): Eight before/after padding values for the four tensor dimensions.
            pad_mode (int): Native AI2D padding mode.
            pad_val (list): Per-channel padding values.

        Returns:
            None.
        """
        with ScopedTiming("init ai2d pad",self.debug_mode > 0):
            self.ai2d.set_pad_param(True,paddings,pad_mode,pad_val)

    # 预处理resize函数
    # interp_method:resize插值方法，ai2d_interp_method类型
    # interp_mode:resize模式，ai2d_interp_mode类型
    def resize(self,interp_method,interp_mode):
        """Enable resizing for subsequent builds.

        Args:
            interp_method (int): nncase_runtime interpolation method constant.
            interp_mode (int): nncase_runtime interpolation coordinate mode.

        Returns:
            None.
        """
        with ScopedTiming("init ai2d resize",self.debug_mode > 0):
            self.ai2d.set_resize_param(True,interp_method,interp_mode)

    # 预处理affine函数
    # interp_method:Affine采用的插值方法,ai2d_interp_method类型
    # cord_round:整数边界0或者1,uint32_t类型
    # bound_ind:边界像素模式0或者1,uint32_t类型
    # bound_val:边界填充值,uint32_t类型
    # bound_smooth:边界平滑0或者1,uint32_t类型
    # M:仿射变换矩阵对应的vector，仿射变换为Y=[a_0, a_1; a_2, a_3] \cdot  X + [b_0, b_1] $, 则  M=[a_0,a_1,b_0,a_2,a_3,b_1 ],list类型
    def affine(self,interp_method,crop_round,bound_ind,bound_val,bound_smooth,M):
        """Enable an affine transform for subsequent builds.

        Args:
            interp_method (int): nncase_runtime interpolation method constant.
            crop_round (int): Native affine coordinate rounding mode.
            bound_ind (int): Native affine boundary mode.
            bound_val (int): Affine out-of-bounds fill value.
            bound_smooth (int): Native affine boundary smoothing setting.
            M (list): Affine coefficients [a00, a01, b0, a10, a11, b1].

        Returns:
            None.
        """
        with ScopedTiming("init ai2d affine",self.debug_mode > 0):
            self.ai2d.set_affine_param(True,interp_method,crop_round,bound_ind,bound_val,bound_smooth,M)

    # 构造ai2d预处理器
    def build(self,ai2d_input_shape,ai2d_output_shape,input_np=None):
        """Build preprocessing and allocate its reusable output tensor.

        Args:
            ai2d_input_shape (list): Four-dimensional input shape in the configured layout.
            ai2d_output_shape (list): Four-dimensional output shape in the configured layout.
            input_np (object or None): Reserved compatibility argument; unused.

        Returns:
            None.

        Notes:
            input_np is reserved for call compatibility and is not used.
            Construction failures preserve the previous configuration. After the
            new configuration is committed, retirement of old resources can
            still raise; failed releases are retained for retry.
        """
        with ScopedTiming("ai2d build",self.debug_mode > 0):
            self._release_pending()
            new_builder = self.ai2d.build(ai2d_input_shape, ai2d_output_shape)
            try:
                # 定义ai2d输出数据(即kmodel的输入数据，所以数据分辨率和模型的input_size一致)，并转换成tensor
                output_data = np.ones((ai2d_output_shape[0],ai2d_output_shape[1],ai2d_output_shape[2],ai2d_output_shape[3]),dtype=self._output_type)
                new_output_tensor = nn.from_numpy(output_data)
            except BaseException:
                try:
                    self._retire(new_builder)
                except Exception:
                    pass
                raise

            old_builder = self.ai2d_builder
            old_input_tensor = self.ai2d_input_tensor
            old_output_tensor = self.ai2d_output_tensor
            self.ai2d_builder = new_builder
            self.ai2d_input_tensor = None
            self.ai2d_output_tensor = new_output_tensor

            cleanup_error = None
            for value in (old_builder, old_input_tensor, old_output_tensor):
                try:
                    self._retire(value)
                except Exception as error:
                    if cleanup_error is None:
                        cleanup_error = error
            if cleanup_error is not None:
                raise cleanup_error

    # 使用ai2d完成预处理
    def run(self,input_np):
        """Preprocess an array with the built AI2D pipeline.

        Args:
            input_np (ulab.numpy.ndarray): Input array matching the configured shape and dtype.

        Returns:
            nncase_runtime.runtime_tensor: AI2D-owned reusable output tensor.

        Notes:
            Call build() first. Later runs overwrite the returned tensor; the
            caller must not release it. Keep the input backing storage valid
            while native processing uses it.
        """
        if self._pending_release:
            self._release_pending()
        new_input_tensor = nn.from_numpy(input_np)
        # 运行ai2d做初始化
        try:
            self.ai2d_builder.run(new_input_tensor, self.ai2d_output_tensor)
        except BaseException:
            try:
                self._retire(new_input_tensor)
            except Exception as error:
                print("Ai2d input rollback failed:", error)
            raise
        old_input_tensor = self.ai2d_input_tensor
        self.ai2d_input_tensor = new_input_tensor
        self._retire(old_input_tensor)
        return self.ai2d_output_tensor

    def deinit(self):
        """Release the builder, tensors, AI2D and pending resources.

        Returns:
            None.

        Raises:
            Exception: The first release error after all resources are attempted.

        Notes:
            Successful releases are safe to repeat; failed resources are kept
            for retry on a later cleanup call.
        """
        cleanup_error = None
        for name in ("ai2d_builder", "ai2d_input_tensor", "ai2d_output_tensor", "ai2d"):
            native_obj = getattr(self, name, None)
            setattr(self, name, None)
            try:
                self._release_native(native_obj)
            except Exception as error:
                setattr(self, name, native_obj)
                if cleanup_error is None:
                    cleanup_error = error
        try:
            self._release_pending()
        except Exception as error:
            if cleanup_error is None:
                cleanup_error = error
        if cleanup_error is not None:
            raise cleanup_error

    def _retire(self, value):
        """Release a replaced resource, retaining it if release fails.

        Args:
            value (object or None): Native resource whose optional release() method is called.

        Returns:
            None.

        Raises:
            Exception: The resource release error; the resource is queued for retry.
        """
        try:
            self._release_native(value)
        except Exception:
            self._pending_release.append(value)
            raise

    def _release_pending(self):
        """Retry all resources whose earlier release failed.

        Returns:
            None.

        Raises:
            Exception: The first error after attempting all pending releases.
        """
        pending = self._pending_release
        if not pending:
            return
        self._pending_release = []
        error = None
        for value in pending:
            try:
                self._retire(value)
            except Exception as exc:
                if error is None:
                    error = exc
        if error is not None:
            raise error

    @staticmethod
    def _release_native(value):
        """Call a native resource's release method when available.

        Args:
            value (object or None): Native resource whose optional release() method is called.

        Returns:
            None.

        Notes:
            None and objects without a callable release() are ignored.
        """
        if value is None:
            return
        release = getattr(value, "release", None)
        if callable(release):
            release()
