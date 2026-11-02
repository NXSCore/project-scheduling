# -*- coding: utf-8 -*-
"""Validación de la arquitectura de la vista `planner`."""
import logging
import os

from lxml import etree

from odoo.tools import misc, view_validation

_logger = logging.getLogger(__name__)
_validator = None


@view_validation.validate("planner")
def schema_planner(arch, **kwargs):
    global _validator
    if _validator is None:
        with misc.file_open(os.path.join("project_planner", "views", "planner.rng")) as f:
            _validator = etree.RelaxNG(etree.parse(f))
    if _validator.validate(arch):
        return True
    for error in _validator.error_log:
        _logger.error("%s", error)
    return False
