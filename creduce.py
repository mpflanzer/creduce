#!/usr/bin/env python3

#TODO: Add mutually exclusive options to load pass group or custom json file

import argparse
import logging
import multiprocessing
import os
import sys
import time

from creduce.creduce import CReduce
from creduce.utils.error import CReduceError
from creduce.utils import parallel
from creduce.utils import statistics

if __name__ == "__main__":
    try:
        core_count = multiprocessing.cpu_count()
    except NotImplementedError:
        core_count = 1

    parser = argparse.ArgumentParser(description="C-Reduce")
    parser.add_argument("--n", "-n", type=int, default=core_count, help="Number of cores to use; C-Reduce tries to automatically pick a good setting but its choice may be too low or high for your situation")
    parser.add_argument("--tidy", action="store_true", default=False, help="Do not make a backup copy of each file to reduce as file.orig")
    parser.add_argument("--shaddap", action="store_true", default=False, help="Suppress output about non-fatal internal errors")
    parser.add_argument("--die-on-pass-bug", action="store_true", default=False, help="Terminate C-Reduce if a pass encounters an otherwise non-fatal problem")
    parser.add_argument("--sanitize", action="store_true", default=False, help="Attempt to obscure details from the original source file")
    parser.add_argument("--sllooww", action="store_true", default=False, help="Try harder to reduce, but perhaps take a long time to do so")
    parser.add_argument("--also-interesting", metavar="EXIT_CODE", type=int, help="A process exit code (somewhere in the range 64-113 would be usual) that, when returned by the interestingness test, will cause C-Reduce to save a copy of the variant")
    parser.add_argument("--debug", action="store_true", default=False, help="Print debug information")
    parser.add_argument("--log-level", type=str, choices=["INFO", "DEBUG", "WARNING", "ERROR"], default="INFO", help="Define the verbosity of the logged events")
    parser.add_argument("--log-file", type=str, help="Log events into LOG_FILE instead of stderr. New events are append to the end of the file")
    parser.add_argument("--no-kill", action="store_true", default=False, help="Wait for parallel instances to terminate on their own instead of killing them (only useful for debugging)")
    #TODO: Don't use fixed manager here
    parser.add_argument("--no-give-up", action="store_true", default=False, help="Don't give up on a pass that hasn't made progress for {} iterations".format(parallel.ConservativeTestManager.GIVEUP_CONSTANT))
    parser.add_argument("--print-diff", action="store_true", default=False, help="Show changes made by transformations, for debugging")
    parser.add_argument("--save-temps", action="store_true", default=False, help="Don't delete /tmp/creduce-xxxxxx directories on termination")
    parser.add_argument("--skip-initial-passes", action="store_true", default=False, help="Skip initial passes (useful if input is already partially reduced)")
    parser.add_argument("--timing", action="store_true", default=False, help="Print timestamps about reduction progress")
    parser.add_argument("--no-cache", action="store_true", default=False, help="Don't cache behavior of passes")
    parser.add_argument("--skip-key-off", action="store_true", default=False, help="Disable skipping the rest of the current pass when \"s\" is pressed")
    parser.add_argument("--max-improvement", metavar="BYTES", type=int, help="Largest improvement in file size from a single transformation that C-Reduce should accept (useful only to slow C-Reduce down)")
	passes_group = parser.add_mutually_exclusive_group()
    passes_group.add_argument("--pass-group", type=str, choices=CReduce.available_pass_groups, default=CReduce.default_pass_group, help="Set of passes used during the reduction")
    passes_group.add_argument("--pass-group-file", type=str, help="JSON file defining a custom pass group")
    parser.add_argument("--test-manager", type=str, choices=["conservative", "fast-conservative", "non-deterministic"], help="Strategy for the parallel reduction process")
    parser.add_argument("--no-fast-test", action="store_true", help="Use the general test runner even if a faster implementation is available")
    parser.add_argument("interestingness_test", metavar="INTERESTINGNESS_TEST", help="Executable to check interestingness of test cases")
    parser.add_argument("test_cases", metavar="TEST_CASE", nargs="+", help="Test cases")

    args = parser.parse_args()

    log_config = {}

    if args.timing:
        log_config["format"] = "%(asctime)s@%(levelname)s@%(name)s@%(message)s"
    else:
        log_config["format"] = "@%(levelname)s@%(name)s@%(message)s"

    if args.debug:
        log_config["level"] = logging.DEBUG
    else:
        log_config["level"] = getattr(logging, args.log_level.upper())

    if args.log_file is not None:
        log_config["filename"] = args.log_file

    logging.basicConfig(**log_config)

    pass_options = set()

    if args.sanitize:
        pass_options.add(CReduce.PassOption.sanitize)

    if args.sllooww:
        pass_options.add(CReduce.PassOption.slow)

    if (not args.no_fast_test and
        parallel.PythonTestRunner.is_valid_test(args.interestingness_test)):
        test_runner = parallel.PythonTestRunner(args.interestingness_test, args.save_temps, args.no_kill)
    else:
        test_runner = parallel.GeneralTestRunner(args.interestingness_test, args.save_temps, args.no_kill)

    pass_statistic = statistics.PassStatistic()

    if args.test_manager == "fast-conservative":
        test_manager_class = parallel.FastConservativeTestManager
    elif args.test_manager == "non-deterministic":
        test_manager_class = parallel.NonDeterministicTestManager
    else:
        test_manager_class = parallel.ConservativeTestManager

    test_manager = test_manager_class(test_runner, pass_statistic, args.test_cases, args.n, args.no_cache, args.shaddap, args.die_on_pass_bug, args.print_diff, args.max_improvement, args.no_give_up, args.also_interesting)

    reducer = CReduce(test_manager)

    reducer.tidy = args.tidy

    # Track runtime
    if args.timing:
        time_start = time.monotonic()

    try:
        success = reducer.reduce(skip_initial=args.skip_initial_passes,
                                 pass_group=CReduce.PassGroup(args.pass_group),
                                 pass_options=pass_options)
    except CReduceError as err:
        print(err)

    if success:
        print("pass statistics:")

        for item in pass_statistic.sorted_results:
            print("method {pass} :: {arg} worked {worked} times and failed {failed} times".format(**item))

        for test_case in test_manager.sorted_test_cases:
            with open(test_case, mode="r") as test_case_file:
                print(test_case_file.read())

    if args.timing:
        time_stop = time.monotonic()
        print("Runtime: {} seconds".format(round((time_stop - time_start))))

    logging.shutdown()
