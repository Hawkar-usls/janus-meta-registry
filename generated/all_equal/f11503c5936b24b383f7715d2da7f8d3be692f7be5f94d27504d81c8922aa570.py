def all_equal(values):
    if len(values) <= 1:
        return True
    return all(x == values[0] for x in values)
