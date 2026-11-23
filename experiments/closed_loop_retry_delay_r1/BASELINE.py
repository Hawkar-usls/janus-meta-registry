def retry_delay(attempt, cap):
    return min(cap, pow(2, attempt))
