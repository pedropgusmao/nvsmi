#!/usr/bin/env python
# -*- coding: utf8 -*-

"""
A (user-)friendly wrapper to nvidia-smi

Author: Panagiotis Mavrogiorgos
Adapted from: https://github.com/anderskm/gputil

"""

from __future__ import division
from __future__ import print_function

from pprint import pprint

import argparse
import json
import itertools as it
import operator
import os
import shlex
import subprocess
import sys

if sys.version_info.major < 3:
    from distutils.spawn import find_executable as which
else:
    from shutil import which

__version__ = "0.0.0"


NVIDIA_SMI_GET_GPUS = "nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.total,memory.used,memory.free,driver_version,name,gpu_serial,display_active,display_mode,temperature.gpu --format=csv,noheader,nounits"
NVIDIA_SMI_GET_PROCS = "nvidia-smi --query-compute-apps=pid,process_name,gpu_uuid,gpu_name,used_memory --format=csv,noheader,nounits"


class GPU(object):
    def __init__(
        self,
        id,
        uuid,
        gpu_util,
        mem_total,
        mem_used,
        mem_free,
        driver,
        gpu_name,
        serial,
        display_mode,
        display_active,
        temperature,
    ):
        self.id = id
        self.uuid = uuid
        self.gpu_util = gpu_util
        self.mem_util = float(mem_used) / float(mem_total) * 100
        self.mem_total = mem_total
        self.mem_used = mem_used
        self.mem_free = mem_free
        self.driver = driver
        self.name = gpu_name
        self.serial = serial
        self.display_mode = display_mode
        self.display_active = display_active
        self.temperature = temperature

    def __repr__(self):
        return json.dumps(self.__dict__)
        # msg = "id: {id} | UUID: {uuid} | gpu util: {gpu_util:5.1f}% | mem util: {mem_util:5.1f}%"
        # msg = msg.format(**self.__dict__)
        # return msg


class GPUProcess(object):
    def __init__(self, pid, process_name, gpu_id, gpu_uuid, gpu_name, used_memory):
        self.pid = pid
        self.process_name = process_name
        self.gpu_id = gpu_id
        self.gpu_uuid = gpu_uuid
        self.gpu_name = gpu_name
        self.used_memory = used_memory

    def __repr__(self):
        return json.dumps(self.__dict__)
        # return str(self.__dict__)


def to_float_or_inf(value):
    try:
        number = float(value)
    except ValueError:
        number = float("nan")
    return number


def get_gpu(line):
    values = line.split(", ")
    id = values[0]
    uuid = values[1]
    gpu_util = to_float_or_inf(values[2])
    mem_total = to_float_or_inf(values[3])
    mem_used = to_float_or_inf(values[4])
    mem_free = to_float_or_inf(values[5])
    driver = values[6]
    gpu_name = values[7]
    serial = values[8]
    display_active = values[9]
    display_mode = values[10]
    temp_gpu = to_float_or_inf(values[11])
    gpu = GPU(
        id,
        uuid,
        gpu_util,
        mem_total,
        mem_used,
        mem_free,
        driver,
        gpu_name,
        serial,
        display_mode,
        display_active,
        temp_gpu,
    )
    return gpu


def get_gpus():
    output = subprocess.check_output(shlex.split(NVIDIA_SMI_GET_GPUS))
    lines = output.decode("utf-8").split(os.linesep)
    gpus = (get_gpu(line) for line in lines if line.strip())
    return gpus


def get_gpu_proc(line, gpu_uuid_to_id_map):
    values = line.split(", ")
    pid = int(values[0])
    process_name = values[1]
    gpu_uuid = values[2]
    gpu_name = values[3]
    used_memory = to_float_or_inf(values[4])
    gpu_id = gpu_uuid_to_id_map.get(gpu_uuid, -1)
    proc = GPUProcess(pid, process_name, gpu_id, gpu_uuid, gpu_name, used_memory)
    return proc


def get_gpu_processes():
    output = subprocess.check_output(shlex.split(NVIDIA_SMI_GET_PROCS))
    lines = output.decode("utf-8").split(os.linesep)
    gpu_uuid_to_id_map = _populate_gpu_uuid_to_id_map()
    processes = [
        get_gpu_proc(line, gpu_uuid_to_id_map) for line in lines if line.strip()
    ]
    return processes


