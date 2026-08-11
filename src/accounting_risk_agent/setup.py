from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="hermes-accounting-risk-agent",
    version=(Path(__file__).parent / "VERSION").read_text(encoding="utf-8").strip(),
    description="Local accounting-standard quantitative risk analysis",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages("src", include=["accounting_risk_agent", "accounting_risk_agent.*"]),
    install_requires=["pandas>=2.0.0", "requests>=2.28.0", "openpyxl>=3.1.0"],
)
