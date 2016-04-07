#!/usr/bin/env python3

import argparse
import multiprocessing
import multiprocessing.connection
import os
import re
import shutil
import subprocess
import sys
import tempfile

class CReduceError(Exception):
    pass

class UnknownArgumentCReduceError(CReduceError):
    pass

class CReduceInvalidFileError(CReduceError):
    def __init__(self, path, error):
        self.path = path
        self.error = error

    def _get_error_name(self):
        if self.error == os.R_OK:
            return "read"
        elif self.error == os.W_OK:
            return "written"
        elif self.error == os.X_OK:
            return "executed"
        elif self.error == os.F_OK:
            return "accessed"

    def __str__(self):
        return "The specified file '{}' cannot be {}!".format(self.path, self._get_error_name())

class CReduceInvalidTestCaseError(CReduceInvalidFileError):
    def __str__(self):
        return "The specified test case '{}' cannot be {}!".format(self.path, self._get_error_name())

class InterestingnessTest:
    def check(self):
        raise NotImplementedError("Please use a custom interestingness test class!")

    def run(self):
        result = self.check()
        if result:
            print("Check Success")
            sys.exit(0)
        else:
            print("Check Failure")
            sys.exit(1)

class SimpleInterestingnessTest(InterestingnessTest):
    def __init__(self, test_cases):
        #FIXME: Need to use super magic?
        self.test_cases = list(test_cases)

    def check(self):
        return (subprocess.call(["clang", "-fsyntax-only", self.test_cases[0]]) == 0)

class Test0InterestingnessTest(InterestingnessTest):
    def __init__(self, test_cases):
        #FIXME: Need to use super magic?
        self.test_cases = list(test_cases)

    def check(self):
        try:
            output = subprocess.check_output(["clang", "-c", "-pedantic", "-Wall", "-O0", self.test_cases[0]], universal_newlines=True, stderr=subprocess.STDOUT)

            if ("incompatible redeclaration" in output or
                    "ordered comparison between pointer" in output or
                    "eliding middle term" in output or
                    "end of non-void function" in output or
                    "invalid in C99" in output or
                    "specifies type" in output or
                    "should return a value" in output or
                    "too few argument" in output or
                    "too many argument" in output or
                    "return type of 'main" in output or
                    "uninitialized" in output or
                    "incompatible pointer to" in output or
                    "incompatible integer to" in output or
                    "type specifier missing" in output):
                return False

            output = subprocess.check_output(["gcc", "-c", "-Wextra", "-Wall", "-O0", self.test_cases[0]], universal_newlines=True, stderr=subprocess.STDOUT)

            if ("uninitialized" in output or
                    "control reaches end" in output or
                    "no semicolon at end" in output or
                    "incompatible pointer" in output or
                    "cast from pointer to integer" in output or
                    "ordered comparison of pointer with integer" in output or
                    "declaration does not declare anything" in output or
                    "expects type" in output or
                    "assumed to have one element" in output or
                    "division by zero" in output or
                    "pointer from integer" in output or
                    "incompatible implicit" in output or
                    "excess elements in struct initializer" in output or
                    "comparison between pointer and integer" in output):
                return False

            with open(self.test_cases[0], "r") as f:
                for l in f.readlines():
                    if "goto" in l:
                        return True

                return False
        except subprocess.CalledProcessError as err:
            print(err)
            return False

class DeltaPass:
    @classmethod
    def new(cls, test_case, arg):
        return 1
        raise NotImplementedError

    @classmethod
    def advance(cls, test_case, arg, state):
        return 1
        raise NotImplementedError

    @classmethod
    def advance_on_success(cls, test_case, arg, state):
        return 1
        raise NotImplementedError

    @classmethod
    def transform(cls, test_case, arg, state):
        return (1, 1)
        raise NotImplementedError

