def retry_delay(attempt, cap):
    return min(cap, 2 ** attempt)
