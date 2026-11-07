from odoo import api, fields, models, _
from io import StringIO
from odoo.tools import html2plaintext
from odoo.exceptions import ValidationError
import base64
import datetime
import logging
import pytz
import re
from pytz import timezone, UTC

_logger = logging.getLogger(__name__)


class PosAuditTrailWizard(models.TransientModel):
    _name = "pos.audit.trail.wizard"
    _description = "POS Audit Trail Wizard"

    pos_config_id = fields.Many2one('pos.config', string='POS Configuration', required=True)

    session_ids = fields.Many2many(
        'pos.session',
        string='POS Sessions',
        required=True,
    )

    def _default_date_from(self):
        """
        Start of current day in user's timezone → converted to naive UTC.
        """
        tz = self.env.user.tz or 'UTC'
        user_tz = timezone(tz)

        now_utc = datetime.datetime.now(UTC)
        now_user = now_utc.astimezone(user_tz)

        start_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)

        # Convert back to UTC and strip tz info
        start_utc = start_user.astimezone(UTC)
        return start_utc.replace(tzinfo=None)

    def _default_date_to(self):
        """
        End of current day in user's timezone → converted to naive UTC.
        """
        tz = self.env.user.tz or 'UTC'
        user_tz = timezone(tz)

        now_utc = datetime.datetime.now(UTC)
        now_user = now_utc.astimezone(user_tz)

        end_user = now_user.replace(hour=23, minute=59, second=59, microsecond=999999)

        end_utc = end_user.astimezone(UTC)
        return end_utc.replace(tzinfo=None)

    date_from = fields.Datetime(
        string="Start Date",
        required=True,
        default=_default_date_from
    )
    date_to = fields.Datetime(
        string="End Date",
        required=True,
        default=_default_date_to
    )
    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        """Ensure date_to is not earlier than date_from"""
        for record in self:
            if record.date_from and record.date_to:
                if record.date_to < record.date_from:
                    raise ValidationError(
                        _("End Date cannot be earlier than Start Date.")
                    )

    @api.constrains('date_from', 'date_to')
    def _check_date_future(self):
        """Prevent selecting future dates (date only, not time)"""
        for record in self:
            employee_timezone = pytz.timezone(self.env.user.tz or 'UTC')
            now_datetime = fields.Datetime.now().astimezone(employee_timezone)
            if record.date_from and record.date_from.date() > now_datetime.date():
                raise ValidationError(
                    _("Start Date cannot be in the future.")
                )

            if record.date_to and record.date_to.date() > now_datetime.date():
                raise ValidationError(
                    _("End Date cannot be in the future.")
                )

    @api.constrains('date_from', 'date_to')
    def _check_date_range_limit(self):
        for record in self:
            if record.date_from and record.date_to:
                delta = record.date_to - record.date_from
                if delta.days > 365:
                    raise ValidationError(
                        _("Date range cannot exceed 365 days.")
                    )

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            self.date_to = self.date_from

    @api.onchange('pos_config_id', 'date_from', 'date_to')
    def _onchange_session_filter(self):
        if self.pos_config_id and self.date_from and self.date_to:
            sessions = self.env['pos.session'].search([
                ('config_id', '=', self.pos_config_id.id),
                ('start_at', '<=', self.date_to),
                '|',
                ('stop_at', '=', False),
                ('stop_at', '>=', self.date_from),
            ])
            self.session_ids = [(6, 0, sessions.ids)]

    def action_generate_txt(self):
        buffer = StringIO()
        buffer.write("POS SHOP|DATE TIME|EMPLOYEE NAME|TRANSACTION#|SI#|AMOUNT|ACTIVITY\n")

        orders = self.env['pos.order'].search(
            [('session_id', 'in', self.session_ids.ids)],
            order='date_order asc'
        )

        tz = self.env.user.tz or 'UTC'
        user_tz = pytz.timezone(tz)

        rows = []

        for order in orders:
            shop_name = order.config_id.name or 'N/A'
            employee = order.employee_id
            employee_name = employee.name.upper() if employee and employee.name else 'UNKNOWN'
            transaction_no = order.transaction_number or order.pos_reference or ''

            # ===== SALE row (original transaction) =====
            order_dt_utc = order.date_order.replace(tzinfo=pytz.UTC)
            order_dt_local = order_dt_utc.astimezone(user_tz)
            order_date_time = order_dt_local.strftime('%m/%d/%Y %H:%M:%S')

            sale_si = order.invoice_number or order.pos_reference or ''
            sale_amount = "%.2f" % order.amount_total

            rows.append((
                order_dt_local,
                f"{shop_name}|{order_date_time}|{employee_name}|{transaction_no}|{sale_si}|{sale_amount}|SALE\n"
            ))

            # ===== REPRINT / VOID / RETURN / REFUND from mail messages =====
            messages = self.env['mail.message'].search([
                ('model', '=', 'pos.order'),
                ('res_id', '=', order.id)
            ], order='date asc')

            for msg in messages:
                body_text = html2plaintext(msg.body or "").strip()
                body_upper = body_text.upper()

                msg_date_time = ""
                msg_dt_local = None
                if msg.date:
                    msg_dt_utc = msg.date.replace(tzinfo=pytz.UTC)
                    msg_dt_local = msg_dt_utc.astimezone(user_tz)
                    msg_date_time = msg_dt_local.strftime('%m/%d/%Y %H:%M:%S')

                activity = False
                si_no = ""

                # ===== ACTIVITY DETECTION =====
                if "RECEIPT REPRINTED" in body_upper:
                    activity = "REPRINT"
                elif "VOID" in body_upper:
                    activity = "VOID"
                elif "REFUND BY" in body_upper:
                    activity = "REFUND"
                elif "RETURN BY" in body_upper:
                    activity = "RETURN"

                # ===== INVOICE NUMBER EXTRACTION =====
                if "INVOICE NO:" in body_upper:
                    si_no = body_text.split("Invoice No:")[1].split("\n")[0].strip()
                elif "INVOICE NUMBER:" in body_upper:
                    si_no = body_text.split("Invoice Number:")[1].split("\n")[0].strip()
                elif "VOID INVOICE NUMBER" in body_upper:
                    si_no = body_text.split("Void Invoice Number:")[1].split("\n")[0].strip()
                elif "RETURN/REFUND INVOICE NO:" in body_upper:
                    si_no = body_text.split("Return/Refund Invoice No:")[1].split("\n")[0].strip()

                if si_no:
                    if "Reason:" in si_no:
                        si_no = si_no.split("Reason:")[0].strip()
                    si_no = si_no.strip('/')
                    if "-" in si_no and si_no.count("-") >= 2:
                        si_no = "-".join(si_no.split("-")[:2])
                    if " - " in si_no:
                        si_no = si_no.split(" - ")[0].strip()

                if not si_no:
                    si_no = order.invoice_number or order.pos_reference or ''

                amount_value = order.amount_total

                if activity in ["RETURN", "VOID", "REFUND"]:
                    specific_return = self.env['pos.order'].search([
                        ('old_pos_reference', '=', order.pos_reference),'|',
                        ('invoice_number', '=', si_no),
                        ('pos_reference', '=', si_no)
                    ], limit=1)

                    if specific_return:
                        amount_value = specific_return.amount_total
                    else:
                        amount_value = -abs(order.amount_total)
                amount = "%.2f" % amount_value

                if activity and si_no and msg_dt_local:
                    rows.append((
                        msg_dt_local,
                        f"{shop_name}|{msg_date_time}|{employee_name}|{transaction_no}|{si_no}|{amount}|{activity}\n"
                    ))

        # ===== Sort all rows chronologically =====
        rows.sort(key=lambda x: x[0])

        txt_data = buffer.getvalue()
        for _, line in rows:
            txt_data += line

        buffer.close()

        shop_name_raw = self.pos_config_id.name or 'POS'
        safe_shop_name = re.sub(r'[\\/*?:"<>|]', '', shop_name_raw).strip()

        local_date_from = self.date_from.replace(tzinfo=pytz.UTC).astimezone(user_tz)
        local_date_to = self.date_to.replace(tzinfo=pytz.UTC).astimezone(user_tz)
        date_from_str = local_date_from.strftime('%m-%d-%Y')
        date_to_str = local_date_to.strftime('%m-%d-%Y')

        attachment = self.env['ir.attachment'].create({
            'name': f'{safe_shop_name}.Audit Trail.{date_from_str} to {date_to_str}.txt',
            'type': 'binary',
            'datas': base64.b64encode(txt_data.encode()),
            'mimetype': 'text/plain',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }