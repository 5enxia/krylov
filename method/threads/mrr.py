from .common import start, end, init


def mrr(A, b, epsilon, T, pu):
    if pu == 'cpu':
        from numpy import dot
        from numpy.linalg import norm
        x, b_norm, N, max_iter, residual, num_of_solution_updates = init(A, b, T, pu)
    else:
        from cupy import dot
        from cupy.linalg import norm
        A, b, x, b_norm, N, max_iter, residual, num_of_solution_updates = init(A, b, T, pu)

    # 初期残差
    r = b - dot(A, x)
    residual[0] = norm(r) / b_norm

    # 初期反復
    start_time = start(method_name='MrR')
    Ar = dot(A, r)
    zeta = dot(r, Ar) / dot(Ar, Ar)
    y = zeta * Ar
    z = -zeta * r
    r -= y
    x -= z
    num_of_solution_updates[1] = 1
    i = 1

    # 反復計算
    while i < max_iter:
        # 収束判定
        residual[i] = norm(r) / b_norm
        if residual[i] < epsilon:
            isConverged = True
            break

        # 解の更新
        Ar = dot(A, r)
        mu = dot(y, y)
        nu = dot(y, Ar)
        gamma = nu / mu
        s = Ar - gamma * y
        rs = dot(r, s)
        ss = dot(s, s)
        zeta = rs / ss
        eta = -zeta * gamma
        y = eta * y + zeta * Ar
        z = eta * z - zeta * r
        r -= y
        x -= z
        i += 1
        num_of_solution_updates[i] = i
    else:
        isConverged = False

    elapsed_time = end(start_time, isConverged, i, residual[i])
    return elapsed_time, num_of_solution_updates[:i+1], residual[:i+1]
