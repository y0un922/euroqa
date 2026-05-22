"""TUI database manager entry point. Run: python -m tools.tui"""

from tools.tui.app import EuroQATUI


def main() -> None:
    app = EuroQATUI()
    app.run()


if __name__ == "__main__":
    main()
