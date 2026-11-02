# -*- coding: utf-8 -*-
"""Código EDT y hito de 0 días en el núcleo genérico."""
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestWbsAndMilestones(TransactionCase):

    def test_wbs_code_follows_sequence_and_parent_not_dates(self):
        T = self.env["project.task"]
        p = self.env["project.project"].create({"name": "EDT genérico"})
        a = T.create({"name": "A", "project_id": p.id, "sequence": 10})
        b = T.create({"name": "B", "project_id": p.id, "sequence": 20})
        b1 = T.create({"name": "B1", "project_id": p.id, "parent_id": b.id})
        self.assertEqual((a.wbs_code, b.wbs_code, b1.wbs_code), ("1", "2", "2.1"))
        b.sequence = 5
        self.assertEqual((b.wbs_code, a.wbs_code, b1.wbs_code), ("1", "2", "1.1"))

    def test_a_milestone_lasts_zero_days(self):
        T = self.env["project.task"]
        p = self.env["project.project"].create({"name": "Hitos genéricos"})
        hito = T.create({"name": "Hito", "project_id": p.id, "is_milestone": True,
                         "planned_date_begin": "2026-11-02 14:00:00", "date_deadline": "2026-11-06 23:00:00"})
        self.assertEqual(hito.date_deadline, hito.planned_date_begin)
        hito.date_deadline = "2026-11-10 14:00:00"
        self.assertEqual(hito.planned_date_begin, hito.date_deadline)
