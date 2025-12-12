import uctypes
import time
from mpp import *
from mpp.vb import *
from mpp.sys import *
from media.media import *

DIV_NUM        = 5
paInt16        = 0        #: 16 bit int
paInt24        = 1        #: 24 bit int
paInt32        = 2        #: 32 bit int

LEFT        = const(1)
RIGHT       = const(2)
LEFT_RIGHT  = const(3)

AUDIO_3A_ENABLE_NONE  = const(0)
AUDIO_3A_ENABLE_ANS   = const(1)
AUDIO_3A_ENABLE_AGC   = const(2)
AUDIO_3A_ENABLE_AEC   = const(4)

USE_EXTERN_BUFFER_CONFIG = True

DEVICE_I2S = "i2s"
DEVICE_PDM = "pdm"

def _vb_pool_init(frames_per_buffer=1024):
    config = k_vb_config()
    config.max_pool_cnt = 2
    config.comm_pool[0].blk_cnt = 50
    config.comm_pool[0].blk_size = int(frames_per_buffer * 2 * 4)
    config.comm_pool[0].mode = VB_REMAP_MODE_NOCACHE

    config.comm_pool[1].blk_cnt = 2
    config.comm_pool[1].blk_size =  int(frames_per_buffer * 2 * 2 * 4)
    config.comm_pool[1].mode = VB_REMAP_MODE_NOCACHE

    blk_total_size = 0
    for i in range(2):
        blk_total_size += config.comm_pool[i].blk_cnt * config.comm_pool[i].blk_size

    print(("mmz block total size: %.2fM")%(blk_total_size/1024/1024))

    ret = kd_mpi_vb_set_config(config)
    if (ret != 0):
        raise ValueError(("kd_mpi_vb_set_config failed:%d")%(ret))

    ret = kd_mpi_vb_init()
    if (ret != 0):
        raise ValueError(("kd_mpi_vb_int failed:%d")%(ret))

def _vb_pool_deinit():
    ret = kd_mpi_vb_exit()
    if (ret != 0):
        raise ValueError(("kd_mpi_vb_exit failed:%d")%(ret))

def _vb_buffer_init(frames_per_buffer=1024):
    config = k_vb_config()
    config.max_pool_cnt = 2
    config.comm_pool[0].blk_cnt = 50
    config.comm_pool[0].blk_size = int(frames_per_buffer * 2 * 4)
    config.comm_pool[0].mode = VB_REMAP_MODE_NOCACHE

    config.comm_pool[1].blk_cnt = 2
    config.comm_pool[1].blk_size =  int(frames_per_buffer * 2 * 2 * 4)
    config.comm_pool[1].mode = VB_REMAP_MODE_NOCACHE

    MediaManager._config(config)

class Stream:
    def __init__(self,
                PA_manager,
                rate,
                channels,
                format,
                input=False,
                output=False,
                input_device_index=None,
                output_device_index=None,
                enable_codec=True,
                frames_per_buffer=1024,
                start=True,
                stream_callback=None):

        if ((input == False and output == False) or (input == True and output == True)):
            raise ValueError("Must specify an input or output " + "stream.")

        # remember parent
        self._parent = PA_manager
        # remember if we are an: input, output (or both)
        self._is_input = input
        self._is_output = output

        # are we running?
        self._is_running = start

        # remember some parameters
        self._rate = rate
        self._channels = channels
        self._format = format
        self._frames_per_buffer = frames_per_buffer

        self._input_device_index = input_device_index
        self._output_device_index = output_device_index
        self._enable_codec = enable_codec
        self._stream_callback = stream_callback
        self.device_type = DEVICE_I2S

    def start_stream(self):
        pass

    def stop_stream(self):
        pass

    def read(self):
        pass

    def write(self, data):
        pass

    def close(self):
        pass

    def volume(self,vol = None, channel = LEFT_RIGHT):
        pass

    def swap_left_right(self, state = True):
        pass

    def enable_audio3a(self, audio3a_value):
        pass

