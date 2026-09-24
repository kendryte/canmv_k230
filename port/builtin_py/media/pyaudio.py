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

DEVICE_I2S = "i2s"
DEVICE_PDM = "pdm"

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
        """Initialize the object.
        Args:
            PA_manager: PyAudio object managing this stream.
            rate: Audio sample rate in Hz.
            channels: Number of audio channels.
            format: Audio sample format.
            input: Whether to create an input stream.
            output: Whether to create an output stream.
            input_device_index: Input device index.
            output_device_index: Output device index.
            enable_codec: Whether to use the on-board audio codec.
            frames_per_buffer: Number of samples in each audio buffer.
            start: Whether to start immediately after creation.
            stream_callback: Audio stream callback function.
        """

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
        """Start the audio stream.
        """
        pass

    def stop_stream(self):
        """Stop the audio stream.
        """
        pass

    def read(self):
        """Read data from the input.
        """
        pass

    def write(self, data):
        """Write data to the output.
        Args:
            data: Media data to write.
        """
        pass

    def close(self):
        """Close the object and release resources.
        """
        pass

    def volume(self,vol = None, channel = LEFT_RIGHT):
        """Get or set the volume.
        Args:
            vol: Volume level; omit to read the current volume.
            channel: Audio channel to operate on.
        """
        pass

    def swap_left_right(self, state = True):
        """Swap the left and right audio channels.
        Args:
            state: State to set.
        """
        pass

    def enable_audio3a(self, audio3a_value):
        """Configure audio 3A processing.
        Args:
            audio3a_value: Audio 3A feature bit mask.
        """
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
        """Initialize the object.
        Args:
            PA_manager: PyAudio object managing this stream.
            rate: Audio sample rate in Hz.
            channels: Number of audio channels.
            format: Audio sample format.
            input: Whether to create an input stream.
            output: Whether to create an output stream.
            input_device_index: Input device index.
            output_device_index: Output device index.
            enable_codec: Whether to use the on-board audio codec.
            frames_per_buffer: Number of samples in each audio buffer.
            start: Whether to start immediately after creation.
            stream_callback: Audio stream callback function.
        """
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
        self._frame_poolid = -1

        if (self._is_running):
            self.start_stream()

    def _init_audio_frame(self):
        """Internal helper method.
        """
        if (self._audio_handle == -1):
            pool_config = k_vb_pool_config()
            pool_config.blk_cnt = 1
            pool_config.blk_size = int(self._frames_per_buffer*self._channels*2)
            pool_config.mode = VB_REMAP_MODE_NOCACHE
            self._frame_poolid = kd_mpi_vb_create_pool(pool_config)

            frame_size = int(self._frames_per_buffer*self._channels*2)
            self._audio_handle = kd_mpi_vb_get_block(self._frame_poolid, frame_size, "")
            if (self._audio_handle == -1):
                raise ValueError("kd_mpi_vb_get_block failed")

            self._audio_frame.len = frame_size
            self._audio_frame.pool_id = kd_mpi_vb_handle_to_pool_id(self._audio_handle)
            self._audio_frame.phys_addr = kd_mpi_vb_handle_to_phyaddr(self._audio_handle)
            self._audio_frame.virt_addr = kd_mpi_sys_mmap(self._audio_frame.phys_addr, frame_size)

    def _deinit_audio_frame(self):
        """Internal helper method.
        """
        if (self._audio_handle != -1):
            kd_mpi_vb_release_block(self._audio_handle)
            self._audio_handle = -1

        if (self._frame_poolid != -1):
            kd_mpi_vb_destory_pool(self._frame_poolid)
            self._frame_poolid = -1

    def start_stream(self):
        """Start the audio stream.
        """
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
        """Stop the audio stream.
        """
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
        """Write data to the output.
        Args:
            data: Media data to write.
        """
        if (self._start_stream):
            uctypes.bytearray_at(self._audio_frame.virt_addr,  self._audio_frame.len)[:] = data
            return kd_mpi_ao_send_frame(self._ao_dev, self._ao_chn, self._audio_frame, 1000)

    def close(self):
        """Close the object and release resources.
        """
        self.stop_stream()
        self._is_running = False
        self._parent._remove_stream(self)

    def volume(self, vol = None, channel = LEFT_RIGHT):
        """Get or set the volume.
        Args:
            vol: Volume level; omit to read the current volume.
            channel: Audio channel to operate on.
        """
        if vol is None:
            return ao_get_vol()
        else:
            return ao_set_vol(vol, channel)

    def swap_left_right(self, state = True):
        """Swap the left and right audio channels.
        Args:
            state: State to set.
        """
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
        """Initialize the object.
        Args:
            PA_manager: PyAudio object managing this stream.
            rate: Audio sample rate in Hz.
            channels: Number of audio channels.
            format: Audio sample format.
            input: Whether to create an input stream.
            output: Whether to create an output stream.
            input_device_index: Input device index.
            output_device_index: Output device index.
            enable_codec: Whether to use the on-board audio codec.
            frames_per_buffer: Number of samples in each audio buffer.
            start: Whether to start immediately after creation.
            stream_callback: Audio stream callback function.
        """
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

        if (self._is_running):
            self.start_stream()

    def start_stream(self):
        """Start the audio stream.
        """
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
        """Stop the audio stream.
        """
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

    def _read_frame(self, ai_chn, block):
        """Internal helper method. Fetch one frame and always return its block.

        Args:
            ai_chn: Audio input channel to read from.
            block: Whether to block while waiting for data.

        Returns:
            bytes or None: Captured samples, or None when no frame arrived.

        Notes:
            The block handed out by kd_mpi_ai_get_frame() comes from the shared
            VB pool and nothing tracks it, unlike a vicap frame which
            vb_mgmt_init() reclaims on the next run. A block that is never
            returned makes kd_mpi_vb_exit() fail on the following soft reset,
            and only a power cycle clears it. KeyboardInterrupt is delivered at
            a bytecode boundary once this blocking call has returned, which is
            exactly where a caller stopping the stream lands, so the release
            belongs in a finally block.
        """
        ret = -1
        try:
            ret = kd_mpi_ai_get_frame(self._ai_dev, ai_chn, self._audio_frame, 1000 if block else 10)
            if (0 != ret):
                return None

            vir_data = kd_mpi_sys_mmap(self._audio_frame.phys_addr, self._audio_frame.len)
            try:
                return uctypes.bytes_at(vir_data,self._audio_frame.len)
            finally:
                kd_mpi_sys_munmap(vir_data,self._audio_frame.len)
        finally:
            if (0 == ret):
                kd_mpi_ai_release_frame(self._ai_dev, ai_chn, self._audio_frame)

    def read(self,chn=0,block=True):
        """Read data from the input.
        Args:
            chn: Media channel number.
            block: Whether to block while waiting for data.
        """
        if (self._start_stream):
            if (self.device_type == DEVICE_I2S):
                return self._read_frame(self._ai_chn, block)
            elif (self.device_type == DEVICE_PDM):
                if (chn < 0 or chn >= self._pdm_chncnt):
                    raise ValueError("pdm chn %d error"%(chn))

                return self._read_frame(chn, block)

    def close(self):
        """Close the object and release resources.
        """
        self.stop_stream()
        self._is_running = False
        self._parent._remove_stream(self)

    def volume(self,vol = None, channel = LEFT_RIGHT):
        """Get or set the volume.
        Args:
            vol: Volume level; omit to read the current volume.
            channel: Audio channel to operate on.
        """
        if vol is None:
            return ai_get_vol()
        else:
            return ai_set_vol(vol, channel)

    def swap_left_right(self, state = True):
        """Swap the left and right audio channels.
        Args:
            state: State to set.
        """
        return ai_swap_left_right(state)

    def enable_audio3a(self, audio3a_value):
        """Configure audio 3A processing.
        Args:
            audio3a_value: Audio 3A feature bit mask.
        """
        aio_vqe_enable = k_ai_vqe_enable()
        if (audio3a_value & AUDIO_3A_ENABLE_ANS):
            aio_vqe_enable.ans_enable = True
        if (audio3a_value & AUDIO_3A_ENABLE_AGC):
            aio_vqe_enable.agc_enable = True
        if (audio3a_value & AUDIO_3A_ENABLE_AEC):
            aio_vqe_enable.aec_enable = True

        if (self.device_type == DEVICE_PDM):
            # PDM has multiple channels, set VQE for each
            for i in range(self._pdm_chncnt):
                ret = kd_mpi_ai_set_vqe_attr(self._ai_dev, i, aio_vqe_enable)
                if (0 != ret):
                    raise ValueError(("kd_mpi_ai_set_vqe_attr failed:%d")%(ret))
        else:
            ret = kd_mpi_ai_set_vqe_attr(self._ai_dev, self._ai_chn, aio_vqe_enable)
            if (0 != ret):
                raise ValueError(("kd_mpi_ai_set_vqe_attr failed:%d")%(ret))

        return ret