def is_gpu_available(
    gpu, gpu_util_max, mem_util_max, mem_free_min, exclude_ids, exclude_uuids
):
    return (
        True
        and (gpu.gpu_util <= gpu_util_max)
        and (gpu.mem_util <= mem_util_max)
        and (gpu.mem_free >= mem_free_min)
        and (gpu.id not in exclude_ids)
        and (gpu.uuid not in exclude_uuids)
    )


def get_available_gpus(
    gpu_util_max=1.0,
    mem_util_max=1.0,
    mem_free_min=0,
    exclude_ids=None,
    exclude_uuids=None,
):
    """ Return up to `limit` available cpus """
    # Normalize inputs (exclude_ids and exclude_uuis need to be iterables)
    exclude_ids = exclude_ids or tuple()
    exclude_uuids = exclude_uuids or tuple()
    # filter available gpus
    gpus = list(get_gpus())
    selectors = (
        is_gpu_available(
            gpu, gpu_util_max, mem_util_max, mem_free_min, exclude_ids, exclude_uuids
        )
        for gpu in gpus
    )
    available_gpus = it.compress(gpus, selectors)
    return available_gpus


# Generate gpu uuid to id map
def _populate_gpu_uuid_to_id_map():
    try:
        gpu_map = {gpu.uuid: gpu.id for gpu in get_gpus()}
    except:
        t, v, tb = sys.exc_info()
        print("Something went wrong while parsing the nvidia-smi output")
        raise
    else:
        return gpu_map


def parse_args():
    main_parser = argparse.ArgumentParser(
        prog="nvsmi", description="A (user-)friendy interface for nvidia-smi"
    )
    main_parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s {version}".format(version=__version__),
    )

    subparsers = main_parser.add_subparsers(
        help="Choose mode of operation", dest="mode", title="subcommands"
    )  # noqa
    ls_parser = subparsers.add_parser("ls", help="List available GPUs")
    ps_parser = subparsers.add_parser("ps", help="Examine the process of a gpu.")

    # list
    ls_parser.add_argument(
        "--limit",
        type=int,
        default=999,
        metavar="",
        help="Limit the number of the GPUs",
    )
    ls_parser.add_argument(
        "--mem-free-min",
        type=float,
        default=0,
        metavar="",
        help="The minimum amount of free memory (in MB)",
    )
    ls_parser.add_argument(
        "--mem-util-max",
        type=int,
        default=100,
        metavar="",
        help="The maximum amount of memory [0, 100]",
    )
    ls_parser.add_argument(
        "--gpu-util-max",
        type=int,
        default=100,
        metavar="",
        help="The maximum amount of load [0, 100]",
    )
    ls_parser.add_argument(
        "--exclude-ids", nargs="+", metavar="", help="List of GPU IDs to exclude"
    )
    ls_parser.add_argument(
        "--exclude-uuids", nargs="+", metavar="", help="List of GPU UUIDs to exclude"
    )
    ls_parser.add_argument(
        "--sort",
        default="id",
        choices=["id", "gpu_util", "mem_util"],
        metavar="",
        help="Sort the GPUs using the specified attribute",
    )

    # processes
    ps_parser.add_argument(
        "--ids",
        nargs="+",
        metavar="",
        help="Show only the processes of the GPU matching the provided ids",
    )
    ps_parser.add_argument(
        "--uuids",
        nargs="+",
        metavar="",
        help="Show only the processes of the GPU matching the provided UUIDs",
    )

    args = main_parser.parse_args()
    return args


def take(n, iterable):
    "Return first n items of the iterable as a list"
    return it.islice(iterable, n)


def is_nvidia_smi_on_path():
    return which("nvidia-smi")


def main():
    args = parse_args()
    if args.mode == "ls":
        gpus = list(
            get_available_gpus(
                gpu_util_max=args.gpu_util_max,
                mem_util_max=args.mem_util_max,
                mem_free_min=args.mem_free_min,
                exclude_ids=args.exclude_ids,
                exclude_uuids=args.exclude_uuids,
            )
        )
        gpus.sort(key=operator.attrgetter(args.sort))
        for gpu in take(args.limit, gpus):
            print(gpu)
    else:
        processes = get_gpu_processes()
        if args.ids:
            for proc in processes:
                if proc.gpu_id in args.ids:
                    print(proc)
        elif args.uuids:
            for proc in processes:
                if proc.gpu_uuid in args.uuids:
                    print(proc)
        else:
            for proc in processes:
                print(proc)


if __name__ == "__main__":
    # cli mode
    if not is_nvidia_smi_on_path():
        sys.exit("Couldn't find 'nvidia-smi' in $PATH: %s" % os.environ["PATH"])
    main()
