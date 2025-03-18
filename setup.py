from setuptools import setup, find_packages

setup(
    name="dayhoff",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "gitpython>=3.1.0",
        # TODO: Add other core dependencies
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
