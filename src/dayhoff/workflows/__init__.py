"""Workflow generation and container integration.

This package provides functionality for:
- Abstract workflow representation
- CWL workflow generation
- Nextflow workflow generation
- Singularity container specification
- Environment tracking and reproducibility
"""
from .base import Workflow
from .cwl import CWLGenerator
from .nextflow import NextflowGenerator
from .containers import ContainerManager
from .environment import EnvironmentTracker

__all__ = [
    'Workflow', 'CWLGenerator', 'NextflowGenerator',
    'ContainerManager', 'EnvironmentTracker'
]