class IncludeIncludesDeltaPass(DeltaPass):
    @classmethod
    def new(cls, test_case, arg):
        return 1

    @classmethod
    def advance(cls, test_case, arg, state):
        return state + 1

    @classmethod
    def advance_on_success(cls, test_case, arg, state):
        return state

    @classmethod
    def transform(cls, test_case, arg, state):
        success = cls.__transform(test_case, state)
        return (CReduce.RES_OK if success else CReduce.RES_STOP, state)

    @staticmethod
    def __transform(test_case, state):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp_file:
            with open(test_case, "r") as in_file:
                includes = 0
                matched = False

                for line in in_file.readlines():
                    include_match = re.match('\s*#\s*include\s*"(.*?)"', line)

                    if include_match is not None:
                        includes += 1

                        if includes == state:
                            try:
                                with open(include_match.group(1), "r") as inc_file:
                                    matched = True
                                    tmp_file.writelines(inc_file.readlines())
                                    continue
                            except Exception:
                                pass

                    tmp_file.writelines(line)

            if matched:
                shutil.move(tmp_file.name, test_case)
            else:
                os.unlink(tmp_file.name)

        return matched

class IncludesDeltaPass(DeltaPass):
    @classmethod
    def new(cls, test_case, arg):
        return 1

    @classmethod
    def advance(cls, test_case, arg, state):
        return state + 1

    @classmethod
    def advance_on_success(cls, test_case, arg, state):
        return state

    @classmethod
    def transform(cls, test_case, arg, state):
        success = cls.__transform(test_case, state)
        return (CReduce.RES_OK if success else CReduce.RES_STOP, state)

    @staticmethod
    def __transform(test_case, state):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp_file:
            with open(test_case, "r") as in_file:
                includes = 0
                matched = False

                for line in in_file.readlines():
                    include_match = re.match("\s*#\s*include", line)

                    if include_match is not None:
                        includes += 1

                        if includes == state:
                            matched = True
                            continue

                    tmp_file.writelines(line)

            if matched:
                shutil.move(tmp_file.name, test_case)
            else:
                os.unlink(tmp_file.name)

        return matched

class UnIfDefDeltaPass(DeltaPass):
    pass

class CommentsDeltaPass(DeltaPass):
    @classmethod
    def new(cls, test_case, arg):
        return -2

    @classmethod
    def advance(cls, test_case, arg, state):
        return state + 1

    @classmethod
    def advance_on_success(cls, test_case, arg, state):
        return state

class BlankDeltaPass(DeltaPass):
    pass

class ClangBinSearchDeltaPass(DeltaPass):
    pass

class LinesDeltaPass(DeltaPass):
    @classmethod
    def new(cls, test_case, arg):
        return {"start": 1}

    @classmethod
    def advance(cls, test_case, arg, state):
        new_state = state.copy()
        new_state["index"] = state["index"] - state["chunk"]
        return new_state

    @classmethod
    def advance_on_success(cls, test_case, arg, state):
        return state

    @classmethod
    def transform(cls, test_case, arg, state):
        new_state = state.copy()

        if "start" in state:
            print("Start")
            del new_state["start"]

            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                with open(test_case, "r") as in_file:
                    subprocess.call(["topformflat", arg], stdin=in_file, stdout=tmp_file, universal_newlines=True)

                shutil.move(tmp_file.name, test_case)

            with open(test_case, "r") as in_file:
                data = in_file.readlines()

            new_state["index"] = len(data)
            new_state["chunk"] = len(data)
            return (CReduce.RES_OK, new_state)
        else:
            with open(test_case, "r") as in_file:
                data = in_file.readlines()

            while True:
                new_state["index"] = min(new_state["index"], len(data))

                print("Index: {}, data: {}, chunk: {}".format(new_state["index"], len(data), new_state["chunk"]))

                if new_state["index"] >= 0 and len(data) > 0 and new_state["chunk"] > 0:
                    start = max(0, new_state["index"] - new_state["chunk"])
                    print("Start: {}, Index: {}, Chunk: {}".format(start, new_state["index"], new_state["chunk"]))
                    chunk = new_state["chunk"]
                    old_len = len(data)
                    data = data[0:start] + data[start + chunk:]
                    print("went from {} lines to {} with chunk {}\n".format(old_len, len(data), chunk))

                    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp_file:
                        tmp_file.writelines(data)
                        shutil.move(tmp_file.name, test_case)
                        print("Break")
                        break
                else:
                    if new_state["chunk"] <= 1:
                        print("Stop")
                        return (CReduce.RES_STOP, new_state)

                    new_state["chunk"] = int(new_state["chunk"] / 2)
                    new_state["index"] = len(data)
                    print("New index: {}, new chunk: {}".format(new_state["index"], new_state["chunk"]))

            return (CReduce.RES_OK, new_state)

