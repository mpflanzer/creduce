import logging
import os
import re
import shutil
import subprocess
import tempfile

from .delta import DeltaPass

class ClangBinarySearchDeltaPass(DeltaPass):
    @classmethod
    def check_prerequisites(cls):
        return shutil.which("clang_delta") is not None

    @classmethod
    def new(cls, test_case, arg):
        return {"start": 1}

    @classmethod
    def advance(cls, test_case, arg, state):
        if "start" in state:
            return state
        else:
            new_state = state.copy()
            new_state["index"] = state["index"] + state["chunk"]

            logging.debug("ADVANCE: index = {}, chunk = {}".format(new_state["index"], new_state["chunk"]))

            return new_state

    @classmethod
    def advance_on_success(cls, test_case, arg, state):
        return state

    @staticmethod
    def __count_instances(test_case, arg):
        try:
            proc = subprocess.run(["clang_delta", "--query-instances={}".format(arg), test_case], universal_newlines=True, stdout=subprocess.PIPE)
        except subprocess.SubprocessError:
            return 0

        m = re.match("Available transformation instances: ([0-9]+)$", proc.stdout)

        if m is None:
            return 0
        else:
            return int(m.group(1))

    @staticmethod
    def __rechunk(state):
        if state["chunk"] < 10:
            return False

        state["chunk"] = round(float(state["chunk"]) / 2.0)
        state["index"] = 1

        logging.debug("granularity = {}".format(state["chunk"]))

        return True

    @classmethod
    def transform(cls, test_case, arg, state):
        new_state = state.copy()

        if "start" in new_state:
            del new_state["start"]

            instances = cls.__count_instances(test_case, arg)

            new_state["chunk"] = instances
            new_state["instances"] = instances
            new_state["index"] = 1

            logging.debug("intial granularity = {}".format(instances))

        while True:
            logging.debug("TRANSFORM: index = {}, chunk = {}, instances = {}".format(new_state["index"], new_state["chunk"], new_state["instances"]))

            if new_state["index"] <= new_state["instances"]:
                end = min(new_state["instances"], new_state["index"] + new_state["chunk"])
                dec = end - new_state["index"] + 1

                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    logging.debug(" ".join(["clang_delta", "--transformation={}".format(arg), "--counter={}".format(new_state["index"]), "--to-counter={}".format(end), test_case]))

                    try:
                        proc = subprocess.run(["clang_delta", "--transformation={}".format(arg), "--counter={}".format(new_state["index"]), "--to-counter={}".format(end), test_case], universal_newlines=True, stdout=tmp_file)
                    except subprocess.SubprocessError:
                        return (DeltaPass.Result.error, new_state)

                if proc.returncode == 0:
                    shutil.move(tmp_file.name, test_case)
                    return (DeltaPass.Result.ok, new_state)
                else:
                    if proc.returncode == 255:
                        #TODO: Do something?
                        pass
                    elif proc.returncode == 1:
                        os.unlink(tmp_file.name)

                        logging.debug("out of instances!")

                        if not cls.__rechunk(new_state):
                            return (DeltaPass.Result.stop, new_state)

                        continue
                    else:
                        os.unlink(tmp_file.name)
                        return (DeltaPass.Result.error, new_state)

                #TODO: Why does this return OK?
                shutil.move(tmp_file.name, test_case)
                return (DeltaPass.Result.ok, new_state)
            else:
                if not cls.__rechunk(new_state):
                    return (DeltaPass.Result.stop, new_state)

        return (DeltaPass.Result.ok, new_state)
