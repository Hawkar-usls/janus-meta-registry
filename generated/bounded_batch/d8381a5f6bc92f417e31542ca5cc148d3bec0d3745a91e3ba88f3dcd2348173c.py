def bounded_batch(remaining, limit):
    return max(0, min(remaining, limit))