class PyAudio:
    def __init__(self):
        """Initialize PortAudio."""
        self._streams = set()

    def terminate(self):
        """
        Terminate PortAudio.

        :attention: Be sure to call this method for every instance of
          this object to release PortAudio resources.
        """
        cleanup_error = None
        for stream in self._streams.copy():
            try:
                stream.close()
            except Exception as error:
                if cleanup_error is None:
                    cleanup_error = error

        if cleanup_error is not None:
            raise cleanup_error

    def open(self, *args, **kwargs):
        """Open a new audio stream.

        Args:
            args: Positional arguments accepted by the stream constructor.
            kwargs: Keyword arguments accepted by the stream constructor.

        Returns:
            Stream: A new input or output stream.
        """
        if (kwargs.get("output") == 1):
            stream = Write_stream(self, *args, **kwargs)
            self._streams.add(stream)
        else:
            stream = Read_stream(self, *args, **kwargs)
            self._streams.add(stream)

        return stream

    def close(self, stream):
        """Close a managed audio stream.

        Args:
            stream: Stream instance to close.

        Raises:
            ValueError: If the stream is not managed by this PyAudio instance.
        """

        if stream not in self._streams:
            raise ValueError("Stream `%s' not found" % str(stream))

        stream.close()

    def _remove_stream(self, stream):
        """Internal helper method.
        Args:
            stream: Audio stream to close.
        """
        if stream in self._streams:
            self._streams.remove(stream)

    def get_sample_size(self, format):
        """Return the sample size for an audio format.
        Args:
            format: Audio sample format.
        """
        if (paInt16 == format):
            return 2
        elif (paInt24 == format):
            return 3
        elif (paInt32 == format):
            return 4
        else:
            return -1

    def get_format_from_width(self, width):
        """Return the audio format for a sample width.
        Args:
            width: Width in pixels.
        """
        if width == 2:
            return paInt16
        elif width == 3:
            return paInt24
        elif width == 4:
            return paInt32
        else:
            return -1
