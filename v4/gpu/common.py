import time

import numpy as np
import cupy as cp
from cupy.cuda import Device
from cupy.cuda.runtime import getDeviceCount

from cupy.cuda import nccl

from ..common import _start, _finish


# 計測開始
def start(method_name: str = '', k: int = None) -> float:
    _start(method_name, k)
    return time.perf_counter()


# 計測終了
def finish(start_time: float, isConverged: bool, num_of_iter: int, final_residual: float, final_k: int = None) -> float:
    elapsed_time = time.perf_counter() - start_time
    _finish(elapsed_time, isConverged, num_of_iter, final_residual, final_k)
    return elapsed_time


# パラメータの初期化
def init(b, x=None, maxiter=None) -> tuple:
    T = np.float64
    b = cp.array(b)
    b_norm = cp.linalg.norm(b)
    N = b.size
    if isinstance(x, np.ndarray):
        x = cp.array(x)
    else:
        x = cp.zeros(N, dtype=T)

    if maxiter == None:
        maxiter = N
    residual = cp.zeros(maxiter+1, T)
    num_of_solution_updates = cp.zeros(maxiter+1, np.int)

    return b, x, maxiter, b_norm, N, residual, num_of_solution_updates


class MultiGpu(object):
    # numbers
    begin: int = 0
    end: int = 0
    num_of_gpu: int = 0
    # dimentinal size
    N: int = 0
    local_N: int = 0
    # matrix
    A: list = []
    # vector
    x: list = []
    y: list = []
    out: np.ndarray = None
    # gpu stream
    streams = None
    # nccl
    comms = None
    comm = None

    # GPUの初期化
    @classmethod
    def init(cls):
        cls.begin = 0
        cls.end = getDeviceCount() - 1
        cls.num_of_gpu = getDeviceCount()
        cls.streams = [None] * cls.num_of_gpu

        cls.comms = nccl.NcclCommunicator.initAll([0,1,2,3])
        # cls.comms = nccl.NcclCommunicator.initAll([3,2,1,0])
        # comm_id = nccl.get_unique_id()
        # cls.comm = nccl.NcclCommunicator(cls.num_of_gpu, comm_id, 0)

        # init memory allocator
        for i in range(cls.num_of_gpu):
        # for i in range(cls.end, -1, -1):
            Device(i).use()
            pool = cp.cuda.MemoryPool(cp.cuda.malloc_managed)
            cp.cuda.set_allocator(pool.malloc)
            cls.streams[i] = cp.cuda.Stream()

            # Enable P2P
            # for j in range(cls.num_of_gpu):
            #     if i == j:
            #         continue
            #     cp.cuda.runtime.deviceEnablePeerAccess(j)

    # メモリー領域を確保
    @classmethod
    def alloc(cls, A, b, T):
        # dimentional size
        cls.N = b.size
        cls.local_N = cls.N // cls.num_of_gpu
        # byte size
        cls.nbytes = b.nbytes
        cls.local_nbytes = b.nbytes // cls.num_of_gpu

        # init list
        cls.A = [None] * cls.num_of_gpu
        cls.x = [None] * cls.num_of_gpu
        cls.y = [None] * cls.num_of_gpu

        # allocate A, x, y
        for i in range(cls.num_of_gpu):
        # for i in range(cls.end, -1, -1):
            Device(i).use()
            # divide A
            if isinstance(A, np.ndarray):
                cls.A[i] = cp.array(A[i*cls.local_N:(i+1)*cls.local_N], T)
            else:
                from cupyx.scipy.sparse import csr_matrix
                cls.A[i] = csr_matrix(A[i*cls.local_N:(i+1)*cls.local_N])
            cls.x[i] = cp.zeros(cls.N, T)
            cls.y[i] = cp.zeros(cls.local_N, T)

        # allocate output vector
        cls.out = cp.zeros(cls.N, T)

    # matvec with multi-gpu
    @classmethod
    def dot(cls, A, x):
        # copy to workers
        nccl.groupStart()
        for i in range(cls.num_of_gpu):
        # for i in range(cls.end, -1, -1):
            cls.comms[i].broadcast(x.data.ptr, cls.x[i].data.ptr, cls.N, nccl.NCCL_FLOAT64, cls.end, cls.streams[i].ptr)
        nccl.groupEnd()

        # dot
        for i in range(cls.num_of_gpu):
        # for i in range(cls.end, -1, -1):
            Device(i).use()
            cls.y[i] = cls.A[i].dot(cls.x[i])

        for i in range(cls.num_of_gpu):
            Device(i).synchronize()
            cls.streams[i].synchronize()

        # copy to master
        nccl.groupStart()
        for i in range(cls.num_of_gpu):
        # for i in range(cls.end, -1, -1):
            # cls.comms[0].send(cls.y[i].data.ptr, cls.local_N, nccl.NCCL_FLOAT64, cls.end, cls.streams[i].ptr)
            # cls.comms[0].recv(cls.out[i*cls.local_N].data.ptr, cls.local_N, nccl.NCCL_FLOAT64, i, cls.streams[i].ptr)
            cp.cuda.runtime.memcpyPeerAsync(cls.out[i*cls.local_N].data.ptr, cls.end, cls.y[i].data.ptr, i, cls.local_nbytes, cls.streams[i].ptr)
            # cls.comms[i].allGather(cls.y[i].data.ptr, cls.out[i*cls.local_N].data.ptr, cls.local_N, nccl.NCCL_FLOAT64, cls.streams[i].ptr)
        nccl.groupEnd()

        for i in range(cls.num_of_gpu):
            cls.streams[i].synchronize()

        return cls.out