class Write_stream(Stream):
    dev_chn_enable = {0:False,1:False}
    def __init__(self,
                PA_manager,
                rate,
                channels,
                format,
                input=False,
                output=False,
                input_device_index=None,
                output_device_index=None,
                enable_codec=True,
                frames_per_buffer=1024,
                start=True,
                stream_callback=None):
        super().__init__(PA_manager,rate,channels,format,input,output,input_device_index,output_device_index,enable_codec,frames_per_buffer,start,stream_callback)
        if (None == self._output_device_index or 0 == self._output_device_index):
            self._ao_dev = 0
            self._ao_chn = 0
        elif (1 == self._output_device_index):
            self._ao_dev = 0
            self._ao_chn = 1
        else:
            self._ao_dev = 0
            self._ao_chn = 0

        self._audio_frame = k_audio_frame()
        self._audio_handle = -1
        self._start_stream = False
        PA_manager.initialize(frames_per_buffer)
        if (self._is_running):
            self.start_stream()

    def _init_audio_frame(self):
        if (self._audio_handle == -1):
            frame_size = int(self._frames_per_buffer*self._channels*2)
            self._audio_handle = kd_mpi_vb_get_block(-1, frame_size, "")
            if (self._audio_handle == -1):
                raise ValueError("kd_mpi_vb_get_block failed")

            self._audio_frame.len = frame_size
            self._audio_frame.pool_id = kd_mpi_vb_handle_to_pool_id(self._audio_handle)
            self._audio_frame.phys_addr = kd_mpi_vb_handle_to_phyaddr(self._audio_handle)
            self._audio_frame.virt_addr = kd_mpi_sys_mmap(self._audio_frame.phys_addr, frame_size)

    def _deinit_audio_frame(self):
        if (self._audio_handle != -1):
            kd_mpi_vb_release_block(self._audio_handle)
            self._audio_handle = -1

    def start_stream(self):
        if (not self._start_stream):
            self._init_audio_frame()
            #init device only once
            if (not (Write_stream.dev_chn_enable[0] and Write_stream.dev_chn_enable[1])):
                aio_dev_attr = k_aio_dev_attr()
                aio_dev_attr.audio_type = KD_AUDIO_OUTPUT_TYPE_I2S
                aio_dev_attr.kd_audio_attr.i2s_attr.sample_rate = self._rate
                aio_dev_attr.kd_audio_attr.i2s_attr.bit_width = self._format
                aio_dev_attr.kd_audio_attr.i2s_attr.chn_cnt = 2
                aio_dev_attr.kd_audio_attr.i2s_attr.snd_mode = self._channels==1 and KD_AUDIO_SOUND_MODE_MONO or KD_AUDIO_SOUND_MODE_STEREO
                aio_dev_attr.kd_audio_attr.i2s_attr.i2s_mode = K_STANDARD_MODE
                aio_dev_attr.kd_audio_attr.i2s_attr.frame_num = DIV_NUM
                aio_dev_attr.kd_audio_attr.i2s_attr.point_num_per_frame = self._frames_per_buffer
                if self._enable_codec:
                    aio_dev_attr.kd_audio_attr.i2s_attr.i2s_type = K_AIO_I2STYPE_INNERCODEC
                else:
                    aio_dev_attr.kd_audio_attr.i2s_attr.i2s_type = K_AIO_I2STYPE_EXTERN

                ret = kd_mpi_ao_set_pub_attr(self._ao_dev, aio_dev_attr)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ao_set_pub_attr failed:%d")%(ret))

                ret = kd_mpi_ao_enable(self._ao_dev)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ao_enable failed:%d")%(ret))

                Write_stream.dev_chn_enable[self._ao_chn] = True

            ret = kd_mpi_ao_enable_chn(self._ao_dev, self._ao_chn)
            if (0 != ret):
                raise ValueError(("kd_mpi_ao_enable_chn failed:%d")%(ret))

            import os
            brd = os.uname()[-1]
            if brd == "k230_canmv_lckfb" or brd == "k230_canmv_yahboom":
                self.swap_left_right()
            del brd
            del os

            self._start_stream = True

    def stop_stream(self):
        if (self._start_stream):
            ret = kd_mpi_ao_disable_chn(self._ao_dev, self._ao_chn)
            if (0 != ret):
                raise ValueError(("kd_mpi_ao_disable_chn failed:%d")%(ret))

            #deinit device only once
            if (Write_stream.dev_chn_enable[0] ^ Write_stream.dev_chn_enable[1]):
                ret = kd_mpi_ao_disable(self._ao_dev)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ao_disable failed:%d")%(ret))

            self._deinit_audio_frame()
            Write_stream.dev_chn_enable[self._ao_chn] = False
            self._start_stream = False

    def write(self,data):
        if (self._start_stream):
            uctypes.bytearray_at(self._audio_frame.virt_addr,  self._audio_frame.len)[:] = data
            return kd_mpi_ao_send_frame(self._ao_dev, self._ao_chn, self._audio_frame, 1000)

    def close(self):
        self._is_running = False
        self._parent._remove_stream(self)

    def volume(self, vol = None, channel = LEFT_RIGHT):
        if vol is None:
            return ao_get_vol()
        else:
            return ao_set_vol(vol, channel)

    def swap_left_right(self, state = True):
        return ao_swap_left_right(state)

