#!/usr/bin/env python2
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

from __future__ import print_function
import lintutils
from subprocess import PIPE
import argparse
import difflib
import multiprocessing as mp
import sys
from functools import partial


# examine the output of clang-format and if changes are
# present assemble a (unified)patch of the difference
def _check_one_file(completed_processes, filename):
    with open(filename, "rb") as reader:
        original = reader.read()

    returncode, stdout, stderr = completed_processes[filename]
    formatted = stdout
    if formatted != original:
        # Run the equivalent of diff -u
        diff = list(
            difflib.unified_diff(
                original.decode('utf8').splitlines(True),
                formatted.decode('utf8').splitlines(True),
                fromfile=filename,
                tofile=f"{filename} (after clang format)",
            )
        )

    else:
        diff = None

    return filename, diff


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Runs clang-format on all of the source "
        "files. If --fix is specified enforce format by "
        "modifying in place, otherwise compare the output "
        "with the existing file and output any necessary "
        "changes as a patch in unified diff format")
    parser.add_argument("--clang_format_binary",
                        required=True,
                        help="Path to the clang-format binary")
    parser.add_argument("--exclude_globs",
                        help="Filename containing globs for files "
                        "that should be excluded from the checks")
    parser.add_argument("--source_dir",
                        required=True,
                        help="Root directory of the source code")
    parser.add_argument("--fix", default=False,
                        action="store_true",
                        help="If specified, will re-format the source "
                        "code instead of comparing the re-formatted "
                        "output, defaults to %(default)s")
    parser.add_argument("--quiet", default=False,
                        action="store_true",
                        help="If specified, only print errors")
    arguments = parser.parse_args()

    exclude_globs = []
    if arguments.exclude_globs:
        exclude_globs.extend(line.strip() for line in open(arguments.exclude_globs))
    formatted_filenames = [
        str(path)
        for path in lintutils.get_sources(arguments.source_dir, exclude_globs)
    ]

    if arguments.fix:
        if not arguments.quiet:
            print("\n".join(map(lambda x: f"Formatting {x}", formatted_filenames)))

        # Break clang-format invocations into chunks: each invocation formats
        # 16 files. Wait for all processes to complete
        results = lintutils.run_parallel([
            [arguments.clang_format_binary, "-i"] + some
            for some in lintutils.chunk(formatted_filenames, 16)
        ])
        for returncode, stdout, stderr in results:
            # if any clang-format reported a parse error, bubble it
            if returncode != 0:
                sys.exit(returncode)

    else:
        # run an instance of clang-format for each source file in parallel,
        # then wait for all processes to complete
        results = lintutils.run_parallel([
            [arguments.clang_format_binary, filename]
            for filename in formatted_filenames
        ], stdout=PIPE, stderr=PIPE)
        for returncode, stdout, stderr in results:
            # if any clang-format reported a parse error, bubble it
            if returncode != 0:
                sys.exit(returncode)

        error = False
        checker = partial(_check_one_file, dict(zip(formatted_filenames, results)))
        pool = mp.Pool()
        try:
            # check the output from each invocation of clang-format in parallel
            for filename, diff in pool.imap(checker, formatted_filenames):
                if not arguments.quiet:
                    print(f"Checking {filename}")
                if diff:
                    print(f"{filename} had clang-format style issues")
                    # Print out the diff to stderr
                    error = True
                    # pad with a newline
                    print(file=sys.stderr)
                    diff_out = [
                        diff_str.encode('raw_unicode_escape').decode('ascii')
                        for diff_str in diff
                    ]

                    sys.stderr.writelines(diff_out)
        except Exception:
            error = True
            raise
        finally:
            pool.terminate()
            pool.join()
        sys.exit(1 if error else 0)

