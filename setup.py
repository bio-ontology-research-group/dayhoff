from setuptools import setup, find_packages

setup(
    name="dayhoff",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "gitpython>=3.1.0",
        "paramiko>=2.7.0", # Moved from extras_require
        # TODO: Add other core dependencies
    ],
    extras_require={
        # "hpc": [], # paramiko is now a core dependency
        "ai": ["transformers", "langchain"],
        "workflows": ["cwlgen", "pynextflow"],
        "dev": [ # Added a dev group for convenience
            "transformers",
            "langchain",
            "cwlgen",
            "pynextflow",
            # Add linters, formatters, testing tools here if needed
            # "pytest",
            # "flake8",
            # "black",
        ]
    },
    entry_points={
        "console_scripts": [
            "dayhoff=dayhoff.cli.main:run_repl", # Point directly to the REPL function
        ],
    },
)