class Read_stream(Stream):
    def __init__(self,
                PA_manager,
                rate,
                channels,
                format,
                input=False,
                output=False,
                input_device_index=None,
                output_device_index=None,
                enable_codec=True,
                frames_per_buffer=1024,
                start=True,
                stream_callback=None):
        super().__init__(PA_manager,rate,channels,format,input,output,input_device_index,output_device_index,enable_codec,frames_per_buffer,start,stream_callback)
        #i2s device 0;pdm device 1
        if (None == self._input_device_index or 0 == self._input_device_index):
            self._ai_dev = 0
            self._ai_chn = 0
        elif (1 == self._input_device_index):
            self._ai_dev = 1
            self._ai_chn = 0
            self._pdm_chncnt = self._channels // 2
            self.device_type = DEVICE_PDM
        else:
            self._ai_dev = 0
            self._ai_chn = 0

        self._audio_frame = k_audio_frame()
        self._start_stream = False
        PA_manager.initialize(frames_per_buffer)
        if (self._is_running):
            self.start_stream()

    def start_stream(self):
        if (not self._start_stream):
            #init device only once
            if (self.device_type == DEVICE_I2S):
                aio_dev_attr = k_aio_dev_attr()
                aio_dev_attr.audio_type = KD_AUDIO_INPUT_TYPE_I2S
                aio_dev_attr.kd_audio_attr.i2s_attr.sample_rate = self._rate
                aio_dev_attr.kd_audio_attr.i2s_attr.bit_width = self._format
                aio_dev_attr.kd_audio_attr.i2s_attr.chn_cnt = 2
                aio_dev_attr.kd_audio_attr.i2s_attr.snd_mode = self._channels==1 and KD_AUDIO_SOUND_MODE_MONO or KD_AUDIO_SOUND_MODE_STEREO
                aio_dev_attr.kd_audio_attr.i2s_attr.i2s_mode = K_STANDARD_MODE
                aio_dev_attr.kd_audio_attr.i2s_attr.frame_num = DIV_NUM
                aio_dev_attr.kd_audio_attr.i2s_attr.point_num_per_frame = self._frames_per_buffer

                if self._enable_codec:
                    aio_dev_attr.kd_audio_attr.i2s_attr.i2s_type = K_AIO_I2STYPE_INNERCODEC
                else:
                    aio_dev_attr.kd_audio_attr.i2s_attr.i2s_type = K_AIO_I2STYPE_EXTERN

                ret = kd_mpi_ai_set_pub_attr(self._ai_dev, aio_dev_attr)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ai_set_pub_attr failed:%d")%(ret))

                ret = kd_mpi_ai_enable(self._ai_dev)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ai_enable failed:%d")%(ret))

                ret = kd_mpi_ai_enable_chn(self._ai_dev, self._ai_chn)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ai_enable_chn failed:%d")%(ret))
            elif (self.device_type == DEVICE_PDM):
                aio_dev_attr = k_aio_dev_attr()
                aio_dev_attr.audio_type = KD_AUDIO_INPUT_TYPE_PDM
                aio_dev_attr.kd_audio_attr.pdm_attr.sample_rate = self._rate
                aio_dev_attr.kd_audio_attr.pdm_attr.bit_width = self._format
                aio_dev_attr.kd_audio_attr.pdm_attr.chn_cnt = self._pdm_chncnt
                aio_dev_attr.kd_audio_attr.pdm_attr.snd_mode = KD_AUDIO_SOUND_MODE_STEREO
                aio_dev_attr.kd_audio_attr.pdm_attr.frame_num = DIV_NUM
                aio_dev_attr.kd_audio_attr.pdm_attr.pdm_oversample = KD_AUDIO_PDM_INPUT_OVERSAMPLE_64
                aio_dev_attr.kd_audio_attr.pdm_attr.point_num_per_frame = self._frames_per_buffer

                ret = kd_mpi_ai_set_pub_attr(self._ai_dev, aio_dev_attr)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ai_set_pub_attr failed:%d")%(ret))

                ret = kd_mpi_ai_enable(self._ai_dev)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ai_enable failed:%d")%(ret))

                for i in range(self._pdm_chncnt):
                    ret = kd_mpi_ai_enable_chn(self._ai_dev, i)
                    if (0 != ret):
                        raise ValueError(("kd_mpi_ai_set_pdm_clk failed:%d")%(ret))

            self._start_stream = True

    def stop_stream(self):
        if (self._start_stream):
            if (self.device_type == DEVICE_I2S):
                ret = kd_mpi_ai_disable_chn(self._ai_dev, self._ai_chn)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ai_disable_chn failed:%d")%(ret))
            elif (self.device_type == DEVICE_PDM):
                for i in range(self._pdm_chncnt - 1, -1, -1):
                    ret = kd_mpi_ai_disable_chn(self._ai_dev, i)
                    if (0 != ret):
                        raise ValueError(("kd_mpi_ai_disable_chn failed:%d")%(ret))

            #deinit device only once
            ret = kd_mpi_ai_disable(self._ai_dev)
            if (0 != ret):
                raise ValueError(("kd_mpi_ai_disable failed:%d")%(ret))

            self._start_stream = False

    def read(self,chn=0,block=True):
        if (self._start_stream):
            if (self.device_type == DEVICE_I2S):
                ret = kd_mpi_ai_get_frame(self._ai_dev, self._ai_chn, self._audio_frame, 1000 if block else 1)
                if (0 == ret):
                    vir_data = kd_mpi_sys_mmap(self._audio_frame.phys_addr, self._audio_frame.len)
                    data = uctypes.bytes_at(vir_data,self._audio_frame.len)
                    kd_mpi_sys_munmap(vir_data,self._audio_frame.len)
                    kd_mpi_ai_release_frame(self._ai_dev, self._ai_chn, self._audio_frame)
                    return data
            elif (self.device_type == DEVICE_PDM):
                if (chn < 0 or chn >= self._pdm_chncnt):
                    raise ValueError("pdm chn %d error"%(chn))

                ret = kd_mpi_ai_get_frame(self._ai_dev, chn, self._audio_frame, 1000 if block else 1)
                if (0 == ret):
                    vir_data = kd_mpi_sys_mmap(self._audio_frame.phys_addr, self._audio_frame.len)
                    data = uctypes.bytes_at(vir_data,self._audio_frame.len)
                    kd_mpi_sys_munmap(vir_data,self._audio_frame.len)
                    kd_mpi_ai_release_frame(self._ai_dev, chn, self._audio_frame)
                    return data

    def close(self):
        self._is_running = False
        self._parent._remove_stream(self)

    def volume(self,vol = None, channel = LEFT_RIGHT):
        if vol is None:
            return ai_get_vol()
        else:
            return ai_set_vol(vol, channel)

    def swap_left_right(self, state = True):
        return ai_swap_left_right(state)

    def enable_audio3a(self, audio3a_value):
        aio_vqe_enable = k_ai_vqe_enable()
        if (audio3a_value & AUDIO_3A_ENABLE_ANS):
            aio_vqe_enable.ans_enable = True
        if (audio3a_value & AUDIO_3A_ENABLE_AGC):
            aio_vqe_enable.agc_enable = True
        if (audio3a_value & AUDIO_3A_ENABLE_AEC):
            aio_vqe_enable.aec_enable = True

        ret = kd_mpi_ai_set_vqe_attr(self._ai_dev, self._ai_chn,aio_vqe_enable)
        if (0 != ret):
            raise ValueError(("kd_mpi_ai_get_vqe_attr failed:%d")%(ret))

        return ret

    def audio3a_send_far_echo_frame(self, frame_data,data_len):
        frame = k_audio_frame()
        handle = kd_mpi_vb_get_block(-1, data_len, "")
        phys_addr = kd_mpi_vb_handle_to_phyaddr(handle)
        vir_data = kd_mpi_sys_mmap(phys_addr, data_len)

        frame.len = data_len
        uctypes.bytearray_at(vir_data, frame.len)[:] = frame_data
        frame.phy_addr = phys_addr
        kd_mpi_sys_munmap(vir_data,frame.len)

        ret = kd_mpi_ai_send_far_echo_frame(self._ai_dev, self._ai_chn, frame,100)
        # del buffer
        kd_mpi_vb_release_block(handle)

        return ret

