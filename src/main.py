# Hermes 量化交易系统主入口

import sys
import os
import time
import argparse
import logging
from qts.logging_config import setup_logging


def daemonize():
    """UNIX double-fork to daemonize the process."""
    if os.name != 'posix':
        print("Daemon mode is only supported on UNIX-like systems.")
        return
    try:
        pid = os.fork()
        if pid > 0:
            # Exit parent
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"fork #1 failed: {e.errno} ({e.strerror})\n")
        sys.exit(1)
    os.setsid()
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"fork #2 failed: {e.errno} ({e.strerror})\n")
        sys.exit(1)
    sys.stdout.flush()
    sys.stderr.flush()
    with open('/dev/null', 'r') as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open('/dev/null', 'a+') as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())


def main():
    parser = argparse.ArgumentParser(description="Hermes Quant Trading System")
    parser.add_argument('--mode', choices=['daemon', 'foreground'], default='foreground', help='Run mode: daemon (UNIX only) or foreground')
    args = parser.parse_args()
    # configure logging before importing modules that may create loggers
    setup_logging(level=logging.INFO, logfile=None, json_format=False)

    if args.mode == 'daemon':
        daemonize()
    print("Hermes Quant Trading System started.")

    # import modules after logging is configured so module-level loggers inherit configuration
    from qts.event_engine.event_engine import EventEngine
    from qts.event_engine.scheduler import Scheduler

    event_engine = EventEngine()
    event_engine.start()
    config_path = os.path.join(os.path.dirname(__file__), 'config/scheduler.json')
    if not os.path.exists(config_path):
        print(f"[WARN] 配置文件 {config_path} 不存在，调度器未启动。")
        scheduler = None
    else:
        scheduler = Scheduler(config_path)
        scheduler.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        if scheduler:
            scheduler.shutdown()
        print("System stopped.")


if __name__ == "__main__":
    main()
