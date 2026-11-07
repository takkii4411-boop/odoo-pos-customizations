from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import datetime
import pytz
from pytz import timezone, UTC


class PosProductAddRemoveReportWizard(models.TransientModel):
    _name = "pos.product.add.remove.report.wizard"
    _description = "Product Add Remove Report Wizard"

    def _default_date_from(self):
        tz = self.env.user.tz or 'UTC'
        user_tz = timezone(tz)
        now_utc = datetime.datetime.now(UTC)
        now_user = now_utc.astimezone(user_tz)
        start_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)
        start_utc = start_user.astimezone(UTC)
        return start_utc.replace(tzinfo=None)

    def _default_date_to(self):
        tz = self.env.user.tz or 'UTC'
        user_tz = timezone(tz)
        now_utc = datetime.datetime.now(UTC)
        now_user = now_utc.astimezone(user_tz)
        end_user = now_user.replace(hour=23, minute=59, second=59, microsecond=999999)
        end_utc = end_user.astimezone(UTC)
        return end_utc.replace(tzinfo=None)

    date_from = fields.Datetime(string="Start Date", required=True, default=_default_date_from)
    date_to = fields.Datetime(string="End Date", required=True, default=_default_date_to)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for record in self:
            if record.date_to < record.date_from:
                raise ValidationError(_("End Date cannot be earlier than Start Date."))
            delta = record.date_to - record.date_from
            if delta.days > 365:
                raise ValidationError(_("Date range cannot exceed 365 days."))

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_to and self.date_to < self.date_from:
            self.date_to = self.date_from

    def action_generate(self):
        return self.env["auditlog.log"].action_export_product_add_remove_report(
            self.date_from, self.date_to
        )
