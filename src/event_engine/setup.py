from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="hermes-event-engine",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Hermes event engine and task scheduler",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src", include=["event_engine", "event_engine.*"]),
    install_requires=["APScheduler>=3.10.0"],
)
