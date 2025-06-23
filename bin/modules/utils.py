import numpy as np

def split_chunks(file_list: list, num_threads: int) -> list:
    # Using numpy to split list into nearly equal parts
    return np.array_split(file_list, num_threads)
