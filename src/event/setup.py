from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="hermes-event",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Hermes event dispatching",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src", include=["event", "event.*"]),
    install_requires=["hermes-agent>=0.1.0", "hermes-data-engine>=0.1.0"],
)