class SpecialDeltaPass(DeltaPass):
    @classmethod
    def new(cls, test_case, arg):
        return 0

    @classmethod
    def advance(cls, test_case, arg, state):
        return state + 1

    @classmethod
    def advance_on_success(cls, test_case, arg, state):
        return state

    @classmethod
    def transform(cls, test_case, arg, state):
        with open(test_case, "r") as in_file:
            prog = in_file.read()
            prog2 = prog

        if arg == "a":
            for i, match in enumerate(re.finditer("(?<all>transparent_crc\s*\((?<list>.*?)\))", prog2, re.DOTALL))
                if i == state:
                    prog2 = "".join(prog2)
        elif arg == "b":
        elif arg == "c":
        else:
            raise UnknownArgumentCReduceError()

        if prog != prog2:
            with open(test_case, "w") as out_file:
                out_file.write(prog2)

            return (CReduce.RES_OK, state)
        else:
            return (CReduce.RES_STOP, state)

class TernaryDeltaPass(DeltaPass):
    pass

class BalancedDeltaPass(DeltaPass):
    pass

class ClangDeltaPass(DeltaPass):
    pass

class PeepDeltaPass(DeltaPass):
    pass

class IntsDeltaPass(DeltaPass):
    pass

class IndentDeltaPass(DeltaPass):
    pass

class ClexDeltaPass(DeltaPass):
    pass

