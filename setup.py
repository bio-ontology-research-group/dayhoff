from setuptools import setup, find_packages

setup(
    name="dayhoff",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        # TODO: Add core dependencies
    ],
    extras_require={
        "hpc": ["paramiko"],
        "ai": ["transformers", "langchain"],
        "workflows": ["cwlgen", "pynextflow"],
    },
    entry_points={
        "console_scripts": [
            "dayhoff=dayhoff.cli:main",
        ],
    },
)
