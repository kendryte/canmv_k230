#!/usr/bin/env python
from __future__ import print_function

import subprocess
import sys
import os

def get_git_info(repo_path):
    # Python 2.6 doesn't have check_output, so check for that
    try:
        subprocess.check_output
        subprocess.check_call
    except AttributeError:
        return None

    # Note: git describe doesn't work if no tag is available
    try:
        git_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--dirty", "--always", "--match", "v[1-9].*"],
            cwd=repo_path,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        ).strip()
    except subprocess.CalledProcessError as er:
        if er.returncode == 128:
            # git exit code of 128 means no repository found
            return None
        git_tag = ""
    except OSError:
        return None

    try:
        git_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_path,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        ).strip()
    except subprocess.CalledProcessError:
        git_hash = "unknown"
    except OSError:
        return None

    try:
        # Check if there are any modified files.
        subprocess.check_call(
            ["git", "diff", "--no-ext-diff", "--quiet", "--exit-code"],
            cwd=repo_path,
            stderr=subprocess.STDOUT,
        )
        # Check if there are any staged files.
        subprocess.check_call(
            ["git", "diff-index", "--cached", "--quiet", "HEAD", "--"],
            cwd=repo_path,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        git_hash += "-dirty"
    except OSError:
        return None

    return git_tag, git_hash


def main():
    repo_path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else "."
    tag, commit = get_git_info(repo_path)
    print("MICROPY_GIT_TAG=" + tag)
    print("MICROPY_GIT_HASH=" + commit)

if __name__ == "__main__":
    main()
