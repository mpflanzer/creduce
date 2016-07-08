#TODO: Extract passes into json files

import enum
import logging
import os
import platform
import sys

from .passes.balanced import BalancedDeltaPass
from .passes.blank import BlankDeltaPass
from .passes.clang import ClangDeltaPass
from .passes.clangbinarysearch import ClangBinarySearchDeltaPass
from .passes.clex import ClexDeltaPass
from .passes.comments import CommentsDeltaPass
from .passes.includeincludes import IncludeIncludesDeltaPass
from .passes.includes import IncludesDeltaPass
from .passes.indent import IndentDeltaPass
from .passes.ints import IntsDeltaPass
from .passes.lines import LinesDeltaPass
from .passes.peep import PeepDeltaPass
from .passes.special import SpecialDeltaPass
from .passes.ternary import TernaryDeltaPass
from .passes.unifdef import UnIfDefDeltaPass

from .utils.error import PassOptionError
from .utils.error import PrerequisitesNotFoundError

class Pass:
    @enum.unique
    class Option(enum.Enum):
        sanitize = "sanitize"
        slow = "slow"
        windows = "windows"

    @classmethod
    def _check_pass_options(cls, options):
        return all(isinstance(opt, cls.Option) for opt in options)

    def __init__(self, pass_, arg, *, include=None, exclude=None):
        self.pass_ = pass_
        self.arg = arg

        if include is not None:
            tmp = set(include)

            if self._check_pass_options(tmp):
                self.include = tmp
            else:
                raise PassOptionError()
        else:
            self.include = None

        if exclude is not None:
            tmp = set(exclude)

            if self._check_pass_options(tmp):
                self.exclude = tmp
            else:
                raise PassOptionError()
        else:
            self.exclude = None

class CReduce:
    def __init__(self, test_manager):
        self.test_manager = test_manager
        self.tidy = False

	@property
	def default_pass_group(self):
		if "all" in self.available_pass_groups:
			return "all"
		else:
			return None

	@property
	def available_pass_groups(self):
		# Check for relative path
		#TODO: Check also for absolute install path, maybe /usr/local/share?
		if os.path.isdir("./pass_groups"):
			pass_group_dir = "./pass_groups"
		else:
			#TODO: More specific error
			raise CReduceError()

		group_names = []

		for entry in os.listdir(pass_group_dir):
			if not os.path.isfile(entry):
				continue

			with open(entry, mode="r") as pass_group_file:
				try:
					pass_group_dict = json.load(pass_group_file)
					self.create_pass_dict(pass_group_dict)
				except JSONDecodeError:
					logging.warning("Skipping file {}. Not valid JSON.".format(entry))
				except CReduceError:
					#TODO: Add more specific error
					logging.warning("Skipping file {}. Not valid pass group.".format(entry))
				else:
					name = os.path.basename(entry)
					(name, _) = os.path.splitext(name)
					group_names.append(name)

		return group_names

	def create_pass_group(self, pass_group_dict, pass_options):
		pass_group = {}

        def include_pass(pass_dict, options):
            return ((("include" not in pass_dict) or bool(set(pass_dict["include"]) & options)) and
                    (("exclude" not in pass_dict) or not bool(set(pass_dict["exclude"]) & options)))

		for category in ["first", "main", "last"]:
			if category not in pass_group_dict:
				raise CReduceError("Missing category {}".format(category))

			pass_group[category] = []

			for pass_dict in pass_group_dict[category]:
				if not include_pass(pass_dict, pass_options):
					continue

				if "pass" not in pass_dict:
					raise CReduceError("Invalid pass in category {}".format(category))

				pass_class = get_pass_class(pass_dict["pass"])

				if "arg" not in pass_dict["arg"]:
					raise CReduceError("Missign arg for pass {}".format(pass_dict["pass"]))

				#TODO: Create pass instances and get rid of Pass class
				pass_group[category].append(Pass(pass_class, pass_dict["arg"]))

		return pass_group

    def reduce(self, skip_initial=False, pass_group=PassGroup.all, pass_options=set()):
        pass_options = set(pass_options)

        if sys.platform == "win32":
            pass_options.add("windows")

        pass_group = self._prepare_pass_group(pass_group, pass_options)

        self._check_prerequisites(pass_group)
        self.test_manager.check_sanity()

        logging.info("===< {} >===".format(os.getpid()))
        logging.info("running {} interestingness test{} in parallel".format(self.test_manager.parallel_tests,
                                                                            "" if self.test_manager.parallel_tests == 1 else "s"))

        if not self.tidy:
            self.test_manager.backup_test_cases()

        if not skip_initial:
            logging.info("INITIAL PASSES")
            self._run_additional_passes(pass_group["first"])

        logging.info("MAIN PASSES")
        self._run_main_passes(pass_group["main"])

        logging.info("CLEANUP PASS")
        self._run_additional_passes(pass_group["last"])

        logging.info("===================== done ====================")
        return True

    @staticmethod
    def _check_prerequisites(pass_group):
        passes = set()
        missing = []

        for category in pass_group:
            passes |= set(map(lambda p: p.pass_, pass_group[category]))

        for p in passes:
            if not p.check_prerequisites():
                logging.error("Prereqs not found for pass {}".format(p))
                missing.append(p)

        if missing:
            raise PrerequisitesNotFoundError(missing)

    def _run_additional_passes(self, passes):
        for p in passes:
            self.test_manager.run_pass(p.pass_, p.arg)

    def _run_main_passes(self, passes):
        while True:
            total_file_size = self.test_manager.total_file_size

            for p in passes:
                self.test_manager.run_pass(p.pass_, p.arg)

            logging.info("Termination check: size was {}; now {}".format(total_file_size, self.test_manager.total_file_size))

            if  self.test_manager.total_file_size >= total_file_size:
                break

    def _prepare_pass_group(self, pass_group, pass_options):
        group = self.groups[pass_group]

        def pass_filter(p):
            return (((p.include is None) or bool(p.include & pass_options)) and
                    ((p.exclude is None) or not bool(p.exclude & pass_options)))

        for category in group:
            group[category] = [p for p in group[category] if pass_filter(p)]

        return group
