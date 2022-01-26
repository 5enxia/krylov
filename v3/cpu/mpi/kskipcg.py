import numpy as np
from numpy import float64, dot
from numpy.linalg import norm

from .common import start, finish, init, MultiCpu


def kskipcg(comm, local_A, b, x=None, tol=1e-05, maxiter=None, k=0, M=None, callback=None, atol=None) -> tuple:
    # MPI初期化
    rank = comm.Get_rank()
    MultiCpu.joint_mpi(comm)

    # 初期化
    T = float64
    x, maxiter, b_norm, N, residual, num_of_solution_updates = init(
        b, x, maxiter)
    MultiCpu.alloc(local_A, T)
    Ax = np.zeros(N, T)
    Ar = np.zeros((k + 2, N), T)
    Ap = np.zeros((k + 3, N), T)
    a = np.zeros(2*k + 2, T)
    f = np.zeros(2*k + 4, T)
    c = np.zeros(2*k + 2, T)

    # 初期残差
    MultiCpu.dot(local_A, x, out=Ax)
    Ar[0] = b - Ax
    Ap[0] = Ar[0].copy()

    # 反復計算
    i = 0
    index = 0
    if rank == 0:
        start_time = start(method_name='k-skip CG + MPI', k=k)
    while i < maxiter:
        # 収束判定
        residual[index] = norm(Ar[0]) / b_norm
        if residual[index] < tol:
            isConverged = True
            break

        # 基底計算
        for j in range(1, k + 1):
            MultiCpu.dot(local_A, Ar[j-1], out=Ar[j])
        for j in range(1, k + 2):
            MultiCpu.dot(local_A, Ap[j-1], out=Ap[j])

        # 係数計算
        for j in range(2 * k + 1):
            jj = j // 2
            a[j] = dot(Ar[jj], Ar[jj + j % 2])
        for j in range(2 * k + 4):
            jj = j // 2
            f[j] = dot(Ap[jj], Ap[jj + j % 2])
        for j in range(2 * k + 2):
            jj = j // 2
            c[j] = dot(Ar[jj], Ap[jj + j % 2])

        # CGでの1反復
        # 解の更新
        alpha = a[0] / f[1]
        beta = alpha ** 2 * f[2] / a[0] - 1
        x += alpha * Ap[0]
        Ar[0] -= alpha * Ap[1]
        Ap[0] = Ar[0] + beta * Ap[0]
        MultiCpu.dot(local_A, Ap[0], out=Ap[1])

        # CGでのk反復
        for j in range(k):
            for l in range(0, 2*(k-j)+1):
                a[l] += alpha*(alpha*f[l+2] - 2*c[l+1])
                d = c[l] - alpha*f[l+1]
                c[l] = a[l] + d*beta
                f[l] = c[l] + beta*(d + beta*f[l])

            # 解の更新
            alpha = a[0] / f[1]
            beta = alpha ** 2 * f[2] / a[0] - 1
            x += alpha * Ap[0]
            Ar[0] -= alpha * Ap[1]
            Ap[0] = Ar[0] + beta * Ap[0]
            MultiCpu.dot(local_A, Ap[0], out=Ap[1])

        i += (k + 1)
        index += 1
        num_of_solution_updates[index] = i
    else:
        isConverged = False
        residual[index] = norm(Ar[0]) / b_norm

    if rank == 0:
        elapsed_time = finish(start_time, isConverged, i, residual[index])
        info = {
            'time': elapsed_time,
            'nosl': num_of_solution_updates[:index+1],
            'residual': residual[:index+1],
        }
        return x, info
    else:
        exit(0)
