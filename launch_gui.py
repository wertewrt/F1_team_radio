"""Launch the desktop studio or run its headless packaged smoke test."""


def main(argv=None):
    import argparse
    from teamradio import runtime

    parser = argparse.ArgumentParser(description="F1 Team Radio Studio")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true", help="run a headless export smoke test")
    mode.add_argument("--gui-smoke-test", action="store_true", help="exercise Tk windows, then close")
    parser.add_argument("--report", help="write the smoke-test JSON report to this path")
    args = parser.parse_args(argv)
    if args.report and not (args.self_test or args.gui_smoke_test):
        parser.error("--report requires --self-test or --gui-smoke-test")
    runtime.install_exception_hooks()
    if args.self_test:
        return runtime.run_self_test(args.report)
    if args.gui_smoke_test:
        return runtime.run_gui_smoke_test(args.report)
    try:
        from teamradio.gui import main as launch
        launch()
        return 0
    except Exception as exc:
        runtime.report_exception(type(exc), exc, exc.__traceback__, title="无法启动 Team Radio Studio")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
