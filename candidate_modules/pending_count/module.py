def pending_count(produced, confirmed):
    return max(0, produced - confirmed)
