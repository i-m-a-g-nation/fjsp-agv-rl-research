"""Linux fail-closed lifetime monitor; holds no credentials or writable pipe end."""

import os
import signal
import sys


def main():
    group, read_fd = int(sys.argv[1]), int(sys.argv[2])
    os.write(1, b"READY\n")
    try:
        while os.read(read_fd, 1):
            pass
    finally:
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.close(read_fd)


if __name__ == "__main__":
    main()
