"""Bounded block reads for Faiss indexes on network-backed storage.

Read compressed IVF lists with ordinary file I/O, then scan them in RAM.
Native Faiss never faults pages from the network mount while holding the GIL.
The selected partitions and their PQ scores are identical to ordinary IVF search.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
import threading

import faiss
import numpy as np

POOL = ThreadPoolExecutor(max_workers=4)
CACHE = OrderedDict()
CACHE_LOCK = threading.Lock()
CACHE_BYTES = 0
CACHE_LIMIT = 320 * 1024**2
BLOCK_RECORDS = 65_536


def read_vector_block(task):
    global CACHE_BYTES
    filename, offset, size = task
    key = ('vectors', filename, offset, size)
    with CACHE_LOCK:
        cached = CACHE.get(key)
        if cached is not None:
            CACHE.move_to_end(key)
            return cached[0]
    with open(filename, 'rb') as handle:
        handle.seek(offset)
        data = handle.read(size)
    if len(data) != size:
        raise ValueError('Original vector block is incomplete')
    with CACHE_LOCK:
        if key not in CACHE:
            while CACHE and CACHE_BYTES + size > CACHE_LIMIT:
                _, old = CACHE.popitem(last=False)
                CACHE_BYTES -= len(old[0]) + len(old[1])
            CACHE[key] = (data, b''); CACHE_BYTES += size
    return data


def original_vectors(path, state, identifiers):
    offsets = np.asarray([s['offset'] for s in state['sources']], dtype=np.int64)
    groups = {}
    for output_row, identifier in enumerate(identifiers):
        source = state['sources'][int(np.searchsorted(offsets, identifier, side='right')) - 1]
        row = int(identifier) - source['offset']
        start = row // 64 * 64
        count = min(64, source['records'] - start)
        task = (str(Path(path) / 'vectors' / (source['id'] + '.f16')), start * 512, count * 512)
        groups.setdefault(task, []).append((output_row, row - start))
    tasks = list(groups)
    result = np.empty((len(identifiers), 256), dtype=np.float32)
    for begin in range(0, len(tasks), 4):
        batch = tasks[begin:begin + 4]
        for task, data in zip(batch, POOL.map(read_vector_block, batch)):
            matrix = np.frombuffer(data, dtype='<f2').reshape(-1, 256)
            for output_row, row in groups[task]:
                result[output_row] = matrix[row]
    faiss.normalize_L2(result)
    return result


@lru_cache(maxsize=4)
def prototype(path):
    index = faiss.read_index(str(Path(path) / 'trained.faiss'))
    if index.ntotal != 0 or index.d != 256:
        raise ValueError('Invalid empty IVF template')
    return index


def read_block(task):
    global CACHE_BYTES
    filename, list_no, offset, capacity, code_size, start, count, distance = task
    key = task[:-1]
    with CACHE_LOCK:
        cached = CACHE.get(key)
        if cached is not None:
            CACHE.move_to_end(key)
            return list_no, distance, cached
    def read_exact(handle, position, length):
        handle.seek(position)
        chunks, remaining = [], length
        while remaining:
            chunk = handle.read(remaining)
            if not chunk:
                raise ValueError('Compressed vector block is incomplete')
            chunks.append(chunk); remaining -= len(chunk)
        return b''.join(chunks)
    with open(filename, 'rb', buffering=0) as handle:
        codes = read_exact(handle, offset + start * code_size, count * code_size)
        ids = read_exact(handle, offset + capacity * code_size + start * 8, count * 8)
    value = (codes, ids)
    size = len(codes) + len(ids)
    with CACHE_LOCK:
        if size <= CACHE_LIMIT and key not in CACHE:
            while CACHE and CACHE_BYTES + size > CACHE_LIMIT:
                _, old = CACHE.popitem(last=False)
                CACHE_BYTES -= len(old[0]) + len(old[1])
            CACHE[key] = value; CACHE_BYTES += size
    return list_no, distance, value


def candidates(path, metadata_index, query, probes, allowed, limit=300):
    base = prototype(path)
    disk = faiss.downcast_InvertedLists(metadata_index.invlists)
    if not isinstance(disk, faiss.OnDiskInvertedLists):
        raise ValueError('Expected an on-disk IVF index')
    if base.nlist != metadata_index.nlist or base.code_size != disk.code_size:
        raise ValueError('IVF template and compressed data differ')
    distances, partitions = base.quantizer.search(query[None, :], probes)
    tasks = []
    for list_no, distance in zip(partitions[0], distances[0]):
        entry = disk.lists.at(int(list_no))
        for start in range(0, entry.size, BLOCK_RECORDS):
            tasks.append((str(Path(path) / 'index.ivfdata'), int(list_no), entry.offset,
                          entry.capacity, disk.code_size, start,
                          min(BLOCK_RECORDS, entry.size - start), float(distance)))
    local = faiss.clone_index(base)
    local.nprobe = 1
    best_scores, best_ids = np.empty(0, dtype=np.float32), np.empty(0, dtype=np.int64)
    # Limit outstanding reads: Executor.map over every list could otherwise
    # retain an entire large index in completed futures.
    for begin in range(0, len(tasks), 4):
        for list_no, distance, (raw_codes, raw_ids) in POOL.map(read_block, tasks[begin:begin + 4]):
            ids = np.frombuffer(raw_ids, dtype='<i8')
            codes = np.frombuffer(raw_codes, dtype='u1').reshape(len(ids), disk.code_size)
            if allowed is not None:
                selected = allowed[ids]
                ids, codes = ids[selected], codes[selected]
            if not len(ids):
                continue
            lists = faiss.ArrayInvertedLists(base.nlist, disk.code_size)
            local.replace_invlists(lists, False)
            lists.add_entries(list_no, len(ids), faiss.swig_ptr(ids), faiss.swig_ptr(codes))
            local.ntotal = len(ids)
            scores, found = local.search_preassigned(query[None, :], limit,
                np.asarray([[list_no]], dtype=np.int64), np.asarray([[distance]], dtype=np.float32))
            valid = found[0] >= 0
            best_ids = np.concatenate((best_ids, found[0][valid]))
            best_scores = np.concatenate((best_scores, scores[0][valid]))
            if len(best_ids) > limit:
                chosen = np.argpartition(best_scores, -limit)[-limit:]
                best_ids, best_scores = best_ids[chosen], best_scores[chosen]
    order = np.argsort(-best_scores, kind='stable')
    return best_scores[order], best_ids[order]
