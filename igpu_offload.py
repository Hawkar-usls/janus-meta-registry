import numpy as np
import logging
import asyncio

logger = logging.getLogger("JANUS")

try:
    import pyopencl as cl
    OPENCL_AVAILABLE = True
except ImportError:
    OPENCL_AVAILABLE = False

class IGpuOffload:
    def __init__(self, core_env=None):
        self.env = core_env  # Ссылка на среду для повышения энтропии
        self.ctx = None
        self.queue = None
        self.prg = None
        self.available = False
        self.error_count = 0
        self._init_opencl()
        self._build_kernels()

    def _init_opencl(self):
        if not OPENCL_AVAILABLE:
            logger.warning("[\u26A0\uFE0F] pyopencl \u043D\u0435 \u0443\u0441\u0442\u0430\u043D\u043E\u0432\u043B\u0435\u043D. iGPU \u043E\u0442\u043A\u043B\u044E\u0447\u0435\u043D.")
            return
        try:
            platforms = cl.get_platforms()
            for plat in platforms:
                devices = plat.get_devices(device_type=cl.device_type.GPU)
                if devices:
                    self.ctx = cl.Context([devices[0]])
                    self.queue = cl.CommandQueue(self.ctx)
                    self.available = True
                    logger.info("[\u2705] iGPU \u0430\u043A\u0442\u0438\u0432\u0438\u0440\u043E\u0432\u0430\u043D: %s", devices[0].name)
                    break
        except Exception as e:
            logger.error("[\u274C] \u041E\u0448\u0438\u0431\u043A\u0430 \u0438\u043D\u0438\u0446\u0438\u0430\u043B\u0438\u0437\u0430\u0446\u0438\u0438 OpenCL: %s", e)

    def _build_kernels(self):
        if not self.available:
            return
        src = """
        __kernel void relu(__global const float *input_tensor, __global float *output_tensor) {
            int gid = get_global_id(0);
            output_tensor[gid] = max(0.0f, input_tensor[gid]);
        }
        """
        try:
            self.prg = cl.Program(self.ctx, src).build()
        except Exception as e:
            logger.error("[\u274C] \u041E\u0448\u0438\u0431\u043A\u0430 \u043A\u043E\u043C\u043F\u0438\u043B\u044F\u0446\u0438\u0438 OpenCL \u044F\u0434\u0440\u0430: %s", e)
            self.available = False

    async def relu(self, input_array):
        if not self.available:
            return np.maximum(0, input_array)
        
        try:
            mf = cl.mem_flags
            input_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=input_array.astype(np.float32))
            output_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY, input_array.nbytes)

            event = self.prg.relu(self.queue, input_array.shape, None, input_buf, output_buf)
            event.wait()

            output_array = np.empty_like(input_array, dtype=np.float32)
            cl.enqueue_copy(self.queue, output_array, output_buf).wait()

            self.error_count = 0  # Сброс счетчика при успехе
            return output_array

        except Exception as e:
            self.error_count += 1
            logger.warning("[\u26A0\uFE0F] \u0421\u0431\u043E\u0439 iGPU (\u041F\u043E\u043F\u044B\u0442\u043A\u0430 %d): %s. Fallback on CPU.", self.error_count, e)
            
            # Компромиссный иммунный ответ (Вариант C)
            if self.error_count >= 2 and self.env is not None:
                self.env.complexity_level += 1
                logger.error("[\U0001F4A5] \u041B\u0435\u0442\u0430\u043B\u044C\u043D\u0430\u044F \u043C\u0443\u0442\u0430\u0446\u0438\u044F iGPU! \u042D\u043D\u0442\u0440\u043E\u043F\u0438\u044F \u0443\u0432\u0435\u043B\u0438\u0447\u0435\u043D\u0430.")
            
            return np.maximum(0, input_array)

    async def is_available(self):
        return self.available