class CReduce:
    RES_OK = 0
    RES_STOP = 1
    RES_ERROR = 2
    default_passes = [
            {"pass": IncludeIncludesDeltaPass, "arg": "0", "pri": 100},
            {"pass": IncludesDeltaPass, "arg": "0", "first_pass_pri": 0},
            {"pass": UnIfDefDeltaPass, "arg": "0", "pri": 450, "first_pass_pri": 0},
            {"pass": CommentsDeltaPass, "arg": "0", "pri": 451, "first_pass_pri":  0},
            {"pass": BlankDeltaPass, "arg": "0", "first_pass_pri":  1},
            {"pass": ClangBinSearchDeltaPass, "arg": "replace-passtion-def-with-decl", "first_pass_pri":  2},
            {"pass": ClangBinSearchDeltaPass, "arg": "remove-unused-passtion", "first_pass_pri":  3},
            {"pass": LinesDeltaPass, "arg": "0", "pri": 410, "first_pass_pri":  20, "last_pass_pri": 999},
            {"pass": LinesDeltaPass, "arg": "0", "first_pass_pri":  21},
            #{"pass": LinesDeltaPass, "arg": "0", "first_pass_pri":  22},
            {"pass": LinesDeltaPass, "arg": "1", "pri": 411, "first_pass_pri":  23},
            {"pass": LinesDeltaPass, "arg": "1", "first_pass_pri":  24},
            #{"pass": LinesDeltaPass, "arg": "1", "first_pass_pri":  25},
            {"pass": LinesDeltaPass, "arg": "2", "pri": 412, "first_pass_pri":  27},
            {"pass": LinesDeltaPass, "arg": "2", "first_pass_pri":  28},
            #{"pass": LinesDeltaPass, "arg": "2", "first_pass_pri":  29},
            {"pass": LinesDeltaPass, "arg": "10", "pri": 413, "first_pass_pri":  30},
            {"pass": LinesDeltaPass, "arg": "10", "first_pass_pri":  31},
            #{"pass": LinesDeltaPass, "arg": "10", "first_pass_pri":  32},
            {"pass": ClangBinSearchDeltaPass, "arg": "replace-passtion-def-with-decl", "first_pass_pri": 33},
            {"pass": ClangBinSearchDeltaPass, "arg": "remove-unused-passtion", "first_pass_pri": 34},
            {"pass": LinesDeltaPass, "arg": "0", "first_pass_pri":  35},
            {"pass": LinesDeltaPass, "arg": "1", "first_pass_pri":  36},
            {"pass": LinesDeltaPass, "arg": "2", "first_pass_pri":  37},
            {"pass": LinesDeltaPass, "arg": "10", "first_pass_pri":  38},
            {"pass": SpecialDeltaPass, "arg": "a", "first_pass_pri": 110},
            {"pass": SpecialDeltaPass, "arg": "b", "pri": 555, "first_pass_pri": 110},
            {"pass": SpecialDeltaPass, "arg": "c", "pri": 555, "first_pass_pri": 110},
            {"pass": TernaryDeltaPass, "arg": "b", "pri": 104},
            {"pass": TernaryDeltaPass, "arg": "c", "pri": 105},
            {"pass": BalancedDeltaPass, "arg": "curly", "pri": 110, "first_pass_pri":  41},
            {"pass": BalancedDeltaPass, "arg": "curly2", "pri": 111, "first_pass_pri":  42},
            {"pass": BalancedDeltaPass, "arg": "curly3", "pri": 112, "first_pass_pri":  43},
            {"pass": BalancedDeltaPass, "arg": "parens", "pri": 113},
            {"pass": BalancedDeltaPass, "arg": "angles", "pri": 114},
            {"pass": BalancedDeltaPass, "arg": "curly-only", "pri": 150},
            {"pass": BalancedDeltaPass, "arg": "parens-only", "pri": 151},
            {"pass": BalancedDeltaPass, "arg": "angles-only", "pri": 152},
            {"pass": ClangDeltaPass, "arg": "remove-namespace", "pri": 200},
            {"pass": ClangDeltaPass, "arg": "aggregate-to-scalar", "pri": 201},
            #{"pass": ClangDeltaPass, "arg": "binop-simplification", "pri": 201},
            {"pass": ClangDeltaPass, "arg": "local-to-global", "pri": 202},
            {"pass": ClangDeltaPass, "arg": "param-to-global", "pri": 203},
            {"pass": ClangDeltaPass, "arg": "param-to-local", "pri": 204},
            {"pass": ClangDeltaPass, "arg": "remove-nested-passtion", "pri": 205},
            {"pass": ClangDeltaPass, "arg": "rename-fun", "last_pass_pri": 207},
            {"pass": ClangDeltaPass, "arg": "union-to-struct", "pri": 208},
            {"pass": ClangDeltaPass, "arg": "rename-param", "last_pass_pri": 209},
            {"pass": ClangDeltaPass, "arg": "rename-var", "last_pass_pri": 210},
            {"pass": ClangDeltaPass, "arg": "rename-class", "last_pass_pri": 211},
            {"pass": ClangDeltaPass, "arg": "rename-cxx-method", "last_pass_pri": 212},
            {"pass": ClangDeltaPass, "arg": "return-void", "pri": 212},
            {"pass": ClangDeltaPass, "arg": "simple-inliner", "pri": 213},
            {"pass": ClangDeltaPass, "arg": "reduce-pointer-level", "pri": 214},
            {"pass": ClangDeltaPass, "arg": "lift-assignment-expr", "pri": 215},
            {"pass": ClangDeltaPass, "arg": "copy-propagation", "pri": 216},
            {"pass": ClangDeltaPass, "arg": "callexpr-to-value", "pri": 217, "first_pass_pri": 49},
            {"pass": ClangDeltaPass, "arg": "replace-callexpr", "pri": 218, "first_pass_pri": 50},
            {"pass": ClangDeltaPass, "arg": "simplify-callexpr", "pri": 219, "first_pass_pri": 51},
            {"pass": ClangDeltaPass, "arg": "remove-unused-passtion", "pri": 220, "first_pass_pri": 40},
            {"pass": ClangDeltaPass, "arg": "remove-unused-enum-member", "pri": 221, "first_pass_pri": 51},
            {"pass": ClangDeltaPass, "arg": "remove-enum-member-value", "pri": 222, "first_pass_pri": 52},
            {"pass": ClangDeltaPass, "arg": "remove-unused-var", "pri": 223, "first_pass_pri": 53},
            {"pass": ClangDeltaPass, "arg": "simplify-if", "pri": 224},
            {"pass": ClangDeltaPass, "arg": "reduce-array-dim", "pri": 225},
            {"pass": ClangDeltaPass, "arg": "reduce-array-size", "pri": 226},
            {"pass": ClangDeltaPass, "arg": "move-passtion-body", "pri": 227},
            {"pass": ClangDeltaPass, "arg": "simplify-comma-expr", "pri": 228},
            {"pass": ClangDeltaPass, "arg": "simplify-dependent-typedef", "pri": 229},
            {"pass": ClangDeltaPass, "arg": "replace-simple-typedef", "pri": 230},
            {"pass": ClangDeltaPass, "arg": "replace-dependent-typedef", "pri": 231},
            {"pass": ClangDeltaPass, "arg": "replace-one-level-typedef-type", "pri": 232},
            {"pass": ClangDeltaPass, "arg": "remove-unused-field", "pri": 233},
            {"pass": ClangDeltaPass, "arg": "instantiate-template-type-param-to-int", "pri": 234},
            {"pass": ClangDeltaPass, "arg": "instantiate-template-param", "pri": 235},
            {"pass": ClangDeltaPass, "arg": "template-arg-to-int", "pri": 236},
            {"pass": ClangDeltaPass, "arg": "template-non-type-arg-to-int", "pri": 237},
            {"pass": ClangDeltaPass, "arg": "reduce-class-template-param", "pri": 238},
            {"pass": ClangDeltaPass, "arg": "remove-trivial-base-template", "pri": 239},
            {"pass": ClangDeltaPass, "arg": "class-template-to-class", "pri": 240},
            {"pass": ClangDeltaPass, "arg": "remove-base-class", "pri": 241},
            {"pass": ClangDeltaPass, "arg": "replace-derived-class", "pri": 242},
            {"pass": ClangDeltaPass, "arg": "remove-unresolved-base", "pri": 243},
            {"pass": ClangDeltaPass, "arg": "remove-ctor-initializer", "pri": 244},
            {"pass": ClangDeltaPass, "arg": "replace-class-with-base-template-spec", "pri": 245},
            {"pass": ClangDeltaPass, "arg": "simplify-nested-class", "pri": 246},
            {"pass": ClangDeltaPass, "arg": "remove-unused-outer-class", "pri": 247},
            {"pass": ClangDeltaPass, "arg": "empty-struct-to-int", "pri": 248},
            {"pass": ClangDeltaPass, "arg": "remove-pointer", "pri": 249},
            {"pass": ClangDeltaPass, "arg": "remove-pointer-pairs", "pri": 250},
            {"pass": ClangDeltaPass, "arg": "remove-array", "pri": 251},
            {"pass": ClangDeltaPass, "arg": "remove-addr-taken", "pri": 252},
            {"pass": ClangDeltaPass, "arg": "simplify-struct", "pri": 253},
            {"pass": ClangDeltaPass, "arg": "replace-undefined-passtion", "pri": 254},
            {"pass": ClangDeltaPass, "arg": "replace-array-index-var", "pri": 255},
            {"pass": ClangDeltaPass, "arg": "replace-dependent-name", "pri": 256},
            {"pass": ClangDeltaPass, "arg": "simplify-recursive-template-instantiation", "pri": 257},
            {"pass": ClangDeltaPass, "arg": "combine-global-var", "last_pass_pri": 990},
            {"pass": ClangDeltaPass, "arg": "combine-local-var", "last_pass_pri": 991},
            {"pass": ClangDeltaPass, "arg": "simplify-struct-union-decl", "last_pass_pri": 992},
            {"pass": ClangDeltaPass, "arg": "move-global-var", "last_pass_pri": 993},
            {"pass": ClangDeltaPass, "arg": "unify-passtion-decl", "last_pass_pri": 994},
            {"pass": PeepDeltaPass, "arg": "a", "pri": 500},
            {"pass": IntsDeltaPass, "arg": "a", "pri": 600},
            {"pass": IntsDeltaPass, "arg": "b", "pri": 601},
            {"pass": IntsDeltaPass, "arg": "c", "pri": 602},
            {"pass": IntsDeltaPass, "arg": "d", "pri": 603},
            {"pass": IntsDeltaPass, "arg": "e", "pri": 603},
            {"pass": IndentDeltaPass, "arg": "regular", "pri": 1000},
            {"pass": ClexDeltaPass, "arg": "delete-string", "last_pass_pri": 1001},
            {"pass": IndentDeltaPass, "arg": "final", "last_pass_pri": 9999},
            {"pass": ClexDeltaPass, "arg": "rm-toks-1", "pri": 9031},
            {"pass": ClexDeltaPass, "arg": "rm-toks-2", "pri": 9030},
            {"pass": ClexDeltaPass, "arg": "rm-toks-3", "pri": 9029},
            {"pass": ClexDeltaPass, "arg": "rm-toks-4", "pri": 9028},
            {"pass": ClexDeltaPass, "arg": "rm-toks-5", "pri": 9027},
            {"pass": ClexDeltaPass, "arg": "rm-toks-6", "pri": 9026},
            {"pass": ClexDeltaPass, "arg": "rm-toks-7", "pri": 9025},
            {"pass": ClexDeltaPass, "arg": "rm-toks-8", "pri": 9024},
            {"pass": ClexDeltaPass, "arg": "rm-toks-9", "pri": 9023},
            {"pass": ClexDeltaPass, "arg": "rm-toks-10", "pri": 9022},
            {"pass": ClexDeltaPass, "arg": "rm-toks-11", "pri": 9021},
            {"pass": ClexDeltaPass, "arg": "rm-toks-12", "pri": 9020},
            {"pass": ClexDeltaPass, "arg": "rm-toks-13", "pri": 9019},
            {"pass": ClexDeltaPass, "arg": "rm-toks-14", "pri": 9018},
            {"pass": ClexDeltaPass, "arg": "rm-toks-15", "pri": 9017},
            {"pass": ClexDeltaPass, "arg": "rm-toks-16", "pri": 9016},
    ]

    def __init__(self, interestingness_test, test_cases):
        self.itest = interestingness_test
        self.test_cases = []
        self.total_file_size = 0

        for test_case in test_cases:
            self._check_file_permissions(test_case, [os.F_OK, os.R_OK, os.W_OK], CReduceInvalidTestCaseError)
            self.test_cases.append(os.path.abspath(test_case))
            self.total_file_size += os.path.getsize(test_case)

    def reduce(self, parallel_tests, skip_initial, tidy):
        self.parallel_tests = parallel_tests
        self.orig_dir = os.getcwd()
        self.variants = []

        if not self._check_sanity():
            return False

        print("===< {} >===".format(os.getpid()))

        if not tidy:
            self._backup_files(self.test_cases)

        if not skip_initial:
            print("INITIAL PASSES")
            self._run_additional_passes("first_pass_pri")

        print("MAIN PASSES")
        self._run_main_passes()

        print("CLEANUP PASS")
        self._run_additional_passes("last_pass_pri")

        print("===================== done ====================")

        #TODO: Output statistics and reduced test cases
        return True

    @staticmethod
    def _check_file_permissions(path, modes, error):
        for m in modes:
            if not os.access(path, m):
                if error is not None:
                    raise error(path, m)
                else:
                    return False

        return True

    def _check_prerequisites(self):
        pass

    def _check_sanity(self):
        print("sanity check... ", end='')

        with tempfile.TemporaryDirectory() as tmp_dir:
            print("tmpdir = {}".format(tmp_dir))

            os.chdir(tmp_dir)
            self._copy_test_cases(tmp_dir)

            #TODO: Output error create extra dir
            result = self.itest.check()

            if result:
                print("successful")

            os.chdir(self.orig_dir)

        return result

    @staticmethod
    def _backup_files(files):
        for f in files:
            orig_file = "{}.orig".format(os.path.splitext(f)[0])

            if not os.path.exists(orig_file):
                # Copy file and preserve attributes
                shutil.copy2(f, orig_file)

    def _copy_test_cases(self, tmp_dir):
        for f in self.test_cases:
            shutil.copy(f, tmp_dir)

    def _run_additional_passes(self, priority):
        passes = CReduce.get_passes(CReduce.default_passes, priority)

        for p in passes:
            self._run_delta_pass(p["pass"], p["arg"])

    def _run_main_passes(self):
        passes = CReduce.get_passes(CReduce.default_passes, "pri")

        while True:
            for p in passes:
                self._run_delta_pass(p["pass"], p["arg"])

            total_file_size = self.get_total_file_size()

            print("Termination check: size was {}; now {}".format(self.total_file_size, total_file_size))

            if total_file_size >= self.total_file_size:
                break
            else:
                self.total_file_size = total_file_size

    def _fork_variant(self, variant_path):
        process = multiprocessing.Process(target=self.itest.run)
        process.start()
        os.setpgid(process.pid, process.pid)
        return process

    def _wait_for_results(self):
        descriptors = list(map(lambda x: x["proc"].sentinel, self.variants))
        return multiprocessing.connection.wait(descriptors)

    def _kill_variants(self):
        for v in self.variants:
            #FIXME: Does not not work on Windows
            proc = v["proc"]

            if proc.is_alive():
                os.killpg(v["proc"].pid, 15)

        self.variants = []
        self.num_running = 0

    def _run_delta_pass(self, pass_, arg):
        #TODO: Check for zero size

        print("===< {} :: {} >===".format(pass_.__name__, arg))

        for test_case in self.test_cases:
            test_case_name = os.path.basename(test_case)
            state = pass_.new(test_case_name, arg)
            again = True
            stopped = False
            self.num_running = 0

            while again:
                while not stopped and self.num_running < self.parallel_tests:
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        os.chdir(tmp_dir)
                        self._copy_test_cases(tmp_dir)

                        variant_path = os.path.join(tmp_dir, test_case_name)

                        (result, state) = pass_.transform(variant_path, arg, state)

                        if result != self.RES_OK and result != self.RES_STOP:
                            #TODO: Report bug
                            pass
                        elif result == self.RES_STOP or result == self.RES_ERROR:
                            stopped = True
                        else:
                            #TODO: Report failure
                            proc = self._fork_variant(variant_path)
                            variant = {"proc" : proc, "state": state, "tmp_dir": tmp_dir, "variant_path": variant_path}
                            self.variants.append(variant)
                            self.num_running += 1
                            state = pass_.advance(variant_path, arg, state)

                        os.chdir(self.orig_dir)

                        if self.num_running > 0:
                            finished = self._wait_for_results()
                            self.num_running -= len(finished)

                        while len(self.variants) > 0:
                            variant = self.variants[0]

                            if variant["proc"].is_alive():
                                break

                            self.variants.pop(0)

                            if variant["proc"].exitcode == 0:
                                self._kill_variants()
                                state = pass_.advance_on_success(variant["variant_path"], arg, variant["state"])
                                shutil.copy(variant["variant_path"], test_case)
                                stopped = False

                if stopped or len(self.variants) == 0:
                    break

    def get_total_file_size(self):
        size = 0

        for test_case in self.test_cases:
            size += os.path.getsize(test_case)

        return size

    @staticmethod
    def get_passes(passes, priority):
        passes = filter(lambda p: priority in p, passes)
        return sorted(passes, key=lambda p: p[priority], reverse=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C-Reduce")
    parser.add_argument("--n", type=int, default=1, help="Number of cores to use; C-Reduce tries to automatically pick a good setting but its choice may be too low or high for your situation")
    parser.add_argument("--tidy", action="store_true", default=False, help="Do not make a backup copy of each file to reduce as file.orig")
    parser.add_argument("--skip-initial-passes", action="store_true", default=False, help="Skip initial passes (useful if input is already partially reduced)")
    parser.add_argument("itest", metavar="INTERESTINGNESS_TEST", help="Executable to check interestingness of test cases")
    parser.add_argument("test_cases", metavar="TEST_CASE", nargs="+", help="Test cases")

    args = parser.parse_args()

    itest = Test0InterestingnessTest(map(os.path.basename, args.test_cases))

    reducer = CReduce(itest, args.test_cases)
    reducer.reduce(args.n, args.skip_initial_passes, args.tidy)