class PyAudio:
    #vb init flag
    _vb_init = False

    def __init__(self):
        """Initialize PortAudio."""
        self._streams = set()

    def initialize(self,frames_per_buffer=1024):
        if USE_EXTERN_BUFFER_CONFIG:
            if (False == PyAudio._vb_init):
                _vb_buffer_init(frames_per_buffer)
                PyAudio._vb_init = True
        else:
            if (False == PyAudio._vb_init):
                _vb_pool_init(frames_per_buffer)
                PyAudio._vb_init = True

    def terminate(self):
        """
        Terminate PortAudio.

        :attention: Be sure to call this method for every instance of
          this object to release PortAudio resources.
        """
        for stream in self._streams.copy():
            stream.close()

        self._streams = set()

        if USE_EXTERN_BUFFER_CONFIG:
            PyAudio._vb_init = False
        else:
            if(PyAudio._vb_init):
                _vb_pool_deinit()
                PyAudio._vb_init = False

    def open(self, *args, **kwargs):
        """
        Open a new stream. See constructor for
        :py:func:`Stream.__init__` for parameter details.

        :returns: A new :py:class:`Stream`
        """
        if (kwargs.get("output") == 1):
            stream = Write_stream(self, *args, **kwargs)
            self._streams.add(stream)
        else:
            stream = Read_stream(self, *args, **kwargs)
            self._streams.add(stream)

        return stream

    def close(self, stream):
        """
        Close a stream. Typically use :py:func:`Stream.close` instead.

        :param stream: An instance of the :py:class:`Stream` object.
        :raises ValueError: if stream does not exist.
        """

        if stream not in self._streams:
            raise ValueError("Stream `%s' not found" % str(stream))

        stream.close()

    def _remove_stream(self, stream):
        if stream in self._streams:
            self._streams.remove(stream)

    def get_sample_size(self, format):
        if (paInt16 == format):
            return 2
        elif (paInt24 == format):
            return 3
        elif (paInt32 == format):
            return 4
        else:
            return -1

    def get_format_from_width(self, width):
        if width == 2:
            return paInt16
        elif width == 3:
            return paInt24
        elif width == 4:
            return paInt32
        else:
            return -1
